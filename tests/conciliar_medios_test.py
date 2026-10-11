import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
import conciliar_medios as reconcile

class Http:
    def __init__(self, body, status=200, declared=None):
        self.body, self.status_code = body, status
        self.headers = {'Content-Length': str(len(body) if declared is None else declared)}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, size):
        yield self.body[:3]
        yield self.body[3:]

class GitIdentity(unittest.TestCase):
    def setUp(self):
        self.body = b'medio-sintetico-inmutable'
        self.oid = subprocess.check_output(['git', 'hash-object', '--stdin'], input=self.body).decode().strip()

    def test_http_bytes_match_identity_computed_by_real_git(self):
        with patch('requests.get', return_value=Http(self.body)) as get:
            actual = reconcile.public_blob('a' * 40, 'muestras/sintetico.wav', self.oid)
            self.assertEqual(actual, self.body)
            self.assertIn('/' + 'a' * 40 + '/muestras/sintetico.wav', get.call_args.args[0])

    def test_different_content_cannot_inherit_the_expected_git_identity(self):
        with patch('requests.get', return_value=Http(b'contenido-diferente')):
            with self.assertRaisesRegex(RuntimeError, 'identity_not_verified'):
                reconcile.public_blob('a' * 40, 'muestras/sintetico.wav', self.oid)

    def test_download_bound_applies_even_if_the_header_understates_size(self):
        with patch('requests.get', return_value=Http(self.body, declared=1)):
            with self.assertRaisesRegex(RuntimeError, 'size_bound'):
                reconcile.public_blob('a' * 40, 'muestras/sintetico.wav', self.oid, maximum=8)

    def test_http_rejection_never_becomes_an_archived_output(self):
        with patch('requests.get', return_value=Http(b'no disponible', status=404)):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                reconcile.public_blob('a' * 40, 'muestras/sintetico.wav', self.oid)

if __name__ == '__main__':
    unittest.main()
