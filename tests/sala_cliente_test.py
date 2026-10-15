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


if __name__ == "__main__":
    unittest.main()
