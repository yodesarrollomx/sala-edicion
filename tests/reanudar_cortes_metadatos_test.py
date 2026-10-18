import copy
import json
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


class VoiceEvidenceTests(unittest.TestCase):
    def fixture(self, encoded, note=''):
        row = {'pieza': 'demo', 'evidencia': {'laminas': [{'item': '1', 'huella': '12345678'}]}}
        ev = {'src': 'same.png', 'dice': 'texto original', 'nota': note, 'de': 'demo', 'lamina': 1}
        voice = {'id': 'demo:voz:1:12345678', 'estado': 'hecho', 'evidencia': json.dumps(ev) if encoded else ev}
        return row, voice

    def test_dict_and_json_evidence_match_without_mutating_queue(self):
        for encoded in (False, True):
            with self.subTest(encoded=encoded):
                row, voice = self.fixture(encoded)
                before = copy.deepcopy([row, voice])
                op.ensure_voice_match(row, {'laminas': [{'n': 1, 'dice': 'texto original'}]}, [voice])
                self.assertEqual([row, voice], before)
                with self.assertRaisesRegex(ValueError, 'voz_texto_distinto'):
                    op.ensure_voice_match(row, {'laminas': [{'n': 1, 'dice': 'texto diferente'}]}, [voice])
                self.assertEqual([row, voice], before)

    def test_selected_candidate_text_still_controls_comparison(self):
        import motores._comun as common
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'demo.json'
            source.write_text(json.dumps({'laminas': [{'n': 1, 'dice': 'texto original',
                'candidatas': [{'src': 'old.png', 'dice': 'texto original'},
                               {'src': 'chosen.png', 'dice': 'texto elegido'}]}]}))
            raw = source.read_bytes()
            with patch.object(common, 'TIRAS', Path(tmp)):
                for encoded in (False, True):
                    with self.subTest(encoded=encoded):
                        row, voice = self.fixture(encoded, '[toma elegida: 2]')
                        before = copy.deepcopy([row, voice])
                        op.ensure_voice_match(row, {'laminas': [{'n': 1, 'dice': 'texto elegido'}]}, [voice])
                        with self.assertRaisesRegex(ValueError, 'voz_texto_distinto'):
                            op.ensure_voice_match(row, {'laminas': [{'n': 1, 'dice': 'texto original'}]}, [voice])
                        self.assertEqual([row, voice], before)
                        self.assertEqual(source.read_bytes(), raw)


    def test_getter_queue_strings_through_sources_target_and_selected_voice(self):
        import motores._comun as common
        row, voice = self.fixture(True, '[toma elegida: 2]')
        row.update(id='demo:corte:completo:12345678', estado='fallo', etapa='corte', item='completo')
        row['evidencia'].update(de='demo', error='ubicación vetada')
        row['evidencia'] = json.dumps(row['evidencia'])
        queue = [row, voice]
        day = {'ok': True, 'fecha': '2026-10-18', 'propuestas': [{'id': 'demo', 'estado': 'en revisión'}],
               'decisiones': {'propuestas': {'demo': {'laminas': ['si'], 'notas': ['[toma elegida: 2]']}}}}
        tira = {'pieza_slug': 'demo', 'formato': 'video', 'promesa': 'Terreno en Hermosillo',
                'guion': [{'n': 1}], 'laminas': [{'n': 1, 'dice': 'texto original',
                    'candidatas': [{'src': 'old.png', 'dice': 'texto original'},
                                   {'src': 'chosen.png', 'dice': 'texto elegido'}]}]}
        raw = json.dumps(tira).encode()
        target = {'id': row['id'], 'pid': 'demo', 'source_sha256': op.digest(raw),
                  'row_sha256': op.digest(op.signature(row).encode()),
                  'replacements': [{'path': ['promesa'], 'before': 'Terreno en Hermosillo', 'after': 'Terreno'}]}
        before = copy.deepcopy(queue)
        responses = {'cola': {'cola': queue}, 'reglas': {'reglas': {}}, 'catalogo': {'catalogo': {}}, 'dia': day}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(op.os.environ, {'SALA_PRODUCCION_HISTORICA': '0'}), \
                patch.object(op.sala, 'get', side_effect=lambda resource, **kwargs: copy.deepcopy(responses[resource])) as get, \
                patch.object(op.sala, 'post', side_effect=AssertionError('no POST')), patch.object(common, 'TIRAS', Path(tmp)):
            path = Path(tmp)/'demo.json'; path.write_bytes(raw)
            _, actual_queue, actual_day, _ = op.fuentes()
            corrected = op.apply(raw, target['source_sha256'], target['replacements'])
            actual_row, resolved = op.check_target(target, actual_queue, actual_day, raw, corrected)
            self.assertEqual(resolved['laminas'][0]['dice'], 'texto elegido')
            self.assertEqual(resolved['laminas'][0]['seleccion']['toma'], 2)
            op.ensure_voice_match(actual_row, resolved, actual_queue)
            resolved['laminas'][0]['dice'] = 'texto original'
            with self.assertRaisesRegex(ValueError, 'voz_texto_distinto'):
                op.ensure_voice_match(actual_row, resolved, actual_queue)
            self.assertEqual(actual_queue, before)
            self.assertEqual(path.read_bytes(), raw)
            self.assertTrue(all(c.kwargs.get('fresco') == '1' for c in get.call_args_list))
        self.assertEqual(queue, before)


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
