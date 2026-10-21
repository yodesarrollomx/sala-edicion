"""Contrato del Space confirmado por error real: máximo cinco segundos."""
import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
from motores.escena_wan_hf import _segundos
from revision_video import perfil

class LimiteWan(unittest.TestCase):
    def test_limites_del_proveedor(self):
        for pedido, esperado in [('8',5), ('999',5), ('4',4), ('1',2), ('mal',5)]:
            self.assertEqual(_segundos({'escena_segundos':pedido}), esperado)
    def test_revision_respeta_contrato(self):
        reglas = perfil({})
        self.assertEqual(int(reglas['escena_segundos']), _segundos(reglas))
        self.assertEqual(reglas['montaje_video_real'], '1')
