#!/usr/bin/env python3
"""Contrato del catálogo: la forma real del GAS llega a sus consumidores."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "nube"))
import sala_catalogo as catalogo
import sala_productor as productor

class CatalogoContratoTest(unittest.TestCase):
    def setUp(self):
        catalogo._cache = None
        self.addCleanup(setattr, catalogo, "_cache", None)
        self.gas = {"catalogo": {"PRUEBA-L01": {
            "serial": "PRUEBA-L01", "pieza": "PRUEBA", "lamina": 1,
            "revisiones": [{
                "r": 2, "de": 2, "huella": "aa11bb22cc33",
                "ruta": "laminas/prueba/L1.png",
                "rutas": "laminas/prueba/L1.png|laminas/alias/L3.png",
                "prueba": "drive-prueba-sintetico",
                "original": "drive-original-sintetico",
                "pidio": "nota sintética", "fecha": "2026-10-10",
            }],
        }}}

    def test_cargar_gas_resuelve_huella_y_drive_desde_todas_las_rutas(self):
        original = copy.deepcopy(self.gas)
        with mock.patch.object(catalogo.sala, "get", return_value=self.gas):
            cat = catalogo.cargar()
        for ruta in ("laminas/prueba/L1.png", "laminas/alias/L3.png"):
            with self.subTest(ruta=ruta):
                ident = catalogo.huella_de(ruta, cat)
                self.assertEqual(ident["serial"], "PRUEBA-L01")
                self.assertEqual(ident["huella"], "aa11bb22cc33")
                self.assertEqual(ident["revision"], 2)
                self.assertEqual(catalogo.drive_de(ruta, cat), {
                    "prueba": "drive-prueba-sintetico",
                    "original": "drive-original-sintetico",
                })
        self.assertEqual(self.gas, original)

    def test_productor_usa_catalogo_en_vez_de_inventar_hash_de_ruta(self):
        with mock.patch.object(catalogo.sala, "get", return_value=self.gas):
            cat = catalogo.cargar()
        version, fuente = productor.huella_insumo({"src": "laminas/alias/L3.png"}, cat)
        self.assertEqual(version, "aa11bb22")
        self.assertEqual(fuente, "catalogo:PRUEBA-L01")

    def test_respaldo_canonico_conserva_su_identidad_si_gas_no_contesta(self):
        canonical = {"PRUEBA-L01": {"pieza": "PRUEBA", "lamina": 1, "revisiones": [{
            "r": 2, "huella": "aa11bb22cc33", "src": "laminas/prueba/L1.png",
            "tambien_en": ["laminas/alias/L3.png"],
            "drive_prueba": "drive-prueba-sintetico",
            "drive_original": "drive-original-sintetico",
        }]}}
        with tempfile.TemporaryDirectory() as temp:
            file = pathlib.Path(temp) / "catalogo.json"
            file.write_text(json.dumps(canonical))
            with mock.patch.object(catalogo, "RESPALDO", file):
                with mock.patch.object(catalogo.sala, "get", side_effect=catalogo.sala.SalaError("sin red")):
                    cat = catalogo.cargar()
            self.assertEqual(cat, canonical)
            self.assertEqual(catalogo.huella_de("laminas/alias/L3.png", cat)["huella"], "aa11bb22cc33")

if __name__ == "__main__":
    unittest.main()
