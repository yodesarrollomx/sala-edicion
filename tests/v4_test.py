import copy, json, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
import sala_v4 as v
from motores._comun import MotorError

JPEG = b'\xff\xd8'


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


class V4Tests(unittest.TestCase):
    def setUp(self):
        self.u = v.universo_de({'universo': None})
        self.guardados = []
        p = patch.object(v.sala, 'post', side_effect=lambda accion, **c: self.guardados.append((accion, c['pieza'], copy.deepcopy(c['expediente']))) or {'ok': True})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(v, 'hoy', return_value='2026-11-09'); p.start(); self.addCleanup(p.stop)

    def e(self, dec=None, prod=None, s=None):
        s = s or serie()
        return {'universo': None, 'serie': {s['id']: s}, 'dec': {s['id']: dec} if dec else {}, 'prod': {s['id']: prod} if prod else {}, 'estado': None}

    def ajustes(self, **kw):
        return dict(self.u, ajustes=dict(self.u['ajustes'], **kw))

    # ---------------------------------------------------------------- almacén y dueños
    def test_almacen_separa_y_respeta_duenos(self):
        e = v.separar({'v4:universo': {'a': 1}, 'v4:serie:x': {'id': 'x'}, 'v4:dec:x': {'serie': 'si'}, 'v4:prod:x': {},
                       'La Servilleta': {'pieza': 'otra cosa'}, 'v4:serie:': {}, 'v4:rara:x': {}, 'v4:prod:y': 'no-dict'})
        self.assertEqual(({'a': 1}, ['x'], ['x'], ['x']), (e['universo'], list(e['serie']), list(e['dec']), list(e['prod'])))
        with self.assertRaises(v.V4Error): v.guardar('dec', 'x', {})                 # la nube no decide
        with self.assertRaises(v.V4Error): v.guardar('serie', 'x', {}, existe=True)   # ni pisa al editor
        with self.assertRaises(v.V4Error): v.guardar('universo', '', {}, existe=True)
        self.assertEqual([], self.guardados)
        v.guardar('prod', 'x', {'a': 1}); v.guardar('estado', '', {})
        self.assertEqual(['v4:prod:x', 'v4:estado'], [g[1] for g in self.guardados])
        with self.assertRaises(v.V4Error): v.guardar('prod', 'x', {'a': 'ñ' * 46000})   # no cabe en una celda del Sheet
        self.assertEqual(2, len(self.guardados))
        with patch.object(v.sala, 'get', return_value={'ok': True}), self.assertRaises(v.V4Error): v.leer()

    def test_semilla_ajustes_y_reglas(self):
        self.assertEqual(2, self.u['ajustes']['tope_clips_dia']); self.assertIn('marta', self.u['personajes'])
        self.assertIn('SIEMPRE es un cliente', self.u['guionista'])
        editado = v.universo_de({'universo': {'ajustes': {'tope_clips_dia': 7}, 'guionista': 'Otro criterio.'}})
        self.assertEqual((7, 10, 'Otro criterio.'), (editado['ajustes']['tope_clips_dia'], editado['ajustes']['episodios'], editado['guionista']))
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
        self.assertTrue(v.validar_serie({'titulo': 'x', 'episodios': []}, self.u))

    def test_prompt_un_personaje_nota_y_gancho(self):
        s = serie(); ep = dict(s['episodios'][0], bloque=30, accion2='She turns.', dialogo2='Adiós.')
        t1, t2 = v.prompt_toma(self.u, s, ep, 1), v.prompt_toma(self.u, s, ep, 2, 'más luz')
        self.assertIn('«Hola.»', t1); self.assertNotIn('ENDING', t1); self.assertIn('CHARACTER (Marta): A Mexican woman', t1)
        self.assertIn('«Adiós.»', t2); self.assertIn('ENDING: A hand.', t2); self.assertIn('más luz', t2)
        self.assertIn('ENDING', v.prompt_toma(self.u, s, s['episodios'][0]))
        self.assertNotIn('IMAGE_REF', t1); self.assertNotIn('reference images', t1)
        mudo = dict(s['episodios'][0], dialogo='')
        self.assertIn('No one speaks', v.prompt_toma(self.u, s, mudo))

    def test_prompt_con_retratos_e_invitado(self):
        s = serie(personajes={'raul': {'nombre': 'Raúl', 'aspecto': 'A tall man.', 'voz': 'deep'}})
        ep = dict(s['episodios'][2], invitados=['raul', 'raul', 'nadie'])
        self.assertEqual(['marta', 'raul'], v.elenco(self.u, s, ep))
        t = v.prompt_toma(self.u, s, ep, 1, '', ['marta', 'raul'])
        self.assertIn('CHARACTER 1 (Marta), the protagonist', t); self.assertIn('CHARACTER 2 (Raúl), a guest', t)
        self.assertLess(t.index('<IMAGE_REF_0>'), t.index('CHARACTER 2')); self.assertIn('<IMAGE_REF_1>', t)
        self.assertIn('Do not use them as the first frame', t); self.assertIn('said once by Marta', t)
        solo_invitado = v.prompt_toma(self.u, s, ep, 1, '', ['raul'])          # el orden de las imágenes manda
        self.assertIn('<IMAGE_REF_0>', solo_invitado.split('CHARACTER 2')[1]); self.assertNotIn('<IMAGE_REF_1>', solo_invitado)

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
        self.assertEqual(3, v.pendiente(s, dec, prod)[0]['n'])
        # el retrato sale del piloto de verdad (el 2) y el 3 lo usa
        d, llamadas = Drive(), []; d.archivos['c1'] = clip(6)
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append(referencias) or clip(6)
        e, u = self.e(dec, prod, s), self.ajustes(tope_clips_dia=9)
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual('E02-v1', prod['retratos']['marta']['de']); self.assertEqual(1, len(llamadas[0]))
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
        h = v.productor(e, self.u, False, gen, d, 'RAIZ')
        self.assertEqual(1, len(llamadas)); self.assertIn('listo para revisar', h[0])          # sólo el piloto
        self.assertEqual((None, None), llamadas[0][1:])                                          # el episodio 1 sale del texto
        prod = e['prod']['s1']; reg = prod['episodios']['1']['versiones'][0]
        self.assertEqual(1, prod['intentos']['2026-11-09']); self.assertEqual('RAIZ/_HISTORIAS/s1/E01-v1.mp4', reg['drive'])
        self.assertEqual((False, 1.05), (reg['con_retrato'], reg['costo_usd_aprox']))
        self.assertEqual({'episodios': {}, 'intentos': {'2026-11-09': 1}}, self.guardados[0][2])  # reserva ANTES del video
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        h = v.productor(e, self.u, False, gen, d, 'RAIZ')                                       # tope 2: cabe uno más hoy
        self.assertEqual(2, len(llamadas)); self.assertIn('tope del día', h[-1]); self.assertEqual(2, v.gastado_hoy(e))
        self.assertEqual([True], ['tope del día' in x for x in v.productor(e, self.u, False, gen, d, 'RAIZ')])
        self.assertEqual(2, len(llamadas))
        # un fallo también gasta la reserva y detiene la corrida
        e2 = self.e(dec={'serie': 'si'}); mal = lambda *a, **k: (_ for _ in ()).throw(MotorError('omni 429'))
        h = v.productor(e2, self.u, False, mal, d, 'RAIZ')
        self.assertIn('falló', h[0]); self.assertEqual(1, e2['prod']['s1']['intentos']['2026-11-09']); self.assertEqual({}, e2['prod']['s1']['episodios'])
        self.assertIn('falló', e2['prod']['s1']['avisos'][0]['texto'])
        # sin Drive no se reserva ni se llama al motor de pago
        class SinDrive(Drive):
            def ruta_carpetas(self, *n):
                raise self.DriveError('la unidad no contesta')
        e3 = self.e(dec={'serie': 'si'}); antes = len(llamadas)
        self.assertIn('Drive no está listo', v.productor(e3, self.u, False, gen, SinDrive(), 'RAIZ')[0])
        self.assertEqual((antes, {}), (len(llamadas), e3['prod']['s1']['intentos']))
        # sin aprobar, apagado y simulación no gastan
        self.assertIn('nada por producir', v.productor(self.e(), self.u, False, mal, d, 'RAIZ')[0])
        self.assertIn('apagado', v.productor(self.e(dec={'serie': 'si'}), self.ajustes(tope_clips_dia=0), False, mal, d, 'RAIZ')[0])
        antes = len(self.guardados)
        self.assertIn('simulación', v.productor(self.e(dec={'serie': 'si'}), self.u, True)[0]); self.assertEqual(antes, len(self.guardados))
        # una serie que dejó de ser válida no se produce
        rota = serie(); rota['episodios'][0]['accion'] = ''
        self.assertIn('no se produce', v.productor(self.e(dec={'serie': 'si'}, s=rota), self.u, False, mal, d, 'RAIZ')[0])

    def test_bloque_de_30_y_continuidad(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((jpg, referencias)) or clip()
        s = serie(2); s['episodios'][0].update(bloque=30, accion2='She turns.', dialogo2='Adiós.'); s['episodios'][1]['continua'] = True
        u = self.ajustes(tope_clips_dia=3, piloto_primero=0)
        e = self.e(dec={'serie': 'si'}, s=s)
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual(3, len(llamadas)); self.assertEqual((None, None), llamadas[0])
        for jpg, refs in llamadas[1:]:                                                          # arrancan en un cuadro del clip previo
            self.assertTrue(jpg[:2] == JPEG and refs is None)
        reg = e['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertEqual(30, reg['segundos']); self.assertEqual(2.1, reg['costo_usd_aprox']); self.assertEqual(3, v.gastado_hoy(e))
        self.assertEqual((['audio', 'video'], 2), (lambda f: (f[0], round(f[1])))(flujos(d.archivos[reg['drive']])))
        self.assertNotIn('retratos', e['prod']['s1'])                                           # con primer cuadro no hace falta retrato
        e2 = self.e(dec={'serie': 'si'}, s=s)
        self.assertIn('tope del día', v.productor(e2, self.ajustes(tope_clips_dia=1, piloto_primero=0), False, gen, d, 'R')[0])
        self.assertEqual(3, len(llamadas))                                                      # un bloque no entra a medias

    def test_retrato_del_personaje_viaja_a_los_episodios(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, jpg, referencias)) or clip(6)
        u = self.ajustes(tope_clips_dia=9)
        e = self.e(dec={'serie': 'si'})
        v.productor(e, u, False, gen, d, 'R')                                                   # episodio 1
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        v.productor(e, u, False, gen, d, 'R')                                                   # episodios 2 y 3
        prod = e['prod']['s1']
        self.assertEqual(3, len(llamadas)); self.assertEqual({'drive': 'R/_HISTORIAS/s1/retrato-marta.jpg', 'de': 'E01-v1'},
                                                             {k: prod['retratos']['marta'][k] for k in ('drive', 'de')})
        self.assertEqual(JPEG, d.archivos['R/_HISTORIAS/s1/retrato-marta.jpg'][:2])
        for texto, jpg, refs in llamadas[1:]:
            self.assertIsNone(jpg); self.assertEqual(1, len(refs)); self.assertEqual(JPEG, refs[0][:2]); self.assertIn('<IMAGE_REF_0>', texto)
        self.assertTrue(prod['episodios']['2']['versiones'][0]['con_retrato'])
        # el episodio 1 se rehace: no usa el retrato sacado de sí mismo, y el retrato se renueva después
        e['dec']['s1']['episodios']['1'] = {'v': 1, 'marca': 'cambio', 'nota': 'más joven'}
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual((None, None), llamadas[3][1:]); self.assertIn('más joven', llamadas[3][0])
        e['dec']['s1']['episodios'].update({'1': {'v': 2, 'marca': 'si'}, '2': {'v': 1, 'marca': 'cambio', 'nota': 'otra toma'}})
        v.productor(e, u, False, gen, d, 'R')
        self.assertEqual('E01-v2', prod['retratos']['marta']['de']); self.assertEqual(1, len(llamadas[4][2]))

    def test_retrato_rechazado_por_google_no_detiene(self):
        d, llamadas = Drive(), []
        def gen(texto, seg, jpg=None, referencias=None):
            llamadas.append((texto, referencias))
            if referencias:
                err = MotorError('omni_flash invalid_request: no'); err.http = 400; raise err
            return clip(6)
        s = serie(personajes={'marta': dict(self.u['personajes']['marta'], referencia_drive='RET')}); d.archivos['RET'] = JPEG + b'x'
        e = self.e(dec={'serie': 'si'}, s=s)
        h = v.productor(e, self.u, False, gen, d, 'R')                                          # trae retrato guardado: lo usa desde el episodio 1
        self.assertEqual(2, len(llamadas)); self.assertEqual(1, len(llamadas[0][1])); self.assertIsNone(llamadas[1][1])
        self.assertNotIn('IMAGE_REF', llamadas[1][0])
        reg = e['prod']['s1']['episodios']['1']['versiones'][0]
        self.assertFalse(reg['con_retrato']); self.assertIn('retrato', reg['aviso']); self.assertIn('retrato', h[0])
        self.assertEqual(1, e['prod']['s1']['intentos']['2026-11-09'])                          # una toma, aunque llamó dos veces
        def cobra(texto, seg, jpg=None, referencias=None):                                      # otro error con retrato SÍ detiene
            err = MotorError('omni_flash too_many_requests'); err.http = 429; raise err
        e2 = self.e(dec={'serie': 'si'}, s=s)
        self.assertIn('falló', v.productor(e2, self.u, False, cobra, d, 'R')[0])

    def test_primer_cuadro_rechazado_no_pierde_la_toma_pagada(self):
        d, llamadas = Drive(), []
        def gen(texto, seg, jpg=None, referencias=None):
            llamadas.append(('cuadro' if jpg else 'retrato' if referencias else 'texto'))
            if jpg:
                err = MotorError('omni_flash invalid_request: image'); err.http = 400; raise err
            return clip(6)
        # bloque de 30 s: la segunda toma no puede arrancar en el cuadro de la primera y sale del texto
        s = serie(2); s['episodios'][0].update(bloque=30, accion2='She turns.', dialogo2='Adiós.'); s['episodios'][1]['continua'] = True
        u = self.ajustes(tope_clips_dia=9, piloto_primero=0)
        e = self.e(dec={'serie': 'si'}, s=s)
        h = v.productor(e, u, False, gen, d, 'R')
        self.assertEqual(['texto', 'cuadro', 'texto', 'cuadro', 'retrato'], llamadas)          # el 2 baja de cuadro a retrato
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
    def test_semillero(self):
        pedidos = []
        pensar = lambda t, i: pedidos.append((t, i)) or CRUDO
        e = {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
        r = v.semillero(e, self.u, False, pensar, SIN_CANDADOS)
        self.assertIn('serie propuesta', r); self.assertIn('no hay candados', r); sid = list(e['serie'])[0]
        self.assertEqual('20261109-el-local-vacio', sid); self.assertEqual('ppp', e['serie'][sid]['vertice'])
        self.assertEqual(('expediente', 'v4:serie:' + sid), self.guardados[-1][:2]); self.assertEqual([], v.validar_serie(e['serie'][sid], self.u))
        pedido, instr = pedidos[0]
        self.assertIn('SIEMPRE es un cliente', instr); self.assertIn('en 10 episodios', instr); self.assertIn('"invitado_final"', instr)
        self.assertNotIn('{n}', instr); self.assertIn('Plan de Potencial', pedido); self.assertNotIn('Personajes conocidos', pedido)
        self.assertEqual('capital', v.vertice_siguiente(self.u, e['serie']))               # rota vértices
        e['serie']['otra'] = serie(); n = len(self.guardados)
        self.assertIn('esperando decisión', v.semillero(e, self.u, False, pensar, SIN_CANDADOS)); self.assertEqual(n, len(self.guardados))
        vacio = lambda: {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
        self.assertIn('no salió', v.semillero(vacio(), self.u, False, lambda t, i: dict(CRUDO, episodios=CRUDO['episodios'][:4]), SIN_CANDADOS))
        self.assertIn('no salió', v.semillero(vacio(), self.u, False, lambda t, i: None, SIN_CANDADOS))
        vetada = dict(CRUDO, trama='Una familia de Sonora')
        self.assertIn('vetada', v.semillero(vacio(), self.u, False, lambda t, i: vetada, SIN_CANDADOS))
        self.assertIn('apagado', v.semillero(vacio(), self.ajustes(semillero=0), False, pensar, SIN_CANDADOS))
        self.assertIn('simulación', v.semillero(vacio(), self.u, True)); self.assertEqual(n, len(self.guardados))
        propio = dict(self.u, guionista='Escribe comedias de {n} partes.')
        v.semillero(vacio(), propio, False, pensar, SIN_CANDADOS)
        self.assertTrue(pedidos[-1][1].startswith('Escribe comedias de 10 partes.'))        # el criterio es un dato de Dirección

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
        d = Drive(); d.archivos.update({'RET-MARTA': JPEG + b'm', 'R/_HISTORIAS/x/E09': clip(6)})
        aprobada = serie(); prod = {'retratos': {'marta': {'drive': 'RET-MARTA', 'de': 'E01-v1'}}, 'episodios': {}}
        e = self.e(dec={'serie': 'si'}, prod=prod, s=aprobada)
        self.assertEqual(['marta'], list(v.conocidos(e, self.u))); self.assertEqual({}, v.conocidos(self.e(prod=prod), self.u))   # sin aprobar no se presta
        pedidos = []
        r = v.semillero(e, self.ajustes(propuestas_en_espera=5), False, lambda t, i: pedidos.append(t) or dict(CRUDO, invitado_final='Marta'), SIN_CANDADOS)
        self.assertIn('serie propuesta', r); self.assertIn('Personajes conocidos', pedidos[0]); self.assertIn('Marta (restaurantera)', pedidos[0])
        nueva = e['serie']['20261109-el-local-vacio']
        self.assertEqual(['marta'], nueva['episodios'][-1]['invitados']); self.assertEqual([], nueva['episodios'][0]['invitados'])
        self.assertEqual(('RET-MARTA', 'invitado'), (nueva['personajes']['marta']['referencia_drive'], nueva['personajes']['marta']['papel']))
        # al producir el último episodio viajan los dos retratos, protagonista primero
        llamadas = []
        gen = lambda texto, seg, jpg=None, referencias=None: llamadas.append((texto, referencias)) or clip(6)
        e['dec'][nueva['id']] = {'serie': 'si', 'episodios': {str(i): {'v': 1, 'marca': 'si'} for i in range(1, 10)}}
        e['prod'][nueva['id']] = {'intentos': {}, 'episodios': {str(i): {'versiones': [{'v': 1, 'drive': 'R/_HISTORIAS/x/E09'}]} for i in range(1, 10)}}
        v.productor(e, self.ajustes(tope_clips_dia=9), False, gen, d, 'R')
        texto, refs = llamadas[-1]
        self.assertEqual(2, len(refs)); self.assertEqual(b'm', refs[1][2:]); self.assertIn('CHARACTER 2 (Marta), a guest', texto); self.assertIn('<IMAGE_REF_1>', texto)
        sin = v.armar_serie(dict(CRUDO, invitado_final=''), self.u, 'ppp', {}, v.conocidos(e, self.u))
        self.assertEqual([], sin['episodios'][-1]['invitados']); self.assertEqual(['raul'], list(sin['personajes']))

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
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {}}):
            self.assertEqual(0, v.main(['--simular']))
        self.assertEqual([], self.guardados)
        with patch.object(v.sala, 'get', side_effect=v.sala.SalaError('caída', codigo='sala_tiempo_agotado')):
            self.assertEqual(2, v.main([]))                                                 # «no contestó» nunca es «no hay nada»
        self.assertEqual([], self.guardados)
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {'v4:universo': self.u}}), \
                patch.object(v, 'semillero', return_value='ok'), patch.object(v, 'productor', side_effect=v.V4Error('sin drive_raiz')):
            self.assertEqual(1, v.main([]))
        self.assertEqual(['v4:estado'], [g[1] for g in self.guardados]); self.assertIn('se detuvo', self.guardados[0][2]['pasos'][-1])


if __name__ == '__main__':
    unittest.main()
