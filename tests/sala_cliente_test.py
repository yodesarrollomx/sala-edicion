#!/usr/bin/env python3
"""Lecturas lentas, respuestas incompletas y escrituras sin recibo confirmado."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "nube"))
import sala_cliente as cliente
import sala_relevo as relevo


class ClienteRelevoTest(unittest.TestCase):
    def setUp(self):
        self.entorno = mock.patch.dict(os.environ, {
            "SALA_GAS_EXEC": "https://example.test/exec",
            "SALA_CLAVE_AGENTE": "clave-falsa-de-prueba",
        })
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

    def test_dia_fresco_conserva_fecha_y_frescura_con_presupuesto_para_redireccion(self):
        with mock.patch.object(cliente, "_curl", return_value='{"propuestas":[],"decisiones":{}}') as curl:
            with mock.patch.object(cliente, "_urllib", side_effect=AssertionError("No usar urllib")):
                dia = cliente.get("dia", f="2026-10-08", fresco="1")
        self.assertEqual(dia["decisiones"], {})
        self.assertEqual(curl.call_count, 1)
        url, cuerpo, espera = curl.call_args.args
        self.assertIn("recurso=dia", url)
        self.assertIn("fresco=1", url)
        self.assertIn("f=2026-10-08", url)
        self.assertIsNone(cuerpo)
        self.assertEqual(espera, 120)

    def test_dia_fresco_reintenta_una_vez_y_recupera(self):
        with mock.patch.object(cliente, "_curl", side_effect=[
            cliente.SalaError("curl falló (28)"),
            '{"fecha":"2026-10-07","propuestas":[],"decisiones":{}}',
        ]) as curl, mock.patch.object(cliente.time, "sleep") as dormir:
            dia = cliente.get("dia", fresco="1")
        self.assertEqual(dia["fecha"], "2026-10-07")
        self.assertEqual(curl.call_count, 2)
        dormir.assert_called_once_with(2)

    def test_dia_fresco_con_dos_timeouts_sigue_fallando(self):
        with mock.patch.object(cliente, "_curl",
                               side_effect=cliente.SalaError("curl falló (28)")) as curl:
            with mock.patch.object(cliente.time, "sleep"):
                with self.assertRaisesRegex(cliente.SalaError, "2 intentos"):
                    cliente.get("dia", fresco="1")
        self.assertEqual(curl.call_count, 2)

    def test_cola_y_reglas_recuperan_lectura_sin_repetir_por_dos_transportes(self):
        for recurso, respuesta in [("cola", {"cola": []}),
                                    ("reglas", {"reglas": {}, "motores": []})]:
            with self.subTest(recurso=recurso):
                with mock.patch.object(cliente, "_curl", side_effect=[
                    cliente.SalaError("curl falló (28)"), json.dumps(respuesta),
                ]) as curl, mock.patch.object(cliente, "_urllib") as u, \
                        mock.patch.object(cliente.time, "sleep"):
                    self.assertEqual(cliente.get(recurso), respuesta)
                self.assertEqual(curl.call_count, 2)
                self.assertTrue(all(c.args[2] == 60 for c in curl.call_args_list))
                u.assert_not_called()

    def test_respuesta_incompleta_no_se_convierte_en_cola_vacia(self):
        for raw in ['{}', 'null', '[]', '{"ok":false}', '{"cola":null}']:
            with self.subTest(raw=raw):
                with mock.patch.object(cliente, "_curl", return_value=raw) as curl, \
                        mock.patch.object(cliente.time, "sleep"):
                    with self.assertRaises(cliente.SalaError):
                        cliente.get("cola")
                self.assertEqual(curl.call_count, 2)

    def test_json_incompleto_se_recupera_con_lectura_confirmada(self):
        with mock.patch.object(cliente, "_curl", side_effect=[
            '{"ok":true}', '{"cola":[]}',
        ]) as curl, mock.patch.object(cliente.time, "sleep"):
            self.assertEqual(cliente.get("cola"), {"cola": []})
        self.assertEqual(curl.call_count, 2)

    def test_otros_recursos_conservan_presupuesto_ordinario(self):
        with mock.patch.object(cliente, "_curl", return_value='{"ok":true}') as curl:
            cliente.get("catalogo")
        self.assertEqual(curl.call_args.args[2], 25)

    def test_escritura_sin_respuesta_no_reenvia_ni_usa_otro_transporte(self):
        with mock.patch.object(cliente, "_curl", side_effect=cliente.SalaError("timeout")) as curl, \
                mock.patch.object(cliente, "_urllib") as u, \
                mock.patch.object(cliente.time, "sleep") as dormir:
            with self.assertRaisesRegex(cliente.SalaError, "sin recibo confirmado; no se reenvió"):
                cliente.post("produccion", evento="Sintético")
        self.assertEqual(curl.call_count, 1)
        self.assertEqual(curl.call_args.args[2], 60)
        u.assert_not_called()
        dormir.assert_not_called()

    def test_error_no_sobrescribe_respaldo(self):
        with tempfile.TemporaryDirectory() as td:
            manifiesto = pathlib.Path(td) / "manifiesto.json"
            viejo = '{"peticiones":[{"estado":"cumplida"}],"decisiones":{"x":"si"}}\n'
            manifiesto.write_text(viejo, encoding="utf-8")
            with mock.patch.object(relevo, "MANIFIESTO", manifiesto):
                with mock.patch.object(relevo.sala, "get", side_effect=cliente.SalaError("timeout")):
                    with mock.patch.object(sys, "argv", ["sala_relevo.py"]):
                        codigo = relevo.main()
            self.assertEqual(codigo, 2)
            self.assertEqual(manifiesto.read_text(encoding="utf-8"), viejo)


class MetadataTest(unittest.TestCase):
    def test_curl_timeout_has_safe_constant_code_without_stderr(self):
        response=type("Response",(),{"returncode":28,"stdout":"\nSALA_TRANSPORTE_V1:000:60.002:0\n",
                                       "stderr":"PRIVATE-URL TOKEN"})()
        with mock.patch.object(cliente.subprocess,"run",return_value=response):
            with self.assertRaises(cliente.SalaError) as raised:
                cliente._curl("https://example.invalid/PRIVATE",espera=60)
        error=raised.exception
        self.assertEqual(error.codigo,"sala_tiempo_agotado")
        self.assertEqual(error.metadatos["curl_codigo"],28)
        self.assertEqual(error.metadatos["latencia_ms"],60002)
        self.assertNotIn("PRIVATE",json.dumps(error.metadatos))

    def test_curl_http_status_is_separate_from_remote_body(self):
        response=type("Response",(),{"returncode":0,"stdout":"PRIVATE-HTML\nSALA_TRANSPORTE_V1:403:1.2:12\n",
                                       "stderr":""})()
        with mock.patch.object(cliente.subprocess,"run",return_value=response):
            with self.assertRaises(cliente.SalaError) as raised:
                cliente._curl("https://example.invalid/PRIVATE",espera=60)
        self.assertEqual(raised.exception.codigo,"sala_http_403")
        self.assertEqual(raised.exception.metadatos["estado_http"],403)
        self.assertNotIn("PRIVATE",json.dumps(raised.exception.metadatos))

    def test_curl_preserves_body_and_handles_marker_inside_remote_content(self):
        body='{"cola":[],"nota":"SALA_TRANSPORTE_V1: PRIVATE"}'
        response=type("Response",(),{"returncode":0,"stdout":body+"\nSALA_TRANSPORTE_V1:200:1.5:48\n","stderr":""})()
        with mock.patch.object(cliente.subprocess,"run",return_value=response):
            raw=cliente._curl("https://example.invalid/exec",espera=60)
        self.assertEqual(raw,body)
        self.assertEqual(raw.metadatos["estado_http"],200)
        self.assertEqual(raw.metadatos["latencia_ms"],1500)

    def test_html_json_contract_and_auth_are_distinguishable(self):
        for raw,code,kind in (("<!doctype html>PRIVATE","sala_json_invalido","html"),
                ('{"error":"clave incorrecta"}',"sala_clave_rechazada","json_error"),
                ('[]',"sala_objeto_invalido","json_no_objeto")):
            with self.subTest(code=code),self.assertRaises(cliente.SalaError) as raised:
                cliente._leer_json(raw,"GET ?recurso=cola")
            self.assertEqual(raised.exception.codigo,code)
            self.assertEqual(raised.exception.metadatos["tipo_respuesta"],kind)
        with self.assertRaises(cliente.SalaError) as raised:
            cliente._validar_lectura('cola',{'cola':None})
        self.assertEqual(raised.exception.codigo,"sala_contrato_lectura")

    def test_exhausted_read_preserves_code_metrics_and_resource(self):
        error=cliente.SalaError("PRIVATE",codigo="sala_tiempo_agotado",
            metadatos={"curl_codigo":28,"latencia_ms":60000,"PRIVATE":"TOKEN"})
        with mock.patch.object(cliente,"_curl",side_effect=error) as curl, \
             mock.patch.object(cliente.time,"sleep"):
            with self.assertRaises(cliente.SalaError) as raised:
                cliente._pedir("https://example.invalid/PRIVATE",None,"GET ?recurso=cola",
                                espera=60,intentos=2,solo_curl=True)
        self.assertEqual(curl.call_count,2)
        self.assertEqual(raised.exception.codigo,"sala_tiempo_agotado")
        self.assertEqual(raised.exception.metadatos["recurso"],"cola")
        self.assertEqual(raised.exception.metadatos["intentos"],2)
        self.assertNotIn("PRIVATE",json.dumps(raised.exception.metadatos))

    def test_probe_is_one_bounded_get_and_never_returns_payload(self):
        with mock.patch.dict(os.environ,{"SALA_GAS_EXEC":"https://example.invalid/exec","SALA_CLAVE_AGENTE":"PRIVATE"}), \
             mock.patch.object(cliente,"_curl",return_value='{"cola":[{"nota":"PRIVATE"}]}') as curl:
            data=cliente.sonda_get("cola")
        self.assertTrue(data["ok"])
        self.assertEqual(curl.call_count,1)
        self.assertIsNone(curl.call_args.args[1])
        self.assertEqual(curl.call_args.args[2],20)
        self.assertNotIn("PRIVATE",json.dumps(data))
        self.assertNotIn("cola",data)
        for resource,budget in (("produccion",20),("cola",60)):
            with self.assertRaises(ValueError):
                cliente.sonda_get(resource,espera=budget)

    def test_probe_failure_has_no_fallback_or_retry(self):
        error=cliente.SalaError("PRIVATE",codigo="sala_http_405",metadatos={"estado_http":405})
        with mock.patch.dict(os.environ,{"SALA_GAS_EXEC":"https://example.invalid/exec","SALA_CLAVE_AGENTE":"PRIVATE"}), \
             mock.patch.object(cliente,"_curl",side_effect=error) as curl:
            data=cliente.sonda_get("cola")
        self.assertFalse(data["ok"])
        self.assertEqual(data["codigo"],"sala_http_405")
        self.assertEqual(curl.call_count,1)
        self.assertNotIn("PRIVATE",json.dumps(data))


class FakeClock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class Read404BudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock()
        self.patches=[mock.patch.dict(os.environ,{"SALA_GAS_EXEC":"https://example.invalid/exec",
                                                 "SALA_CLAVE_AGENTE":"synthetic"}),
                      mock.patch.object(cliente.time,"monotonic",self.clock.monotonic),
                      mock.patch.object(cliente.time,"sleep",self.clock.sleep)]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def transport(self,steps):
        calls=[]
        def request(url,body,timeout):
            calls.append((body,timeout))
            seconds,result=steps[len(calls)-1]
            self.clock.now+=seconds if seconds is not None else timeout
            if isinstance(result,Exception):raise result
            return result
        return calls,request

    def test_fresh_json_after_404_recovers_inside_original_budget(self):
        for resource,response in (("cola",'{"cola":[{"id":"synthetic","estado":"pendiente"}]}'),
                                  ("reglas",'{"reglas":{"nube_ejecuta_etapas":"voz"},"motores":[]}')):
            self.clock.now=0
            calls,transport=self.transport([(60,cliente.SalaError("timeout",codigo="sala_tiempo_agotado")),
                (35,cliente.SalaError("http",codigo="sala_http_404")),(2.4,response)])
            with self.subTest(resource=resource),mock.patch.object(cliente,"_curl",side_effect=transport), \
                 mock.patch.object(cliente,"avisar") as public_log,mock.patch.object(cliente,"sonda_get") as probe:
                result=cliente.get(resource)
            self.assertEqual(result,json.loads(response))
            self.assertEqual(calls,[(None,60),(None,60),(None,20)])
            self.assertLessEqual(self.clock.now,122)
            self.assertEqual(self.clock.now,99.4)
            self.assertNotIn("synthetic",str(public_log.call_args))
            probe.assert_not_called()

    def test_exhausted_budget_does_not_open_additional_period(self):
        calls,transport=self.transport([(60,cliente.SalaError("http",codigo="sala_http_404")),
                                       (60,cliente.SalaError("http",codigo="sala_http_404"))])
        with mock.patch.object(cliente,"_curl",side_effect=transport),self.assertRaises(cliente.SalaError) as raised:
            cliente.get("cola")
        self.assertEqual(len(calls),2)
        self.assertEqual(self.clock.now,122)
        self.assertEqual(raised.exception.codigo,"sala_http_404")

    def test_final_get_can_only_use_remaining_budget(self):
        error=cliente.SalaError("http",codigo="sala_http_404")
        calls,transport=self.transport([(60,error),(52.5,error),(None,error)])
        with mock.patch.object(cliente,"_curl",side_effect=transport),self.assertRaises(cliente.SalaError) as raised:
            cliente.get("cola")
        self.assertEqual(calls,[(None,60),(None,60),(None,7.5)])
        self.assertEqual(self.clock.now,122)
        self.assertEqual(raised.exception.metadatos["intentos"],3)
        self.assertEqual(raised.exception.metadatos["duracion_total_ms"],122000)

    def test_other_error_keeps_two_attempts_even_with_budget_left(self):
        for code in ("sala_http_403","sala_tiempo_agotado","sala_contrato_lectura","sala_clave_rechazada"):
            self.clock.now=0
            error=cliente.SalaError("synthetic",codigo=code)
            calls,transport=self.transport([(1,error),(1,error)])
            with self.subTest(code=code),mock.patch.object(cliente,"_curl",side_effect=transport), \
                 self.assertRaises(cliente.SalaError):cliente.get("cola")
            self.assertEqual(len(calls),2)

    def test_third_response_must_satisfy_original_contract(self):
        error=cliente.SalaError("http",codigo="sala_http_404")
        calls,transport=self.transport([(1,error),(1,error),(1,'{"cola":null}')])
        with mock.patch.object(cliente,"_curl",side_effect=transport),self.assertRaises(cliente.SalaError) as raised:
            cliente.get("cola")
        self.assertEqual(len(calls),3)
        self.assertEqual(raised.exception.codigo,"sala_contrato_lectura")

    def test_post_404_is_never_retried_or_recovered(self):
        calls,transport=self.transport([(1,cliente.SalaError("http",codigo="sala_http_404"))])
        with mock.patch.object(cliente,"_curl",side_effect=transport), \
             mock.patch.object(cliente,"_leer_sheet") as recover,self.assertRaises(cliente.SalaError):
            cliente.post("produccion",estado="synthetic")
        self.assertEqual(len(calls),1)
        self.assertIsNotNone(calls[0][0])
        recover.assert_not_called()

    def test_other_resources_do_not_receive_new_recovery(self):
        with mock.patch.object(cliente,"_leer_sheet",side_effect=AssertionError("recovery fuera de alcance")), \
             mock.patch.object(cliente,"_curl",return_value='{"ok":true}'):
            self.assertEqual(cliente.get("catalogo"),{"ok":True})


if __name__ == "__main__":
    unittest.main()
