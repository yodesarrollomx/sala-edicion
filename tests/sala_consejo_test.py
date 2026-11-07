"""Roast Room (7-nov-2026): reglas del consejo sin red.

Lo que se prueba:
  · el veredicto: aprueba con el umbral, el veto de Alejandro virtual tumba la aprobación,
    con menos de cinco jueces se abstiene;
  · qué cartas juzga: nunca una lámina que un humano ya marcó ni una carta que ya firmó;
  · el contrato de producción: la marca humana manda sobre la del consejo en la misma lámina;
  · el candado de verificar.py: sólo sala_consejo.py decide y sólo con _clave_consejo().
"""
import ast
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import sala_consejo as consejo
import sala_produccion as prod

CANDADOS = [
    {'id': 'A01', 'de': 'Alejandro', 'candado': 'Nunca mencionar ciudades', 'tipo': 'veto', 'aplica': 'todo'},
    {'id': 'A05', 'de': 'Alejandro', 'candado': 'Todo empuja al PPP', 'tipo': 'criterio', 'aplica': 'todo'},
    {'id': 'S01', 'de': 'Sayri', 'candado': 'Lote urbano', 'tipo': 'veto', 'aplica': 'laminas'},
]


def votos(si_de, i=0, alejandro=None):
    out = {}
    for k, _, _ in consejo.JUECES:
        v = 'si' if k in si_de else 'no'
        out[k] = {i: {'voto': v, 'nota': 'cambia %s' % k if v == 'no' else '', 'candados': []}}
    if alejandro:
        out['alejandro'][i] = alejandro
    return out


class VeredictoTests(unittest.TestCase):
    def test_aprueba_con_cuatro_de_seis(self):
        r = consejo.veredicto(votos({'hormozi', 'chris_do', 'zuckerberg', 'alejandro'}), [0], CANDADOS, 4)
        self.assertEqual(r[0]['marca'], 'si')
        self.assertEqual(r[0]['nota'], '')

    def test_tres_de_seis_regresa_con_notas_ordenadas(self):
        r = consejo.veredicto(votos({'hormozi', 'chris_do', 'zuckerberg'}), [0], CANDADOS, 4)
        self.assertEqual(r[0]['marca'], 'no')
        self.assertTrue(r[0]['nota'].startswith('3 de 6 a favor'))
        self.assertIn('Alejandro virtual: cambia alejandro', r[0]['nota'])

    def test_veto_de_alejandro_tumba_cinco_a_favor(self):
        a = {'voto': 'no', 'nota': 'dice Hermosillo', 'candados': ['A01']}
        r = consejo.veredicto(votos({'hormozi', 'chris_do', 'zuckerberg', 'especialista', 'sayri'}, alejandro=a),
                              [0], CANDADOS, 4)
        self.assertEqual(r[0]['marca'], 'no')
        self.assertTrue(r[0]['veto'])
        self.assertIn('veto de Alejandro virtual', r[0]['nota'])

    def test_no_de_alejandro_sin_candado_de_veto_no_veta(self):
        a = {'voto': 'no', 'nota': 'podría empujar más al PPP', 'candados': ['A05']}
        r = consejo.veredicto(votos({'hormozi', 'chris_do', 'zuckerberg', 'especialista', 'sayri'}, alejandro=a),
                              [0], CANDADOS, 4)
        self.assertEqual(r[0]['marca'], 'si')

    def test_veto_de_sayri_virtual_no_es_veto_del_consejo(self):
        v = votos({'hormozi', 'chris_do', 'zuckerberg', 'especialista', 'alejandro'})
        v['sayri'][0] = {'voto': 'no', 'nota': 'se ve rural', 'candados': ['S01']}
        self.assertEqual(consejo.veredicto(v, [0], CANDADOS, 4)[0]['marca'], 'si')

    def test_con_menos_de_cinco_jueces_se_abstiene(self):
        v = votos({'hormozi', 'chris_do', 'zuckerberg', 'especialista'})
        for k in ('sayri', 'alejandro'):
            v.pop(k)
        self.assertIsNone(consejo.veredicto(v, [0], CANDADOS, 4))


def dia(firmas=None, laminas=None, tipo='laminas'):
    p = {'id': 'pieza-1', 'tipo': tipo, 'titulo': 'Pieza', 'laminas': ['laminas/x/L1.jpg', 'laminas/x/L2.jpg'],
         'opciones': [], 'video': None}
    dec = {}
    if firmas is not None:
        dec['pieza-1'] = {'laminas': laminas or [None, None], 'notas': ['', ''], 'firmas': firmas}
    return {'propuestas': [p], 'decisiones': {'propuestas': dec}}


class CartasTests(unittest.TestCase):
    def test_sin_decisiones_juzga_todas(self):
        c = consejo.cartas_pendientes(dia())
        self.assertEqual(c[0]['abiertas'], [0, 1])

    def test_lamina_marcada_por_un_humano_no_se_juzga(self):
        f = [[{'quien': 'Alejandro', 'marca': 'no', 'nota': 'x'}], []]
        c = consejo.cartas_pendientes(dia(f, ['no', None]))
        self.assertEqual(c[0]['abiertas'], [1])

    def test_carta_ya_firmada_por_el_consejo_no_se_repite(self):
        f = [[{'quien': 'Roast Room', 'marca': 'si', 'nota': ''}], []]
        self.assertEqual(consejo.cartas_pendientes(dia(f, ['si', None])), [])

    def test_tipos_desconocidos_quedan_para_los_humanos(self):
        self.assertEqual(consejo.cartas_pendientes(dia(tipo='guion')), [])


class MotoresTests(unittest.TestCase):
    def test_solo_motores_con_llave(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k-sol-123456', 'ANTHROPIC_API_KEY': ''}):
            self.assertEqual(consejo.motores_disponibles({'consejo_motores': 'sol,opus'}), ['sol'])
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k-sol-123456', 'ANTHROPIC_API_KEY': 'k-opus-123456'}):
            self.assertEqual(consejo.motores_disponibles({}), ['sol', 'opus'])

    def test_con_hermes_compiten_sol_y_opus_sin_llaves_de_api(self):
        env = {'HERMES_API_URL': 'http://127.0.0.1:8642', 'HERMES_API_KEY': 'k-hermes-123456',
               'OPENAI_API_KEY': '', 'ANTHROPIC_API_KEY': ''}
        with patch.dict(os.environ, env):
            self.assertEqual(consejo.motores_disponibles({'consejo_motores': 'sol,opus'}), ['sol', 'opus'])

    def test_hermes_recibe_proveedor_modelo_e_imagen(self):
        visto = {}

        def falso(url, cuerpo, cabeceras, quien):
            visto.update(url=url, cuerpo=cuerpo, cabeceras=cabeceras)
            return {'choices': [{'message': {'content': '{"piezas": [{"i": 0, "voto": "si", "candados": [], "nota": ""}]}'}}]}
        env = {'HERMES_API_URL': 'http://127.0.0.1:8642/', 'HERMES_API_KEY': 'k-hermes-123456'}
        with patch.dict(os.environ, env), patch.object(consejo, '_post', side_effect=falso):
            r = consejo.llamar('opus', 'claude-opus-5-5', 'sistema', 'texto', [('Lámina 0', b'\xff\xd8\xffdatos')], {})
        self.assertEqual(r['piezas'][0]['voto'], 'si')
        self.assertEqual(visto['url'], 'http://127.0.0.1:8642/v1/chat/completions')
        self.assertEqual(visto['cuerpo']['provider'], 'anthropic')
        self.assertEqual(visto['cuerpo']['model'], 'claude-opus-5-5')
        partes = visto['cuerpo']['messages'][1]['content']
        self.assertTrue(any(p.get('type') == 'image_url' and p['image_url']['url'].startswith('data:image/jpeg;base64,')
                            for p in partes))
        self.assertEqual(visto['cabeceras']['Authorization'], 'Bearer k-hermes-123456')

    def test_apagado_no_lee_la_mesa(self):
        with patch.object(consejo, 'leer_reglas', return_value={'consejo_activo': '0'}), \
                patch.object(consejo.sala, 'get', side_effect=AssertionError('no debe leer la mesa')):
            self.assertEqual(consejo.corrida(), 0)


def contrato(group, mark):
    """Una lámina con sus firmas, armada como la entrega el GAS."""
    notas = [s for s in group if s['nota']]
    nota = notas[0]['nota'] if len(notas) == 1 else ' | '.join(s['quien'] + ': ' + s['nota'] for s in notas)
    d = {'laminas': [mark], 'nota': '', 'firmas_nota': [], 'notas': [nota], 'firmas': [group]}
    return {'ok': True, 'contrato': prod.CONTRATO_PRODUCCION, 'version': prod.VERSION_PRODUCCION,
            'alcance': 'historial_completo', 'fecha': '2026-11-07', 'dias': ['2026-11-07'],
            'propuestas': [{'id': 'sintetica', 'fecha_fuente': '2026-11-07', 'estado': 'en revisión',
                            'tipo': 'laminas', 'titulo': 'Sintética', 'video': None,
                            'origen': None, 'laminas': ['imagen.jpg'], 'opciones': []}],
            'decisiones': {'propuestas': {'sintetica': d}, 'editores': ['Alejandro', 'Roast Room'],
                           'guardado': '2026-11-07T19:00:00.000Z'},
            'fuentes': {'leidas': 1, 'activas': 1, 'retiradas': 0, 'decisiones_leidas': 3}}


def firma(rol, quien, marca, nota=''):
    return {'rol': rol, 'quien': quien, 'marca': marca, 'nota': nota, 'guardado': '2026-11-07T18:00:00.000Z'}


class ContratoTests(unittest.TestCase):
    def cargar(self, valor):
        return prod.cargar(lambda *a, **k: copy.deepcopy(valor), lambda *a, **k: None, historica=True)

    def test_si_del_consejo_sin_humanos_aprueba(self):
        got = self.cargar(contrato([firma('consejo', 'Roast Room', 'si')], 'si'))
        self.assertEqual(got['_produccion']['si'], 1)

    def test_no_humano_manda_sobre_si_del_consejo(self):
        g = [firma('consejo', 'Roast Room', 'si'), firma('editor', 'Alejandro', 'no', 'no va')]
        self.cargar(contrato(g, 'no'))
        with self.assertRaises(Exception):
            self.cargar(contrato(g, 'si'))

    def test_si_humano_manda_sobre_no_del_consejo(self):
        g = [firma('consejo', 'Roast Room', 'no', '2 de 6 a favor'), firma('editor2', 'Sayri', 'si')]
        self.cargar(contrato(g, 'si'))
        with self.assertRaises(Exception):
            self.cargar(contrato(g, 'no'))

    def test_tres_firmas_caben(self):
        g = [firma('consejo', 'Roast Room', 'si'), firma('editor', 'Alejandro', 'si'), firma('editor2', 'Sayri', 'no', 'x')]
        self.cargar(contrato(g, 'no'))

    def test_rol_desconocido_sigue_bloqueado(self):
        with self.assertRaises(Exception):
            self.cargar(contrato([firma('agente', 'Bot', 'si')], 'si'))


class CandadoVerificarTests(unittest.TestCase):
    def test_el_decidir_del_consejo_usa_su_llave(self):
        arbol = ast.parse((ROOT / 'nube' / 'sala_consejo.py').read_text(encoding='utf-8'))
        sobres = [n for n in ast.walk(arbol) if isinstance(n, ast.Dict) and any(
            isinstance(k, ast.Constant) and k.value == 'accion' and isinstance(v, ast.Constant) and v.value == 'decidir'
            for k, v in zip(n.keys, n.values))]
        self.assertEqual(len(sobres), 1)
        clave = [v for k, v in zip(sobres[0].keys, sobres[0].values) if isinstance(k, ast.Constant) and k.value == 'clave']
        self.assertEqual(clave[0].func.id, '_clave_consejo')

    def test_ningun_otro_archivo_decide(self):
        for p in (ROOT / 'nube').glob('*.py'):
            if p.name in ('sala_consejo.py', 'verificar.py', 'sala_cliente.py'):
                continue
            self.assertNotIn("'accion': 'decidir'", p.read_text(encoding='utf-8'), p.name)


if __name__ == '__main__':
    unittest.main()
