import copy
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'nube'))
import reanudar_cortes_metadatos as op


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'id': 'demo:corte:completo:12345678', 'estado': 'fallo',
                      'evidencia': {'error': 'ubicación vetada'}, 'actualizado': 'antes'}]

    def test_lost_ack_does_not_resend_and_preserves_evidence(self):
        calls = []
        current = copy.deepcopy(self.rows)
        def write(changes):
            calls.append(changes)
            current[0]['estado'] = 'pendiente'
            current[0]['actualizado'] = 'despues'
            raise op.sala.SalaError('respuesta perdida')
        result = op.transition(self.rows, lambda: copy.deepcopy(current), write)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result[0]['evidencia'], self.rows[0]['evidencia'])

    def test_no_effect_ack_is_not_claimed_success(self):
        calls = []
        with self.assertRaisesRegex(ValueError, 'reanudacion_sin_acuse_no_reenviar'):
            op.transition(self.rows, lambda: copy.deepcopy(self.rows), lambda rows: calls.append(rows))
        self.assertEqual(len(calls), 1)

    def test_concurrent_change_stops_before_post(self):
        newer = copy.deepcopy(self.rows)
        newer[0]['estado'] = 'hecho'
        def forbidden(rows):
            self.fail('must not write')
        with self.assertRaisesRegex(ValueError, 'cola_cambio_antes_de_reanudar'):
            op.transition(self.rows, lambda: newer, forbidden)

    def test_duplicate_target_rejected(self):
        t = {'id': self.rows[0]['id'], 'pid': 'demo', 'source_sha256': '0'*64, 'row_sha256': '1'*64}
        with self.assertRaisesRegex(ValueError, 'objetivos_repetidos'):
            op.validate_manifest({'schema': 1, 'code_sha': 'a'*40, 'targets': [t]*4})

    def test_voice_text_mismatch_stops_reuse(self):
        row = {'pieza': 'demo', 'evidencia': {'laminas': [{'item': '1', 'huella': '12345678'}]}}
        voice = {'id': 'demo:voz:1:12345678', 'estado': 'hecho', 'evidencia': {'src': 'same.png', 'dice': 'texto viejo'}}
        resolved = {'laminas': [{'n': 1, 'dice': 'texto elegido'}]}
        with self.assertRaisesRegex(ValueError, 'voz_texto_distinto'):
            op.ensure_voice_match(row, resolved, [voice])


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.draft = {'schema': 1, 'targets': [
            {'id': f'demo{i}:corte:completo:12345678', 'pid': f'demo{i}',
             'source_sha256': 'a'*64, 'replacements': []} for i in range(4)]}
        self.rows = [{'id': t['id'], 'estado': 'fallo', 'etapa': 'corte', 'item': 'completo',
                      'creado': 'Sun Oct 18 2026 09:07:00 GMT-0700 (MST)',
                      'actualizado': 'Sun Oct 18 2026 10:08:00 GMT-0700 (MST)',
                      'evidencia': {'de': t['pid'], 'error': 'ubicación vetada'}} for t in self.draft['targets']]

    def test_captures_exact_dates_and_preserves_input(self):
        before = copy.deepcopy(self.draft)
        out = op.prepare_manifest(self.draft, lambda: self.rows, lambda: 'b'*40)
        self.assertEqual(self.draft, before)
        self.assertEqual(out['cola_capturada'], self.rows)
        self.assertEqual(out['manifest']['targets'][0]['row_sha256'], op.digest(op.signature(self.rows[0]).encode()))
        self.assertEqual(out['manifest']['code_sha'], 'b'*40)

    def test_unstable_row_rejected(self):
        changed = copy.deepcopy(self.rows)
        changed[0]['actualizado'] = 'changed'
        read = Mock(side_effect=[self.rows, changed])
        with self.assertRaisesRegex(ValueError, 'cola_cambio'):
            op.prepare_manifest(self.draft, read, lambda: 'b'*40)

    def test_preparar_main_never_changes_sources_posts_or_snapshots(self):
        raw = op.canonical(self.draft)
        meta = Mock(); meta.json.return_value = {'trashed': False, 'parents': ['folder'], 'mimeType': 'application/vnd.google-apps.document'}
        export = Mock(content=raw)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'datos/tiras/demo.json'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'unchanged source')
            with patch.object(op, 'ROOT', Path(tmp)), patch.dict(op.os.environ, {
                    'EDITORIAL_PATCH_DOC_ID': 'document0000000', 'EDITORIAL_PATCH_SHA256': op.digest(raw),
                    'EDITORIAL_PATCH_MODE': 'preparar'}), \
                 patch.object(op.sala, 'enmascarar_en_actions'), \
                 patch.object(op, 'private_config', return_value=({}, 'folder')), \
                 patch.object(op.drive, '_peticion', side_effect=[meta, export]) as drive_calls, \
                 patch.object(op.sala, 'get', return_value={'cola': self.rows}), \
                 patch.object(op.sala, 'post') as post, \
                 patch.object(op, 'read_code_sha', return_value='b'*40), \
                 patch.object(op, 'Snapshots') as snapshots, \
                 patch.object(op, 'guardar') as save:
                self.assertEqual(op.main(), 0)
                post.assert_not_called()
                snapshots.assert_not_called()  # includes bootstrap/prepare/dispatch/release
                self.assertEqual(source.read_bytes(), b'unchanged source')
                self.assertEqual(save.call_count, 1)
                self.assertEqual(save.call_args.args[2], 'metadatos-manifiesto-preparado')
                self.assertTrue(all(c.args[0] == 'GET' for c in drive_calls.call_args_list))

    def test_preparar_inhibits_gas_post(self):
        with patch.object(op.sala, 'post') as original:
            with op.gas_read_only():
                with self.assertRaisesRegex(ValueError, 'preparar_prohibe_post_gas'):
                    op.sala.post('cola')
            original.assert_not_called()
            self.assertIs(op.sala.post, original)


if __name__ == '__main__':
    unittest.main()
