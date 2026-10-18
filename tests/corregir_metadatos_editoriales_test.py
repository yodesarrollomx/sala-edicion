import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'nube'))
from corregir_metadatos_editoriales import apply, CorreccionError
from contenido_reglas import ContenidoVetado


class MetadataCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.data = {'promesa': 'Un terreno en Hermosillo', 'guion': [{'n': 1, 'dice': 'Texto anterior'}],
                     'laminas': [{'n': 1, 'dice': 'Texto elegido', 'src': 'original.png', 'estado': 'aprobada',
                                  'seleccion': {'toma': 1}, 'candidatas': [{'dice': 'Texto elegido', 'src': 'original.png'}]}]}
        self.edit = [{'path': ['promesa'], 'before': 'Un terreno en Hermosillo', 'after': 'Un terreno'}]

    def run_patch(self, edits=None, **kwargs):
        raw = json.dumps(self.data).encode()
        return apply(raw, hashlib.sha256(raw).hexdigest(), edits or self.edit, **kwargs)

    def test_preserves_narration_images_decisions_and_input(self):
        original = json.dumps(self.data, sort_keys=True)
        out = json.loads(self.run_patch())
        self.assertEqual(out['laminas'], self.data['laminas'])
        self.assertEqual(original, json.dumps(self.data, sort_keys=True))

    def test_source_sha_changed_blocks(self):
        with self.assertRaisesRegex(CorreccionError, 'fuente_cambio'):
            apply(json.dumps(self.data).encode(), '0'*64, self.edit)

    def test_cannot_change_visible_narration(self):
        with self.assertRaisesRegex(CorreccionError, 'campo_fuera_de_alcance'):
            self.run_patch([{'path': ['laminas', 0, 'dice'], 'before': 'Texto elegido', 'after': 'Otro texto'}])

    def test_candidate_veto_blocks_instead_of_silent_rewrite(self):
        self.data['laminas'][0]['candidatas'][0]['ve'] = 'Paisaje de Sonora'
        with self.assertRaises(ContenidoVetado):
            self.run_patch()

    def test_explicit_voice_script_requires_review(self):
        with self.assertRaisesRegex(CorreccionError, 'requiere_revision_guion_de_voz'):
            self.run_patch(family_has_voice_script=True)

    def test_no_global_replace_or_unreviewed_text(self):
        self.edit[0]['before'] = 'Un terreno distinto en Hermosillo'
        with self.assertRaisesRegex(CorreccionError, 'texto_fuente_cambio'):
            self.run_patch()


if __name__ == '__main__':
    unittest.main()
