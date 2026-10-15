"""Diagnóstico agregado de selección: fuentes sintéticas, sin APIs ni contenido real."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
import sala_mesa as mesa
import sala_cliente as sala


class SelectionCountsTests(unittest.TestCase):
    def run_mesa(self, sources, props, published=(), selected=None, opened=None):
        """Usa los filtros reales y falla si un caso sin trabajo llama al motor."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / 'datos' / 'tiras'
            folder.mkdir(parents=True)
            for slug, pid, name in sources:
                value = {'pieza': name, 'pieza_slug': slug, 'fecha': '2026-10-14',
                         'laminas': [{'n': 1, 'src': 'laminas/sintetica.png',
                                      'dice': 'Texto reservado sintético', 'estado': 'aprobada'}]}
                (folder / (pid + '.json')).write_text(json.dumps(value))
            args = ['mesa', '--producir'] + (['--pieza', selected] if selected else [])
            dia = {'fecha': '2026-10-14', 'propuestas': copy.deepcopy(props),
                   'decisiones': {'propuestas': {}}}
            with patch.object(sys, 'argv', args), patch.object(mesa, 'RAIZ', root), \
                 patch.object(mesa, 'TIRAS', folder), patch.object(mesa, 'PLAN', root / 'plan.json'), \
                 patch.object(mesa, 'contexto_produccion', return_value=dia), \
                 patch.object(mesa, 'publicadas', return_value=set(published)), \
                 patch.object(mesa, 'abiertas', return_value=opened or []) as open_call, \
                 patch.object(mesa, 'producir_tomas', side_effect=AssertionError('no debe generar')) as motor, \
                 patch.object(mesa.produccion, 'peticiones_abiertas', return_value=False), \
                 patch.object(sala, 'post') as post, patch.object(sala, 'avisar') as logs, \
                 patch.object(sala, 'get', side_effect=lambda r, **kw: {'reglas': {}} if r == 'reglas' else {'cola': []}):
                code = mesa.main()
            report = json.loads((root / 'datos' / 'mesa-estado.json').read_text())
            plan = json.loads((root / 'plan.json').read_text())
            public_logs = [c.args for c in logs.call_args_list
                           if c.args and c.args[0] in ('selección Mesa:', 'estado Mesa:')]
            return code, report, plan, open_call.call_count, motor.call_count, post.call_count, public_logs

    def test_zero_selected_explains_other_live_types_and_stale_local_tiras(self):
        sources = [('privado-a', 'privado-a-20261014', 'Cliente reservado A'),
                   ('privado-b', 'privado-b-20261014', 'Cliente reservado B')]
        props = [{'id': 'eje-privado', 'tipo': 'eje', 'titulo': 'Título privado', 'laminas': []},
                 {'id': 'otro-privado', 'tipo': 'categoría confidencial', 'nota': 'Nota privada'}]
        code, report, plan, opens, motors, posts, logs = self.run_mesa(sources, props)
        counts = report['seleccion']
        self.assertEqual(code, 0)
        self.assertEqual(counts['propuestas_vivas'], 2)
        self.assertEqual(counts['propuestas_por_tipo']['eje'], 1)
        self.assertEqual(counts['propuestas_por_tipo']['otros'], 1)
        self.assertEqual(counts['propuestas_con_laminas'], 0)
        self.assertEqual(counts['tiras_locales'], 2)
        self.assertEqual(counts['tiras_vigentes'], 0)
        self.assertEqual(counts['tiras_sin_fuente_vigente'], 2)
        self.assertEqual(counts['tiras_preparadas'], 0)
        self.assertEqual((opens, motors, posts), (0, 0, 0))
        self.assertEqual(plan['cartas'], [])
        self.assertEqual(report['laminas_preparadas'], 0)
        self.assertEqual(report['tomas_obtenidas'], 0)
        exposed = json.dumps([report, logs], ensure_ascii=False)
        for private in ('privado-a', 'privado-b', 'eje-privado', 'Cliente reservado',
                        'Título privado', 'categoría confidencial', 'Nota privada', 'Texto reservado'):
            self.assertNotIn(private, exposed)

    def test_zero_work_distinguishes_published_from_no_open_slides(self):
        sources = [('a', 'a-20261014', 'Reservado A'), ('b', 'b-20261014', 'Reservado B'),
                   ('c', 'c-20261014', 'Reservado C')]
        props = [{'id': pid, 'tipo': 'laminas', 'laminas': ['laminas/sintetica.png']}
                 for _, pid, _ in sources[:2]]
        code, report, plan, opens, motors, posts, _ = self.run_mesa(sources, props, ['reservado a'])
        counts = report['seleccion']
        self.assertEqual(code, 0)
        self.assertEqual(counts['propuestas_por_tipo']['laminas'], 2)
        self.assertEqual(counts['tiras_vigentes'], 2)
        self.assertEqual(counts['tiras_sin_fuente_vigente'], 1)
        self.assertEqual(counts['tiras_excluidas_publicadas'], 1)
        self.assertEqual(counts['tiras_sin_laminas_abiertas'], 1)
        self.assertEqual(counts['tiras_con_laminas_abiertas'], 0)
        self.assertEqual(counts['tiras_preparadas'], len(plan['cartas']))
        self.assertEqual((opens, motors, posts), (1, 0, 0))

    def test_piece_filter_is_counted_without_producing_other_pieces(self):
        sources = [('a', 'a-20261014', 'Reservado A'), ('b', 'b-20261014', 'Reservado B')]
        props = [{'id': pid, 'tipo': 'laminas', 'laminas': ['laminas/sintetica.png']}
                 for _, pid, _ in sources]
        code, report, _, opens, motors, posts, _ = self.run_mesa(sources, props, selected='b')
        counts = report['seleccion']
        self.assertEqual(code, 0)
        self.assertEqual(counts['tiras_fuera_filtro_pieza'], 1)
        self.assertEqual(counts['tiras_sin_laminas_abiertas'], 1)
        self.assertEqual((opens, motors, posts), (1, 0, 0))

    def test_replaced_source_is_counted_without_changing_inputs(self):
        before = {'pieza': ('huérfana-privada', {'nota': 'Reservado'})}
        active = {'pieza': ('montada-privada', {'nota': 'Otra nota'})}
        dia = {'propuestas': [{'id': 'montada-privada', 'tipo': 'laminas', 'laminas': ['privada.png']}]}
        original = copy.deepcopy((dia, before, active))
        counts = mesa.conteos_seleccion(dia, before, active, recuperadas=1)
        self.assertEqual(counts['fuentes_recuperadas'], 1)
        self.assertEqual(counts['tiras_con_fuente_reemplazada'], 1)
        self.assertEqual(counts['tiras_sin_fuente_vigente'], 0)
        self.assertEqual((dia, before, active), original)
        for private in ('huérfana', 'montada', 'privada.png', 'Reservado', 'Otra nota'):
            self.assertNotIn(private, json.dumps(counts))

    def test_report_whitelist_rejects_text_inside_counter_fields_and_unknown_keys(self):
        hostile = {'fuente': 'URL privada', 'propuestas_vivas': 'Nombre privado',
                   'tiras_vigentes': -1, 'laminas_abiertas': True,
                   'id': 'identidad reservada', 'titulo': 'Título reservado',
                   'propuestas_por_tipo': {'eje': 2, 'tipo reservado': 9, 'laminas': 'Nota privada'}}
        with tempfile.TemporaryDirectory() as td, patch.object(mesa, 'RAIZ', Path(td)), \
             patch.object(sala, 'avisar') as logs:
            mesa.guardar_estado_mesa(0, 0, 0, 0, seleccion=hostile)
            report = json.loads((Path(td) / 'datos' / 'mesa-estado.json').read_text())
        counts = report['seleccion']
        self.assertEqual(counts['fuente'], 'sin_confirmar')
        self.assertEqual(counts['propuestas_por_tipo']['eje'], 2)
        self.assertEqual(counts['propuestas_vivas'], 0)
        self.assertEqual(counts['laminas_abiertas'], 0)
        exposed = json.dumps([report, [c.args for c in logs.call_args_list]], ensure_ascii=False)
        for private in ('URL privada', 'Nombre privado', 'tipo reservado', 'Nota privada',
                        'identidad reservada', 'Título reservado'):
            self.assertNotIn(private, exposed)

    def test_local_test_source_does_not_claim_backend_has_zero_live_proposals(self):
        counts = mesa.conteos_seleccion({}, {}, {}, sin_sheet=True)
        self.assertEqual(counts['fuente'], 'sin_sheet')

    def test_open_slides_still_produce_the_same_limited_wave(self):
        from sala_produccion_test import MesaIntegrationTests, P, tira, yes
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / 'datos' / 'tiras'
            folder.mkdir(parents=True)
            (folder / (P + '.json')).write_text(json.dumps(tira()))
            _, generated = MesaIntegrationTests().run_wave(root, P, tira(), yes(), cap=1, variants=2)
            report = json.loads((root / 'datos' / 'mesa-estado.json').read_text())
        counts = report['seleccion']
        self.assertEqual(counts['propuestas_vivas'], 1)
        self.assertEqual(counts['tiras_vigentes'], 1)
        self.assertEqual(counts['tiras_con_laminas_abiertas'], 1)
        self.assertEqual(counts['laminas_abiertas'], 2)
        self.assertEqual(counts['tiras_preparadas'], 1)
        self.assertEqual((report['generadas'], report['limite_pendiente']), (1, 1))
        self.assertEqual(report['laminas_preparadas'], 1)
        self.assertEqual(report['tomas_obtenidas'], 2)
        self.assertEqual(report['tiras_reutilizadas'], 0)
        self.assertEqual(generated['decidir'], [2])
        self.assertEqual(generated['laminas'][0]['estado'], 'aprobada')


if __name__ == '__main__':
    unittest.main()
