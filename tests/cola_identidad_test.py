import copy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
from cola_identidad import cola_segura, consolidar_plan


def trabajo(source='fuente-a', **evidence):
    return {'id': 'sintetica:voz:1:abcdef12', 'pieza': 'sintetica', 'etapa': 'voz',
            'item': '1', 'estado': 'pendiente', 'prioridad': 5,
            'evidencia': {'de': source, 'src': 'laminas/sintetica.png', 'dice': 'Texto', **evidence}}


class IdentidadTests(unittest.TestCase):
    def test_equal_execution_consolidates_and_preserves_every_source_in_any_order(self):
        rows = [trabajo('fuente-b'), trabajo(), trabajo()]
        for order in itertools.permutations(rows):
            before = copy.deepcopy(order)
            unique, blocked = consolidar_plan(order)
            self.assertEqual(blocked, [])
            self.assertEqual(len(unique), 1)
            self.assertEqual(unique[0]['evidencia']['fuentes_equivalentes'], ['fuente-a', 'fuente-b'])
            self.assertEqual(unique[0]['evidencia']['de'], 'fuente-a')
            self.assertEqual(order, before)

    def test_different_note_or_content_blocks_identity_but_keeps_unrelated_work(self):
        for change in ({'nota': 'Otra instrucción'}, {'dice': 'Otro texto'}, {'src': 'otra.png'}):
            separate = trabajo('otra-fuente'); separate['id'] = 'sintetica:voz:2:abcd1234'
            rows = [trabajo(), trabajo('fuente-b', **change), separate]
            for order in itertools.permutations(rows):
                unique, blocked = consolidar_plan(order)
                self.assertEqual([x['id'] for x in unique], [separate['id']])
                self.assertEqual(blocked, [rows[0]['id']])

    def test_duplicate_running_or_pending_is_blocked_before_rescue_or_execution(self):
        rows = [trabajo(), trabajo('fuente-b')]; rows[0]['estado'] = 'corriendo'
        before = copy.deepcopy(rows)
        safe, count = cola_segura(rows)
        self.assertEqual(count, 1)
        self.assertTrue(all(x['estado'] == 'bloqueado' for x in safe))
        self.assertEqual(rows, before)

    def test_obsolete_history_does_not_reexecute_or_block_the_unique_active_row(self):
        obsolete = trabajo('fuente-b'); obsolete['estado'] = 'obsoleto'
        safe, count = cola_segura([trabajo(), obsolete])
        self.assertEqual(count, 0)
        self.assertEqual(safe, [trabajo()])


if __name__ == '__main__': unittest.main()
