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


if __name__ == "__main__":
    unittest.main()
