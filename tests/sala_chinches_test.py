"""Recibos del puente con un Sheet y GitHub sintéticos, sin red ni decisiones."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
import sala_chinches as puente
import sala_cliente as sala

CID = 'CHN-20261014-2111-abcd'
EVENTO = 'ENCARGO CUMPLIDO · chinche'
PENDIENTE = 'chinche-cumplido-pendiente'


def issue(labels=(), state='CLOSED', reason='COMPLETED'):
    return {'number': 27, 'chn': CID, 'url': 'https://github.com/example/repo/issues/27',
            'etiquetas': list(labels), 'state': state, 'stateReason': reason}


def row(event=EVENTO, **detail):
    return {'pieza': event, 'detalle': json.dumps({'id': CID, **detail})}


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.labels, self.posts = [], set(), []
        self.reader_error = False
        self.hide_receipts = False
        self.lost_response = False
        self.label_failure = False
        self.dispatch_failure = False
        self.dispatches = 0
        self.created = []
        self.patches = [patch.object(puente, 'gh', side_effect=self.gh),
                        patch.object(sala, 'get', side_effect=self.get),
                        patch.object(sala, 'post', side_effect=self.post),
                        patch.object(sala, 'avisar')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def get(self, resource, **kw):
        self.assertEqual(resource, 'dia')
        self.assertEqual(kw, {'fresco': '1'})
        if self.reader_error:
            raise sala.SalaError('lectura no disponible')
        return {'produccion': [] if self.hide_receipts else copy.deepcopy(self.rows)}

    def post(self, action, **kw):
        self.assertEqual(action, 'produccion')
        self.assertIn(PENDIENTE, self.labels) if kw['pieza'] == EVENTO else None
        self.posts.append(copy.deepcopy(kw))
        self.rows.append(kw)
        if self.lost_response:
            raise sala.SalaError('el servidor guardó y se perdió la respuesta')
        return {'ok': True}

    def gh(self, *args):
        if args[:2] == ('issue', 'edit'):
            label = args[args.index('--add-label') + 1]
            if self.label_failure and label == 'en-sheet':
                raise RuntimeError('falló el guardado de la etiqueta final')
            self.labels.add(label)
            if '--remove-label' in args:
                self.labels.discard(args[args.index('--remove-label') + 1])
            return ''
        if args[:2] == ('workflow', 'run'):
            self.assertIn('semillero-por-confirmar', self.labels)
            self.dispatches += 1
            if self.dispatch_failure:
                raise RuntimeError('dispatch sin respuesta concluyente')
            return ''
        if args[:2] == ('issue', 'create'):
            self.created.append(args)
            self.labels.update(args[args.index('--label') + 1].split(','))
            return 'https://github.com/example/repo/issues/27\n'
        self.fail('llamada GitHub inesperada: %r' % (args,))

    def reconcile(self, it=None):
        return puente.apuntar_una_vez(it or issue(self.labels), EVENTO, 'cumplida',
                                     PENDIENTE, 'en-sheet')

    def test_lost_response_is_verified_without_repeating_append(self):
        self.lost_response = True
        self.assertTrue(self.reconcile())
        self.assertTrue(self.reconcile())
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.labels, {'en-sheet'})
        detail = json.loads(self.posts[0]['detalle'])
        self.assertEqual(detail['recibo_clave'], EVENTO + ':' + CID)

    def test_truncated_read_after_ambiguous_write_stays_pending_across_runs(self):
        self.lost_response = self.hide_receipts = True
        self.assertFalse(self.reconcile())
        self.assertFalse(self.reconcile())
        self.assertEqual(len(self.posts), 1)
        self.assertIn(PENDIENTE, self.labels)
        self.hide_receipts = False
        self.assertTrue(self.reconcile())
        self.assertEqual(len(self.posts), 1)

    def test_label_failure_after_append_is_recovered_by_read_not_post(self):
        self.label_failure = True
        with self.assertRaises(RuntimeError):
            self.reconcile()
        self.assertIn(PENDIENTE, self.labels)
        self.label_failure = False
        self.assertTrue(self.reconcile())
        self.assertEqual(len(self.posts), 1)

    def test_missing_read_never_becomes_permission_to_append(self):
        self.reader_error = True
        self.assertFalse(self.reconcile())
        self.assertFalse(self.labels)
        self.assertFalse(self.posts)

    def test_cached_or_malformed_read_cannot_authorize_append(self):
        for result in ({'produccion': [], 'cache': True}, {'ok': False},
                       {'produccion': None}, []):
            with patch.object(sala, 'get', return_value=result):
                self.assertFalse(self.reconcile())
        self.assertFalse(self.posts)
        self.assertFalse(self.labels)

    def test_existing_legacy_receipt_is_reconciled_without_post(self):
        self.rows.append(row())
        self.assertTrue(self.reconcile())
        self.assertEqual(self.labels, {'en-sheet'})
        self.assertFalse(self.posts)

    def test_receipt_requires_same_event_id_and_key(self):
        key = EVENTO + ':' + CID
        self.assertFalse(puente.tiene_recibo([row('ENCARGO TOMADO · chinche')], CID, EVENTO, key))
        self.assertFalse(puente.tiene_recibo([row(recibo_clave='otra')], CID, EVENTO, key))
        self.assertFalse(puente.tiene_recibo([row(id='CHN-20261014-2112-abcd')], CID, EVENTO, key))
        self.assertTrue(puente.tiene_recibo([row(recibo_clave=key)], CID, EVENTO, key))

    def test_not_planned_and_unknown_closure_never_look_fulfilled(self):
        for reason in ('NOT_PLANNED', None):
            it = issue(reason=reason)
            self.assertFalse(puente.completado(it))
            self.assertNotEqual(puente.estado_encargo(it), 'cumplida')
        self.assertEqual(puente.estado_encargo(issue()), 'cumplida')
        self.assertEqual(puente.estado_encargo(issue(state='OPEN')), 'en curso')

    def test_ideas_request_has_generic_stable_issue_and_is_only_solicited(self):
        with patch.object(puente, 'issues_con_etiqueta', return_value=[]):
            puente.ideas_solicitadas([row('ENCARGO · ideas', texto='contenido privado sintético')], False)
        self.assertEqual(self.dispatches, 1)
        self.assertEqual(len(self.created), 1)
        self.assertNotIn('contenido privado', self.created[0][self.created[0].index('--body') + 1])
        self.assertEqual(self.posts[0]['pieza'], 'ENCARGO SOLICITADO · ideas')
        self.assertEqual(self.posts[0]['estado'], 'solicitada')
        with patch.object(puente, 'issues_con_etiqueta', return_value=[issue(self.labels, 'OPEN')]):
            puente.ideas_solicitadas([], False)
        self.assertEqual(self.dispatches, 1)
        self.assertEqual(len(self.posts), 1)

    def test_ambiguous_dispatch_keeps_durable_marker_and_never_repeats(self):
        self.dispatch_failure = True
        first = issue((), 'OPEN')
        self.assertFalse(puente.solicitar_semillero(first))
        self.assertFalse(puente.solicitar_semillero(issue(self.labels, 'OPEN')))
        self.assertEqual(self.dispatches, 1)
        self.assertIn('semillero-por-confirmar', self.labels)
        self.assertFalse(self.posts)

    def test_old_ideas_fulfilled_row_only_accredits_previous_request(self):
        with patch.object(puente, 'issues_con_etiqueta', return_value=[]):
            puente.ideas_solicitadas([row('ENCARGO CUMPLIDO · ideas')], False)
        self.assertEqual(self.dispatches, 0)
        self.assertEqual(self.posts[0]['pieza'], 'ENCARGO SOLICITADO · ideas')
        self.assertEqual(self.posts[0]['estado'], 'solicitada')

    def test_simulation_does_not_create_or_dispatch_or_write(self):
        puente.ideas_solicitadas([row('ENCARGO · ideas')], True)
        self.assertFalse(self.created)
        self.assertEqual(self.dispatches, 0)
        self.assertFalse(self.posts)


if __name__ == '__main__':
    unittest.main()
