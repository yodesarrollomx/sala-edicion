import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'nube'))
import medir_lectura_sala as probe

class Medicion(unittest.TestCase):
    def test_presupuesto_y_privacidad(self):
        with patch.object(probe.sala,'enmascarar_en_actions'), patch.object(probe.sala,'_exec_url',return_value='https://example.invalid'), patch.object(probe.sala,'_clave',return_value='synthetic-secret'), patch.object(probe.sala,'_curl',side_effect=probe.sala.SalaError('private payload',codigo='sala_tiempo_agotado',metadatos={'estado_http':0})) as get, patch.object(probe.time,'sleep'):
            result=probe.medir()
        self.assertEqual(get.call_count,2)
        self.assertTrue(all(c.kwargs=={'espera':8} for c in get.call_args_list))
        self.assertNotIn('synthetic-secret',str(result))
        self.assertNotIn('private payload',str(result))
        self.assertFalse(result['arranque_frio_acreditado'])
        self.assertTrue(all(not r['ok'] for r in result['muestras']))
