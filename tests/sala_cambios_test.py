"""Órdenes de cambio sobre láminas ya aprobadas (9-nov-2026, DEC-08 «Las 48 Horas»).

Lo que se prueba, sin red:
  · la nube sólo LEE las órdenes (llave `cambio:<slug>` de EXPEDIENTES) y lo ilegible se ignora;
  · una orden vale para la tira para la que se pidió y sólo reabre láminas APROBADAS;
  · el montador rehace esa lámina con la nota del editor, con id nuevo y `rehecha-de`, y si la
    producción falla no vuelve a presentar las tomas viejas;
  · la estación de salida deja de dar por lista (o por completa) una pieza con orden de cambio;
  · nada de esto decide: la aprobación sigue en DECISIONES y la carta nueva espera al editor.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
sys.path.insert(0, str(ROOT / 'tests'))
import sala_cambios as cambios
import sala_cliente as sala
import sala_mesa as mesa
import sala_produccion as prod
import sala_salida as salida
import sala_salida_test as est

P = '48-horas-arranque-2026-09-24-e98d7d'
NOTA = 'Cambia el texto: quita «en solo 48 horas». No prometemos plazos.'


def tira_de_una():
    """Una pieza de una sola imagen, como quedó «Las 48 Horas»: su tira de arranque, sin base."""
    return {'pieza': 'Las 48 Horas', 'pieza_slug': '48-horas', 'fecha': '2026-09-24', 'formato': 'Lámina',
            'base': None, 'decidir': [1], 'mapa': {'1': 1},
            'guion': [{'n': 1, 'dice': '¿Imaginas saberlo en solo 48 horas?', 've': 'Dos personas con una tablet'}],
            'laminas': [{'n': 1, 'src': 'laminas/t/L1-1.jpg', 'dice': '¿Imaginas saberlo en solo 48 horas?',
                         've': 'Dos personas con una tablet', 'estado': 'propuesta', 'candidatas': [
                             {'src': 'laminas/t/L1-1.jpg', 'original': 'laminas/t/L1-1.png', 'dice': 'Toma A', 'motor': 'm'},
                             {'src': 'laminas/t/L1-2.jpg', 'original': 'laminas/t/L1-2.png', 'dice': 'Toma B', 'motor': 'm'}]}]}


def si():
    return {'laminas': ['si'], 'notas': ['[toma elegida: 2]']}


def orden(tira=P, n=1, nota=NOTA, **extra):
    return dict({'v': 1, 'pieza': 'Las 48 Horas', 'tira': tira,
                 'ordenes': [{'n': n, 'nota': nota, 'cuando': '2026-11-10T03:30:00.000Z', 'por': 'editor'}]}, **extra)


class LeerTests(unittest.TestCase):
    def test_una_orden_bien_formada_se_lee_por_tira(self):
        self.assertEqual(cambios.leer({'cambio:48-horas': orden(), 'La servilleta': {'estado': 'lista'}}),
                         {P: {1: NOTA}})

    def test_lo_ilegible_se_ignora_sin_tumbar_nada(self):
        raros = {
            'cambio:a': None, 'cambio:b': 'texto', 'cambio:c': [],
            'cambio:d': orden(tira='../etc'), 'cambio:e': orden(tira=''), 'cambio:f': orden(tira=7),
            'cambio:g': {'tira': P, 'ordenes': 'no es lista'},
            'cambio:h': orden(n=0), 'cambio:i': orden(n=100), 'cambio:j': orden(n='1'), 'cambio:k': orden(n=1.0),
            'cambio:l': orden(n=True), 'cambio:m': orden(nota='   '), 'cambio:n': orden(nota=None),
            'cambio:o': {'tira': P, 'ordenes': ['x', None, 3]},
            'salida:plan': orden(), 'v4:universo': orden(), 'Las 48 Horas': orden()}
        self.assertEqual(cambios.leer(raros), {})
        for vacio in (None, [], 'x', 3):
            self.assertEqual(cambios.leer(vacio), {})

    def test_la_nota_llega_en_una_linea_y_con_tope(self):
        leidas = cambios.leer({'cambio:x': orden(nota='  Más   luminosa\n\ny sin   letrero  ' + 'a' * 900)})
        nota = leidas[P][1]
        self.assertTrue(nota.startswith('Más luminosa y sin letrero a'))
        self.assertEqual(len(nota), cambios.MAX_NOTA)

    def test_una_orden_por_lamina_y_tope_de_ordenes(self):
        muchas = {'tira': P, 'ordenes': [{'n': k, 'nota': 'nota %d' % k} for k in range(1, 40)]}
        self.assertEqual(sorted(cambios.leer({'cambio:x': muchas})[P]), list(range(1, cambios.MAX_ORDENES + 1)))
        repetida = {'tira': P, 'ordenes': [{'n': 2, 'nota': 'primera'}, {'n': 2, 'nota': 'la última manda'}]}
        self.assertEqual(cambios.leer({'cambio:x': repetida}), {P: {2: 'la última manda'}})

    def test_solo_vale_para_la_tira_para_la_que_se_pidio(self):
        leidas = cambios.leer({'cambio:48-horas': orden()})
        self.assertEqual(cambios.de_tira(leidas, P), {1: NOTA})
        self.assertEqual(cambios.de_tira(leidas, '48-horas-nube-2026-11-10-abc123'), {})
        self.assertEqual(cambios.de_tira(None, P), {})

    def test_la_nube_y_la_pantalla_leen_igual_el_mismo_contrato(self):
        """Los mismos casos los corre tests/sala-salida.test.cjs contra sala-salida.js."""
        contrato = json.loads((ROOT / 'tests' / 'fixtures' / 'cambios-casos.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(contrato['casos']), 12)
        for caso in contrato['casos']:
            leidas = cambios.leer({'cambio:pieza': caso['registro']})
            esperado = {int(n): nota for n, nota in caso['ordenes'].items()}
            if esperado:
                self.assertEqual(leidas, {caso['tira']: esperado}, caso['caso'])
            else:
                self.assertEqual(leidas, {}, caso['caso'])

    def test_el_modulo_no_escribe_ni_decide(self):
        fuente = (ROOT / 'nube' / 'sala_cambios.py').read_text(encoding='utf-8')
        for prohibido in ('sala_cliente', 'post(', 'urllib', 'requests', 'open(', 'decidir'):
            self.assertNotIn(prohibido, fuente.split('"""', 2)[2], prohibido)


class AplicarTests(unittest.TestCase):
    def test_solo_reabre_laminas_aprobadas_y_no_toca_el_original(self):
        resuelta = prod.resolver_tira(tira_de_una(), si())
        self.assertEqual(resuelta['laminas'][0]['estado'], 'aprobada')
        antes = copy.deepcopy(resuelta)
        nueva, reabiertas = cambios.aplicar(resuelta, {1: NOTA})
        self.assertEqual(reabiertas, [1])
        self.assertEqual(resuelta, antes)
        lam = nueva['laminas'][0]
        self.assertEqual((lam['estado'], lam['marca_previa'], lam['nota_previa'], lam['reabierta']),
                         ('rechazada', 'no', NOTA, True))
        self.assertEqual(lam['src'], 'laminas/t/L1-2.png')          # lo que se ve mientras tanto: lo aprobado
        self.assertNotIn('candidatas', lam)                         # las tomas viejas no vuelven a presentarse
        self.assertNotIn('seleccion', lam)

    def test_sin_ordenes_devuelve_la_misma_tira(self):
        resuelta = prod.resolver_tira(tira_de_una(), si())
        for nada in (None, {}):
            misma, reabiertas = cambios.aplicar(resuelta, nada)
            self.assertIs(misma, resuelta)
            self.assertEqual(reabiertas, [])

    def test_una_lamina_sin_aprobar_sigue_su_camino(self):
        pendiente = prod.resolver_tira(tira_de_una(), {})
        nueva, reabiertas = cambios.aplicar(pendiente, {1: NOTA, 7: 'no existe'})
        self.assertEqual(reabiertas, [])
        self.assertEqual(nueva['laminas'][0]['estado'], 'propuesta')
        self.assertEqual(len(nueva['laminas'][0]['candidatas']), 2)


class MesaTests(unittest.TestCase):
    def abiertas(self, t, decision, ordenes=None):
        with patch.object(mesa, 'decision_del_sheet', return_value=(decision, ['laminas/t/L1-1.jpg'])):
            return mesa.abiertas(P, t, ordenes=ordenes)

    def test_sin_orden_una_pieza_aprobada_no_abre_nada(self):
        self.assertEqual(self.abiertas(tira_de_una(), si()), [])
        self.assertEqual(self.abiertas(tira_de_una(), si(), {}), [])

    def test_con_orden_la_lamina_aprobada_se_rehace_con_la_nota_del_editor(self):
        t = tira_de_una()
        antes = copy.deepcopy(t)
        abiertas = self.abiertas(t, si(), {1: NOTA})
        self.assertEqual([(lam['n'], marca, nota) for lam, marca, nota in abiertas], [(1, 'no', NOTA)])
        self.assertEqual(t, antes)

    def test_la_orden_no_convierte_en_rechazo_lo_que_sigue_por_decidir(self):
        # Sin marca todavía: sus tomas siguen en la carta. La orden no las da por rechazadas.
        self.assertEqual(self.abiertas(tira_de_una(), {}, {1: NOTA}), [])

    def test_si_la_produccion_no_alcanzo_la_siguiente_vuelta_hace_tomas_nuevas(self):
        """La lámina reabierta que viajó a una tira nueva sin tomas no vuelve con las tomas viejas."""
        reabierta, _ = cambios.aplicar(prod.resolver_tira(tira_de_una(), si()), {1: NOTA})
        reabierta.update(decidir=[2], mapa={'1': 2}, base=P)        # la carta nueva mostró otra lámina
        reabierta['laminas'].append({'n': 2, 'src': 'laminas/t/L2-1.jpg', 'dice': 'Dos', 'estado': 'rehecha',
                                     'candidatas': [{'src': 'laminas/t/L2-1.jpg', 'dice': 'Dos', 'motor': 'm'}]})
        reabierta['guion'].append({'n': 2, 'dice': 'Dos'})
        abiertas = self.abiertas(reabierta, {'laminas': [''], 'notas': ['']})
        self.assertEqual([(lam['n'], marca, nota) for lam, marca, nota in abiertas], [(1, 'pendiente', NOTA)])


class MontadorTests(unittest.TestCase):
    def correr(self, root, expedientes):
        notas = []

        def tomas_de_mentira(slug, referencia, lam, nota, reglas, cola, carpeta, cuantas):
            notas.append((lam['n'], nota))
            carpeta.mkdir(parents=True, exist_ok=True)
            base = carpeta / ('L%d-1' % lam['n'])
            base.with_suffix('.png').write_bytes(b'imagen-nueva')
            base.with_suffix('.jpg').write_bytes(b'vista-nueva')
            return [{'src': str(base.with_suffix('.jpg').relative_to(root)),
                     'original': str(base.with_suffix('.png').relative_to(root)),
                     'motor': 'doble', 'dice': '¿Imaginas saber el potencial real de tu terreno?',
                     'huella': hashlib.md5(b'imagen-nueva').hexdigest()}], []

        dia = {'fecha': '2026-11-10', 'dias': ['2026-11-10'],
               'propuestas': [{'id': P, 'laminas': ['laminas/t/L1-1.jpg']}], 'decisiones': {'propuestas': {P: si()}}}

        def get(recurso, **kw):
            if recurso == 'reglas':
                return {'reglas': {'mesa_tope_laminas': '4', 'mesa_tomas_por_lamina': '1'}}
            if recurso == 'expedientes':
                if expedientes is None:
                    raise sala.SalaError('el Sheet no contestó')
                return {'ok': True, 'expedientes': expedientes}
            return {'cola': []}

        with patch.object(sys, 'argv', ['mesa', '--producir']), \
                patch.object(mesa, 'RAIZ', root), patch.object(mesa, 'TIRAS', root / 'datos' / 'tiras'), \
                patch.object(mesa, 'PLAN', root / 'plan.json'), \
                patch.object(mesa, 'contexto_produccion', return_value=dia), \
                patch.object(mesa, 'hidratar_tiras_activas', return_value=0), \
                patch.object(mesa, 'tiras_por_pieza', return_value={'48-horas': (P, tira_de_una())}), \
                patch.object(mesa, 'publicadas', return_value=set()), \
                patch.object(mesa, 'producir_tomas', side_effect=tomas_de_mentira), \
                patch.object(prod, 'peticiones_abiertas', return_value=False), \
                patch.object(sala, 'avisar'), patch.object(sala, 'post') as post, \
                patch.object(sala, 'get', side_effect=get):
            codigo = mesa.main()
        post.assert_not_called()                                      # producir no monta ni decide
        plan = json.loads((root / 'plan.json').read_text())
        return codigo, plan['cartas'], notas

    def test_la_orden_produce_una_rehecha_con_id_nuevo_y_su_origen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'datos' / 'tiras').mkdir(parents=True)
            codigo, cartas, notas = self.correr(root, {'cambio:48-horas': orden()})
            self.assertEqual(codigo, 0)
            self.assertEqual(notas, [(1, NOTA)])                      # la nota del editor llega al cerebro
            self.assertEqual(len(cartas), 1)
            nueva_id, carta = cartas[0]['tira_id'], cartas[0]['carta']
            self.assertNotEqual(nueva_id, P)                          # INVIOLABLE 5: id nuevo…
            self.assertEqual(carta['origen'], 'rehecha-de ' + P)      # …y su origen
            self.assertEqual(carta['id'], nueva_id)
            nueva = json.loads((root / 'datos' / 'tiras' / (nueva_id + '.json')).read_text())
            self.assertEqual((nueva['base'], nueva['decidir']), (P, [1]))
            lam = nueva['laminas'][0]
            self.assertEqual((lam['estado'], lam['marca_previa'], lam['nota_previa']), ('rehecha', 'no', NOTA))
            self.assertEqual([c['dice'] for c in lam['candidatas']], ['¿Imaginas saber el potencial real de tu terreno?'])
            self.assertNotIn('seleccion', lam)
            self.assertNotIn('reabierta', lam)
            # La orden era para la tira anterior: con la tira nueva ya no reabre nada.
            self.assertEqual(cambios.de_tira(cambios.leer({'cambio:48-horas': orden()}), nueva_id), {})

    def test_sin_orden_o_con_orden_de_otra_version_no_se_produce_nada(self):
        for expedientes in ({}, {'cambio:48-horas': orden(tira='48-horas-nube-2026-10-01-000000')},
                            {'cambio:48-horas': orden(nota='  ')}, {'cambio:48-horas': orden(ordenes=[])}):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / 'datos' / 'tiras').mkdir(parents=True)
                codigo, cartas, notas = self.correr(root, expedientes)
                self.assertEqual((codigo, cartas, notas), (0, [], []), expedientes)

    def test_si_no_se_pueden_leer_las_ordenes_la_mesa_sigue_sin_reabrir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'datos' / 'tiras').mkdir(parents=True)
            self.assertEqual(self.correr(root, None), (0, [], []))


class SalidaTests(unittest.TestCase):
    def lista(self):
        """Una pieza ya empacada: el escenario de la estación con su paquete vigente."""
        e = est.Escenario()
        with e:
            self.assertEqual(e.empacar(), 0)
        return copy.deepcopy(e.expedientes)

    def test_con_orden_la_pieza_lista_deja_de_estar_lista(self):
        expedientes = self.lista()
        with est.Escenario(expedientes=expedientes) as e:
            self.assertEqual([f['estado'] for f in e.filas()], ['lista'])
        expedientes['cambio:' + est.SLUG] = orden(tira=est.PID, n=2, nota='Más luminosa')
        with est.Escenario(expedientes=expedientes) as e:
            fila = e.filas()[0]
            self.assertEqual((fila['estado'], fila['motivo']), ('en_laminas', 'cambio pedido por un editor (L2)'))
            # ni el jurado le escribe texto ni la estación la vuelve a empacar
            self.assertEqual(salida.para_el_jurado(e.reglas, e.filas(), 'receta')['pendientes'], [])
            antes = len(e.escrituras)
            self.assertEqual(e.empacar([{'id': est.PID, 'sello': 'a' * 12, 'texto': est.TEXTO, 'revision': []}]), 0)
            self.assertEqual(len(e.escrituras), antes)

    def test_una_orden_de_otra_version_no_la_saca(self):
        expedientes = self.lista()
        expedientes['cambio:' + est.SLUG] = orden(tira='tres-opiniones-nube-2026-09-01-aaaaaa', n=2, nota='Más luminosa')
        with est.Escenario(expedientes=expedientes) as e:
            self.assertEqual([f['estado'] for f in e.filas()], ['lista'])

    def test_una_pieza_completa_con_orden_no_llega_al_jurado(self):
        with est.Escenario(expedientes={'cambio:' + est.SLUG: orden(tira=est.PID, n=1, nota='Otra pareja')}) as e:
            fila = e.filas()[0]
            self.assertEqual((fila['estado'], fila['motivo']), ('en_laminas', 'cambio pedido por un editor (L1)'))
            self.assertEqual(salida.para_el_jurado(e.reglas, e.filas(), 'receta')['pendientes'], [])


if __name__ == '__main__':
    unittest.main()
