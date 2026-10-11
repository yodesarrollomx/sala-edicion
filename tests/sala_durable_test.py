import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
import sala_ejecutor as executor

class Response:
    def __init__(self, data=None, content=b''):
        self.data = data
        self.content = content
    def json(self):
        return self.data

class DurableProduction(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / 'pieza-L1-escena.mp4'
        self.body = b'producto-sintetico-v1'
        self.path.write_bytes(self.body)
        self.md5 = hashlib.md5(self.body).hexdigest()

    def response(self, method, url, **kwargs):
        if kwargs.get('params', {}).get('alt') == 'media':
            return Response(content=self.body)
        return Response({'id': 'file-confirmed', 'size': str(len(self.body)),
                         'md5Checksum': self.md5, 'trashed': False})

    def upload(self, existing=None, side_effect=None):
        with patch.object(executor.drive, 'ruta_carpetas', return_value='folder') as folder, \
             patch.object(executor.drive, 'buscar_hijo', return_value=existing), \
             patch.object(executor.drive, 'subir', return_value='file-confirmed') as upload, \
             patch.object(executor.drive, '_peticion', side_effect=side_effect or self.response):
            result = executor.subir_producto(self.path, 'pieza', 'root', {})
            return result, upload, folder

    def test_versioned_filename_and_readback_before_confirmation(self):
        result, upload, _ = self.upload()
        self.assertEqual(result, ('file-confirmed', None))
        self.assertEqual(upload.call_args.kwargs['nombre'],
                         'pieza-L1-escena-' + self.md5 + '.mp4')

    def test_existing_identical_version_is_read_without_overwriting(self):
        result, upload, _ = self.upload(existing='file-confirmed')
        self.assertEqual(result, ('file-confirmed', None))
        upload.assert_not_called()

    def test_conflicting_existing_version_is_not_overwritten(self):
        def bad(method, url, **kwargs):
            return Response({'id': 'file-confirmed', 'size': str(len(self.body)),
                             'md5Checksum': '0' * 32, 'trashed': False})
        result, upload, _ = self.upload(existing='file-confirmed', side_effect=bad)
        self.assertIsNone(result[0])
        self.assertIn('huella', result[1])
        upload.assert_not_called()

    def test_metadata_confirmation_does_not_hide_failed_download(self):
        def bad(method, url, **kwargs):
            if kwargs.get('params', {}).get('alt') == 'media':
                return Response(content=b'contenido-diferente')
            return self.response(method, url, **kwargs)
        result, _, _ = self.upload(side_effect=bad)
        self.assertIsNone(result[0])
        self.assertIn('recuperado', result[1])

    def test_missing_root_has_no_drive_effects(self):
        with patch.object(executor.drive, 'ruta_carpetas') as folder:
            result = executor.subir_producto(self.path, 'pieza', None, {})
            self.assertIsNone(result[0])
            folder.assert_not_called()

    def run_job(self, result):
        job = {'id': 'synthetic:corte:1:12345678', 'pieza': 'synthetic',
               'etapa': 'corte', 'evidencia': {'laminas': [{'item': '1', 'huella': '12345678'}]}}
        with patch.object(executor, '_leer_tira', return_value=None), \
             patch.object(executor.montador, 'ensamblar', return_value=self.path), \
             patch.object(executor, 'duracion_de', return_value=3.2), \
             patch.object(executor, 'subir_producto', return_value=result):
            return executor.ejecutar_uno(job, {}, {}, {}, 'root', [])

    def test_failed_storage_never_reports_completed_production(self):
        state, evidence = self.run_job((None, 'subida no confirmada'))
        self.assertEqual(state, 'fallo')
        self.assertFalse(evidence['durable'])
        self.assertEqual(evidence['md5'], self.md5)
        self.assertIn('revisar', evidence['error'])

    def test_only_confirmed_storage_reports_completed_production(self):
        state, evidence = self.run_job(('file-confirmed', None))
        self.assertEqual(state, 'hecho')
        self.assertTrue(evidence['durable'])
        self.assertEqual(evidence['drive_id'], 'file-confirmed')

if __name__ == '__main__':
    unittest.main()
