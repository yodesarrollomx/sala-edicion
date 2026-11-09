"""Consejo de nube (9-nov-2026, Sala corta): la tarea programada juzga, Actions valida y firma.

Lo que se prueba, sin red:
  · el expediente lleva lo que el jurado necesita (cartas, tomas, guion, candados), no decide
    nada, no lleva llaves y deja fuera los cortes de video;
  · aplicar convierte votos en decisiones con la MISMA regla de siempre (`veredicto`) y sólo
    sobre cartas que siguen pendientes y son las que el jurado vio (sello);
  · un «sí» sobre una lámina con tomas siempre dice cuál: el contrato de producción lo exige;
  · los votos son dato: un candado inventado no veta, un id raro no llega al registro público
    y las notas nunca se imprimen;
  · el workflow pasa los votos por variable de entorno, nunca dentro del guion.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import sala_cliente as sala
import sala_consejo as consejo
import sala_produccion as prod

PID = 'servilleta-nube-2026-11-09-abc123'
CANDADOS = [
    {'id': 'A01', 'de': 'Alejandro', 'candado': 'Nunca mencionar ciudades', 'tipo': 'veto', 'aplica': 'todo'},
    {'id': 'A05', 'de': 'Alejandro', 'candado': 'Todo empuja al PPP', 'tipo': 'criterio', 'aplica': 'todo'},
    {'id': 'S01', 'de': 'Sayri', 'candado': 'Lote urbano', 'tipo': 'veto', 'aplica': 'laminas'},
]
REGLAS = {'consejo_activo': '1', 'consejo_motores': 'claude', 'consejo_aprobar_con': '4', 'drive_raiz': 'RAIZ'}
NOTA_SECRETA = 'la mesa se ve vacía y el texto no engancha'


def tira():
    def toma(n, k):
        return {'src': 'laminas/x/L%d-%d.jpg' % (n, k), 'original': 'laminas/x/L%d-%d.png' % (n, k),
                'titulo': 'AB'[k - 1], 'texto': 'por qué %d' % k, 'dice': 'Texto %d toma %d' % (n, k),
                'motor': 'cloudflare', 'huella': 'h%d%d' % (n, k)}
    return {'pieza': 'La servilleta', 'pieza_slug': 'servilleta', 'promesa': 'Se calcula, no se opina',
            'formato': 'Carrusel', 'decidir': [2, 3], 'mapa': {'1': 2, '2': 3}, 'guion': '',
            'laminas': [
                {'n': 1, 'src': 'laminas/x/L1.png', 'dice': 'Uno', 'estado': 'aprobada'},
                {'n': 2, 'src': 'laminas/v/L2.png', 'dice': 'Dos', 'estado': 'rehecha',
                 'nota_previa': 'Más luminosa', 'candidatas': [toma(2, 1), toma(2, 2)]},
                {'n': 3, 'src': 'laminas/v/L3.png', 'dice': 'Tres', 'estado': 'rehecha',
                 'candidatas': [toma(3, 1), toma(3, 2)]}]}


def carta_laminas(pid=PID):
    return {'id': pid, 'tipo': 'laminas', 'titulo': 'La servilleta · rehechas', 'origen': 'rehecha-de x',
            'laminas': ['laminas/x/L2-1.jpg', 'laminas/x/L3-1.jpg'], 'opciones': [], 'video': None}


def dia(extra=None, decisiones=None):
    return {'propuestas': [carta_laminas()] + list(extra or []),
            'decisiones': {'propuestas': decisiones or {}}}


def votos(si_de, posiciones=(0, 1), alejandro=None):
    out = {}
    for k, _, _ in consejo.JUECES:
        v = 'si' if k in si_de else 'no'
        out[k] = [{'i': i, 'voto': v, 'candados': [], 'nota': '' if v == 'si' else '%s (%s)' % (NOTA_SECRETA, k)}
                  for i in posiciones]
    if alejandro:
        out['alejandro'] = [dict(alejandro, i=i) for i in posiciones]
    return out


TODOS = {k for k, _, _ in consejo.JUECES}


class Escenario:
    """La mesa, la tira y los candados de mentira, y lo que el consejo intentó mandar."""

    def __init__(self, reglas=None, el_dia=None, tiras=None):
        self.reglas = dict(REGLAS if reglas is None else reglas)
        self.dia = dia() if el_dia is None else el_dia
        self.tiras = {PID: tira()} if tiras is None else tiras
        self.decisiones, self.filas, self.lecturas, self.subidas = [], [], [], []

    def __enter__(self):
        drive = types.ModuleType('sala_drive')
        drive.DriveError = type('DriveError', (RuntimeError,), {})
        drive.ruta_carpetas = lambda raiz, *nombres: '/'.join((raiz,) + nombres)

        def subir(ruta, carpeta, nombre=None):
            self.subidas.append((carpeta, nombre, Path(ruta).read_bytes()))
            return 'archivo-1'
        drive.subir = subir

        def get(recurso, **kw):
            self.lecturas.append(recurso)
            return copy.deepcopy(self.dia)
        self.pila = contextlib.ExitStack()
        for parche in (
                patch.dict(sys.modules, {'sala_drive': drive}),
                patch.dict(os.environ, {'SALA_CLAVE_CONSEJO': 'llave-de-prueba-123456', 'GITHUB_RUN_ID': '777'}),
                patch.object(consejo, 'leer_reglas', lambda: dict(self.reglas)),
                patch.object(consejo, 'leer_candados', lambda: self.lecturas.append('candados') or list(CANDADOS)),
                patch.object(consejo, '_tira', lambda pid: copy.deepcopy(self.tiras.get(str(pid)))),
                patch.object(consejo, '_url_imagen', lambda ruta: 'https://medios.test/' + str(ruta)),
                patch.object(consejo, 'enviar_decision',
                             lambda fecha, envio, props: self.decisiones.append((fecha, envio, props)) or {'ok': True}),
                patch.object(consejo, 'registrar', lambda filas: self.filas.extend(filas)),
                patch.object(sala, 'get', get),
                patch.object(sala, 'hoy_hermosillo', lambda: '2026-11-09'),
                patch.object(sala, 'enmascarar_en_actions', lambda: None)):
            self.pila.enter_context(parche)
        self.salida = io.StringIO()
        self.pila.enter_context(contextlib.redirect_stdout(self.salida))
        return self

    def __exit__(self, *exc):
        self.pila.close()

    def expediente(self):
        self.codigo = consejo.expediente()
        return json.loads(self.subidas[-1][2].decode('ascii'))

    def sello(self, pid=PID):
        carta = next(c for c in consejo.cartas_pendientes(self.dia) if c['p']['id'] == pid)
        return consejo.sello_de_carta(carta, self.tiras.get(pid))

    def aplicar(self, cartas, ensayo=False, **extra):
        cuerpo = dict({'esquema': 1, 'motor': 'claude', 'modelo': 'claude-fable-5-2', 'cartas': cartas}, **extra)
        return consejo.aplicar(json.dumps(cuerpo, ensure_ascii=False), ensayo=ensayo)


class ExpedienteTests(unittest.TestCase):
    def test_lleva_cartas_tomas_y_candados_y_no_decide(self):
        with Escenario() as e:
            doc = e.expediente()
        self.assertEqual(e.codigo, 0)
        self.assertEqual(e.decisiones, [])
        self.assertEqual((e.subidas[0][0], e.subidas[0][1]), ('RAIZ/_consejo', 'expediente.txt'))
        self.assertTrue(doc['activo'])
        self.assertEqual(doc['corrida'], '777')
        self.assertEqual([c['id'] for c in doc['candados']], ['A01', 'A05', 'S01'])
        self.assertEqual([j['juez'] for j in doc['jueces']], [k for k, _, _ in consejo.JUECES])
        carta = doc['cartas'][0]
        self.assertEqual((carta['id'], carta['abiertas'], carta['promesa']), (PID, [0, 1], 'Se calcula, no se opina'))
        self.assertEqual([p['n'] for p in carta['piezas']], [2, 3])
        self.assertEqual(carta['piezas'][0]['nota_previa'], 'Más luminosa')
        self.assertEqual([(t['toma'], t['url'], t['dice']) for t in carta['piezas'][0]['tomas']],
                         [(1, 'https://medios.test/laminas/x/L2-1.jpg', 'Texto 2 toma 1'),
                          (2, 'https://medios.test/laminas/x/L2-2.jpg', 'Texto 2 toma 2')])
        self.assertEqual([s['estado'] for s in carta['serie']], ['aprobada', 'rehecha', 'rehecha'])
        self.assertRegex(carta['sello'], r'^[0-9a-f]{12}$')

    def test_no_lleva_llaves_y_es_ascii(self):
        with Escenario() as e:
            e.expediente()
        crudo = e.subidas[0][2]
        crudo.decode('ascii')
        self.assertNotIn(b'llave-de-prueba', crudo)
        self.assertNotIn(b'"clave"', crudo)

    def test_los_cortes_de_video_y_lo_que_pasa_del_tope_quedan_omitidos(self):
        corte = {'id': 'corte-1', 'tipo': 'eje', 'titulo': 'Corte', 'laminas': [],
                 'opciones': [{'titulo': 'Corte final'}], 'video': 'https://drive.google.com/file/d/abcdefghijkl/view'}
        otra = carta_laminas('otra-nube-2026-11-09-ffffff')
        with Escenario(reglas=dict(REGLAS, consejo_nube_cartas='1'), el_dia=dia([corte, otra]),
                       tiras={PID: tira(), otra['id']: tira()}) as e:
            doc = e.expediente()
        self.assertEqual([c['id'] for c in doc['cartas']], [PID])
        self.assertEqual(doc['pendientes_en_mesa'], 3)
        motivos = {o['id']: o['motivo'] for o in doc['omitidas']}
        self.assertIn('video', motivos['corte-1'])
        self.assertIn('tope', motivos[otra['id']])

    def test_una_carta_sin_tira_no_se_manda_a_juzgar(self):
        with Escenario(tiras={}) as e:
            doc = e.expediente()
        self.assertEqual(doc['cartas'], [])
        self.assertEqual(doc['omitidas'], [{'id': PID, 'motivo': 'sin tira publicada'}])

    def test_apagado_por_regla_no_lee_la_mesa(self):
        for reglas in (dict(REGLAS, consejo_motores='sol'), dict(REGLAS, consejo_activo='0')):
            with self.subTest(reglas=reglas), Escenario(reglas=reglas) as e:
                doc = e.expediente()
                self.assertFalse(doc['activo'])
                self.assertEqual((doc['cartas'], doc['candados'], e.lecturas), ([], [], []))

    def test_un_eje_lleva_sus_opciones(self):
        eje = {'id': 'guion-1', 'tipo': 'eje', 'titulo': 'Elige el gancho', 'laminas': [], 'video': None,
               'opciones': {'porque': 'Elige una', 'candidatas': [{'titulo': 'A', 'texto': 'Uno'}, {'titulo': 'B', 'texto': 'Dos'}]}}
        with Escenario(el_dia={'propuestas': [eje], 'decisiones': {'propuestas': {}}}, tiras={}) as e:
            doc = e.expediente()
        carta = doc['cartas'][0]
        self.assertEqual((carta['porque'], [o['texto'] for o in carta['opciones']], carta['abiertas']),
                         ('Elige una', ['Uno', 'Dos'], [0, 1]))


class AplicarTests(unittest.TestCase):
    def test_aprueba_y_dice_que_toma(self):
        with Escenario() as e:
            codigo = e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 2, '1': 1},
                                 'votos': votos(TODOS - {'zuckerberg'})}])
        self.assertEqual(codigo, 0)
        (fecha, envio, props), = e.decisiones
        self.assertEqual(fecha, '2026-11-09')
        self.assertTrue(envio.startswith('consejo-claude-2026-11-09-'))
        self.assertEqual(props, {PID: {'laminas': ['si', 'si'], 'nota': '',
                                       'notas': ['[toma elegida: 2]', '[toma elegida: 1]']}})
        self.assertEqual({(f[5], f[6]) for f in e.filas}, {('claude', 'claude-fable-5-2')})
        self.assertEqual([f[11] for f in e.filas if f[7] == 'VEREDICTO'], ['si', 'si'])

    def test_la_decision_que_firma_la_acepta_el_contrato_de_produccion(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 2, '1': 1}, 'votos': votos(TODOS)}])
        decision = e.decisiones[0][2][PID]
        resuelta = prod.resolver_tira(tira(), decision, carta_laminas())
        por_n = {l['n']: l for l in resuelta['laminas']}
        self.assertEqual((por_n[2]['estado'], por_n[2]['src']), ('aprobada', 'laminas/x/L2-2.png'))
        self.assertEqual(por_n[3]['seleccion']['toma'], 1)
        # Lo que pasaba antes: un «sí» sin toma tumbaba al montador.
        with self.assertRaises(sala.SalaError):
            prod.resolver_tira(tira(), {'laminas': ['si', 'si'], 'notas': ['', '']}, carta_laminas())

    def test_regresa_con_las_notas_de_los_jueces_y_no_las_imprime(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 1},
                        'votos': votos({'hormozi', 'chris_do', 'zuckerberg'})}])
        props = e.decisiones[0][2][PID]
        self.assertEqual(props['laminas'], ['no', 'no'])
        self.assertTrue(props['notas'][0].startswith('3 de 6 a favor'))
        self.assertIn(NOTA_SECRETA, props['notas'][0])
        self.assertNotIn(NOTA_SECRETA, e.salida.getvalue())
        self.assertIn('L0 no (3/6)', e.salida.getvalue())

    def test_un_si_sin_toma_valida_no_se_firma(self):
        for tomas in ({}, {'0': 3, '1': 1}, {'0': 'dos', '1': 1}, {'0': 0, '1': 1}, None):
            with self.subTest(tomas=tomas), Escenario() as e:
                e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': tomas, 'votos': votos(TODOS)}])
                self.assertEqual(e.decisiones, [])
                self.assertIn('qué toma', e.salida.getvalue())

    def test_un_no_no_necesita_toma(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'votos': votos(set())}])
        self.assertEqual(e.decisiones[0][2][PID]['laminas'], ['no', 'no'])

    def test_otra_carta_que_la_que_se_juzgo_no_se_firma(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': '000000000000', 'tomas': {'0': 1, '1': 1}, 'votos': votos(TODOS)}])
        self.assertEqual(e.decisiones, [])
        self.assertIn('cambió desde el expediente', e.salida.getvalue())

    def test_una_carta_que_ya_decidio_un_humano_no_se_toca(self):
        firmas = [[{'quien': 'Alejandro', 'marca': 'no', 'nota': 'x'}], [{'quien': 'Alejandro', 'marca': 'si', 'nota': ''}]]
        decididas = {PID: {'laminas': ['no', 'si'], 'notas': ['x', ''], 'firmas': firmas}}
        with Escenario() as e:
            sello = e.sello()
            e.dia = dia(decisiones=decididas)
            e.aplicar([{'id': PID, 'sello': sello, 'tomas': {'0': 1, '1': 1}, 'votos': votos(TODOS)}])
        self.assertEqual(e.decisiones, [])
        self.assertIn('ya no está pendiente', e.salida.getvalue())

    def test_solo_se_vota_lo_que_sigue_abierto(self):
        firmas = [[{'quien': 'Sayri', 'marca': 'no', 'nota': 'x'}], []]
        with Escenario(el_dia=dia(decisiones={PID: {'laminas': ['no', None], 'notas': ['x', ''], 'firmas': firmas}})) as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 2, '1': 2}, 'votos': votos(TODOS)}])
        self.assertEqual(e.decisiones[0][2][PID]['laminas'], [None, 'si'])
        self.assertEqual(e.decisiones[0][2][PID]['notas'], ['', '[toma elegida: 2]'])

    def test_un_candado_inventado_no_veta_y_uno_real_si(self):
        for candado, esperado in (('Z99', 'si'), ('A05', 'si'), ('A01', 'no')):
            a = {'voto': 'no', 'nota': 'no me convence', 'candados': [candado]}
            with self.subTest(candado=candado), Escenario() as e:
                e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 1},
                            'votos': votos(TODOS - {'alejandro'}, alejandro=a)}])
                self.assertEqual(e.decisiones[0][2][PID]['laminas'], [esperado, esperado])

    def test_con_menos_de_cinco_jueces_completos_se_abstiene(self):
        v = votos(TODOS)
        v.pop('sayri')
        v['hormozi'] = v['hormozi'][:1]                # votó una sola de las dos láminas
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 1}, 'votos': v}])
        self.assertEqual(e.decisiones, [])
        self.assertIn('4 de 6 jueces', e.salida.getvalue())

    def test_apagado_por_regla_no_aplica_ni_lee_la_mesa(self):
        for reglas in (dict(REGLAS, consejo_motores='sol,opus'), dict(REGLAS, consejo_activo='0')):
            with self.subTest(reglas=reglas), Escenario(reglas=reglas) as e:
                codigo = e.aplicar([{'id': PID, 'sello': 'x', 'votos': votos(TODOS)}])
                self.assertEqual((codigo, e.decisiones, e.lecturas), (0, [], []))

    def test_veredictos_mal_formados_fallan_sin_decidir(self):
        malos = ('', 'no es json', '[]', json.dumps({'esquema': 2, 'motor': 'claude', 'cartas': []}),
                 json.dumps({'esquema': 1, 'motor': 'sol', 'cartas': []}),
                 json.dumps({'esquema': 1, 'motor': 'claude', 'cartas': [{'id': 7, 'votos': {}}]}),
                 json.dumps({'esquema': 1, 'motor': 'claude', 'cartas': [{'id': PID}]}),
                 json.dumps({'esquema': 1, 'motor': 'claude', 'cartas': 'todas'}),
                 json.dumps({'esquema': 1, 'motor': 'claude', 'cartas': [], 'relleno': 'x' * 70000}))
        for crudo in malos:
            with self.subTest(crudo=crudo[:30]), Escenario() as e:
                with self.assertRaises(consejo.ConsejoError):
                    consejo.aplicar(crudo)
                self.assertEqual(e.decisiones, [])

    def test_el_ensayo_valida_y_no_firma(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 2}, 'votos': votos(TODOS)}], ensayo=True)
        self.assertEqual((e.decisiones, e.filas), ([], []))
        self.assertIn('ENSAYO %s [claude]: L0 si (6/6), L1 si (6/6)' % PID, e.salida.getvalue())

    def test_un_corte_de_video_no_lo_juzga_la_nube(self):
        corte = {'id': 'corte-1', 'tipo': 'eje', 'titulo': 'Corte', 'laminas': [],
                 'opciones': [{'titulo': 'Corte final'}], 'video': 'https://drive.google.com/file/d/abcdefghijkl/view'}
        with Escenario(el_dia={'propuestas': [corte], 'decisiones': {'propuestas': {}}}, tiras={}) as e:
            carta = consejo.cartas_pendientes(e.dia)[0]
            e.aplicar([{'id': 'corte-1', 'sello': consejo.sello_de_carta(carta, None), 'votos': votos(TODOS, (0,))}])
        self.assertEqual(e.decisiones, [])
        self.assertIn('corte de video', e.salida.getvalue())

    def test_un_id_que_no_es_de_la_mesa_no_llega_al_registro_publico(self):
        veneno = '::error::falso\n::add-mask::x'
        with Escenario() as e:
            e.aplicar([{'id': veneno, 'sello': 'x', 'votos': {}}, {'id': PID, 'sello': e.sello(),
                                                                  'tomas': {'0': 1, '1': 1}, 'votos': votos(TODOS)}])
        self.assertNotIn('::error::', e.salida.getvalue())
        self.assertEqual(len(e.decisiones), 1)

    def test_la_misma_carta_dos_veces_se_firma_una(self):
        with Escenario() as e:
            v = {'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 1}, 'votos': votos(TODOS)}
            e.aplicar([v, copy.deepcopy(v)])
        self.assertEqual(len(e.decisiones), 1)

    def test_el_modelo_declarado_se_limpia(self):
        with Escenario() as e:
            e.aplicar([{'id': PID, 'sello': e.sello(), 'tomas': {'0': 1, '1': 1}, 'votos': votos(TODOS)}],
                      modelo='<script>alert(1)</script>')
        self.assertEqual({f[6] for f in e.filas}, {'sin-declarar'})


class TomaPorHermesTests(unittest.TestCase):
    """Por Hermes el jurado sólo ve la imagen que la carta enseña: ésa es la toma que aprueba."""

    def res(self, *marcas):
        return {i: {'marca': m, 'nota': '' if m == 'si' else 'cambiar', 'a_favor': 5, 'veto': False}
                for i, m in enumerate(marcas)}

    def test_un_si_lleva_la_toma_de_la_portada(self):
        p = dict(carta_laminas(), laminas=['laminas/x/L2-2.jpg', {'src': 'laminas/x/L3-1.png'}])
        res = self.res('si', 'si')
        with patch.object(consejo, '_tira', lambda pid: tira()):
            self.assertTrue(consejo.sellar_tomas(p, res))
        self.assertEqual([res[0]['nota'], res[1]['nota']], ['[toma elegida: 2]', '[toma elegida: 1]'])

    def test_si_la_portada_no_es_una_de_las_tomas_no_se_firma(self):
        p = dict(carta_laminas(), laminas=['laminas/otra/L2.jpg', 'laminas/x/L3-1.jpg'])
        with patch.object(consejo, '_tira', lambda pid: tira()):
            self.assertFalse(consejo.sellar_tomas(p, self.res('si', 'no')))

    def test_sin_tira_no_se_aprueba_pero_si_se_regresa(self):
        with patch.object(consejo, '_tira', lambda pid: None):
            self.assertFalse(consejo.sellar_tomas(carta_laminas(), self.res('si', 'no')))
            self.assertTrue(consejo.sellar_tomas(carta_laminas(), self.res('no', 'no')))

    def test_una_lamina_sin_tomas_no_lleva_marca(self):
        t = tira()
        for lam in t['laminas']:
            lam.pop('candidatas', None)
        res = self.res('si', 'si')
        with patch.object(consejo, '_tira', lambda pid: t):
            self.assertTrue(consejo.sellar_tomas(carta_laminas(), res))
        self.assertEqual(res[0]['nota'], '')

    def corrida(self, portadas):
        """Una corrida completa por Hermes con los seis jueces a favor de todo."""
        el_dia = dia()
        el_dia['propuestas'][0]['laminas'] = portadas
        jurado = {k: {i: {'voto': 'si', 'nota': '', 'candados': []} for i in (0, 1)} for k, _, _ in consejo.JUECES}
        with Escenario(reglas=dict(REGLAS, consejo_motores='sol'), el_dia=el_dia) as e, \
                patch.object(consejo, 'motores_disponibles', lambda reglas: ['sol']), \
                patch.object(consejo, '_llamadas_hoy', lambda fecha: 0), \
                patch.object(consejo, 'material', lambda carta, reglas, tmp: ([], [], None)), \
                patch.object(consejo, 'juzgar', lambda *a, **kw: (copy.deepcopy(jurado), [])):
            self.assertEqual(consejo.corrida(), 0)
        return e

    def test_la_corrida_por_hermes_firma_con_la_toma_que_vio(self):
        e = self.corrida(['laminas/x/L2-2.jpg', 'laminas/x/L3-1.jpg'])
        (_, envio, props), = e.decisiones
        self.assertTrue(envio.startswith('consejo-sol-'))
        self.assertEqual(props[PID]['notas'], ['[toma elegida: 2]', '[toma elegida: 1]'])
        prod.resolver_tira(tira(), props[PID], dict(carta_laminas(), laminas=['laminas/x/L2-2.jpg', 'laminas/x/L3-1.jpg']))

    def test_la_corrida_por_hermes_se_abstiene_si_no_sabe_que_toma_aprobo(self):
        e = self.corrida(['laminas/otra/L2.jpg', 'laminas/x/L3-1.jpg'])
        self.assertEqual(e.decisiones, [])
        self.assertIn('no pude acreditar qué toma', e.salida.getvalue())

    def test_hermes_queda_en_reserva_sin_alarma_si_la_regla_solo_pide_claude(self):
        salida = io.StringIO()
        with patch.object(consejo, 'leer_reglas', lambda: dict(REGLAS)), \
                patch.dict(os.environ, {'HERMES_API_URL': 'http://127.0.0.1:8642/p/sol', 'HERMES_API_KEY': 'k-hermes-123456'}), \
                patch.object(sala, 'enmascarar_en_actions', lambda: None), contextlib.redirect_stdout(salida):
            self.assertEqual(consejo.corrida(), 0)
        self.assertIn('en reserva', salida.getvalue())


class TiraTests(unittest.TestCase):
    def test_la_tira_que_no_esta_en_el_checkout_se_lee_de_pages(self):
        pedidas = []

        def bajar(url, tope):
            pedidas.append(url)
            return json.dumps({'promesa': 'x', 'laminas': []}).encode()
        with patch.object(consejo, '_bajar', bajar), patch.dict(consejo._TIRAS, {}, clear=True):
            self.assertEqual(consejo._tira('pieza-nube-2026-11-09-abcdef')['promesa'], 'x')
            consejo._tira('pieza-nube-2026-11-09-abcdef')
        self.assertEqual(pedidas, [consejo.PAGES + 'datos/tiras/pieza-nube-2026-11-09-abcdef.json'])

    def test_un_id_raro_no_sale_a_la_red(self):
        with patch.object(consejo, '_bajar', side_effect=AssertionError('no debe pedirse')), \
                patch.dict(consejo._TIRAS, {}, clear=True):
            self.assertIsNone(consejo._tira('../../secreto'))
            self.assertIsNone(consejo._tira('a b?c=d'))


class WorkflowTests(unittest.TestCase):
    TEXTO = (ROOT / '.github' / 'workflows' / 'sala-consejo.yml').read_text(encoding='utf-8')

    def test_los_votos_viajan_por_variable_y_no_dentro_del_guion(self):
        self.assertIn('CONSEJO_VEREDICTOS: ${{ inputs.veredictos }}', self.TEXTO)
        for guion in re.findall(r'^\s+run: (?:\|\n(?:\s{10,}.*\n?)+|.*)$', self.TEXTO, flags=re.M):
            self.assertNotIn('inputs.veredictos', guion)
            self.assertNotIn('CONSEJO_VEREDICTOS', guion)

    def test_solo_corre_en_main_y_no_en_pull_request(self):
        self.assertIn("if: github.ref == 'refs/heads/main'", self.TEXTO)
        self.assertNotIn('pull_request', self.TEXTO)

    def test_la_siguiente_ronda_solo_se_lanza_tras_aplicar_de_verdad(self):
        paso = self.TEXTO.split('- name: Que la siguiente ronda salga enseguida', 1)[1]
        self.assertIn("if: env.MODO == 'aplicar' && !inputs.ensayo", paso)
        self.assertIn('for proceso in mesa arranque', paso)
        self.assertIn('gh workflow run sala-cada-hora.yml', paso)

    def test_los_modos_del_workflow_existen_en_el_codigo(self):
        modos = re.search(r'options: \[([^\]]+)\]', self.TEXTO).group(1).replace(' ', '').split(',')
        self.assertEqual(set(modos), {'corrida', 'ensayo', 'marcador', 'expediente', 'aplicar'})
        fuente = (ROOT / 'nube' / 'sala_consejo.py').read_text(encoding='utf-8')
        for modo in modos:
            self.assertIn("'%s'" % modo, fuente.split("if __name__ == '__main__':", 1)[1])


if __name__ == '__main__':
    unittest.main()
