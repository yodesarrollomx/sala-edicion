import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import sala_cliente as sala
import sala_produccion as prod
READ_GET = sala.get


def fixture():
    d = {'laminas': ['si'], 'nota': '', 'firmas_nota': [], 'notas': ['Elección sintética'], 'firmas': [[{
        'rol': 'editor', 'quien': 'Uno', 'marca': 'si', 'nota': 'Elección sintética',
        'guardado': '2026-08-01T19:00:00.000Z'}]]}
    return {'ok': True, 'contrato': prod.CONTRATO_PRODUCCION, 'version': prod.VERSION_PRODUCCION,
        'alcance': 'historial_completo', 'fecha': '2026-10-15', 'dias': ['2026-08-01'],
        'propuestas': [{'id': 'sintetica', 'fecha_fuente': '2026-08-01', 'estado': 'en revisión',
                        'tipo': 'laminas', 'titulo': 'Sintética', 'video': None,
                        'origen': None, 'laminas': ['imagen.jpg'], 'opciones': []}],
        'decisiones': {'propuestas': {'sintetica': d}, 'editores': ['Uno'],
                       'guardado': '2026-08-01T19:00:00.000Z'},
        'fuentes': {'leidas': 2, 'activas': 1, 'retiradas': 1, 'decisiones_leidas': 3}}


def legacy():
    return {'version': 'dos-compuertas-2026-09-12', 'fecha': '2026-10-15', 'dias': [],
            'propuestas': [], 'decisiones': {'propuestas': {}}}


class HistoricalProductionTests(unittest.TestCase):
    def setUp(self):
        # Estas pruebas no pueden usar credenciales ni destinos externos, incluso
        # si un helper importado cambia accidentalmente su comportamiento.
        for target in ('urllib.request.urlopen', 'requests.sessions.Session.request', 'sala_cliente.get'):
            guard = patch(target, side_effect=AssertionError('red prohibida en fixtures sintéticas'))
            guard.start(); self.addCleanup(guard.stop)

    def test_canonical_get_is_fresh_exact_and_does_not_consult_local_tira_or_legacy(self):
        getter, local = Mock(return_value=fixture()), Mock(side_effect=AssertionError('sin fallback local'))
        before = fixture()
        with patch.object(sala, 'post', side_effect=AssertionError('ninguna escritura')):
            got = prod.cargar(getter, local, historica=True)
        getter.assert_called_once_with('produccion', fresco='1')
        local.assert_not_called()
        self.assertEqual(got['propuestas'], before['propuestas'])
        self.assertEqual(got['_produccion']['cuenta_historial'], 'exacta')
        self.assertEqual(got['_produccion']['si'], 1)
        self.assertEqual(got['_produccion']['fuentes_no_vigentes'], 1)

    def test_rollout_is_off_until_backend_verified_and_empty_legacy_is_not_history_zero(self):
        getter = Mock(return_value=legacy())
        with patch.dict(os.environ, {'SALA_PRODUCCION_HISTORICA': '0'}):
            got = prod.cargar(getter)
        getter.assert_called_once_with('dia', fresco='1')
        self.assertEqual(got['_produccion']['alcance'], 'legacy_ventana_limitada')
        self.assertEqual(got['_produccion']['cuenta_historial'], 'no_confirmada')
        self.assertIsNone(got['_produccion']['fuentes_no_vigentes'])

    def test_recognized_legacy_ignoring_new_resource_declares_its_scope(self):
        getter = Mock(return_value=legacy())
        got = prod.cargar(getter, historica=True)
        getter.assert_called_once_with('produccion', fresco='1')
        self.assertEqual(got['_produccion']['motivo_legacy'], 'gas_legacy_reconocido')
        self.assertEqual(got['_produccion']['cuenta_historial'], 'no_confirmada')

    def test_only_explicit_resource_unavailable_allows_fallback(self):
        getter = Mock(side_effect=[sala.SalaError('constante', codigo='sala_recurso_no_disponible'), legacy()])
        got = prod.cargar(getter, historica=True)
        self.assertEqual([c.args[0] for c in getter.call_args_list], ['produccion', 'dia'])
        self.assertEqual(got['_produccion']['motivo_legacy'], 'recurso_no_disponible')
        for code in ('sala_clave_rechazada', 'sala_permiso_rechazado', 'sala_tiempo_agotado',
                     'sala_red_sin_confirmar', 'sala_contrato_lectura', 'sala_http_404'):
            getter = Mock(side_effect=sala.SalaError('privado no se imprime', codigo=code))
            with self.subTest(code=code), self.assertRaises(sala.SalaError):
                prod.cargar(getter, historica=True)
            self.assertEqual(getter.call_count, 1)

    def test_unknown_or_partial_contract_never_falls_back_to_old_approval(self):
        variants = [{}, legacy(), fixture(), fixture(), fixture()]
        variants[1]['version'] = 'desconocida'
        variants[2]['contrato'] = 'v2'
        variants[3]['ok'] = False
        variants[4]['alcance'] = 'limitado'
        for value in variants:
            getter = Mock(return_value=value)
            with self.subTest(keys=list(value)), self.assertRaises(sala.SalaError):
                prod.cargar(getter, historica=True)
            self.assertEqual(getter.call_count, 1)

    def test_ids_duplicates_retired_sources_dates_and_counts_are_validated(self):
        edits = [lambda x: x['propuestas'][0].update(id='../otra'),
                 lambda x: x['propuestas'].append(copy.deepcopy(x['propuestas'][0])),
                 lambda x: x['propuestas'][0].update(estado='retirada'),
                 lambda x: x['propuestas'][0].update(origen='retirada explícita'),
                 lambda x: x['propuestas'][0].update(fecha_fuente='2026-02-30'),
                 lambda x: x['propuestas'][0].update(fecha_fuente='2027-01-01'),
                 lambda x: x['fuentes'].update(activas=True),
                 lambda x: x['fuentes'].update(leidas=0)]
        for edit in edits:
            value = fixture(); edit(value)
            with self.subTest(edit=edit), self.assertRaises(sala.SalaError): prod.validar_historica(value)

    def test_forged_unsigned_approval_or_missing_other_editor_veto_fails(self):
        for mode in ('unsigned', 'veto', 'duplicate_role'):
            value = fixture(); d = value['decisiones']['propuestas']['sintetica']
            if mode == 'unsigned': d['firmas'][0] = []
            elif mode == 'veto': d['firmas'][0][0]['marca'] = 'no'
            else: d['firmas'][0].append(copy.deepcopy(d['firmas'][0][0]))
            with self.subTest(mode=mode), self.assertRaises(sala.SalaError): prod.validar_historica(value)

    def test_forged_lamina_or_proposal_notes_cannot_select_another_take(self):
        for mode in ('lamina', 'propuesta'):
            value = fixture(); d = value['decisiones']['propuestas']['sintetica']
            if mode == 'lamina': d['notas'][0] = '[toma elegida: 2]'
            else: d['nota'] = '[toma elegida: 2]'
            with self.subTest(mode=mode), self.assertRaises(sala.SalaError): prod.validar_historica(value)

    def test_true_guardado_must_be_utc_valid_and_not_after_reported_latest(self):
        for value in ('sin-fecha', '2026-02-30T12:00:00Z', '2026-08-01T19:00:00', '2026-08-02T19:00:00Z'):
            obj = fixture(); obj['decisiones']['propuestas']['sintetica']['firmas'][0][0]['guardado'] = value
            with self.subTest(value=value), self.assertRaises(sala.SalaError): prod.validar_historica(obj)

    def test_clear_with_signed_null_is_preserved_for_resolver(self):
        value = fixture(); d = value['decisiones']['propuestas']['sintetica']
        d['laminas'] = [None]; d['firmas'][0][0]['marca'] = None
        got = prod.cargar(Mock(return_value=value), historica=True)
        t = {'laminas': [{'n': 1, 'estado': 'aprobada'}], 'mapa': {'1': 1}}
        result = prod.resolver_tira(t, got['decisiones']['propuestas']['sintetica'])
        self.assertEqual(result['laminas'][0]['estado'], 'pendiente')

    def test_two_editors_choose_different_takes_is_truthful_but_cannot_approve_an_arbitrary_take(self):
        value = fixture(); d = value['decisiones']['propuestas']['sintetica']
        d['firmas'][0][0]['nota'] = '[toma elegida: 1]'
        second = copy.deepcopy(d['firmas'][0][0]); second.update(rol='editor2', quien='Dos', nota='[toma elegida: 2]')
        d['firmas'][0].append(second)
        d['notas'][0] = 'Uno: [toma elegida: 1] | Dos: [toma elegida: 2]'
        value['decisiones']['editores'].append('Dos')
        got = prod.cargar(Mock(return_value=value), historica=True)
        t = {'laminas': [{'n': 1, 'estado': 'pendiente', 'candidatas': [{'src': 'uno.jpg'}, {'src': 'dos.jpg'}]}]}
        with self.assertRaisesRegex(sala.SalaError, 'contradictorias'):
            prod.resolver_tira(t, got['decisiones']['propuestas']['sintetica'])

    def test_counts_only_include_marks_from_active_exact_sources(self):
        value = fixture()
        value['decisiones']['propuestas']['retirada'] = copy.deepcopy(value['decisiones']['propuestas']['sintetica'])
        got = prod.cargar(Mock(return_value=value), historica=True)
        self.assertEqual(got['_produccion']['si'], 1)
        self.assertEqual(got['_produccion']['decisiones_sin_fuente_activa'], 1)

    def test_response_limit_and_invalid_rollout_flag_close(self):
        value = fixture(); value['relleno'] = 'a' * (4 * 1024 * 1024)
        with self.assertRaises(sala.SalaError): prod.validar_historica(value)
        with patch.dict(os.environ, {'SALA_PRODUCCION_HISTORICA': 'auto'}), self.assertRaises(sala.SalaError):
            prod.cargar(Mock())

    def test_actual_gas_synthetic_wire_contract_is_accepted_by_python(self):
        script = """const fs=require('fs'),vm=require('vm');const c=vm.createContext({});
vm.runInContext(fs.readFileSync('gas/Code.gs','utf8'),c);c.leerConfig=()=>'';
const pr=[{prop_id:'sintetica',fecha:'2026-08-01',laminas_json:'[\"a.jpg\"]',opciones_json:'[]'}];
const de=[{prop_id:'sintetica',fecha:'2026-08-01',guardado:'2026-08-01T12:00:00-07:00',quien:'editor',lamina:0,marca:'si'}];
de.push({prop_id:'sintetica',fecha:'2026-08-01',guardado:'2026-08-01T12:00:00-07:00',quien:'editor',lamina:'',marca:'',nota_propuesta:'[toma elegida: 2]'});
process.stdout.write(JSON.stringify(c.produccionHistorica_('2026-10-15',pr,de)));"""
        run = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(prod.validar_historica(json.loads(run.stdout))['decisiones']['propuestas']['sintetica']['laminas'], ['si'])

    def test_shared_client_sends_existing_key_and_validates_production_shape_without_network(self):
        with patch.dict(os.environ, {'SALA_GAS_EXEC': 'https://example.invalid/exec', 'SALA_CLAVE_AGENTE': 'sintetica'}), \
             patch.object(sala, '_pedir', return_value=fixture()) as request:
            READ_GET('produccion', fresco='1')
        from urllib.parse import parse_qs, urlsplit
        query = parse_qs(urlsplit(request.call_args.args[0]).query)
        self.assertEqual(query, {'recurso': ['produccion'], 'clave': ['sintetica'], 'fresco': ['1']})
        sala._validar_lectura('produccion', fixture())
        with self.assertRaises(sala.SalaError): sala._validar_lectura('produccion', {'ok': True})


if __name__ == '__main__': unittest.main()
