"""Estación de salida (9-nov-2026, Sala corta): de «láminas aprobadas» a «paquete listo».

Lo que se prueba, sin red y con un Drive de mentira:
  · una pieza sólo sale si TODAS sus láminas están aprobadas y ya no falta nada del guion;
  · el paquete lleva las tomas elegidas, en orden, con su documento, y repetirlo no duplica;
  · el texto es dato: se valida contra los candados que una regla puede comprobar y nunca se
    imprime; un texto escrito para otra versión de la pieza no entra;
  · el expediente conserva todo lo que ya decía (la historia y las palabras de los editores);
  · «ya la publiqué» (una fila de PRODUCCION) cierra el expediente y guarda el paquete;
  · la estación no decide, no publica y respeta sus frenos.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import sala_cliente as sala
import sala_salida as salida

PID = 'tres-opiniones-nube-2026-10-12-87ec1e'
SLUG = 'tres-opiniones'
TITULO = 'Tres opiniones, tres números distintos'
REGLAS = {'drive_raiz': 'RAIZ', 'nube_ejecuta_etapas': 'prospecto'}
TEXTO = ('En la sobremesa todos opinan del terreno familiar.\n'
         'El tío ve locales. La vecina, departamentos.\n\n'
         'Nosotros preferimos leer lo que dice la norma:\n'
         'cuántos m² permite y qué giros caben de verdad.\n\n'
         'Eso es tu Plan de Potencial Personalizado.\n\n'
         'Tú traes la ubicación. El primer paso es una videollamada 👇')
PALABRA_SECRETA = 'sobremesa'


def png(nombre):
    return b'\x89PNG\r\n\x1a\n' + nombre.encode()


def md5(b):
    return hashlib.md5(b).hexdigest()


def tira(formato='Carrusel', pid_dir='t'):
    def toma(n, k):
        original = 'laminas/%s/L%d-%d.png' % (pid_dir, n, k)
        return {'src': 'laminas/%s/L%d-%d.jpg' % (pid_dir, n, k), 'original': original, 'titulo': 'AB'[k - 1],
                'dice': 'Lámina %d toma %d' % (n, k), 'huella': md5(png(original))}
    return {'pieza': TITULO, 'pieza_slug': SLUG, 'promesa': 'La norma supera a las opiniones.',
            'formato': formato, 'fecha': '2026-10-12', 'decidir': [2, 3], 'mapa': {'1': 2, '2': 3},
            'guion': [{'n': 1, 'dice': 'Uno'}, {'n': 2, 'dice': 'Dos'}, {'n': 3, 'dice': 'Tres'}],
            'laminas': [
                {'n': 1, 'src': 'laminas/%s/L1.png' % pid_dir, 'dice': 'Uno', 'estado': 'aprobada'},
                {'n': 2, 'src': 'laminas/%s/L2-1.jpg' % pid_dir, 'dice': 'Dos', 'estado': 'rehecha',
                 'candidatas': [toma(2, 1), toma(2, 2)]},
                {'n': 3, 'src': 'laminas/%s/L3-1.jpg' % pid_dir, 'dice': 'Tres', 'estado': 'rehecha',
                 'candidatas': [toma(3, 1), toma(3, 2)]}]}


def carta(pid=PID, **extra):
    return dict({'id': pid, 'tipo': 'laminas', 'titulo': TITULO, 'origen': None, 'video': None,
                 'laminas': ['laminas/t/L2-1.jpg', 'laminas/t/L3-1.jpg'], 'opciones': [],
                 'fecha_fuente': '2026-10-12'}, **extra)


def decision(marcas=('si', 'si'), tomas=(2, 1)):
    return {'laminas': list(marcas),
            'notas': ['[toma elegida: %d]' % t if m == 'si' else 'Más luminosa' for m, t in zip(marcas, tomas)],
            'firmas': [[] for _ in marcas], 'nota': ''}


class Drive:
    """Un Drive en memoria con las operaciones que usa la estación."""

    def __init__(self):
        self.nodos = {'RAIZ': {'name': 'YOD Editorial', 'padre': None, 'tipo': 'carpeta'}}
        self.n, self.subidas, self.movidas, self.fallar_en = 0, [], [], None
        self.DriveError = type('DriveError', (RuntimeError,), {})

    def _nuevo(self, **nodo):
        self.n += 1
        fid = 'f%d' % self.n
        self.nodos[fid] = nodo
        return fid

    def listar(self, padre):
        return [{'id': k, 'name': v['name'], 'md5Checksum': v.get('md5'),
                 'mimeType': {'carpeta': 'application/vnd.google-apps.folder',
                              'doc': 'application/vnd.google-apps.document'}.get(v['tipo'], 'image/png')}
                for k, v in self.nodos.items() if v['padre'] == padre]

    def asegurar_carpeta(self, padre, nombre):
        for h in self.listar(padre):
            if h['name'] == nombre and h['mimeType'].endswith('folder'):
                return h['id']
        return self._nuevo(name=nombre, padre=padre, tipo='carpeta')

    def ruta_carpetas(self, raiz, *nombres):
        for n in nombres:
            raiz = self.asegurar_carpeta(raiz, n)
        return raiz

    def subir(self, ruta, carpeta, nombre=None):
        datos = Path(ruta).read_bytes()
        if self.fallar_en and self.fallar_en in self.nodos[carpeta]['name']:
            raise self.DriveError('Drive 503')
        self.subidas.append((self.nodos[carpeta]['name'], nombre))
        for h in self.listar(carpeta):
            if h['name'] == nombre:
                self.nodos[h['id']].update(md5=md5(datos), datos=datos)
                return h['id']
        return self._nuevo(name=nombre, padre=carpeta, tipo='archivo', md5=md5(datos), datos=datos)

    def subir_documento(self, nombre, html, carpeta):
        for h in self.listar(carpeta):
            if h['name'] == nombre:
                self.nodos[h['id']]['html'] = html
                return h['id']
        return self._nuevo(name=nombre, padre=carpeta, tipo='doc', html=html)

    def mover(self, fid, origen, destino):
        assert self.nodos[fid]['padre'] == origen
        self.nodos[fid]['padre'] = destino
        self.movidas.append(self.nodos[fid]['name'])

    def hijos(self, *ruta):
        actual = 'RAIZ'
        for n in ruta:
            actual = next(k for k, v in self.nodos.items() if v['padre'] == actual and v['name'] == n)
        return sorted(v['name'] for v in self.nodos.values() if v['padre'] == actual)


class Escenario:
    def __init__(self, reglas=None, tiras=None, cartas=None, decisiones=None, expedientes=None, produccion=None):
        self.reglas = dict(REGLAS if reglas is None else reglas)
        self.tiras = {PID: tira()} if tiras is None else tiras
        self.cartas = [carta()] if cartas is None else cartas
        self.decisiones = {PID: decision()} if decisiones is None else decisiones
        self.expedientes = copy.deepcopy(expedientes or {})
        self.produccion = list(produccion or [])
        self.drive, self.escrituras, self.proyeccion, self.sheet_falla = Drive(), [], None, None

    def __enter__(self):
        modulo = types.ModuleType('sala_drive')
        for nombre in ('listar', 'asegurar_carpeta', 'ruta_carpetas', 'subir', 'subir_documento', 'mover'):
            setattr(modulo, nombre, getattr(self.drive, nombre))
        modulo.DriveError = self.drive.DriveError

        def get(recurso, **kw):
            if recurso == 'reglas':
                return {'reglas': dict(self.reglas), 'motores': []}
            if recurso == 'dia':
                return {'fecha': '2026-11-09', 'propuestas': [], 'decisiones': {'propuestas': {}},
                        'produccion': copy.deepcopy(self.produccion)}
            if recurso == 'expedientes':
                return {'ok': True, 'expedientes': copy.deepcopy(self.expedientes)}
            if recurso == 'prompts':
                return {'ok': True, 'prompts': []}
            raise AssertionError('lectura inesperada: ' + recurso)

        def post(accion, **campos):
            if accion in sala.PROHIBIDAS:
                raise AssertionError('la estación intentó decidir')
            if self.sheet_falla and self.sheet_falla in str(campos.get('pieza')):
                raise sala.SalaError('sin confirmar')
            self.escrituras.append((accion, copy.deepcopy(campos)))
            if accion == 'expediente':
                self.expedientes[campos['pieza']] = copy.deepcopy(campos['expediente'])
            return {'ok': True}

        def bajar(url, tope):
            ruta = url.replace(salida.PAGES, '')
            if ruta.startswith('datos/'):
                raise OSError('sin red')
            return png(ruta)
        self.pila = contextlib.ExitStack()
        salida._TIRAS.clear()
        salida._CREADAS.clear()
        for parche in (
                patch.dict(sys.modules, {'sala_drive': modulo}),
                patch.dict(os.environ, {'GITHUB_RUN_ID': '888'}),
                patch.object(salida.produccion, 'cargar', lambda: {
                    'fecha': '2026-11-09', 'propuestas': copy.deepcopy(self.cartas),
                    'decisiones': {'propuestas': copy.deepcopy(self.decisiones)}}),
                patch.object(salida, 'leer_tira', lambda pid: copy.deepcopy(self.tiras.get(str(pid)))),
                patch.object(salida, 'proyeccion_de_la_mesa', lambda: self.proyeccion),
                patch.object(salida, 'medios', lambda: {}),
                patch.object(salida, '_publicadas_del_repo', lambda: set()),
                patch.object(salida, '_bajar', bajar),
                patch.object(sala, 'get', get), patch.object(sala, 'post', post),
                patch.object(sala, 'hoy_hermosillo', lambda: '2026-11-09'),
                patch.object(sala, 'enmascarar_en_actions', lambda: None)):
            self.pila.enter_context(parche)
        self.log = io.StringIO()
        self.pila.enter_context(contextlib.redirect_stdout(self.log))
        return self

    def __exit__(self, *exc):
        self.pila.close()

    def filas(self):
        reglas, dia_p, dia, exp = salida.leer_mesa()
        return salida.estado_de_piezas(dia_p, dia, reglas, exp, proyeccion=self.proyeccion)

    def sello(self, pid=PID):
        return next(f for f in self.filas() if f['id'] == pid)['sello']

    def empacar(self, paquetes=None, ensayo=False):
        if paquetes is None:
            paquetes = [{'id': PID, 'sello': self.sello(), 'texto': TEXTO, 'revision': ['Lámina 3: el fondo se ve ajeno.']}]
        return salida.empacar(json.dumps({'esquema': 1, 'paquetes': paquetes}, ensure_ascii=False), ensayo=ensayo)

    def de(self, accion):
        return [c for a, c in self.escrituras if a == accion]


class TextoTests(unittest.TestCase):
    def test_un_texto_de_la_casa_pasa(self):
        self.assertEqual(salida.revisar_texto(TEXTO, REGLAS), [])

    def test_cada_candado_comprobable_tiene_su_codigo(self):
        casos = {
            'ubicacion': 'Tu terreno en Hermosillo merece saberlo.',
            'dinero_o_gratis': 'La primera videollamada es gratis.',
            'plazo': 'En 48 horas sabes qué cabe.',
            'liga': 'Entra a www.yodesarrollo.mx hoy.',
            'otra_marca': 'Con el respaldo de Aurum.',
            'palabra_vetada': 'Se acabó el pleito de la familia.',
            'nombre_del_plan': 'Pide tu Plan de Potencial personalizado.',
        }
        for codigo, frase in casos.items():
            with self.subTest(codigo):
                self.assertEqual(salida.revisar_texto(TEXTO.replace('Eso es tu Plan de Potencial Personalizado.', frase), REGLAS),
                                 [codigo])

    def test_el_plan_va_completo_y_con_sus_mayusculas(self):
        for mal in ('plan de potencial', 'Plan Potencial Personalizado', 'Plan de potencial Personalizado', 'Plan de Potencial'):
            with self.subTest(mal):
                self.assertIn('nombre_del_plan', salida.revisar_texto(TEXTO.replace('Plan de Potencial Personalizado', mal)))

    def test_largo_corto_y_caracteres_raros(self):
        self.assertEqual(salida.revisar_texto('Hola.'), ['corto'])
        self.assertIn('largo', salida.revisar_texto(TEXTO + ' más' * 700))
        self.assertIn('caracteres_de_control', salida.revisar_texto(TEXTO + '\x07'))
        self.assertEqual(salida.revisar_texto(None), ['sin_texto'])

    def test_reglas_agregan_ubicaciones_y_palabras(self):
        reglas = {'contenido_ubicaciones_vetadas': 'Guaymas', 'salida_palabras_vetadas': 'baldío'}
        self.assertEqual(salida.revisar_texto(TEXTO + '\nUn baldío en Guaymas.', reglas), ['ubicacion', 'palabra_vetada'])

    def test_las_ligas_las_pone_la_estacion_y_se_miden_por_pieza(self):
        c = salida.componer(TEXTO, SLUG, '2026-11-09', REGLAS)
        self.assertEqual(c['comentario'], 'https://yodesarrollo.github.io/plan-potencial/?utm_source=instagram'
                                          '&utm_medium=social&utm_campaign=ig-2026-11-09&utm_content=tres-opiniones')
        self.assertTrue(c['instagram'].endswith(salida.CIERRE_IG))
        self.assertTrue(c['facebook'].endswith('utm_campaign=fb-2026-11-09&utm_content=tres-opiniones'))
        propia = salida.componer(TEXTO, SLUG, '2026-11-09', {'salida_liga': 'https://tableros.yodesarrollo.mx/plan/?x=1'})
        self.assertTrue(propia['comentario'].startswith('https://tableros.yodesarrollo.mx/plan/?x=1&utm_source=instagram'))
        with self.assertRaises(salida.SalidaError):
            salida.componer(TEXTO, SLUG, '2026-11-09', {'salida_liga': 'javascript:alert(1)'})


class PiezaCompletaTests(unittest.TestCase):
    def test_completa_lleva_las_tomas_elegidas_en_orden_y_el_original(self):
        with Escenario() as e:
            fila = e.filas()[0]
        self.assertEqual(fila['estado'], 'completa')
        self.assertEqual([(l['n'], l['ruta'], l['toma']) for l in fila['laminas']],
                         [(1, 'laminas/t/L1.png', None), (2, 'laminas/t/L2-2.png', 2), (3, 'laminas/t/L3-1.png', 1)])
        self.assertEqual(fila['formato'], 'Carrusel')

    def test_una_lamina_sin_aprobar_o_rechazada_no_sale(self):
        for marcas in (('si', None), ('si', 'no'), (None, None)):
            with self.subTest(marcas), Escenario(decisiones={PID: decision(marcas)}) as e:
                fila = e.filas()[0]
                self.assertEqual(fila['estado'], 'en_laminas')
                self.assertEqual(e.empacar([{'id': PID, 'sello': 'a' * 12, 'texto': TEXTO}]), 0)
                self.assertEqual(e.escrituras, [])
                self.assertEqual(e.drive.subidas, [])

    def test_guion_con_laminas_por_hacer_no_sale(self):
        t = tira()
        t['guion'].append({'n': 4, 'dice': 'Cuatro'})
        with Escenario(tiras={PID: t}) as e:
            fila = e.filas()[0]
        self.assertEqual((fila['estado'], fila['motivo']), ('en_laminas', 'faltan 1 lámina(s) del guion'))

    def test_guion_heredado_en_texto_no_frena(self):
        t = tira()
        t['guion'] = 'Texto corrido de la época de la Mac'
        with Escenario(tiras={PID: t}) as e:
            self.assertEqual(e.filas()[0]['estado'], 'completa')

    def test_manda_la_tira_viva_mas_reciente_de_cada_pieza(self):
        vieja, nueva = 'tres-opiniones-nube-2026-10-11-74015b', PID
        tiras = {vieja: dict(tira(pid_dir='v'), fecha='2026-10-11'), nueva: tira()}
        cartas = [carta(vieja, fecha_fuente='2026-10-11'), carta(nueva)]
        with Escenario(tiras=tiras, cartas=cartas, decisiones={vieja: decision(), nueva: decision()}) as e:
            filas = e.filas()
        self.assertEqual([f['id'] for f in filas], [nueva])

    def test_entre_dos_tiras_vivas_manda_la_que_publico_la_mesa(self):
        otra = 'tres-opiniones-nube-2026-10-12-zzzzzz'                 # misma fecha y un id «mayor»: sin la mesa ganaría
        tiras = {PID: tira(), otra: tira(pid_dir='z')}
        cartas = [carta(), carta(otra)]
        with Escenario(tiras=tiras, cartas=cartas, decisiones={PID: decision(), otra: decision((None, None))}) as e:
            self.assertEqual([(f['id'], f['estado']) for f in e.filas()], [(otra, 'en_laminas')])
            e.proyeccion = {PID}
            self.assertEqual([(f['id'], f['estado']) for f in e.filas()], [(PID, 'completa')])

    def test_una_tira_rota_no_detiene_a_las_demas(self):
        rota, buena = 'rota-nube-2026-10-12-000000', PID
        tiras = {buena: tira(), rota: dict(tira(pid_dir='r'), pieza='Rota', pieza_slug='rota', mapa='no es un mapa')}
        with Escenario(tiras=tiras, cartas=[carta(), carta(rota)], decisiones={buena: decision(), rota: decision()}) as e:
            self.assertEqual({f['slug']: f['estado'] for f in e.filas()}, {'rota': 'en_laminas', SLUG: 'completa'})
            self.assertEqual(e.empacar(), 0)
            self.assertEqual([c['pieza'] for c in e.de('expediente')], [TITULO])

    def test_cortes_de_video_y_ejes_no_son_piezas(self):
        cartas = [carta(), carta('zeta-corte-2026-10-20-aaaaaa'), carta('zeta-nube-1', tipo='eje'),
                  carta('zeta-nube-2', video='https://drive.google.com/file/d/x/preview'), carta('zeta-nube-3')]
        tiras = {c['id']: dict(tira(), pieza_slug='slug-%d' % i, pieza='Pieza %d' % i) for i, c in enumerate(cartas)}
        tiras[PID] = tira()
        decs = {c['id']: decision() for c in cartas}
        with Escenario(tiras=tiras, cartas=cartas, decisiones=decs) as e:
            self.assertEqual(sorted(f['id'] for f in e.filas()), [PID, 'zeta-nube-3'])

    def test_una_lamina_aprobada_con_la_prueba_ligera_sale_con_su_original(self):
        t = tira()
        t['laminas'][0] = {'n': 1, 'src': 'laminas/t/L1-1.jpg', 'dice': 'Uno', 'estado': 'aprobada',
                           'candidatas': [{'src': 'laminas/t/L1-1.jpg', 'original': 'laminas/t/L1-1.png'}]}
        with Escenario(tiras={PID: t}) as e:
            self.assertEqual(e.filas()[0]['laminas'][0]['ruta'], 'laminas/t/L1-1.png')

    def test_formato_de_salida(self):
        f = salida.formato_de_salida
        self.assertEqual(f({'formato': 'Lámina'}, 1, REGLAS), ('Lámina', ''))
        self.assertEqual(f({'formato': 'Carrusel'}, 5, REGLAS), ('Carrusel', ''))
        self.assertEqual(f({'formato': 'Reel'}, 6, REGLAS)[0], 'Carrusel')
        self.assertEqual(f({}, 7, {'nube_ejecuta_etapas': 'voz,escena,corte'}), ('Carrusel', ''))
        self.assertIsNone(f({'formato': 'Reel'}, 6, {'nube_ejecuta_etapas': 'voz,escena,corte,prospecto'})[0])
        self.assertIsNone(f({'formato': 'Reel'}, 6, dict(REGLAS, salida_reels_como_carrusel='0'))[0])

    def test_un_reel_sale_como_carrusel_solo_con_el_video_en_pausa(self):
        with Escenario(tiras={PID: tira('Reel')}) as e:
            fila = e.filas()[0]
            self.assertEqual((fila['estado'], fila['formato']), ('completa', 'Carrusel'))
            self.assertIn('video', fila['nota_formato'])
        with Escenario(tiras={PID: tira('Reel')}, reglas=dict(REGLAS, nube_ejecuta_etapas='voz,escena,corte')) as e:
            self.assertEqual(e.filas()[0]['estado'], 'video')

    def test_frenos_excluir_y_proyeccion_de_la_mesa(self):
        with Escenario(reglas=dict(REGLAS, salida_excluir='apodo, tres-opiniones')) as e:
            self.assertEqual(e.filas()[0]['estado'], 'excluida')
        with Escenario() as e:
            e.proyeccion = {'otra-pieza'}
            self.assertEqual(e.filas()[0]['estado'], 'en_laminas')
            e.proyeccion = {PID}
            self.assertEqual(e.filas()[0]['estado'], 'completa')

    def test_una_ruta_rara_no_es_publicable(self):
        t = tira()
        t['laminas'][0]['src'] = '../secreto.png'
        with Escenario(tiras={PID: t}) as e:
            self.assertEqual(e.filas()[0]['estado'], 'en_laminas')

    def test_publicada_no_vuelve(self):
        with Escenario(expedientes={TITULO: {'estado': 'publicada'}}) as e:
            self.assertEqual(e.filas()[0]['estado'], 'publicada')
        with Escenario(produccion=[{'fecha': '2026-11-09', 'pieza': TITULO, 'estado': 'publicada', 'enlace': ''}]) as e:
            self.assertEqual(e.filas()[0]['estado'], 'publicada')


class PaqueteTests(unittest.TestCase):
    def test_paquete_completo_en_drive_y_en_la_sala(self):
        with Escenario() as e:
            e.drive.ruta_carpetas('RAIZ', salida.CARPETA, '4 · La Autopsia del Coeficiente')
            self.assertEqual(e.empacar(), 0)
            carpeta = '5 · ' + TITULO
            self.assertEqual(e.drive.hijos(salida.CARPETA, carpeta), ['01.png', '02.png', '03.png', 'COPY · ' + TITULO])
            nodos = {v['name']: v for v in e.drive.nodos.values()}
            self.assertEqual(nodos['02.png']['datos'], png('laminas/t/L2-2.png'))       # la toma elegida, no la otra
            doc = nodos['COPY · ' + TITULO]['html']
            for parte in ('Instagram · primer comentario', 'utm_content=tres-opiniones', 'Antes de publicar, mira esto',
                          'el fondo se ve ajeno', 'L2 toma 2'):
                self.assertIn(parte, doc)
            (exp,) = e.de('expediente')
            ex = exp['expediente']
            self.assertEqual((exp['pieza'], ex['estado'], ex['portada']), (TITULO, 'lista', 'laminas/t/L1.png'))
            self.assertEqual(ex['paquete']['carpeta'], carpeta)
            self.assertEqual(ex['paquete']['orden'], 5)
            self.assertEqual([i['archivo'] for i in ex['paquete']['imagenes']], ['01.png', '02.png', '03.png'])
            self.assertTrue(ex['paquete']['url'].startswith('https://drive.google.com/drive/folders/'))
            self.assertEqual(ex['copy']['texto'], TEXTO)
            self.assertEqual(ex['copy']['revision'], ['Lámina 3: el fondo se ve ajeno.'])
            (fila,) = e.de('produccion')
            self.assertEqual((fila['pieza'], fila['estado'], fila['enlace']), (TITULO, 'paquete listo', ex['paquete']['url']))
            self.assertNotIn('decidir', [a for a, _ in e.escrituras])

    def test_conserva_la_historia_del_expediente(self):
        previo = {'pieza': TITULO, 'estado': 'en camino', 'reglas': [{'regla': 'Primero el guion'}],
                  'hitos': [{'quien': 'tu', 'fecha': '27 AGO', 'que': 'Dijiste que…', 'dijo': 'palabras textuales'}],
                  'versiones': [{'tag': 'v1'}]}
        with Escenario(expedientes={TITULO: previo}) as e:
            e.empacar()
            ex = e.de('expediente')[0]['expediente']
        self.assertEqual(ex['reglas'], previo['reglas'])
        self.assertEqual(ex['versiones'], previo['versiones'])
        self.assertEqual(ex['hitos'][0], previo['hitos'][0])
        self.assertEqual(ex['hitos'][-1]['que'], 'Paquete listo para publicar')

    def test_repetir_no_duplica_ni_vuelve_a_subir(self):
        with Escenario() as e:
            e.empacar()
            antes = (len(e.drive.subidas), len(e.escrituras), dict(e.drive.nodos))
            sello = e.sello()
            self.assertEqual(e.filas()[0]['estado'], 'lista')
            self.assertEqual(e.empacar([{'id': PID, 'sello': sello, 'texto': TEXTO}]), 0)
            self.assertEqual((len(e.drive.subidas), len(e.escrituras)), antes[:2])
            self.assertEqual(set(e.drive.nodos), set(antes[2]))

    def test_si_el_sheet_no_confirma_se_reintenta_sin_duplicar_en_drive(self):
        with Escenario() as e:
            e.sheet_falla = 'Tres opiniones'
            self.assertEqual(e.empacar(), 2)
            self.assertEqual(e.de('expediente'), [])
            subidas = len(e.drive.subidas)
            e.sheet_falla = None
            self.assertEqual(e.empacar(), 0)
            self.assertEqual(len(e.drive.subidas), subidas)             # idénticas: no se suben otra vez
            self.assertEqual(len([n for n in e.drive.hijos(salida.CARPETA)]), 1)
            self.assertEqual(len(e.de('expediente')), 1)

    def test_el_texto_con_un_candado_roto_regresa_y_no_se_escribe_nada(self):
        with Escenario() as e:
            malo = TEXTO.replace('la norma', 'la norma de Sonora')
            self.assertEqual(e.empacar([{'id': PID, 'sello': e.sello(), 'texto': malo}]), 0)
            self.assertEqual((e.escrituras, e.drive.subidas), ([], []))
            self.assertIn('texto regresado', e.log.getvalue())
            self.assertIn('ubicacion', e.log.getvalue())

    def test_el_texto_nunca_se_imprime(self):
        with Escenario() as e:
            sello = e.sello()
            e.empacar([{'id': PID, 'sello': sello, 'texto': TEXTO.replace('norma', 'norma en Sonora'),
                        'revision': ['Lámina 3: el fondo se ve ajeno.']}])
            self.assertIn('texto regresado', e.log.getvalue())
            e.empacar()
            self.assertIn('✓', e.log.getvalue())
            self.assertNotIn(PALABRA_SECRETA, e.log.getvalue())
            self.assertNotIn('el fondo se ve ajeno', e.log.getvalue())

    def test_un_texto_escrito_para_otra_version_no_entra(self):
        with Escenario() as e:
            sello = e.sello()
            e.decisiones[PID] = decision(tomas=(1, 1))                  # Dirección cambió de toma
            self.assertNotEqual(e.sello(), sello)
            self.assertEqual(e.empacar([{'id': PID, 'sello': sello, 'texto': TEXTO}]), 0)
            self.assertEqual((e.escrituras, e.drive.subidas), ([], []))
            self.assertIn('cambió desde que se escribió su texto', e.log.getvalue())

    def test_ensayo_no_escribe_en_ningun_lado(self):
        with Escenario(produccion=[{'fecha': '2026-11-09', 'pieza': 'Otra', 'estado': 'publicada'}]) as e:
            self.assertEqual(e.empacar(ensayo=True), 0)
            self.assertEqual((e.escrituras, e.drive.subidas, e.drive.n), ([], [], 0))
            self.assertIn('ensayo', e.log.getvalue())

    def test_en_pausa_no_empaca(self):
        with Escenario(reglas=dict(REGLAS, salida_activa='0')) as e:
            self.assertEqual(e.empacar([{'id': PID, 'sello': e.sello(), 'texto': TEXTO}]), 0)
            self.assertEqual((e.escrituras, e.drive.subidas), ([], []))
            self.assertIn('en pausa', e.log.getvalue())

    def test_sin_drive_raiz_no_inventa_carpeta(self):
        with Escenario(reglas={'nube_ejecuta_etapas': 'prospecto'}) as e:
            self.assertEqual(e.empacar(), 2)
            self.assertEqual((e.escrituras, e.drive.subidas), ([], []))

    def test_una_falla_de_drive_no_detiene_a_las_demas(self):
        otra, titulo2 = 'doble-via-nube-2026-10-12-6f2f2a', 'Doble vía'
        t2 = dict(tira(pid_dir='d'), pieza=titulo2, pieza_slug='doble-via')
        with Escenario(tiras={PID: tira(), otra: t2}, cartas=[carta(), carta(otra)],
                       decisiones={PID: decision(), otra: decision()}) as e:
            e.drive.fallar_en = 'Tres opiniones'
            codigo = e.empacar([{'id': PID, 'sello': e.sello(PID), 'texto': TEXTO},
                                {'id': otra, 'sello': e.sello(otra), 'texto': TEXTO}])
            self.assertEqual(codigo, 2)
            self.assertEqual([c['pieza'] for c in e.de('expediente')], [titulo2])

    def test_dos_paquetes_nuevos_llevan_numeros_distintos(self):
        otra, titulo2 = 'doble-via-nube-2026-10-12-6f2f2a', 'Doble vía'
        t2 = dict(tira(pid_dir='d'), pieza=titulo2, pieza_slug='doble-via')
        with Escenario(tiras={PID: tira(), otra: t2}, cartas=[carta(), carta(otra)],
                       decisiones={PID: decision(), otra: decision()}) as e:
            listar = e.drive.listar
            e.drive.listar = lambda padre: [] if e.drive.nodos[padre]['name'] == salida.CARPETA else listar(padre)   # Drive aún no la lista
            modulo = sys.modules['sala_drive']
            modulo.listar = e.drive.listar
            e.empacar([{'id': otra, 'sello': e.sello(otra), 'texto': TEXTO},
                       {'id': PID, 'sello': e.sello(PID), 'texto': TEXTO}])
            self.assertEqual(sorted(c['expediente']['paquete']['carpeta'] for c in e.de('expediente')),
                             ['1 · Doble vía', '2 · ' + TITULO])

    def test_la_imagen_tiene_que_ser_la_que_se_aprobo(self):
        with Escenario() as e:
            sello = e.sello()
            with patch.object(salida, '_bajar', lambda url, tope: png('otra-cosa')):
                self.assertEqual(e.empacar([{'id': PID, 'sello': sello, 'texto': TEXTO}]), 2)
            self.assertEqual(e.escrituras, [])
            self.assertIn('no es la toma que se aprobó', e.log.getvalue())
        lam = {'n': 1, 'ruta': 'laminas/t/L1.png', 'huella': ''}
        with patch.object(salida, '_bajar', lambda url, tope: b'<html>404</html>'), patch.object(salida, 'medios', lambda: {}):
            with self.assertRaises(salida.SalidaError):
                salida.traer_imagen(lam)
        medios = {'laminas/t/L1.png': {'url': 'https://github.com/yodesarrollomx/sala-edicion/releases/download/x/a.png', 'sha256': '0' * 64}}
        with patch.object(salida, '_bajar', lambda url, tope: png('x')), patch.object(salida, 'medios', lambda: medios):
            with self.assertRaises(salida.SalidaError):
                salida.traer_imagen(lam)
        with self.assertRaises(salida.SalidaError):
            salida.traer_imagen({'n': 1, 'ruta': 'laminas/../../etc/passwd.png', 'huella': ''})

    def test_los_textos_mal_formados_fallan_sin_tocar_nada(self):
        malos = ['no es json', '[]', json.dumps({'esquema': 2, 'paquetes': []}), json.dumps({'esquema': 1, 'paquetes': {}}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': '../x', 'sello': 'a' * 12, 'texto': 't'}]}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': PID, 'sello': 'XYZ', 'texto': 't'}]}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': PID, 'sello': 'a' * 12, 'texto': 5}]}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': PID, 'sello': 'a' * 12, 'texto': 't'}] * 2}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': PID, 'sello': 'a' * 12, 'texto': 't', 'revision': 'x'}]}),
                 json.dumps({'esquema': 1, 'paquetes': [{'id': 'p%d' % i, 'sello': 'a' * 12, 'texto': 't'} for i in range(41)]}),
                 'x' * (salida.MAX_PAQUETES + 1)]
        for crudo in malos:
            with self.subTest(crudo[:30]), Escenario() as e:
                with self.assertRaises(salida.SalidaError):
                    salida.empacar(crudo)
                self.assertEqual((e.escrituras, e.drive.subidas), ([], []))
        self.assertEqual(salida.leer_paquetes(''), [])


class PublicadaTests(unittest.TestCase):
    def publicada(self, **extra):
        return dict({'fecha': '2026-11-10', 'pieza': TITULO, 'estado': 'publicada',
                     'detalle': json.dumps({'texto': 'Publicada desde la Sala', 'texto_final': 'El texto que sí usé.'}),
                     'enlace': 'https://www.instagram.com/p/ABC123/'}, **extra)

    def test_ya_la_publique_cierra_el_expediente_y_guarda_el_paquete(self):
        with Escenario() as e:
            e.empacar()
            e.produccion = [self.publicada()]
            self.assertEqual(e.empacar([]), 0)
            ex = e.expedientes[TITULO]
            self.assertEqual((ex['estado'], ex['post'], ex['publicada_el']),
                             ('publicada', 'https://www.instagram.com/p/ABC123/', '2026-11-10'))
            self.assertEqual(ex['copy']['publicado'], 'El texto que sí usé.')
            self.assertEqual(ex['copy']['texto'], TEXTO)                 # lo que escribió el jurado se conserva
            self.assertEqual(ex['hitos'][-1]['que'], 'Publicada')
            self.assertEqual(e.drive.movidas, ['1 · ' + TITULO])
            self.assertEqual(e.drive.hijos(salida.CARPETA), [])
            self.assertEqual(e.drive.hijos(salida.CARPETA_PUBLICADAS), ['1 · ' + TITULO])
            n = len(e.escrituras)
            self.assertEqual(e.empacar([]), 0)                           # repetir no vuelve a escribir ni a mover
            self.assertEqual((len(e.escrituras), len(e.drive.movidas)), (n, 1))
            self.assertEqual(e.filas()[0]['estado'], 'publicada')

    def test_una_liga_rara_no_se_guarda_como_publicacion(self):
        with Escenario() as e:
            e.empacar()
            e.produccion = [self.publicada(enlace='javascript:alert(1)', detalle='texto suelto')]
            e.empacar([])
            ex = e.expedientes[TITULO]
            self.assertEqual(ex['estado'], 'publicada')
            self.assertNotIn('post', ex)
            self.assertNotIn('publicado', ex['copy'])

    def test_solo_cierra_lo_que_la_estacion_entrego(self):
        previo = {'La Servilleta': {'pieza': 'La Servilleta', 'estado': 'en camino', 'hitos': []}}
        fila = {'fecha': '2026-08-29', 'pieza': 'La Servilleta', 'estado': 'publicada', 'enlace': 'https://x.test/p'}
        with Escenario(expedientes=previo, produccion=[fila]) as e:
            e.empacar([])
            self.assertEqual(e.escrituras, [])

    def test_si_drive_no_mueve_la_carpeta_el_registro_no_se_pierde(self):
        with Escenario() as e:
            e.empacar()
            e.produccion = [self.publicada()]

            def falla(*a):
                raise e.drive.DriveError('503')
            sys.modules['sala_drive'].mover = falla
            self.assertEqual(e.empacar([]), 0)
            self.assertEqual(e.expedientes[TITULO]['estado'], 'publicada')
            self.assertNotIn('guardado_en', e.expedientes[TITULO]['paquete'])


class JuradoTests(unittest.TestCase):
    def test_lo_que_ve_el_jurado(self):
        with Escenario() as e:
            doc = salida.para_el_jurado(e.reglas, e.filas(), salida.receta())
        self.assertTrue(doc['activa'])
        self.assertEqual(doc['resumen'], {'completa': 1})
        (p,) = doc['pendientes']
        self.assertEqual((p['id'], p['slug'], p['formato']), (PID, SLUG, 'Carrusel'))
        self.assertRegex(p['sello'], r'^[0-9a-f]{12}$')
        self.assertEqual([l['url'] for l in p['laminas']],
                         [salida.PAGES + r for r in ('laminas/t/L1.png', 'laminas/t/L2-2.png', 'laminas/t/L3-1.png')])
        self.assertIn('Plan de Potencial Personalizado', doc['receta'])

    def test_tope_por_sesion_y_pausa(self):
        cartas, tiras, decs = [], {}, {}
        for i in range(5):
            pid = 'pieza%d-nube-2026-10-12-00000%d' % (i, i)
            cartas.append(carta(pid))
            tiras[pid] = dict(tira(pid_dir='p%d' % i), pieza='Pieza %d' % i, pieza_slug='pieza%d' % i)
            decs[pid] = decision()
        with Escenario(tiras=tiras, cartas=cartas, decisiones=decs) as e:
            doc = salida.para_el_jurado(e.reglas, e.filas(), 'r')
            self.assertEqual((len(doc['pendientes']), doc['en_espera']), (3, 2))
            pausa = salida.para_el_jurado(dict(e.reglas, salida_activa='0'), e.filas(), 'r')
            self.assertEqual((pausa['activa'], pausa['pendientes']), (False, []))
            uno = salida.para_el_jurado(dict(e.reglas, salida_piezas_por_sesion='1'), e.filas(), 'r')
            self.assertEqual(len(uno['pendientes']), 1)

    def test_la_receta_la_puede_cambiar_direccion_en_el_sheet(self):
        with Escenario():
            with patch.object(sala, 'get', lambda recurso, **kw: {'prompts': [{'pieza': '_copy', 'prompt_base': 'Mi receta nueva.'}]}):
                self.assertEqual(salida.receta(), 'Mi receta nueva.')

            def sin_sheet(recurso, **kw):
                raise sala.SalaError('sin confirmar')
            with patch.object(sala, 'get', sin_sheet):
                self.assertEqual(salida.receta(), salida.RECETA)


class WorkflowTests(unittest.TestCase):
    TEXTO = (ROOT / '.github' / 'workflows' / 'sala-consejo.yml').read_text(encoding='utf-8')
    PASO = TEXTO.split('- name: Estación de salida', 1)[1].split('- name:', 1)[0]

    def test_el_texto_viaja_por_variable_y_no_dentro_del_guion(self):
        import re
        self.assertIn('SALIDA_PAQUETES: ${{ inputs.paquetes }}', self.PASO)
        for guion in re.findall(r'^\s+run: (?:\|\n(?:\s{10,}.*\n?)+|.*)$', self.TEXTO, flags=re.M):
            self.assertNotIn('inputs.paquetes', guion)
            self.assertNotIn('SALIDA_PAQUETES', guion)

    def test_la_estacion_entra_como_agente_y_sin_la_llave_del_consejo(self):
        self.assertIn("if: env.MODO == 'paquete'", self.PASO)
        self.assertIn('SALA_CLAVE_AGENTE', self.PASO)
        self.assertNotIn('SALA_CLAVE_CONSEJO', self.PASO)
        self.assertIn('run: python3 nube/sala_salida.py paquete', self.PASO)
        jurado = self.TEXTO.split('- name: Sesión del Roast Room', 1)[1].split('- name:', 1)[0]
        self.assertIn("if: env.MODO != 'paquete'", jurado)

    def test_la_estacion_no_decide(self):
        fuente = (ROOT / 'nube' / 'sala_salida.py').read_text(encoding='utf-8')
        self.assertNotIn("'decidir'", fuente)
        self.assertNotIn('_clave_consejo', fuente)
        self.assertNotIn('SALA_CLAVE_CONSEJO', fuente)

    def test_el_checkout_trae_los_datos_que_lee_la_estacion(self):
        self.assertRegex(self.TEXTO, r'sparse-checkout: \|\n\s+nube\n\s+datos\n')


if __name__ == '__main__':
    unittest.main()
