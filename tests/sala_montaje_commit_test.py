"""Regresión de montaje del commit publicado; Git real, GAS doble y sin red."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import sala_cliente
import sala_mesa

PID = 'ficha-nube-2026-10-10-abcdef'
TIRA = 'datos/tiras/' + PID + '.json'
IMAGE = 'laminas/ficha/L1.jpg'


class MontajeCommitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Prueba')
        self.git('config', 'user.email', 'prueba@example.invalid')
        (self.root / 'README.md').write_text('base\n')
        self.commit('base')
        self.addCleanup(patch.stopall)
        patch.object(sala_mesa, 'RAIZ', self.root).start()
        patch.object(sala_mesa, 'TIRAS', self.root / 'datos' / 'tiras').start()
        patch.object(sala_mesa, 'validar_nuevas_tomas').start()
        patch.object(sala_cliente, 'avisar').start()
        self.post = patch.object(sala_cliente, 'post', return_value={'ok': True}).start()

    def git(self, *args):
        p = subprocess.run(['git', *args], cwd=self.root, text=True,
                           capture_output=True, check=True, timeout=15)
        return p.stdout.strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)

    def add_tira(self, image=True):
        path = self.root / TIRA
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            'pieza': 'Ficha', 'pieza_slug': 'ficha', 'fecha': '2026-10-10',
            'decidir': [1], 'laminas': [{'n': 1, 'src': IMAGE}]
        }), encoding='utf-8')
        if image:
            asset = self.root / IMAGE
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(b'fixture de existencia: no imagen de produccion')

    def assert_mount(self):
        self.assertEqual(sala_mesa.montar_desde_commit(), 0)
        self.post.assert_called_once()
        args, kwargs = self.post.call_args
        self.assertEqual(args, ('proponer',))
        self.assertEqual(kwargs['familia'], 'ficha')
        self.assertEqual(kwargs['propuestas'][0]['id'], PID)
        self.assertEqual(kwargs['propuestas'][0]['laminas'], [IMAGE])

    def test_commit_simple_monta_una_tira_nueva(self):
        self.add_tira()
        self.commit('tira nueva')
        self.assert_mount()

    def test_merge_con_dos_padres_detecta_y_monta_la_tira(self):
        self.git('checkout', '-b', 'propuesta')
        self.add_tira()
        self.commit('tira en PR')
        self.git('checkout', 'main')
        (self.root / 'README.md').write_text('avance paralelo en main\n')
        self.commit('avance de main')
        self.git('merge', '--no-ff', 'propuesta', '-m', 'integrar PR')
        self.assertEqual(len(self.git('show', '-s', '--format=%P', 'HEAD').split()), 2)
        self.assert_mount()

    def test_modificar_tira_existente_no_la_vuelve_a_proponer(self):
        self.add_tira()
        self.commit('tira previa')
        path = self.root / TIRA
        data = json.loads(path.read_text())
        data['fecha'] = '2026-10-11'
        path.write_text(json.dumps(data))
        self.commit('solo historia')
        self.assertEqual(sala_mesa.montar_desde_commit(), 0)
        self.post.assert_not_called()

    def test_sin_imagen_publicada_no_se_escribe_en_gas(self):
        self.add_tira(image=False)
        self.commit('tira sin archivo')
        with self.assertRaises(sala_cliente.SalaError):
            sala_mesa.montar_desde_commit()
        self.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
