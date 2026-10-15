"""Synthetic records only; no network or business effects."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
from revisiones_presentacion import PRIVATE_KIND, public_projection, assert_public_bytes
import sala_relevo
import snapshots_online as so


class ReviewProjectionTests(unittest.TestCase):
    def setUp(self):
        self.cid = 'CHN-20261015-0900-abcd'
        self.private = {'kind': PRIVATE_KIND, 'id': self.cid,
                        'objeto': {'revision': {'comment': 'PRIVATE-SYNTHETIC-NOTE',
                                               'capture': {'data': 'PRIVATE-SYNTHETIC-IMAGE'}}}}
        self.raw = json.dumps(self.private)

    def test_projection_preserves_only_id_and_fixed_note_without_mutating_source(self):
        original = copy.deepcopy(self.private)
        result = public_projection(self.private)
        self.assertEqual(result['id'], self.cid)
        self.assertEqual(set(result), {'id', 'texto'})
        self.assertNotIn('PRIVATE-SYNTHETIC', json.dumps(result))
        self.assertEqual(self.private, original)

    def test_serialized_truncated_and_nested_cells_are_projected(self):
        for raw in (self.raw, self.raw[:200], self.raw[:70], self.raw.replace('"', '\\"'),
                    self.raw.replace('yod-', 'yod\\u002d')):
            result = public_projection({'bitacora': [{'detalle': raw}]})
            self.assertNotIn(PRIVATE_KIND, json.dumps(result))
            self.assertNotIn('PRIVATE-SYNTHETIC', json.dumps(result))

    def test_ordinary_history_and_editor_decisions_are_unchanged(self):
        original = {'decisiones': {'editor': {'si': True, 'nota': 'original'}},
                    'produccion': [{'detalle': 'historia normal'}]}
        self.assertEqual(public_projection(original), original)

    def test_relevo_projects_private_cells_and_retains_current_decisions_and_prior_history(self):
        day = {'fecha': '2026-10-15', 'produccion': [{'detalle': self.raw}],
               'bitacora': [{'detalle': self.raw[:200]}], 'decisiones': {'original': True}}
        result = sala_relevo.armar(day, {'historial': [{'detalle': self.raw}], 'rol': 'agente'})
        self.assertEqual(result['decisiones'], day['decisiones'])
        self.assertNotIn('rol', result)
        self.assertNotIn(PRIVATE_KIND, json.dumps(result))
        self.assertNotIn('PRIVATE-SYNTHETIC', json.dumps(result))
        self.assertEqual(day['produccion'][0]['detalle'], self.raw)

    def test_snapshot_rejects_raw_nested_envelope_and_accepts_public_projection(self):
        path = 'datos/manifiesto.json'
        for value in (self.private, {'detalle': self.raw}, {'detalle': self.raw[:200]}):
            data = json.dumps(value).encode()
            with self.assertRaises(so.OnlineError):
                so.validate_file(path, data)
            so.validate_file(path, json.dumps(public_projection(value)).encode())

    def test_public_bundle_rejects_even_tracked_json_before_deleting_old_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'; root.mkdir()
            (root / 'bad.json').write_text(self.raw)
            dest = Path(tmp) / 'old'; dest.mkdir(); (dest / 'keep').write_text('keep')
            instance = object.__new__(so.Snapshots); instance.root = root
            with patch.object(instance, 'hydrate_media', return_value=None), \
                 patch.object(instance, 'git', return_value='bad.json\0'), \
                 patch.object(instance, 'fingerprint', return_value={}), \
                 patch.object(instance, 'plan_hash_for_receipt'), \
                 patch.object(instance, 'media_hash_for_receipt'):
                with self.assertRaises(so.OnlineError):
                    instance.build_site(dest)
            self.assertEqual((dest / 'keep').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
