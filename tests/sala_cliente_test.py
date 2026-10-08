#!/usr/bin/env python3
"""Pruebas sin red del timeout del relevo y del respaldo inviolable."""
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

    def test_dia_fresco_usa_curl_60_segundos_sin_urllib(self):
        with mock.patch.object(cliente, "_curl", return_value='{"decisiones":{}}') as curl:
            with mock.patch.object(cliente, "_urllib", side_effect=AssertionError("No usar urllib")):
                dia = cliente.get("dia", fresco="1")
        self.assertEqual(dia["decisiones"], {})
        self.assertEqual(curl.call_count, 1)
        url, cuerpo, espera = curl.call_args.args
        self.assertIn("recurso=dia", url)
        self.assertIn("fresco=1", url)
        self.assertIsNone(cuerpo)
        self.assertEqual(espera, 60)

    def test_dia_fresco_reintenta_una_vez_y_recupera(self):
        with mock.patch.object(cliente, "_curl", side_effect=[
            cliente.SalaError("curl falló (28)"),
            '{"fecha":"2026-10-07","decisiones":{}}',
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

    def test_otros_recursos_conservan_el_timeout_anterior(self):
        with mock.patch.object(cliente, "_urllib", return_value='{"ok":true}') as u:
            with mock.patch.object(cliente, "_curl", side_effect=AssertionError("No necesita curl")):
                cliente.get("reglas")
        self.assertEqual(u.call_args.args[2], 25)

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
