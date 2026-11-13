import copy, io, json, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
import sala_v4 as v
from motores._comun import MotorError

JPEG = b'\xff\xd8'


def foto(color=(200, 120, 80), formato='PNG', lado=96):
    """Una imagen de verdad: PNG como la entrega el motor de imagen, o JPEG como queda guardada."""
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (lado * 2 // 3, lado), color).save(b, formato)
    return b.getvalue()


def ID(nombre):
    """Un id con forma de id de Drive (los de verdad miden 28 caracteres o más)."""
    return ('id-%s-' % nombre).ljust(28, '0')


def clip(segundos=1, audio=True):
    """Un MP4 de verdad para que ffmpeg una y saque cuadros como en producción."""
    with tempfile.TemporaryDirectory() as t:
        f = pathlib.Path(t) / 'c.mp4'
        fuente = ['-f', 'lavfi', '-i', 'testsrc=size=180x320:rate=24'] + (['-f', 'lavfi', '-i', 'sine=frequency=440'] if audio else [])
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + fuente + ['-t', str(segundos), '-pix_fmt', 'yuv420p', str(f)], check=True)
        return f.read_bytes()


def flujos(datos):
    with tempfile.TemporaryDirectory() as t:
        f = pathlib.Path(t) / 'x.mp4'
        f.write_bytes(datos)
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(f)],
                           capture_output=True, text=True, check=True)
        d = json.loads(r.stdout)
        return sorted(s['codec_type'] for s in d['streams']), float(d['format']['duration'])


class Drive:
    class DriveError(RuntimeError):
        pass

    def __init__(self):
        self.archivos, self.falla = {}, False

    def ruta_carpetas(self, *n):
        return '/'.join(n)

    def subir(self, ruta, carpeta, nombre=None):
        if self.falla:
            raise self.DriveError('sin permiso')
        fid = carpeta + '/' + pathlib.Path(ruta).name
        self.archivos[fid] = pathlib.Path(ruta).read_bytes()
        return fid

    def bajar(self, fid, destino):
        if fid not in self.archivos:
            raise self.DriveError('no existe ' + str(fid))
        pathlib.Path(destino).write_bytes(self.archivos[fid])
        return destino


def serie(n=3, **kw):
    s = {'id': 's1', 'titulo': 'La prueba', 'trama': 't', 'vertice': 'ppp', 'personaje': 'marta', 'lugar': 'terreno',
         'creada': '2026-11-09T00:00:00Z',
         'episodios': [{'n': i, 'titulo': 'E%d' % i, 'accion': 'She walks.', 'dialogo': 'Hola.', 'gancho': 'A hand.',
                        'bloque': 15, 'continua': False} for i in range(1, n + 1)]}
    s.update(kw)
    return s


CRUDO = {'titulo': 'El local vacío', 'trama': 'x', 'invitado_final': '',
         'personaje': {'nombre': 'Raúl', 'industria': 'ferretero', 'aspecto': 'A man', 'voz': 'warm', 'quiere': 'y'},
         'lugar': {'nombre': 'El local', 'aspecto': 'An empty shop'},
         'episodios': [{'titulo': 'E', 'accion': 'He walks.', 'dialogo': 'Hola.', 'gancho': 'A door.'}] * 10}
SIN_CANDADOS = lambda: []
VACIO = lambda: {'universo': None, 'mundo': {}, 'serie': {}, 'dec': {}, 'prod': {}, 'canon': None, 'estado': None}


class V4Tests(unittest.TestCase):
    def setUp(self):
        self.u = v.universo_de({'universo': None})
        self.sin = dict(self.u, ajustes=dict(self.u['ajustes'], fichas_por_dia=0))     # imágenes de referencia apagadas
        self.guardados = []
        p = patch.object(v.sala, 'post', side_effect=lambda accion, **c: self.guardados.append((accion, c['pieza'], copy.deepcopy(c['expediente']))) or {'ok': True})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(v, 'hoy', return_value='2026-11-09'); p.start(); self.addCleanup(p.stop)

    def e(self, dec=None, prod=None, s=None):
        s = s or serie()
        return {'universo': None, 'serie': {s['id']: s}, 'dec': {s['id']: dec} if dec else {}, 'prod': {s['id']: prod} if prod else {}, 'canon': None, 'estado': None}

    def ajustes(self, **kw):
        return dict(self.u, ajustes=dict(self.u['ajustes'], **kw))

    def pintado(self, clase, ident, fid, universo=None, s=None, **mas):
        """El registro que deja la nube al pintar la imagen de un elemento con su ficha de hoy."""
        ficha = v.MUNDO[clase](universo or self.u, s or {})[ident]
        return dict({'drive': fid, 'huella': v.huella(v.descripcion_ficha(clase, ficha))}, **mas)

    # ---------------------------------------------------------------- almacén y dueños
    def test_almacen_separa_y_respeta_duenos(self):
        e = v.separar({'v4:universo': {'a': 1}, 'v4:serie:x': {'id': 'x'}, 'v4:dec:x': {'serie': 'si'}, 'v4:prod:x': {}, 'v4:canon': {'objetos': {}},
                       'v4:mundo:personajes': {'ana': {'nombre': 'Ana'}}, 'v4:mundo:planetas': {'x': {}}, 'v4:mundo:': {},
                       'La Servilleta': {'pieza': 'otra cosa'}, 'v4:serie:': {}, 'v4:rara:x': {}, 'v4:prod:y': 'no-dict'})
        self.assertEqual(({'a': 1}, ['x'], ['x'], ['x'], {'objetos': {}}), (e['universo'], list(e['serie']), list(e['dec']), list(e['prod']), e['canon']))
        self.assertEqual({'personajes': {'ana': {'nombre': 'Ana'}}}, e['mundo'])          # cada clase del mundo, en su celda
        with self.assertRaises(v.V4Error): v.guardar('mundo', 'personajes', {})        # el mundo es del editor: la nube no lo escribe
        with self.assertRaises(v.V4Error): v.guardar('dec', 'x', {})                 # la nube no decide
        with self.assertRaises(v.V4Error): v.guardar('serie', 'x', {}, existe=True)   # ni pisa al editor
        with self.assertRaises(v.V4Error): v.guardar('universo', '', {}, existe=True)
        self.assertEqual([], self.guardados)
        v.guardar('prod', 'x', {'a': 1}); v.guardar('estado', '', {}); v.guardar('canon', '', {})
        self.assertEqual(['v4:prod:x', 'v4:estado', 'v4:canon'], [g[1] for g in self.guardados])
        with self.assertRaises(v.V4Error): v.guardar('prod', 'x', {'a': 'ñ' * 46000})   # no cabe en una celda del Sheet
        self.assertEqual(3, len(self.guardados))
        with patch.object(v.sala, 'get', return_value={'ok': True}), self.assertRaises(v.V4Error): v.leer()

    def test_semilla_ajustes_y_reglas(self):
        self.assertEqual(2, self.u['ajustes']['tope_clips_dia']); self.assertIn('marta', self.u['personajes'])
        self.assertIn('SIEMPRE es un cliente', self.u['guionista'])
        editado = v.universo_de({'universo': {'ajustes': {'tope_clips_dia': 7}, 'guionista': 'Otro criterio.'}})
        self.assertEqual((7, 10, 'Otro criterio.'), (editado['ajustes']['tope_clips_dia'], editado['ajustes']['episodios'], editado['guionista']))
        # el canon de fábrica: mundo compartido, encuadres, reglas y temporada
        self.assertTrue({'marta', 'don-carlos', 'sofia', 'miguel', 'arquitecto'} <= set(self.u['personajes']))
        self.assertTrue({'servilleta', 'plano', 'camioneta', 'silla'} <= set(self.u['objetos'])); self.assertIn('seguimiento', self.u['encuadres'])
        self.assertIn('CONTINUIDAD', self.u['canon']); self.assertEqual('la-mesa', self.u['temporada'][-1]['id'])
        for plan in self.u['temporada']:                                                     # la temporada sólo cita lo que existe
            self.assertIn(plan['protagonista'], self.u['personajes']); self.assertIn(plan['lugar'], self.u['lugares'])
            self.assertTrue(set([plan['objeto']] + plan['guinos']) <= set(self.u['objetos'])); self.assertIn(plan['vertice'], self.u['vertices'])
            self.assertTrue(set(plan.get('invitados') or []) <= set(self.u['personajes']))
        self.assertEqual([], v.contenido_reglas.prohibidas(json.dumps(v.semilla(), ensure_ascii=False)))
        # un universo guardado antes del canon (versión 1) recibe lo nuevo sin perder lo suyo
        viejo = v.universo_de({'universo': {'version': 1, 'ajustes': {'tope_clips_dia': 5, 'listas_carpeta': 'X'}, 'formato': {'estilo': 'viejo'},
                                            'vertices': {'solo': {'nombre': 'Uno'}}, 'personajes': {'marta': {'nombre': 'Marta', 'aspecto': 'vieja'}, 'mia': {'nombre': 'Mía'}}}})
        self.assertEqual((5, ['solo'], 2), (viejo['ajustes']['tope_clips_dia'], list(viejo['vertices']), viejo['version']))
        self.assertIn('long take', viejo['formato']['estilo']); self.assertIn('vestuario', viejo['personajes']['marta']); self.assertIn('mia', viejo['personajes'])
        self.assertIn('servilleta', viejo['objetos']); self.assertTrue(viejo['temporada'] and viejo['encuadres'] and viejo['canon'])
        ya = v.universo_de({'universo': {'version': 2, 'personajes': {'x': {'nombre': 'X'}}, 'objetos': {}, 'temporada': [], 'formato': {'estilo': 'mío'}}})
        self.assertEqual((['x'], [], 'mío', {}), (list(ya['personajes']), ya['temporada'], ya['formato']['estilo'], ya['objetos']))   # la versión 2 es del editor: no se rellena
        # el mundo partido: cada clase en su celda manda sobre lo que el universo traiga adentro, y un mundo vacío a propósito se respeta
        partido = v.universo_de({'universo': {'version': 2, 'personajes': {'x': {'nombre': 'X'}}, 'temporada': []},
                                 'mundo': {'personajes': {'ana': {'nombre': 'Ana'}}, 'objetos': {}}})
        self.assertEqual((['ana'], {}), (list(partido['personajes']), partido['objetos']))
        self.assertIn('terreno', partido['lugares'])          # ni aparte ni adentro: vale el de fábrica, nunca un mundo vacío por accidente
        for forma in ({'drive_raiz': 'ABC'}, {'drive_raiz': {'valor': 'ABC', 'descripcion': 'x'}}):   # el backend entrega las dos
            with patch.object(v.sala, 'get', return_value={'reglas': forma, 'motores': []}):
                self.assertEqual('ABC', v.regla('drive_raiz')); self.assertEqual('', v.regla('no_existe'))

    # ---------------------------------------------------------------- la serie
    def test_validar_serie(self):
        self.assertEqual([], v.validar_serie(serie(), self.u))
        larga = serie(); larga['episodios'][0]['dialogo'] = ' '.join(['palabra'] * 39)
        self.assertIn('no caben', ' '.join(v.validar_serie(larga, self.u)))
        self.assertTrue(v.validar_serie(serie(personaje='nadie'), self.u))
        bloque = serie(); bloque['episodios'][0]['bloque'] = 30
        self.assertIn('segunda toma', ' '.join(v.validar_serie(bloque, self.u)))
        vetada = serie(); vetada['episodios'][1]['dialogo'] = 'Vivo en Hermosillo.'
        self.assertIn('vetada', ' '.join(v.validar_serie(vetada, self.u)))
        fantasma = serie(); fantasma['episodios'][2]['invitados'] = ['nadie']
        self.assertIn('invitado', ' '.join(v.validar_serie(fantasma, self.u)))
        cosa = serie(); cosa['episodios'][0].update(objetos=['llaves', 'no-hay'], encuadre='rostro')
        self.assertEqual(['episodio 1: el objeto «no-hay» no existe'], v.validar_serie(cosa, self.u))
        cosa['episodios'][0].update(objetos=['llaves'], encuadre='dron')
        self.assertIn('encuadre', ' '.join(v.validar_serie(cosa, self.u)))
        self.assertTrue(v.validar_serie({'titulo': 'x', 'episodios': []}, self.u))

    def test_prompt_un_personaje_nota_y_gancho(self):
        s = serie(); ep = dict(s['episodios'][0], bloque=30, accion2='She turns.', dialogo2='Adiós.')
        t1, t2 = v.prompt_toma(self.u, s, ep, 1), v.prompt_toma(self.u, s, ep, 2, 'más luz')
        self.assertIn('«Hola.»', t1); self.assertNotIn('ENDING', t1); self.assertIn('CHARACTER (Marta): A Mexican woman', t1)
        self.assertIn('«Adiós.»', t2); self.assertIn('ENDING: A hand.', t2); self.assertIn('más luz', t2)
        self.assertIn('ENDING', v.prompt_toma(self.u, s, s['episodios'][0]))
        self.assertNotIn('IMAGE_REF', t1); self.assertNotIn('reference images', t1)
        mudo = dict(s['episodios'][0], dialogo='', tono='softly')
        self.assertIn('No one speaks', v.prompt_toma(self.u, s, mudo)); self.assertNotIn('DELIVERY', v.prompt_toma(self.u, s, mudo))
        # el canon entra a cada toma: encuadre, vestuario, gesto, anclas del lugar, objetos y cómo se dice
        ep = dict(s['episodios'][0], encuadre='manos', objetos=['llaves', 'recibos'], tono='Quietly, almost to herself.')
        c = v.prompt_toma(self.u, s, ep)
        for trozo in ('CAMERA: Close-up of the character', 'Always wearing: Olive-green linen shirt', 'Habit: Turns a ring of keys',
                      'Always visible there: A chain-link fence', 'PROP (Las llaves del portón): A ring of four worn brass keys',
                      'PROP (Los recibos del predial)', 'same object in every episode', 'DELIVERY: Quietly', 'never a still photo with a zoom', 'No music, no narrator'):
            self.assertIn(trozo, c)
        self.assertLess(c.index('CAMERA'), c.index('LOCATION')); self.assertLess(c.index('PROP'), c.index('ACTION'))
        self.assertNotIn('CAMERA', t1)

    def test_prompt_con_referencias_e_invitado(self):
        s = serie(personajes={'raul': {'nombre': 'Raúl', 'aspecto': 'A tall man.', 'voz': 'deep'}})
        ep = dict(s['episodios'][2], invitados=['raul', 'raul', 'nadie'], objetos=['plano'])
        self.assertEqual(['marta', 'raul'], v.elenco(self.u, s, ep))
        todo = [('personajes', 'marta'), ('personajes', 'raul'), ('objetos', 'plano'), ('lugares', 'terreno'), ('objetos', 'silla')]
        t = v.prompt_toma(self.u, s, ep, 1, '', todo)                                # la silla no sale en este episodio: no cuenta
        self.assertTrue(t.startswith('[# References <IMAGE_REF_0>@Image1 <IMAGE_REF_1>@Image2 <IMAGE_REF_2>@Image3 <IMAGE_REF_3>@Image4]'))
        self.assertIn('CHARACTER 1 (Marta), the protagonist', t); self.assertIn('CHARACTER 2 (Raúl), a guest', t)
        self.assertIn('person shown in <IMAGE_REF_0>', t.split('CHARACTER 2')[0]); self.assertIn('person shown in <IMAGE_REF_1>', t.split('CHARACTER 2')[1])
        self.assertIn('It is the object shown in <IMAGE_REF_2>.', t); self.assertIn('This is the place shown in <IMAGE_REF_3>', t)
        self.assertIn('Do not use them as the first frame', t); self.assertIn('said once by Marta', t)
        solo_invitado = v.prompt_toma(self.u, s, ep, 1, '', [('personajes', 'raul')])       # el orden de las imágenes manda
        self.assertIn('<IMAGE_REF_0>', solo_invitado.split('CHARACTER 2')[1]); self.assertNotIn('<IMAGE_REF_1>', solo_invitado)
        # con primer cuadro las referencias se recorren un lugar; sólo un lugar de referencia no pide el aviso de identidad
        junto = v.prompt_toma(self.u, s, ep, 1, '', [('personajes', 'marta')], primer_cuadro=True)
        self.assertTrue(junto.startswith('[# Sources <FIRST_FRAME>@Image1]\n[# References <IMAGE_REF_0>@Image2]'))
        self.assertIn('Start exactly on the first frame image', junto)
        self.assertNotIn('Do not use them as the first frame', v.prompt_toma(self.u, s, ep, 1, '', [('lugares', 'terreno')]))

    def test_pendiente_piloto_cambio_y_no(self):
        s = serie(); ver = lambda n, k=1: {'versiones': [{'v': i, 'drive': 'd'} for i in range(1, k + 1)]}
        r = v.pendiente(s, {}, {}); self.assertEqual((1, 1, ''), (r[0]['n'], r[1], r[2]))
        prod = {'episodios': {'1': ver(1)}}
        self.assertIsNone(v.pendiente(s, {}, prod))                                   # espera el visto bueno del piloto
        self.assertEqual(2, v.pendiente(s, {}, prod, piloto_primero=False)[0]['n'])
        dec = {'episodios': {'1': {'v': 1, 'marca': 'cambio', 'nota': 'otra voz'}}}
        self.assertEqual((1, 2, 'otra voz'), (lambda r: (r[0]['n'], r[1], r[2]))(v.pendiente(s, dec, prod)))
        prod2 = {'episodios': {'1': ver(1, 2)}}
        self.assertIsNone(v.pendiente(s, dec, prod2))                                 # el «cambio» era de la v1: ya no aplica
        si = {'episodios': {'1': {'v': 2, 'marca': 'si'}}}
        self.assertEqual(2, v.pendiente(s, si, prod2)[0]['n'])
        todo = {'episodios': {'1': ver(1), '2': ver(2), '3': ver(3)}}
        no = {'episodios': {'1': {'v': 1, 'marca': 'si'}, '2': {'v': 1, 'marca': 'no'}}}
        self.assertIsNone(v.pendiente(s, no, todo))                                   # «no va» no se rehace

    def test_no_va_deja_fuera_al_episodio(self):
        s = serie(); ver = lambda k=1: {'versiones': [{'v': i, 'drive': 'c%d' % i} for i in range(1, k + 1)]}
        # «no va» antes de producirlo: el episodio 1 queda fuera y el 2 pasa a ser el piloto
        dec = {'serie': 'si', 'episodios': {'1': {'v': 0, 'marca': 'no'}}}
        self.assertEqual(2, v.pendiente(s, dec, {})[0]['n'])
        prod = {'episodios': {'2': ver()}, 'intentos': {}}
        self.assertIsNone(v.pendiente(s, dec, prod))                                    # el 2 es el piloto: espera su «sí»
        dec['episodios']['2'] = {'v': 1, 'marca': 'si'}
        self.assertEqual(3, v.pendiente(s, dec, prod)[0]['n']); self.assertEqual(2, v.piloto_de(s, dec, prod))
        # el retrato sale del piloto de verdad (el 2) y el 3 lo usa
        d, llamadas = Drive(), []; d.archivos['c1'] = clip(6)
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append(referencias) or clip(6)
        e, u = self.e(dec, prod, s), self.ajustes(tope_clips_dia=9, fichas_por_dia=0)
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual('s1:E02-v1', e['canon']['personajes']['marta']['de']); self.assertEqual(1, len(llamadas[0]))
        self.assertFalse(v.completa(s, dec, prod))                                      # el 3 espera decisión
        # con el 3 aprobado la serie está completa sin el 1, y el paquete sólo lleva lo aprobado
        dec['episodios']['3'] = {'v': 1, 'marca': 'si'}
        self.assertTrue(v.completa(s, dec, prod)); self.assertEqual([2, 3], [ep['n'] for ep in v.aprobados(s, dec, prod)])
        escribe = lambda t, i: {'episodios': ['Texto %d.' % k for k in range(1, t.count('Día ') + 1)]}
        self.assertIn('listo en Drive', v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS)[0])
        carpeta = prod['paquete']['carpeta']; texto = d.archivos[carpeta + '/COPY.txt'].decode()
        self.assertEqual({'2': 1, '3': 1}, prod['paquete']['versiones'])
        self.assertIn('Día 1 · E2', texto); self.assertIn('Archivo: E02.mp4', texto); self.assertIn('Día 2 · E3', texto); self.assertNotIn('E01.mp4', texto)
        self.assertNotIn(carpeta + '/E01.mp4', d.archivos); self.assertEqual(['ningún paquete nuevo'], v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS))
        # un cambio pedido después del paquete: versión nueva y, al aprobarla, el paquete se rehace
        dec['episodios']['3'] = {'v': 1, 'marca': 'cambio', 'nota': 'más cerca'}
        self.assertEqual(['ningún paquete nuevo'], v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS))
        v.productor(e, u, False, gen, d, 'R'); self.assertEqual(2, v.ultima(prod, 3)['v'])
        dec['episodios']['3'] = {'v': 2, 'marca': 'si'}
        self.assertIn('listo en Drive', v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS)[0]); self.assertEqual({'2': 1, '3': 2}, prod['paquete']['versiones'])
        # «no va» sobre un episodio ya producido: tampoco se rehace y sale del paquete
        dec['episodios']['3'] = {'v': 2, 'marca': 'no'}
        self.assertIsNone(v.pendiente(s, dec, prod)); self.assertTrue(v.completa(s, dec, prod))
        v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS)
        self.assertEqual({'2': 1}, prod['paquete']['versiones']); self.assertNotIn('Día 2', d.archivos[carpeta + '/COPY.txt'].decode())
        # todo en «no» no es una serie completa; una serie descartada no se empaqueta
        dec['episodios']['2'] = {'v': 1, 'marca': 'no'}; self.assertFalse(v.completa(s, dec, prod))
        dec['episodios']['2'] = {'v': 1, 'marca': 'si'}; dec['serie'] = 'no'; prod.pop('paquete')
        self.assertEqual(['ningún paquete nuevo'], v.paquete(e, u, False, d, 'R', escribe, SIN_CANDADOS))

    # ---------------------------------------------------------------- productor
    def test_productor_reserva_tope_y_fallo(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, jpg, referencias)) or clip()
        e = self.e(dec={'serie': 'si'})
        h = v.productor(e, self.sin, False, gen, d, 'RAIZ')
        self.assertEqual(1, len(llamadas)); self.assertIn('listo para revisar', h[0])          # sólo el piloto
        self.assertEqual((None, None), llamadas[0][1:])                                          # el episodio 1 sale del texto
        prod = e['prod']['s1']; reg = prod['episodios']['1']['versiones'][0]
        self.assertEqual(1, prod['intentos']['2026-11-09']); self.assertEqual('RAIZ/_HISTORIAS/s1/E01-v1.mp4', reg['drive'])
        self.assertEqual((False, 1.05, []), (reg['con_retrato'], reg['costo_usd_aprox'], reg['referencias']))
        self.assertEqual({'episodios': {}, 'intentos': {'2026-11-09': 1}}, self.guardados[0][2])  # reserva ANTES del video
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        h = v.productor(e, self.sin, False, gen, d, 'RAIZ')                                     # tope 2: cabe uno más hoy
        self.assertEqual(2, len(llamadas)); self.assertIn('tope del día', h[-1]); self.assertEqual(2, v.gastado_hoy(e))
        self.assertEqual([True], ['tope del día' in x for x in v.productor(e, self.sin, False, gen, d, 'RAIZ')])
        self.assertEqual(2, len(llamadas))
        # un fallo también gasta la reserva y detiene la corrida
        e2 = self.e(dec={'serie': 'si'}); mal = lambda *a, **k: (_ for _ in ()).throw(MotorError('omni 429'))
        h = v.productor(e2, self.sin, False, mal, d, 'RAIZ')
        self.assertIn('falló', h[0]); self.assertEqual(1, e2['prod']['s1']['intentos']['2026-11-09']); self.assertEqual({}, e2['prod']['s1']['episodios'])
        self.assertIn('falló', e2['prod']['s1']['avisos'][0]['texto'])
        # sin Drive no se reserva ni se llama al motor de pago
        class SinDrive(Drive):
            def ruta_carpetas(self, *n):
                raise self.DriveError('la unidad no contesta')
        e3 = self.e(dec={'serie': 'si'}); antes = len(llamadas)
        self.assertIn('Drive no está listo', v.productor(e3, self.sin, False, gen, SinDrive(), 'RAIZ')[0])
        self.assertEqual((antes, {}), (len(llamadas), e3['prod']['s1']['intentos']))
        # sin aprobar, apagado y simulación no gastan
        self.assertIn('nada por producir', v.productor(self.e(), self.sin, False, mal, d, 'RAIZ')[0])
        self.assertIn('apagado', v.productor(self.e(dec={'serie': 'si'}), self.ajustes(tope_clips_dia=0), False, mal, d, 'RAIZ')[0])
        antes = len(self.guardados)
        self.assertIn('simulación', v.productor(self.e(dec={'serie': 'si'}), self.sin, True)[0]); self.assertEqual(antes, len(self.guardados))
        # una serie que dejó de ser válida no se produce
        rota = serie(); rota['episodios'][0]['accion'] = ''
        self.assertIn('no se produce', v.productor(self.e(dec={'serie': 'si'}, s=rota), self.sin, False, mal, d, 'RAIZ')[0])

    def test_el_episodio_espera_sus_imagenes_y_lo_gratis_va_antes_de_reservar(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, jpg, referencias)) or clip(6)
        # con las imágenes de referencia encendidas, el episodio espera a que lo que sale en él tenga la suya: ni gasta ni reserva
        e = self.e(dec={'serie': 'si'}); n = len(self.guardados)
        espera = ['«La prueba» episodio 1 espera la imagen de: Marta, El terreno de Marta']
        self.assertEqual(espera, v.productor(e, self.u, False, gen, d, 'R')); self.assertEqual(espera, v.productor(e, self.u, True))
        self.assertEqual(([], n, {}), (llamadas, len(self.guardados), e['prod']['s1']['intentos']))
        # la ficha cambió después de pintarla: también espera, para no producir con la cara vieja
        e['canon'] = {'personajes': {'marta': self.pintado('personajes', 'marta', 'M')}, 'lugares': {'terreno': self.pintado('lugares', 'terreno', 'T')}}
        d.archivos.update(M=foto(formato='JPEG'), T=foto((9, 9, 9), 'JPEG'))
        otra = dict(self.u, personajes=dict(self.u['personajes'], marta=dict(self.u['personajes']['marta'], vestuario='Red dress.')))
        self.assertEqual(['«La prueba» episodio 1 espera la imagen de: Marta'], v.productor(e, otra, False, gen, d, 'R'))
        apagadas = dict(otra, ajustes=dict(otra['ajustes'], fichas_por_dia=0))                  # apagadas no espera: usa la imagen que hay
        self.assertIn('listo para revisar', v.productor(e, apagadas, False, gen, d, 'R')[0]); self.assertEqual(2, len(llamadas[0][2]))
        # una nota con una ubicación vetada se detiene ANTES de reservar: no gasta el día en un episodio que no puede salir
        e2 = self.e(dec={'serie': 'si', 'episodios': {'1': {'v': 1, 'marca': 'cambio', 'nota': 'que se vea Hermosillo'}}},
                    prod={'episodios': {'1': {'versiones': [{'v': 1, 'drive': 'PIL'}]}}, 'intentos': {}})
        d.archivos['PIL'] = clip(6); antes = len(llamadas)
        h = v.productor(e2, self.sin, False, gen, d, 'R')
        self.assertTrue(any('no se produjo y no se gastó' in x and 'vetada' in x for x in h)); self.assertEqual((antes, {}), (len(llamadas), e2['prod']['s1']['intentos']))
        n = len(self.guardados); v.productor(e2, self.sin, False, gen, d, 'R')
        self.assertEqual((n, 1), (len(self.guardados), len(e2['prod']['s1']['avisos'])))        # el aviso se anota una vez, no en cada corrida
        # si el retrato del piloto no se puede sacar, el episodio siguiente no se produce a ciegas ni gasta
        e3 = self.e(dec={'serie': 'si', 'episodios': {'1': {'v': 1, 'marca': 'si'}}}, prod={'episodios': {'1': {'versiones': [{'v': 1, 'drive': 'PERDIDO'}]}}, 'intentos': {}})
        h = v.productor(e3, self.sin, False, gen, d, 'R')
        self.assertIn('no pude sacar del piloto la imagen de «Marta»', h[0]); self.assertIn('no se produjo y no se gastó: falta sacar del piloto la imagen de Marta', h[1])
        self.assertEqual((antes, {}), (len(llamadas), e3['prod']['s1']['intentos']))

    def test_bloque_de_30_y_continuidad(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((jpg, referencias)) or clip()
        s = serie(2); s['episodios'][0].update(bloque=30, accion2='She turns.', dialogo2='Adiós.'); s['episodios'][1]['continua'] = True
        u = self.ajustes(tope_clips_dia=3, piloto_primero=0, fichas_por_dia=0)
        e = self.e(dec={'serie': 'si'}, s=s)
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual(3, len(llamadas)); self.assertEqual((None, None), llamadas[0])
        self.assertTrue(llamadas[1][0][:2] == JPEG and llamadas[1][1] is None)                  # la segunda toma arranca en el cuadro de la primera
        self.assertTrue(llamadas[2][0][:2] == JPEG and len(llamadas[2][1]) == 1)                # el episodio 2: último cuadro y además el retrato
        reg = e['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertEqual(30, reg['segundos']); self.assertEqual(2.1, reg['costo_usd_aprox']); self.assertEqual(3, v.gastado_hoy(e))
        self.assertEqual((['audio', 'video'], 2), (lambda f: (f[0], round(f[1])))(flujos(d.archivos[reg['drive']])))
        self.assertEqual('s1:E01-v1', e['canon']['personajes']['marta']['de'])
        e2 = self.e(dec={'serie': 'si'}, s=s)
        self.assertIn('tope del día', v.productor(e2, self.ajustes(tope_clips_dia=1, piloto_primero=0, fichas_por_dia=0), False, gen, d, 'R')[0])
        self.assertEqual(3, len(llamadas))                                                      # un bloque no entra a medias

    def test_retrato_del_personaje_viaja_a_los_episodios(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, jpg, referencias)) or clip(6)
        u = self.ajustes(tope_clips_dia=9, fichas_por_dia=0)
        e = self.e(dec={'serie': 'si'})
        v.productor(e, u, False, gen, d, 'R')                                                   # episodio 1, con las imágenes apagadas: sale del texto
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        h = v.productor(e, u, False, gen, d, 'R')                                               # episodios 2 y 3
        retrato = 'R/_HISTORIAS/_CANON/personajes/Marta (marta).jpg'                            # queda en el canon, con su nombre, como las demás
        marta = e['canon']['personajes']['marta']
        self.assertEqual(3, len(llamadas)); self.assertEqual({'drive': retrato, 'de': 's1:E01-v1'}, {k: marta[k] for k in ('drive', 'de')})
        self.assertEqual(JPEG, d.archivos[retrato][:2]); self.assertIn('imagen de referencia lista: Marta (salió del piloto)', h)
        self.assertNotIn('retratos', e['prod']['s1'])
        for texto, jpg, refs in llamadas[1:]:
            self.assertIsNone(jpg); self.assertEqual([d.archivos[retrato]], refs); self.assertIn('<IMAGE_REF_0>', texto)
        self.assertTrue(e['prod']['s1']['episodios']['2']['versiones'][0]['con_retrato'])
        # el episodio 1 se rehace: no usa el retrato sacado de sí mismo, y el retrato se renueva después
        e['dec']['s1']['episodios']['1'] = {'v': 1, 'marca': 'cambio', 'nota': 'más joven'}
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual((None, None), llamadas[3][1:]); self.assertIn('más joven', llamadas[3][0])
        e['dec']['s1']['episodios'].update({'1': {'v': 2, 'marca': 'si'}, '2': {'v': 1, 'marca': 'cambio', 'nota': 'otra toma'}})
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual('s1:E01-v2', e['canon']['personajes']['marta']['de']); self.assertEqual(1, len(llamadas[4][2]))
        # las imágenes se encienden después: la cara de Marta ya la fijó el piloto y no se pinta aparte; el lugar sí
        pedidas = []
        v.fichas(e, self.ajustes(fichas_por_dia=9), False, lambda texto: pedidas.append(texto) or foto(), d, 'R')
        self.assertEqual(1, len(pedidas)); self.assertIn('no people', pedidas[0]); self.assertEqual('s1:E01-v2', e['canon']['personajes']['marta']['de'])
        # el paso de referencias saca el retrato él mismo (no cuesta, ni con las imágenes apagadas) y otra serie usa esa misma cara
        e2 = self.e(dec={'serie': 'si', 'episodios': {'1': {'v': 1, 'marca': 'si'}}},
                    prod={'episodios': {'1': {'versiones': [{'v': 1, 'drive': 'PIL', 'referencias': []}]}}, 'intentos': {}})
        d.archivos['PIL'] = clip(6); pedidas.clear()
        self.assertEqual(['simulación: referencias apagadas (imágenes por día en 0): 1 sin pintar; sacaría del piloto la de Marta'], v.fichas(e2, self.sin, True))
        h = v.fichas(e2, self.sin, False, lambda texto: pedidas.append(texto) or foto(), d, 'R')
        self.assertEqual(['imagen de referencia lista: Marta (salió del piloto)', 'referencias apagadas (imágenes por día en 0): 1 sin pintar'], h); self.assertEqual([], pedidas)
        self.assertEqual('s1:E01-v1', e2['canon']['personajes']['marta']['de'])
        self.assertEqual(retrato, v.referencia_de('personajes', 'marta', self.u, serie(id='s2'), e2['canon'], piloto=True))
        # un piloto que nació de la imagen del protagonista no necesita retrato
        con = {'episodios': {'1': {'versiones': [{'v': 1, 'drive': 'PIL', 'referencias': ['personajes:marta']}]}}}
        self.assertIsNone(v.retrato_pendiente(self.u, serie(), {}, con, {}))

    def test_retrato_rechazado_por_google_no_detiene(self):
        d, llamadas = Drive(), []
        def gen(texto, seg, jpg=None, referencias=None):
            llamadas.append((texto, referencias))
            if referencias:
                err = MotorError('omni_flash invalid_request: no'); err.http = 400; raise err
            return clip(6)
        suya = ID('marta'); d.archivos[suya] = foto(formato='JPEG')
        s = serie(personajes={'marta': dict(self.u['personajes']['marta'], referencia_drive='https://drive.google.com/file/d/%s/view' % suya)})
        e = self.e(dec={'serie': 'si'}, s=s)
        h = v.productor(e, self.sin, False, gen, d, 'R')                                        # trae su propia imagen: la usa desde el episodio 1
        self.assertEqual(2, len(llamadas)); self.assertEqual([d.archivos[suya]], llamadas[0][1]); self.assertIsNone(llamadas[1][1])
        self.assertNotIn('IMAGE_REF', llamadas[1][0])
        reg = e['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertFalse(reg['con_retrato']); self.assertIn('imágenes de referencia', reg['aviso']); self.assertIn('imágenes de referencia', h[0])
        self.assertEqual([], reg['referencias'])
        self.assertEqual(1, e['prod']['s1']['intentos']['2026-11-09'])                          # una toma, aunque llamó dos veces
        def cobra(texto, seg, jpg=None, referencias=None):                                      # otro error con imagen SÍ detiene
            err = MotorError('omni_flash too_many_requests'); err.http = 429; raise err
        e2 = self.e(dec={'serie': 'si'}, s=s)
        self.assertIn('falló', v.productor(e2, self.sin, False, cobra, d, 'R')[0])
        # una foto de teléfono, grande y girada, viaja derecha y ligera
        from PIL import Image
        grande = io.BytesIO(); im = Image.new('RGB', (3000, 2000), (9, 9, 9)); ex = im.getexif(); ex[0x0112] = 6; im.save(grande, 'JPEG', exif=ex)
        chica = Image.open(io.BytesIO(v.a_jpeg(grande.getvalue())))
        self.assertEqual(('JPEG', (683, 1024)), (chica.format, chica.size))
        with self.assertRaises(MotorError): v.a_jpeg(b'no es una imagen')

    def test_primer_cuadro_rechazado_no_pierde_la_toma_pagada(self):
        d, llamadas = Drive(), []
        def gen(texto, seg, jpg=None, referencias=None):
            llamadas.append(('cuadro' if jpg else 'retrato' if referencias else 'texto'))
            if jpg:
                err = MotorError('omni_flash invalid_request: image'); err.http = 400; raise err
            return clip(6)
        # bloque de 30 s: la segunda toma no puede arrancar en el cuadro de la primera y sale del texto
        s = serie(2); s['episodios'][0].update(bloque=30, accion2='She turns.', dialogo2='Adiós.'); s['episodios'][1]['continua'] = True
        u = self.ajustes(tope_clips_dia=9, piloto_primero=0, fichas_por_dia=0)
        e = self.e(dec={'serie': 'si'}, s=s)
        h = v.productor(e, u, False, gen, d, 'R')
        self.assertEqual(['texto', 'cuadro', 'texto', 'cuadro', 'cuadro', 'retrato'], llamadas)   # el 2 baja: cuadro con retrato, cuadro solo, retrato
        reg1, reg2 = (e['prod']['s1']['episodios'][k]['versiones'][0] for k in ('1', '2'))
        self.assertEqual(30, reg1['segundos']); self.assertIn('último cuadro', reg1['aviso']); self.assertFalse(reg1['con_retrato'])
        self.assertTrue(reg2['con_retrato']); self.assertIn('último cuadro', reg2['aviso']); self.assertEqual(3, v.gastado_hoy(e))
        self.assertEqual(2, len([x for x in h if 'listo para revisar' in x]))

    def test_unir_tolera_un_clip_mudo(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t); (t / 'a.mp4').write_bytes(clip(1)); (t / 'b.mp4').write_bytes(clip(1, audio=False))
            self.assertEqual((['audio', 'video'], 2), (lambda f: (f[0], round(f[1])))(flujos(v.unir([t / 'a.mp4', t / 'b.mp4'], t / 'o.mp4').read_bytes())))
            self.assertEqual((t / 'a.mp4').read_bytes(), v.unir([t / 'a.mp4'], t / 'solo.mp4').read_bytes())   # uno solo no se recodifica

    # ---------------------------------------------------------------- semillero
    def test_semillero_sigue_la_temporada(self):
        pedidos = []
        pensar = lambda t, i: pedidos.append((t, i)) or CRUDO
        e = VACIO()
        r = v.semillero(e, self.u, False, pensar, SIN_CANDADOS)
        self.assertIn('serie propuesta', r); self.assertIn('no hay candados', r); sid = list(e['serie'])[0]
        s = e['serie'][sid]
        self.assertEqual('20261109-el-local-vacio', sid); self.assertEqual(('expediente', 'v4:serie:' + sid), self.guardados[-1][:2])
        # la primera historia planeada manda: protagonista, lugar, objeto y vértice son los de la temporada, no los que inventó el modelo
        self.assertEqual(('el-terreno-de-marta', 'marta', 'terreno', 'llaves', 'ppp', {}, {}), (s['temporada'], s['personaje'], s['lugar'], s['objeto'], s['vertice'], s['personajes'], s['lugares']))
        self.assertEqual([], v.validar_serie(s, self.u))
        self.assertIn('llaves', s['episodios'][0]['objetos']); self.assertIn('llaves', s['episodios'][-1]['objetos'])     # el objeto propio abre y cierra
        vistos = {o for ep in s['episodios'] for o in ep['objetos']}
        self.assertTrue({'recibos', 'camioneta', 'videollamada'} <= vistos)                 # los guiños que el modelo olvidó se reparten
        self.assertEqual(3, len({ep['n'] for ep in s['episodios'] for o in ep['objetos'] if o in ('recibos', 'camioneta', 'videollamada')}))
        pedido, instr = pedidos[0]
        for trozo in ('HISTORIA PLANEADA', 'usa el id «marta»', 'REGLAS DEL MUNDO', 'CONTINUIDAD', 'EL MUNDO COMPARTIDO', '- servilleta: La servilleta', '- rostro: Acercamiento al rostro', 'Plan de Potencial', 'Don Carlos abre el portón'):
            self.assertIn(trozo, pedido)
        self.assertIn('SIEMPRE es un cliente', instr); self.assertIn('en 10 episodios', instr); self.assertIn('"encuadre"', instr); self.assertIn('"objetos"', instr)
        self.assertNotIn('{n}', instr); self.assertNotIn('HISTORIA LIBRE', pedido)
        # la siguiente propuesta es la segunda historia; una serie descartada libera su lugar en la temporada
        self.assertEqual('el-de-la-esquina', v.temporada_pendiente(self.u, e)['id'])
        e['dec'][sid] = {'serie': 'no'}; self.assertEqual('el-terreno-de-marta', v.temporada_pendiente(self.u, e)['id'])
        e['dec'][sid] = {'serie': 'si'}
        r2 = v.semillero(e, self.u, False, lambda t, i: dict(CRUDO, titulo='', episodios=[dict(x, encuadre='mesa', tono='Slowly.', objetos=['plano', 'nada'], invitados=['marta', 'don-carlos']) for x in CRUDO['episodios']]), SIN_CANDADOS)
        s2 = e['serie']['20261109-el-de-la-esquina']                                        # sin título del modelo, vale el planeado
        self.assertIn('serie propuesta', r2); self.assertEqual(('don-carlos', 'esquina', 'plano', 'capital'), (s2['personaje'], s2['lugar'], s2['objeto'], s2['vertice']))
        self.assertEqual(('mesa', 'Slowly.', ['plano'], ['marta']), tuple(s2['episodios'][1][k] for k in ('encuadre', 'tono', 'objetos', 'invitados')))   # lo que no existe y el propio protagonista se quitan
        e['serie']['otra'] = serie(); e['serie']['otra2'] = serie(id='otra2'); n = len(self.guardados)
        self.assertIn('esperando decisión', v.semillero(e, self.u, False, pensar, SIN_CANDADOS)); self.assertEqual(n, len(self.guardados))
        self.assertIn('no salió', v.semillero(VACIO(), self.u, False, lambda t, i: dict(CRUDO, episodios=CRUDO['episodios'][:4]), SIN_CANDADOS))
        self.assertIn('no salió', v.semillero(VACIO(), self.u, False, lambda t, i: None, SIN_CANDADOS))
        vetada = dict(CRUDO, trama='Una familia de Sonora')
        self.assertIn('vetada', v.semillero(VACIO(), self.u, False, lambda t, i: vetada, SIN_CANDADOS))
        self.assertIn('apagado', v.semillero(VACIO(), self.ajustes(semillero=0), False, pensar, SIN_CANDADOS))
        self.assertIn('«El terreno que no hacía nada», de la temporada', v.semillero(VACIO(), self.u, True)); self.assertEqual(n, len(self.guardados))
        propio = dict(self.u, guionista='Escribe comedias de {n} partes.')
        v.semillero(VACIO(), propio, False, pensar, SIN_CANDADOS)
        self.assertTrue(pedidos[-1][1].startswith('Escribe comedias de 10 partes.'))        # el criterio es un dato de Dirección

    def test_un_borrador_de_direccion_no_frena_al_semillero(self):
        # 9-nov (corrida 42755180401): un «Nueva serie» en blanco más la propuesta que ya esperaba llegaron al
        # tope de 2 y el semillero no propuso la primera historia de la temporada. Un borrador no es una propuesta.
        e = VACIO()
        e['serie']['vieja'] = dict(serie(id='vieja'), origen='semillero')
        e['serie']['borrador'] = dict(serie(id='borrador', titulo='', episodios=[]), origen='editor')
        r = v.semillero(e, self.u, False, lambda t, i: CRUDO, SIN_CANDADOS)
        self.assertIn('serie propuesta', r)
        self.assertEqual(['el-terreno-de-marta'], [s.get('temporada') for s in e['serie'].values() if s.get('temporada')])
        # dos propuestas del semillero sí lo frenan, vengan o no con su origen anotado (las de antes no lo traían)
        dos = VACIO(); dos['serie'] = {'a': dict(serie(id='a'), origen='semillero'), 'b': serie(id='b'), 'c': dict(serie(id='c'), origen='editor')}
        n = len(self.guardados)
        self.assertEqual('ya hay 2 serie(s) esperando decisión', v.semillero(dos, self.u, False, lambda t, i: CRUDO, SIN_CANDADOS))
        self.assertEqual(n, len(self.guardados))

    def test_semillero_libre_cuando_no_hay_temporada(self):
        pedidos, libre = [], dict(self.u, temporada=[])
        e = VACIO()
        r = v.semillero(e, libre, False, lambda t, i: pedidos.append(t) or dict(CRUDO, objeto={'nombre': 'La báscula', 'aspecto': 'An old iron scale.', 'significado': 'x'}), SIN_CANDADOS)
        s = e['serie']['20261109-el-local-vacio']
        self.assertIn('serie propuesta', r); self.assertIn('HISTORIA LIBRE', pedidos[0]); self.assertNotIn('temporada', s)
        self.assertEqual(('raul', 'el-local', 'la-bascula', 'ppp'), (s['personaje'], s['lugar'], s['objeto'], s['vertice']))     # cliente, lugar y objeto nuevos: son de la serie
        self.assertEqual((['raul'], ['el-local'], ['la-bascula'], 'cliente'), (list(s['personajes']), list(s['lugares']), list(s['objetos']), s['personajes']['raul']['papel']))
        self.assertEqual('s9:raul', v.llave_canon(libre, dict(s, id='s9'), 'personajes', 'raul')); self.assertEqual('marta', v.llave_canon(libre, s, 'personajes', 'marta'))
        self.assertEqual('capital', v.vertice_siguiente(libre, e['serie']))                 # sin temporada, rota vértices
        # uno «nuevo» que se llama como alguien del mundo ES el del mundo (nadie cambia de cara), y un id dicho por su nombre se entiende
        choque = v.armar_serie(dict(CRUDO, titulo='Choque', personaje={'nombre': 'Marta', 'aspecto': 'Another woman.'}, lugar='Terreno'), libre, 'ppp', {})
        self.assertEqual(('marta', 'terreno', {}, {}), (choque['personaje'], choque['lugar'], choque['personajes'], choque['lugares']))
        self.assertEqual('don-carlos', v.armar_serie(dict(CRUDO, titulo='Por nombre', personaje='Don Carlos'), libre, 'ppp', {})['personaje'])
        sin_vertices = dict(libre, vertices={})
        self.assertIn('no tiene vértices', v.semillero(VACIO(), sin_vertices, False, lambda t, i: CRUDO, SIN_CANDADOS))

    def test_candados_entran_al_pedido(self):
        filas = [{'id': 'C1', 'de': 'Alejandro', 'candado': 'Nunca prometer plazos.', 'tipo': 'veto', 'activo': 1},
                 {'id': 'C2', 'de': 'Sayri', 'candado': 'Apagado.', 'tipo': 'regla', 'activo': '0'}, 'basura']
        texto, aviso = v.candados_texto(lambda: filas)
        self.assertEqual(('- [veto · de Alejandro] Nunca prometer plazos.', ''), (texto, aviso))
        def caida():
            raise v.sala.SalaError('x', codigo='sala_permiso_rechazado')
        self.assertEqual('', v.candados_texto(caida)[0]); self.assertIn('sala_permiso_rechazado', v.candados_texto(caida)[1])
        pedidos = []
        e = {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
        r = v.semillero(e, self.u, False, lambda t, i: pedidos.append(t) or CRUDO, lambda: filas)
        self.assertIn('Nunca prometer plazos.', pedidos[0]); self.assertNotIn('Apagado.', pedidos[0]); self.assertNotIn(' · ', r.split(')')[-1])
        self.assertIn('no leí los candados', v.semillero({'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None},
                                                        self.u, False, lambda t, i: CRUDO, caida))

    def test_historias_que_se_cruzan(self):
        RAUL, MARTA, LUPE = ID('raul'), ID('marta'), ID('lupe')
        d = Drive(); d.archivos.update({RAUL: foto(formato='JPEG'), MARTA: foto((10, 90, 60), 'JPEG'), LUPE: foto((1, 2, 3), 'JPEG'), 'R/_HISTORIAS/x/E09': clip(6)})
        libre = dict(self.ajustes(propuestas_en_espera=5, tope_clips_dia=9, fichas_por_dia=0), temporada=[])
        raul = {'nombre': 'Raúl', 'industria': 'ferretero', 'aspecto': 'A tall man.', 'voz': 'deep', 'quiere': 'crecer'}
        aprobada = serie(id='vieja', personaje='raul', personajes={'raul': raul})
        e = self.e(dec={'serie': 'si'}, prod={'episodios': {}}, s=aprobada)
        self.assertEqual({}, v.conocidos(e, libre))                                           # sin imagen todavía no se presta
        # se puede invitar a quien ya tiene imagen: el protagonista de una serie aprobada y los del universo
        e['canon'] = {'personajes': {'vieja:raul': {'drive': RAUL, 'huella': 'x', 'de': 'vieja:E01-v1'}}}
        self.assertEqual(['raul'], list(v.conocidos(e, libre))); self.assertEqual({}, v.conocidos(dict(e, dec={}), libre))   # sin aprobar no se presta
        e['canon']['personajes']['marta'] = {'drive': MARTA, 'huella': 'x'}
        self.assertEqual({'marta': MARTA, 'raul': RAUL}, {k: x['referencia_drive'] for k, x in v.conocidos(e, libre).items()})
        pedidos = []
        nuevo = dict(CRUDO, titulo='La panadería', personaje={'nombre': 'Lupe', 'industria': 'panadera', 'aspecto': 'A woman.', 'voz': 'soft'}, invitado_final='Raúl')
        r = v.semillero(e, libre, False, lambda t, i: pedidos.append(t) or nuevo, SIN_CANDADOS)
        self.assertIn('serie propuesta', r); self.assertIn('Personajes conocidos', pedidos[0]); self.assertIn('Raúl (ferretero)', pedidos[0])
        s = e['serie']['20261109-la-panaderia']
        self.assertEqual(['raul'], s['episodios'][-1]['invitados']); self.assertEqual([], s['episodios'][0]['invitados'])
        self.assertEqual((RAUL, 'invitado'), (s['personajes']['raul']['referencia_drive'], s['personajes']['raul']['papel']))   # llega con su imagen
        otra = v.armar_serie(dict(nuevo, titulo='Otra', invitado_final='Marta'), libre, 'ppp', {}, v.conocidos(e, libre))
        self.assertEqual((['marta'], ['lupe']), (otra['episodios'][-1]['invitados'], list(otra['personajes'])))   # la del universo no se copia: ya es de todos
        # al producir el último episodio viajan las dos imágenes, protagonista primero
        llamadas = []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, referencias)) or clip(6)
        e['dec'][s['id']] = {'serie': 'si', 'episodios': {str(i): {'v': 1, 'marca': 'si'} for i in range(1, 10)}}
        e['prod'][s['id']] = {'intentos': {}, 'episodios': {str(i): {'versiones': [{'v': 1, 'drive': 'R/_HISTORIAS/x/E09', 'referencias': ['personajes:lupe']}]} for i in range(1, 10)}}
        e['canon']['personajes'][s['id'] + ':lupe'] = {'drive': LUPE, 'huella': 'x'}
        v.productor(e, libre, False, gen, d, 'R')
        texto, refs = llamadas[-1]
        self.assertEqual([d.archivos[LUPE], d.archivos[RAUL]], refs)
        self.assertIn('CHARACTER 2 (Raúl), a guest', texto); self.assertIn('<IMAGE_REF_1>', texto)
        self.assertEqual(['personajes:lupe', 'personajes:raul'], e['prod'][s['id']]['episodios']['10']['versiones'][0]['referencias'])
        sin = v.armar_serie(dict(nuevo, invitado_final=''), libre, 'ppp', {}, v.conocidos(e, libre))
        self.assertEqual([], sin['episodios'][-1]['invitados']); self.assertEqual(['lupe'], list(sin['personajes']))
        # la temporada reparte a sus invitados en los últimos episodios, uno por episodio
        final = v.armar_serie(CRUDO, self.u, 'ppp', {}, {}, self.u['temporada'][-1])
        self.assertEqual(('miguel', 'mesa', 'silla'), (final['personaje'], final['lugar'], final['objeto']))
        self.assertEqual([['don-roberto'], ['rodrigo'], ['sofia'], ['don-carlos'], ['marta']], [ep['invitados'] for ep in final['episodios'][-5:]])

    def test_referencias_del_canon(self):
        liga = '1AbCdEfGhIjKlMnOpQrStUvWx'
        self.assertEqual(liga, v.id_drive('https://drive.google.com/file/d/%s/view?usp=sharing' % liga))
        self.assertEqual(liga, v.id_drive('https://drive.google.com/open?id=' + liga)); self.assertEqual(liga, v.id_drive(' %s ' % liga))
        # lo que no es un archivo de Drive no cuenta: ni un texto cualquiera ni la liga de una carpeta
        self.assertEqual(('', '', ''), (v.id_drive(' RET '), v.id_drive(None), v.id_drive('https://drive.google.com/drive/folders/' + liga)))
        s = serie()
        canon = {'personajes': {'marta': self.pintado('personajes', 'marta', 'PINTADA')}, 'objetos': {'llaves': self.pintado('objetos', 'llaves', 'LLAVES')}}
        # prioridad: la que puso Dirección y, si no, la del canon
        mia = dict(self.u, personajes=dict(self.u['personajes'], marta=dict(self.u['personajes']['marta'], referencia_drive='https://drive.google.com/file/d/%s/view' % liga)))
        self.assertEqual(liga, v.referencia_de('personajes', 'marta', mia, s, canon))
        self.assertEqual('PINTADA', v.referencia_de('personajes', 'marta', self.u, s, canon))
        self.assertEqual(('LLAVES', '', ''), (v.referencia_de('objetos', 'llaves', self.u, s, canon), v.referencia_de('objetos', 'plano', self.u, s, canon), v.referencia_de('lugares', 'terreno', self.u, s, canon)))
        # el retrato que salió del piloto de ESTA serie no sirve para rehacer ese mismo piloto; para otra serie sí
        del_piloto = {'personajes': {'marta': self.pintado('personajes', 'marta', 'RETRATO', de='s1:E01-v1')}}
        self.assertEqual(('RETRATO', '', 'RETRATO'), (v.referencia_de('personajes', 'marta', self.u, s, del_piloto), v.referencia_de('personajes', 'marta', self.u, s, del_piloto, piloto=True),
                                                     v.referencia_de('personajes', 'marta', self.u, serie(id='s2'), del_piloto, piloto=True)))
        # por pintar: lo que no tiene imagen o cambió de ficha; nunca lo que puso Dirección
        self.assertEqual((False, True, False), (v.por_pintar('personajes', 'marta', self.u, s, canon), v.por_pintar('lugares', 'terreno', self.u, s, canon), v.por_pintar('personajes', 'marta', mia, s, {})))
        otra = dict(self.u, personajes=dict(self.u['personajes'], marta=dict(self.u['personajes']['marta'], vestuario='Red dress.')))
        self.assertTrue(v.por_pintar('personajes', 'marta', otra, s, canon))
        self.assertEqual(('PINTADA', 'la pintó la nube'), v.origen_imagen('personajes', 'marta', self.u, s, canon)); self.assertEqual('salió del piloto', v.origen_imagen('personajes', 'marta', self.u, s, del_piloto)[1])
        self.assertEqual((liga, 'la puso Dirección'), v.origen_imagen('personajes', 'marta', mia, s, canon)); self.assertEqual(('', ''), v.origen_imagen('objetos', 'plano', self.u, s, canon))
        # en la toma viajan, en orden: quién sale, los objetos y el lugar; el piloto ya nace de las imágenes
        d, llamadas = Drive(), []
        d.archivos.update({'PINTADA': foto(formato='JPEG'), 'LLAVES': foto((1, 1, 1), 'JPEG'), 'RECIBOS': foto((5, 5, 5), 'JPEG'), 'TERRENO': foto((9, 9, 9), 'JPEG')})
        canon['lugares'] = {'terreno': self.pintado('lugares', 'terreno', 'TERRENO')}
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, jpg, referencias)) or clip(6)
        s['episodios'][0].update(objetos=['llaves', 'recibos'], encuadre='revelacion')
        e = self.e(dec={'serie': 'si'}, s=s); e['canon'] = canon
        self.assertEqual(['«La prueba» episodio 1 espera la imagen de: Los recibos del predial'], v.productor(e, self.u, False, gen, d, 'R'))   # falta una: espera, no gasta
        self.assertEqual(([], {}), (llamadas, e['prod']['s1']['intentos']))
        canon['objetos']['recibos'] = self.pintado('objetos', 'recibos', 'RECIBOS')
        v.productor(e, self.u, False, gen, d, 'R')
        texto, jpg, refs = llamadas[0]
        self.assertEqual((None, [d.archivos[k] for k in ('PINTADA', 'LLAVES', 'RECIBOS', 'TERRENO')]), (jpg, refs))
        self.assertTrue(texto.startswith('[# References <IMAGE_REF_0>@Image1 <IMAGE_REF_1>@Image2 <IMAGE_REF_2>@Image3 <IMAGE_REF_3>@Image4]')); self.assertIn('CAMERA: The camera starts on a close detail', texto)
        reg = e['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertEqual((['personajes:marta', 'objetos:llaves', 'objetos:recibos', 'lugares:terreno'], True), (reg['referencias'], reg['con_retrato'])); self.assertNotIn('aviso', reg)
        # el piloto nació de la imagen de Marta: no hace falta sacar retrato, y los demás episodios usan la misma
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        v.productor(e, self.ajustes(tope_clips_dia=9), False, gen, d, 'R')
        self.assertNotIn('de', e['canon']['personajes']['marta']); self.assertEqual(3, len(llamadas)); self.assertEqual(2, len(llamadas[1][2]))   # episodio 2: sin objetos, viajan Marta y el lugar
        # Google rechaza el juego completo: baja a sólo los personajes y lo dice
        def quisquilloso(texto, seg, jpg=None, referencias=None):
            if referencias and len(referencias) > 1:
                err = MotorError('omni_flash invalid_request: too many'); err.http = 400; raise err
            llamadas.append((texto, jpg, referencias)); return clip(6)
        e2 = self.e(dec={'serie': 'si'}, s=s); e2['canon'] = canon
        v.productor(e2, self.u, False, quisquilloso, d, 'R')
        reg = e2['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertEqual(['personajes:marta'], reg['referencias']); self.assertEqual([d.archivos['PINTADA']], llamadas[-1][2])
        self.assertIn('no se pudo usar las imágenes de referencia', reg['aviso'])
        # Google no acepta la imagen de la persona: al menos viajan los objetos y el lugar, y la toma lo dice
        def sin_caras(texto, seg, jpg=None, referencias=None):
            if referencias and d.archivos['PINTADA'] in referencias:
                err = MotorError('omni_flash invalid_request: person'); err.http = 400; raise err
            llamadas.append((texto, jpg, referencias)); return clip(6)
        e4 = self.e(dec={'serie': 'si'}, s=s); e4['canon'] = canon
        v.productor(e4, self.u, False, sin_caras, d, 'R')
        reg = e4['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertEqual((['objetos:llaves', 'objetos:recibos', 'lugares:terreno'], False), (reg['referencias'], reg['con_retrato']))
        self.assertIn('no se pudo usar las imágenes de los personajes', reg['aviso']); self.assertNotIn('person shown in', llamadas[-1][0])
        self.assertIsNone(v.retrato_pendiente(self.u, s, e4['dec']['s1'], e4['prod']['s1'], canon))   # ya tiene imagen pintada: no se cambia por otra cara
        # una imagen que existe pero no se puede leer detiene el episodio ANTES de gastar: producido sin ella saldría distinto
        e3 = self.e(dec={'serie': 'si'}, s=s); e3['canon'] = dict(canon, objetos=dict(canon['objetos'], llaves=dict(canon['objetos']['llaves'], drive='YA-NO-ESTA')))
        antes = len(llamadas)
        h = v.productor(e3, self.u, False, gen, d, 'R')
        self.assertIn('no se produjo y no se gastó: no pude leer la imagen de «Las llaves del portón»', h[0]); self.assertIn('carpeta del canon', h[0])
        self.assertEqual((antes, {}), (len(llamadas), e3['prod']['s1']['intentos'])); self.assertEqual(h[0], e3['prod']['s1']['avisos'][-1]['texto'])

    def test_fichas_pinta_el_canon_una_vez(self):
        d, pedidas = Drive(), []
        pintar = lambda texto: pedidas.append(texto) or foto()
        s = serie(2, personajes={'mateo': {'nombre': 'Mateo', 'aspecto': 'A man of 38.', 'vestuario': 'Linen shirt.'}}, personaje='mateo')
        s['episodios'][0].update(objetos=['llaves']); s['episodios'][1].update(invitados=['marta'], lugar='cafe', objetos=['llaves', 'camioneta'])
        e = self.e(s=s)
        # sin series aprobadas no se pinta nada, pero la carpeta y el índice quedan en Drive desde la primera corrida: ahí pone Dirección sus imágenes
        self.assertEqual(['referencias: no hay series aprobadas'], v.fichas(e, self.u, False, pintar, d, 'R')); self.assertEqual([], pedidas)
        self.assertEqual(('R/_HISTORIAS/_CANON', ['v4:canon']), (e['canon']['carpeta'], [g[1] for g in self.guardados]))
        self.assertIn('· Marta (marta)', d.archivos['R/_HISTORIAS/_CANON/CANON.txt'].decode())
        n = len(self.guardados)
        self.assertEqual(['referencias: no hay series aprobadas'], v.fichas(e, self.u, False, pintar, d, 'R')); self.assertEqual(n, len(self.guardados))
        e['dec']['s1'] = {'serie': 'si'}
        self.assertEqual([('personajes', 'mateo'), ('lugares', 'terreno'), ('objetos', 'llaves'), ('objetos', 'camioneta'), ('personajes', 'marta'), ('lugares', 'cafe')],
                         [(c, i) for c, i, _ in v.necesarios(self.u, s)])
        self.assertIn('pintaría 6', v.fichas(e, self.u, True, pintar, d, 'R')[0]); self.assertEqual(([], n), (pedidas, len(self.guardados)))
        h = v.fichas(e, self.ajustes(fichas_por_dia=4), False, pintar, d, 'R')
        self.assertEqual(4, len(pedidas)); self.assertIn('tope de imágenes de referencia del día (4): 2 esperan', h[-1])
        canon = e['canon']
        self.assertEqual({'personajes': ['s1:mateo'], 'lugares': ['terreno'], 'objetos': ['llaves', 'camioneta']}, {c: list(canon[c]) for c in v.CLASES_MUNDO})   # lo propio de la serie lleva su id delante
        self.assertEqual({'drive': 'R/_HISTORIAS/_CANON/personajes/Mateo (s1 · mateo).jpg', 'huella': v.huella(v.descripcion_ficha('personajes', s['personajes']['mateo']))},
                         canon['personajes']['s1:mateo'])                                    # el registro es corto: caben cientos en una celda
        self.assertEqual(JPEG, d.archivos['R/_HISTORIAS/_CANON/objetos/Las llaves del portón (llaves).jpg'][:2])       # llega PNG y se guarda JPEG ligero
        self.assertIn('A man of 38. Linen shirt.', pedidas[0]); self.assertIn('no people', pedidas[1]); self.assertIn('one single object', pedidas[2]); self.assertTrue(pedidas[0].endswith('no watermark.'))
        self.assertEqual(4, canon['intentos']['2026-11-09']); self.assertEqual(4, v.gastado_fichas(e))
        self.assertEqual({'v4:canon'}, {g[1] for g in self.guardados}); self.assertEqual({'2026-11-09': 1}, self.guardados[n][2]['intentos'])   # reserva ANTES de la primera imagen
        indice = d.archivos['R/_HISTORIAS/_CANON/CANON.txt'].decode()
        for trozo in ('CANON · quién es quién', '· Mateo (s1:mateo)', 'Imagen: https://drive.google.com/file/d/R/_HISTORIAS/_CANON/personajes/Mateo (s1 · mateo).jpg/view (la pintó la nube)',
                      'Sale en: La prueba', '· Sofía (sofia)', 'Imagen: todavía no tiene', 'TEMPORADA', '5. La mesa', 'súbela a esta carpeta'):
            self.assertIn(trozo, indice)
        # al día siguiente termina lo que faltó y después ya no pinta nada
        with patch.object(v, 'hoy', return_value='2026-11-10'):
            h = v.fichas(e, self.u, False, pintar, d, 'R')
            self.assertEqual(6, len(pedidas)); self.assertEqual(2, len([x for x in h if 'lista' in x]))
            n = len(self.guardados)
            self.assertEqual(['referencias al día'], v.fichas(e, self.u, False, pintar, d, 'R')); self.assertEqual((6, n), (len(pedidas), len(self.guardados)))
            # cambia la ficha de Marta: sólo esa imagen se vuelve a pintar; la que pone Dirección no se toca
            otra = dict(self.ajustes(fichas_por_dia=40), personajes=dict(self.u['personajes'], marta=dict(self.u['personajes']['marta'], vestuario='Red dress.')))
            v.fichas(e, otra, False, pintar, d, 'R'); self.assertEqual(7, len(pedidas)); self.assertIn('Red dress.', pedidas[-1])
            cafe = dict(otra['lugares']['cafe'], aspecto='Another place.')
            suya = dict(otra, lugares=dict(otra['lugares'], cafe=dict(cafe, referencia_drive=ID('cafe'))))
            v.fichas(e, suya, False, pintar, d, 'R'); self.assertEqual(7, len(pedidas))
            self.assertIn('/view (la puso Dirección)', d.archivos['R/_HISTORIAS/_CANON/CANON.txt'].decode())
            # una liga que no es de un archivo no cuenta como imagen propia: el lugar se vuelve a pintar
            carpeta = dict(otra, lugares=dict(otra['lugares'], cafe=dict(cafe, referencia_drive='https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx')))
            v.fichas(e, carpeta, False, pintar, d, 'R'); self.assertEqual(8, len(pedidas)); self.assertIn('Another place.', pedidas[-1])
            # un fallo detiene el paso y gasta su reserva; esa imagen no se vuelve a pedir hoy, y lo demás no se queda esperando por ella
            mala = dict(carpeta, objetos=dict(self.u['objetos'], llaves=dict(self.u['objetos']['llaves'], aspecto='New keys.'), camioneta=dict(self.u['objetos']['camioneta'], aspecto='New truck.')))
            antes = v.gastado_fichas(e)
            h = v.fichas(e, mala, False, lambda t: (_ for _ in ()).throw(MotorError('Gemini imagen 429')), d, 'R')
            self.assertEqual(['la imagen de «Las llaves del portón» falló: Gemini imagen 429'], h); self.assertEqual(antes + 1, v.gastado_fichas(e))
            self.assertEqual('Gemini imagen 429', e['canon']['fallas']['objetos:llaves']['motivo'])
            h = v.fichas(e, mala, False, pintar, d, 'R')                                    # misma ficha, mismo día: las llaves esperan y la camioneta sí se pinta
            self.assertIn('falló hoy (Gemini imagen 429)', h[0]); self.assertIn('imagen de referencia lista: La camioneta blanca (objeto)', h); self.assertIn('New truck.', pedidas[-1])
            cuenta, n = len(pedidas), len(self.guardados)
            self.assertIn('falló hoy', v.fichas(e, mala, False, pintar, d, 'R')[0]); self.assertEqual((cuenta, n), (len(pedidas), len(self.guardados)))
            arreglada = dict(mala, objetos=dict(mala['objetos'], llaves=dict(mala['objetos']['llaves'], aspecto='Brass keys.')))
            v.fichas(e, arreglada, False, pintar, d, 'R')                                   # con la ficha cambiada se reintenta enseguida
            self.assertEqual((cuenta + 1, {}), (len(pedidas), e['canon']['fallas'])); self.assertIn('Brass keys.', pedidas[-1])
            # apagado no pinta; una respuesta que no es imagen se dice
            vieja = dict(arreglada, objetos=dict(arreglada['objetos'], llaves=dict(arreglada['objetos']['llaves'], aspecto='Old keys.')))
            self.assertIn('referencias apagadas', ' '.join(v.fichas(e, dict(vieja, ajustes=dict(vieja['ajustes'], fichas_por_dia=0)), False, pintar, d, 'R'))); self.assertEqual(cuenta + 1, len(pedidas))
            self.assertIn('no se pudo leer', ' '.join(v.fichas(e, vieja, False, lambda t: b'no es imagen', d, 'R')))
        # los intentos viejos se podan: el documento no crece para siempre
        e['canon']['intentos'] = {'2026-10-%02d' % k: 1 for k in range(1, 31)}
        with patch.object(v, 'hoy', return_value='2026-11-12'):
            v.fichas(e, vieja, False, pintar, d, 'R')
        self.assertEqual(15, len(e['canon']['intentos'])); self.assertIn('2026-11-12', e['canon']['intentos'])
        class SinDrive(Drive):
            def ruta_carpetas(self, *n):
                raise self.DriveError('la unidad no contesta')
        limpio = self.e(dec={'serie': 'si'}, s=s); n, cuenta = len(self.guardados), len(pedidas)
        self.assertIn('Drive no está listo', v.fichas(limpio, self.u, False, pintar, SinDrive(), 'R')[0]); self.assertEqual((cuenta, n), (len(pedidas), len(self.guardados)))

    # ---------------------------------------------------------------- paquete
    def test_paquete(self):
        d = Drive(); s = serie(2)
        prod = {'episodios': {str(i): {'versiones': [{'v': 1, 'drive': 'c%d' % i}]} for i in (1, 2)}}
        d.archivos.update(c1=clip(), c2=clip())
        dec = {'serie': 'si', 'episodios': {'1': {'v': 1, 'marca': 'si'}, '2': {'v': 1, 'marca': 'cambio'}}}
        pedidos = []
        escribe = lambda t, i: pedidos.append(t) or {'episodios': ['Hoy empieza.', 'Mañana sigue.']}
        self.assertFalse(v.completa(s, dec, prod)); self.assertEqual(['ningún paquete nuevo'], v.paquete(self.e(dec, prod, s), self.u, False, d, 'R', escribe, SIN_CANDADOS))
        dec['episodios']['2'] = {'v': 1, 'marca': 'si'}; e = self.e(dec, prod, s)
        d.falla = True
        self.assertIn('no se pudo armar', v.paquete(e, self.u, False, d, 'R', escribe, SIN_CANDADOS)[0]); self.assertNotIn('paquete', e['prod']['s1'])
        d.falla = False
        self.assertIn('listo en Drive', v.paquete(e, self.u, False, d, 'R', escribe, lambda: [{'candado': 'Nunca prometer plazos.', 'tipo': 'veto', 'de': 'Alejandro'}])[0])
        self.assertIn('Nunca prometer plazos.', pedidos[-1])
        carpeta = e['prod']['s1']['paquete']['carpeta']; self.assertEqual('R/_LISTAS PARA PUBLICAR/Historia · La prueba', carpeta)
        nombres = sorted(k.rsplit('/', 1)[1] for k in d.archivos if k.startswith(carpeta))
        self.assertEqual(['COPY.txt', 'E01.mp4', 'E02.mp4', 'HISTORIA-COMPLETA.mp4'], nombres)
        texto = d.archivos[carpeta + '/COPY.txt'].decode()
        self.assertIn('La prueba', texto); self.assertIn('Texto para publicar: Mañana sigue.', texto); self.assertTrue(e['prod']['s1']['paquete']['con_textos'])
        self.assertEqual(2, round(flujos(d.archivos[carpeta + '/HISTORIA-COMPLETA.mp4'])[1]))
        self.assertEqual(['ningún paquete nuevo'], v.paquete(e, self.u, False, d, 'R', escribe, SIN_CANDADOS))    # no se arma dos veces
        # textos mal formados o vetados: el paquete sale con el guion y lo dice
        for malo in (lambda t, i: {'episodios': ['uno']}, lambda t, i: {'episodios': ['Ven a Sonora.', 'ok']}, lambda t, i: None):
            self.assertEqual([], v.textos_para_publicar(s, self.u, malo))
        limpio = copy.deepcopy(prod); limpio.pop('paquete')
        e2 = self.e(dec, limpio, s)
        self.assertIn('sin textos', v.paquete(e2, self.u, False, d, 'R', lambda t, i: None, SIN_CANDADOS)[0])

    # ---------------------------------------------------------------- la corrida
    def test_main_siembra_universo_deja_estado_y_no_actua_a_ciegas(self):
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {'La Servilleta': {}}}), patch.object(v, 'semillero', return_value='ok'):
            self.assertEqual(0, v.main([]))
        self.assertEqual(['v4:universo', 'v4:estado'], [g[1] for g in self.guardados])
        self.assertEqual((0, 0.0), (self.guardados[-1][2]['clips_hoy'], self.guardados[-1][2]['gasto_usd_aprox_hoy']))
        self.assertIn('guionista', self.guardados[0][2])
        self.guardados.clear()
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {}}), patch.object(v, 'motores_listos', return_value='motores: ok') as motores:
            self.assertEqual(0, v.main(['--simular']))
        self.assertEqual([], self.guardados); self.assertEqual(1, motores.call_count)       # la simulación pregunta por los modelos; no escribe ni gasta
        with patch.object(v.sala, 'get', side_effect=v.sala.SalaError('caída', codigo='sala_tiempo_agotado')):
            self.assertEqual(2, v.main([]))                                                 # «no contestó» nunca es «no hay nada»
        self.assertEqual([], self.guardados)
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {'v4:universo': self.u}}), \
                patch.object(v, 'semillero', return_value='ok'), patch.object(v, 'productor', side_effect=v.V4Error('sin drive_raiz')):
            self.assertEqual(1, v.main([]))
        self.assertEqual(['v4:estado'], [g[1] for g in self.guardados]); self.assertIn('se detuvo', self.guardados[0][2]['pasos'][-1])

    def test_motores_listos_pregunta_sin_gastar(self):
        from motores import escena_omni
        paginas = [{'models': [{'name': 'models/gemini-3.6-flash'}], 'nextPageToken': 'p 2'}, {'models': [{'name': 'models/' + escena_omni.MODELO}, 'basura']}]
        rutas = []
        with patch.object(escena_omni, 'llamar', side_effect=lambda metodo, ruta: rutas.append((metodo, ruta)) or paginas[len(rutas) - 1]):
            linea = v.motores_listos(self.u)
        self.assertEqual([('GET', 'models?pageSize=1000'), ('GET', 'models?pageSize=1000&pageToken=p%202')], rutas)
        self.assertIn('guion «gemini-3.6-flash» está disponible', linea); self.assertIn('imágenes «gemini-2.5-flash-image» NO aparece', linea)
        self.assertIn('video «%s» está disponible' % escena_omni.MODELO, linea)
        with patch.object(escena_omni, 'llamar', side_effect=MotorError('falta GEMINI_API_KEY')):
            self.assertIn('no pude preguntar', v.motores_listos(self.u))


if __name__ == '__main__':
    unittest.main()
