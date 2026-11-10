import copy, json, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
import sala_v4 as v
from motores._comun import MotorError


def clip(segundos=1):
    """Un MP4 de verdad, con audio, para que ffmpeg una y saque cuadros como en producción."""
    with tempfile.TemporaryDirectory() as t:
        f = pathlib.Path(t) / 'c.mp4'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=180x320:rate=24',
                        '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', str(segundos), '-pix_fmt', 'yuv420p', str(f)], check=True)
        return f.read_bytes()


class Drive:
    class DriveError(RuntimeError):
        pass

    def __init__(self):
        self.archivos, self.falla = {}, False

    def ruta_carpetas(self, *n):
        return '/'.join(n)

    def asegurar_carpeta(self, padre, nombre):
        return padre + '/' + nombre

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
        with patch.object(v.sala, 'get', return_value={'ok': True}), self.assertRaises(v.V4Error): v.leer()

    def test_semilla_y_ajustes(self):
        self.assertEqual(2, self.u['ajustes']['tope_clips_dia']); self.assertIn('marta', self.u['personajes'])
        self.assertEqual(7, v.universo_de({'universo': {'ajustes': {'tope_clips_dia': 7}}})['ajustes']['tope_clips_dia'])
        self.assertEqual(10, v.universo_de({'universo': {'ajustes': {}}})['ajustes']['episodios'])

    def test_validar_serie(self):
        self.assertEqual([], v.validar_serie(serie(), self.u))
        larga = serie(); larga['episodios'][0]['dialogo'] = ' '.join(['palabra'] * 39)
        self.assertIn('no caben', ' '.join(v.validar_serie(larga, self.u)))
        self.assertTrue(v.validar_serie(serie(personaje='nadie'), self.u))
        bloque = serie(); bloque['episodios'][0]['bloque'] = 30
        self.assertIn('segunda toma', ' '.join(v.validar_serie(bloque, self.u)))
        vetada = serie(); vetada['episodios'][1]['dialogo'] = 'Vivo en Hermosillo.'
        self.assertTrue(v.validar_serie(vetada, self.u))
        self.assertTrue(v.validar_serie({'titulo': 'x', 'episodios': []}, self.u))

    def test_prompt_lleva_nota_y_gancho_solo_al_final(self):
        s = serie(); ep = dict(s['episodios'][0], bloque=30, accion2='She turns.', dialogo2='Adiós.')
        t1, t2 = v.prompt_toma(self.u, s, ep, 1), v.prompt_toma(self.u, s, ep, 2, 'más luz')
        self.assertIn('«Hola.»', t1); self.assertNotIn('ENDING', t1)
        self.assertIn('«Adiós.»', t2); self.assertIn('ENDING: A hand.', t2); self.assertIn('más luz', t2)
        self.assertIn('ENDING', v.prompt_toma(self.u, s, s['episodios'][0]))

    def test_pendiente_piloto_cambio_y_no(self):
        s = serie(); ver = lambda n, k=1: {'versiones': [{'v': i, 'drive': 'd'} for i in range(1, k + 1)]}
        self.assertEqual((1, 1), v.pendiente(s, {}, {})[0:2][0]['n'] and (v.pendiente(s, {}, {})[0]['n'], v.pendiente(s, {}, {})[1]))
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

    def test_productor_reserva_tope_y_fallo(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None: llamadas.append((texto, jpg)) or clip()
        e = self.e(dec={'serie': 'si'})
        h = v.productor(e, self.u, False, gen, d, 'RAIZ')
        self.assertEqual(1, len(llamadas)); self.assertIn('listo para revisar', h[0])          # sólo el piloto
        prod = e['prod']['s1']
        self.assertEqual(1, prod['intentos']['2026-11-09']); self.assertEqual('RAIZ/_HISTORIAS/s1/E01-v1.mp4', prod['episodios']['1']['versiones'][0]['drive'])
        self.assertEqual({'episodios': {}, 'intentos': {'2026-11-09': 1}}, self.guardados[0][2])  # reserva ANTES del video
        e['dec']['s1']['episodios'] = {'1': {'v': 1, 'marca': 'si'}}
        h = v.productor(e, self.u, False, gen, d, 'RAIZ')                                       # tope 2: cabe uno más hoy
        self.assertEqual(2, len(llamadas)); self.assertIn('tope del día', h[-1]); self.assertEqual(2, v.gastado_hoy(e))
        self.assertEqual(['tope del día' in x for x in v.productor(e, self.u, False, gen, d, 'RAIZ')], [True])
        self.assertEqual(2, len(llamadas))
        # un fallo también gasta la reserva y detiene la corrida
        e2 = self.e(dec={'serie': 'si'}); mal = lambda *a, **k: (_ for _ in ()).throw(MotorError('omni 429'))
        h = v.productor(e2, self.u, False, mal, d, 'RAIZ')
        self.assertIn('falló', h[0]); self.assertEqual(1, e2['prod']['s1']['intentos']['2026-11-09']); self.assertEqual({}, e2['prod']['s1']['episodios'])
        # sin aprobar, apagado y simulación no gastan
        self.assertIn('nada por producir', v.productor(self.e(), self.u, False, mal, d, 'RAIZ')[0])
        apagado = dict(self.u, ajustes=dict(self.u['ajustes'], tope_clips_dia=0))
        self.assertIn('apagado', v.productor(self.e(dec={'serie': 'si'}), apagado, False, mal, d, 'RAIZ')[0])
        antes = len(self.guardados)
        self.assertIn('simulación', v.productor(self.e(dec={'serie': 'si'}), self.u, True)[0]); self.assertEqual(antes, len(self.guardados))

    def test_bloque_de_30_y_continuidad(self):
        d, llamadas = Drive(), []
        gen = lambda texto, seg, jpg=None: llamadas.append(jpg) or clip()
        s = serie(2); s['episodios'][0].update(bloque=30, accion2='She turns.', dialogo2='Adiós.'); s['episodios'][1]['continua'] = True
        u = dict(self.u, ajustes=dict(self.u['ajustes'], tope_clips_dia=3, piloto_primero=0))
        e = self.e(dec={'serie': 'si'}, s=s)
        h = v.productor(e, u, False, gen, d, 'R')
        self.assertEqual(3, len(llamadas)); self.assertIsNone(llamadas[0])
        self.assertTrue(llamadas[1][:2] == b'\xff\xd8' and llamadas[2][:2] == b'\xff\xd8')     # arrancan en un JPEG del clip previo
        self.assertEqual(30, e['prod']['s1']['episodios']['1']['versiones'][0]['segundos']); self.assertEqual(3, v.gastado_hoy(e))
        u2 = dict(u, ajustes=dict(u['ajustes'], tope_clips_dia=1)); e2 = self.e(dec={'serie': 'si'}, s=s)
        self.assertIn('tope del día', v.productor(e2, u2, False, gen, d, 'R')[0]); self.assertEqual(3, len(llamadas))   # un bloque no entra a medias

    def test_semillero(self):
        crudo = {'titulo': 'El local vacío', 'trama': 'x', 'personaje': {'nombre': 'Raúl', 'industria': 'ferretero', 'aspecto': 'A man', 'voz': 'warm', 'quiere': 'y'},
                 'lugar': {'nombre': 'El local', 'aspecto': 'An empty shop'},
                 'episodios': [{'titulo': 'E', 'accion': 'He walks.', 'dialogo': 'Hola.', 'gancho': 'A door.'}] * 10}
        e = {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
        r = v.semillero(e, self.u, False, lambda t, i: crudo)
        self.assertIn('serie propuesta', r); sid = list(e['serie'])[0]
        self.assertEqual('20261109-el-local-vacio', sid); self.assertEqual('ppp', e['serie'][sid]['vertice'])
        self.assertEqual(('expediente', 'v4:serie:' + sid), self.guardados[-1][:2]); self.assertEqual([], v.validar_serie(e['serie'][sid], self.u))
        self.assertEqual('capital', v.vertice_siguiente(self.u, e['serie']))               # rota vértices
        e['serie']['otra'] = serie(); n = len(self.guardados)
        self.assertIn('esperando decisión', v.semillero(e, self.u, False, lambda t, i: crudo)); self.assertEqual(n, len(self.guardados))
        vacio = {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
        self.assertIn('no salió', v.semillero(vacio, self.u, False, lambda t, i: dict(crudo, episodios=crudo['episodios'][:4])))
        self.assertIn('no salió', v.semillero(vacio, self.u, False, lambda t, i: None)); self.assertEqual({}, vacio['serie'])
        apagado = dict(self.u, ajustes=dict(self.u['ajustes'], semillero=0))
        self.assertIn('apagado', v.semillero(vacio, apagado, False, lambda t, i: crudo))
        self.assertIn('simulación', v.semillero(vacio, self.u, True)); self.assertEqual(n, len(self.guardados))

    def test_paquete(self):
        d = Drive(); s = serie(2)
        prod = {'episodios': {str(i): {'versiones': [{'v': 1, 'drive': 'c%d' % i}]} for i in (1, 2)}}
        d.archivos.update(c1=clip(), c2=clip())
        dec = {'serie': 'si', 'episodios': {'1': {'v': 1, 'marca': 'si'}, '2': {'v': 1, 'marca': 'cambio'}}}
        self.assertFalse(v.completa(s, dec, prod)); self.assertEqual(['ningún paquete nuevo'], v.paquete(self.e(dec, prod, s), self.u, False, d, 'R'))
        dec['episodios']['2'] = {'v': 1, 'marca': 'si'}; e = self.e(dec, prod, s)
        self.assertIn('listo en Drive', v.paquete(e, self.u, False, d, 'R')[0])
        carpeta = e['prod']['s1']['paquete']['carpeta']; nombres = sorted(k.rsplit('/', 1)[1] for k in d.archivos if k.startswith(carpeta))
        self.assertEqual(['COPY.txt', 'E01.mp4', 'E02.mp4', 'HISTORIA-COMPLETA.mp4'], nombres)
        self.assertIn('La prueba', d.archivos[carpeta + '/COPY.txt'].decode()); self.assertGreater(len(d.archivos[carpeta + '/HISTORIA-COMPLETA.mp4']), 1000)
        self.assertEqual(['ningún paquete nuevo'], v.paquete(e, self.u, False, d, 'R'))    # no se arma dos veces

    def test_main_siembra_universo_y_deja_estado(self):
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {'La Servilleta': {}}}), patch.object(v, 'semillero', return_value='ok'):
            self.assertEqual(0, v.main([]))
        self.assertEqual(['v4:universo', 'v4:estado'], [g[1] for g in self.guardados]); self.assertEqual(0, self.guardados[-1][2]['clips_hoy'])
        self.guardados.clear()
        with patch.object(v.sala, 'get', return_value={'ok': True, 'expedientes': {}}):
            self.assertEqual(0, v.main(['--simular']))
        self.assertEqual([], self.guardados)


if __name__ == '__main__':
    unittest.main()
