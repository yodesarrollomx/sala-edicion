import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
from sala_publicaciones import proyectar

class PublicacionesTest(unittest.TestCase):
    def test_solo_vigentes_y_campos_publicos(self):
        tira = {"laminas": [{"n": 1, "estado": "aprobada", "nota": "privada",
                            "seleccion": {"toma": 2, "src": "privado"}}]}
        seen = []
        def resolve(t, d, p):
            seen.append((d, p))
            return t
        out = proyectar({"a": ("actual", tira), "b": ("retirada", tira)},
                        {"propuestas": [{"id": "actual"}],
                         "decisiones": {"propuestas": {"actual": {"notas": ["privada"]}}}}, resolve)
        self.assertEqual(out, [{"id": "actual", "laminas": [{"n": 1, "estado": "aprobada", "toma": 2}]}])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0]["notas"], ["privada"])

    def test_fallo_no_equivale_a_inventario_vacio(self):
        def fail(*args):
            raise RuntimeError("lectura sin confirmar")
        with self.assertRaises(RuntimeError):
            proyectar({"a": ("actual", {})}, {"propuestas": [{"id": "actual"}]}, fail)

    def test_identidad_invalida_no_se_publica(self):
        with self.assertRaises(ValueError):
            proyectar({"a": ("../secret", {})}, {"propuestas": [{"id": "../secret"}]}, lambda t,d,p:t)

    def test_pendiente_no_se_convierte_en_aprobada(self):
        self.assertEqual(proyectar({"a": ("actual", {"laminas": [{"n": 1, "estado": "rehecha"}]})},
                                  {"propuestas": [{"id": "actual"}]}, lambda t,d,p:t)[0]["laminas"][0]["estado"], "pendiente")
