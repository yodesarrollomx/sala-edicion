#!/usr/bin/env python3
"""Sala 4.0 · historias en episodios de 15 segundos (9-nov-2026).

Una SERIE cuenta una historia en N episodios (de fábrica 10), uno por día. Cada episodio es
una toma continua de 15 s, o un bloque de 30 s hecho de dos tomas. Todo lo editable vive en
la hoja EXPEDIENTES, con la acción `expediente` que el Apps Script ya atiende (no se toca el
backend), en cinco clases de documento con UN solo dueño cada una:

    v4:universo        editor   formato, ajustes, vértices, personajes y lugares
    v4:serie:<id>      quien la crea (semillero o editor); después sólo el editor la edita
    v4:dec:<id>        editor   aprobar la serie y sí / cambio / no por episodio
    v4:prod:<id>       nube     versiones producidas, ligas de Drive, intentos, paquete
    v4:estado          nube     qué hizo la última corrida y qué falta

La nube NUNCA escribe `dec` (decidir es de los editores, INVIOLABLE 3) ni pisa `universo` o
una `serie` que ya existe: `guardar` se niega antes de la red.

El video lo genera Gemini Omni Flash (de pago). El gasto lo limita `ajustes.tope_clips_dia`,
y la reserva se anota ANTES de llamar: un intento fallido también cuenta. No pasa por la
COLA ni por `nube_ejecuta_etapas`; la línea vieja de video sigue en pausa.

Pasos, en orden: semillero → productor → paquete → estado. `--simular` no escribe ni gasta.
"""

import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unicodedata

import contenido_reglas
import sala_cliente as sala
from motores._comun import MotorError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SEMILLA = RAIZ / 'datos' / 'universo' / 'universo.json'
IDEAS = RAIZ / 'datos' / 'ideas.json'
PREFIJO = 'v4:'
DE_LA_NUBE = ('prod', 'estado')
PALABRAS_15S = 38                       # lo que cabe hablado en una toma de 15 s
MARCAS = ('si', 'cambio', 'no')
AJUSTES = {'semillero': 1, 'propuestas_en_espera': 2, 'episodios': 10, 'tope_clips_dia': 2,
           'piloto_primero': 1, 'listas_carpeta': ''}


class V4Error(RuntimeError):
    pass


def hoy():
    """La fecha de Dirección (UTC-7, sin horario de verano)."""
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=7)).strftime('%Y-%m-%d')


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ------------------------------------------------------------------ almacén

def separar(expedientes):
    """{'universo':…, 'serie':{id:…}, 'dec':{id:…}, 'prod':{id:…}, 'estado':…} de la hoja."""
    e = {'universo': None, 'serie': {}, 'dec': {}, 'prod': {}, 'estado': None}
    for llave, doc in (expedientes or {}).items():
        if not str(llave).startswith(PREFIJO) or not isinstance(doc, dict):
            continue
        clase, _, ident = str(llave)[len(PREFIJO):].partition(':')
        if clase in ('universo', 'estado'):
            e[clase] = doc
        elif clase in ('serie', 'dec', 'prod') and ident:
            e[clase][ident] = doc
    return e


def leer():
    datos = sala.get('expedientes')
    if not isinstance(datos.get('expedientes'), dict):
        raise V4Error('la hoja EXPEDIENTES no contestó con su contrato')   # «no contestó» ≠ «vacío»
    return separar(datos['expedientes'])


def guardar(clase, ident, doc, existe=False):
    """Escribe UN documento. La nube sólo es dueña de prod y estado; puede CREAR una serie o
    sembrar el universo, nunca pisarlos; y jamás escribe decisiones."""
    if clase == 'dec':
        raise V4Error('la nube no decide (INVIOLABLE 3): v4:dec es de los editores')
    if clase not in DE_LA_NUBE and existe:
        raise V4Error('v4:%s ya existe y es del editor: la nube no lo pisa' % clase)
    if clase not in DE_LA_NUBE + ('serie', 'universo'):
        raise V4Error('clase desconocida: %s' % clase)
    llave = PREFIJO + clase + (':' + ident if ident else '')
    return sala.post('expediente', pieza=llave, expediente=doc)


def universo_de(e):
    """El universo vigente; si el editor aún no guardó uno, la semilla del repo."""
    u = e['universo'] or json.loads(SEMILLA.read_text(encoding='utf-8'))
    u = dict(u)
    u['ajustes'] = dict(AJUSTES, **(u.get('ajustes') or {}))
    for k in ('vertices', 'personajes', 'lugares'):
        u[k] = u.get(k) or {}
    return u


def entero(v, defecto=0):
    try:
        return max(0, int(str(v).strip()))
    except (TypeError, ValueError):
        return defecto


# ------------------------------------------------------------------ la serie

def slug(texto):
    plano = ''.join(c for c in unicodedata.normalize('NFD', str(texto).lower()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '-', plano).strip('-')[:40] or 'serie'


def textos(dato):
    """Todo el texto de un documento, sin importar cómo se llamen sus campos."""
    if isinstance(dato, str):
        return [dato]
    if isinstance(dato, dict):
        return [t for v in dato.values() for t in textos(v)]
    if isinstance(dato, list):
        return [t for v in dato for t in textos(v)]
    return []


def exigir_sin_veto(dato):
    """El veto de ubicaciones sobre TODO el texto (el revisor común sólo mira ciertos campos)."""
    malas = contenido_reglas.prohibidas('\n'.join(textos(dato)))
    if malas:
        raise contenido_reglas.ContenidoVetado('requiere reescritura; ubicación vetada: ' + ', '.join(malas))


def validar_serie(s, universo):
    """Lista de problemas de una serie (vacía = se puede producir)."""
    p = []
    eps = s.get('episodios')
    if not str(s.get('titulo') or '').strip():
        p.append('falta el título')
    if not isinstance(eps, list) or not eps:
        return p + ['no trae episodios']
    quien = dict(universo.get('personajes') or {}, **(s.get('personajes') or {}))
    donde = dict(universo.get('lugares') or {}, **(s.get('lugares') or {}))
    if s.get('personaje') not in quien:
        p.append('el personaje «%s» no existe' % s.get('personaje'))
    for i, ep in enumerate(eps, 1):
        if not isinstance(ep, dict):
            p.append('episodio %d: mal formado' % i)
            continue
        if (ep.get('lugar') or s.get('lugar')) not in donde:
            p.append('episodio %d: el lugar no existe' % i)
        tomas = 2 if entero(ep.get('bloque'), 15) >= 30 else 1
        for t in range(1, tomas + 1):
            suf = '' if t == 1 else '2'
            if not str(ep.get('accion' + suf) or '').strip():
                p.append('episodio %d: falta la acción%s' % (i, ' de la segunda toma' if suf else ''))
            n = len(str(ep.get('dialogo' + suf) or '').split())
            if n > PALABRAS_15S:
                p.append('episodio %d: %d palabras no caben en 15 s (máximo %d)' % (i, n, PALABRAS_15S))
    try:
        exigir_sin_veto({k: s.get(k) for k in ('titulo', 'trama', 'episodios', 'personajes', 'lugares')})
    except contenido_reglas.ContenidoVetado as e:
        p.append(str(e))
    return p


def prompt_toma(universo, s, ep, toma=1, nota=''):
    """El texto que recibe Omni para UNA toma de 15 s."""
    f = universo.get('formato') or {}
    quien = dict(universo.get('personajes') or {}, **(s.get('personajes') or {}))[s['personaje']]
    lugar = dict(universo.get('lugares') or {}, **(s.get('lugares') or {}))[ep.get('lugar') or s['lugar']]
    suf = '' if toma == 1 else '2'
    dialogo = str(ep.get('dialogo' + suf) or '').strip()
    partes = [
        f.get('estilo', ''),
        'LOCATION: ' + lugar.get('aspecto', ''),
        'CHARACTER (%s): %s Voice: %s' % (quien.get('nombre', ''), quien.get('aspecto', ''), quien.get('voz', '')),
        'ACTION: ' + str(ep.get('accion' + suf) or ''),
        ('SPOKEN LINE, in Spanish, said once by %s: «%s»' % (quien.get('nombre', ''), dialogo)) if dialogo
        else 'No one speaks in this shot.',
        ('ENDING: ' + ep['gancho']) if ep.get('gancho') and (toma == 2 or entero(ep.get('bloque'), 15) < 30) else '',
        ('DIRECTOR NOTE, fix this from the previous version: ' + nota) if nota else '',
        f.get('audio', ''), f.get('prohibido', ''),
    ]
    return '\n'.join(x for x in partes if x)


# ------------------------------------------------------------------ 1 · semillero

INSTRUCCION_SERIE = (
    'Eres guionista de series cortas verticales para redes de una desarrolladora inmobiliaria y '
    'despacho de arquitectura. Escribe UNA historia contada en {n} episodios de 15 segundos, uno por '
    'día. El protagonista SIEMPRE es un cliente (cada serie, de una industria distinta). Cada episodio '
    'es una sola toma continua, sin cortes, en un solo lugar, con una sola frase hablada de máximo 32 '
    'palabras en español natural. Cada episodio termina con un gancho que obliga a ver el siguiente; el '
    'último cierra la historia y deja una puerta abierta hacia otra serie. La historia debe enseñar el '
    'vértice del negocio indicado sin sonar a anuncio: nada de precios, cifras de dinero, marcas, '
    'logotipos ni texto en pantalla. Devuelve SOLO un objeto JSON con esta forma exacta: '
    '{{"titulo": "...", "trama": "una línea", "personaje": {{"nombre": "...", "industria": "...", '
    '"aspecto": "descripción física y de vestuario EN INGLÉS, concreta y repetible", "voz": "cómo suena, '
    'en inglés", "quiere": "..."}}, "lugar": {{"nombre": "...", "aspecto": "descripción EN INGLÉS"}}, '
    '"episodios": [{{"titulo": "...", "accion": "qué hace el personaje y la cámara, EN INGLÉS", '
    '"dialogo": "la frase en español", "gancho": "el último segundo, EN INGLÉS"}}]}}')


def inspiracion(limite=10):
    """Títulos y bajadas de las ideas pasadas que no se descartaron: nutren, no se copian."""
    try:
        ideas = json.loads(IDEAS.read_text(encoding='utf-8')).get('ideas') or []
    except (OSError, ValueError):
        return []
    vivas = [i for i in ideas if str(i.get('estado')) != 'descartada']
    vivas.sort(key=lambda i: str(i.get('estado')) != 'en_produccion')
    return ['%s — %s' % (i.get('titulo', ''), i.get('bajada', '')) for i in vivas[:limite]]


def vertice_siguiente(universo, series):
    """El vértice menos contado hasta ahora (empates: orden del universo)."""
    usados = [s.get('vertice') for s in series.values()]
    vs = list(universo['vertices'])
    return min(vs, key=lambda v: (usados.count(v), vs.index(v))) if vs else ''


def armar_serie(crudo, universo, vertice, existentes):
    """De la respuesta del modelo a un documento de serie válido (o V4Error con el motivo)."""
    if not isinstance(crudo, dict):
        raise V4Error('el modelo no devolvió un objeto')
    titulo = str(crudo.get('titulo') or '').strip()
    base = '%s-%s' % (hoy().replace('-', ''), slug(titulo))
    sid, k = base, 2
    while sid in existentes:
        sid, k = '%s-%d' % (base, k), k + 1
    pj, lg = crudo.get('personaje') or {}, crudo.get('lugar') or {}
    if not isinstance(pj, dict) or not isinstance(lg, dict):
        raise V4Error('personaje o lugar mal formados')
    pid, lid = slug(pj.get('nombre') or 'cliente'), slug(lg.get('nombre') or 'lugar')
    eps = []
    for n, ep in enumerate(crudo.get('episodios') or [], 1):
        if not isinstance(ep, dict):
            raise V4Error('episodio %d mal formado' % n)
        eps.append({'n': n, 'titulo': str(ep.get('titulo') or '').strip(), 'accion': str(ep.get('accion') or '').strip(),
                    'dialogo': str(ep.get('dialogo') or '').strip(), 'gancho': str(ep.get('gancho') or '').strip(),
                    'bloque': 15, 'continua': False})
    s = {'id': sid, 'titulo': titulo, 'trama': str(crudo.get('trama') or '').strip(), 'vertice': vertice,
         'personaje': pid, 'lugar': lid, 'personajes': {pid: dict(pj, papel='cliente')}, 'lugares': {lid: lg},
         'episodios': eps, 'origen': 'semillero', 'creada': ahora()}
    quiere = entero(universo['ajustes'].get('episodios'), 10)
    if len(eps) != quiere:
        raise V4Error('trajo %d episodios y se pidieron %d' % (len(eps), quiere))
    problemas = validar_serie(s, universo)
    if problemas:
        raise V4Error('; '.join(problemas[:4]))
    return s


def semillero(e, universo, simular, pensar=None):
    aj = universo['ajustes']
    if not entero(aj.get('semillero')):
        return 'semillero apagado en Ajustes'
    espera = [i for i, s in e['serie'].items() if (e['dec'].get(i) or {}).get('serie') not in ('si', 'no')]
    if len(espera) >= entero(aj.get('propuestas_en_espera'), 2):
        return 'ya hay %d serie(s) esperando decisión' % len(espera)
    vertice = vertice_siguiente(universo, e['serie'])
    if not vertice:
        return 'el universo no tiene vértices'
    n = entero(aj.get('episodios'), 10)
    v = universo['vertices'][vertice]
    pedido = ('Vértice del negocio: %s — %s\nIndustrias de clientes ya usadas (elige otra): %s\n'
              'Ideas pasadas que pueden nutrir la historia (no las copies):\n- %s' % (
                  v.get('nombre', vertice), v.get('mensaje', ''),
                  ', '.join(sorted({str(p.get('industria')) for s in e['serie'].values()
                                    for p in (s.get('personajes') or {}).values() if p.get('industria')})) or 'ninguna',
                  '\n- '.join(inspiracion()) or 'ninguna'))
    if simular:
        return 'simulación: pediría una serie de %d episodios sobre «%s»' % (n, vertice)
    if pensar is None:
        from motores import cerebro
        from motores.estrategia import con_estrategia
        pensar = lambda texto, instr: cerebro._json_de(cerebro._gemini(texto, {}, con_estrategia(instr, {})))
    ultimo = None
    for _ in range(2):                    # un segundo intento si el JSON vino mal; no más
        try:
            s = armar_serie(pensar(pedido, INSTRUCCION_SERIE.format(n=n)), universo, vertice, e['serie'])
        except (V4Error, MotorError) as err:
            ultimo = err
            continue
        guardar('serie', s['id'], s, existe=False)
        e['serie'][s['id']] = s
        return 'serie propuesta: «%s» (%s)' % (s['titulo'], s['id'])
    return 'no salió una serie válida: %s' % sala.redactar(str(ultimo))[:200]


# ------------------------------------------------------------------ 2 · productor

def gastado_hoy(e, dia=None):
    dia = dia or hoy()
    return sum(entero((p.get('intentos') or {}).get(dia)) for p in e['prod'].values())


def ultima(prod, n):
    vs = ((prod.get('episodios') or {}).get(str(n)) or {}).get('versiones') or []
    return vs[-1] if vs else None


def pendiente(s, dec, prod, piloto_primero=True):
    """El siguiente episodio por producir: (episodio, versión nueva, nota) o None."""
    marcas = (dec or {}).get('episodios') or {}
    for ep in s.get('episodios') or []:
        n = entero(ep.get('n'))
        u, m = ultima(prod or {}, n), marcas.get(str(n)) or {}
        vigente = m if u and entero(m.get('v')) == entero(u.get('v')) else {}
        if not u:
            return ep, 1, ''
        if vigente.get('marca') == 'cambio':
            return ep, entero(u.get('v')) + 1, str(vigente.get('nota') or '')
        if n == 1 and piloto_primero and vigente.get('marca') != 'si':
            return None                  # el primer episodio es el piloto de la serie
    return None


def _ffmpeg(*args):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        raise MotorError('ffmpeg no pudo: %s' % sala.redactar(r.stderr)[-200:])


def ultimo_cuadro(video, destino):
    _ffmpeg('-sseof', '-0.2', '-i', str(video), '-frames:v', '1', '-q:v', '2', str(destino))
    return pathlib.Path(destino).read_bytes()


def unir(videos, destino):
    """Une tomas o episodios re-codificando: tolera clips que difieran en detalles."""
    if len(videos) == 1:
        pathlib.Path(destino).write_bytes(pathlib.Path(videos[0]).read_bytes())
        return destino
    entradas, filtro = [], ''
    for i, v in enumerate(videos):
        entradas += ['-i', str(v)]
        filtro += '[%d:v:0]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24[v%d];' % (i, i)
    filtro += ''.join('[v%d][%d:a:0]' % (i, i) for i in range(len(videos)))
    filtro += 'concat=n=%d:v=1:a=1[v][a]' % len(videos)
    _ffmpeg(*entradas, '-filter_complex', filtro, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(destino))
    return destino


def producir_episodio(universo, s, ep, version, nota, prod, tmp, generar, drive, raiz):
    """Genera las tomas de UN episodio, las une, sube el video y devuelve su registro."""
    tomas = 2 if entero(ep.get('bloque'), 15) >= 30 else 1
    n = entero(ep.get('n'))
    arranque = None
    if ep.get('continua') and n > 1 and ultima(prod, n - 1):
        previo = drive.bajar(ultima(prod, n - 1)['drive'], str(tmp / 'previo.mp4'))
        arranque = ultimo_cuadro(previo, tmp / 'previo.jpg')
    clips = []
    for t in range(1, tomas + 1):
        texto = prompt_toma(universo, s, ep, t, nota)
        exigir_sin_veto(texto)
        clip = tmp / ('toma%d.mp4' % t)
        clip.write_bytes(generar(texto, 15, jpg=arranque))
        clips.append(clip)
        if t < tomas:
            arranque = ultimo_cuadro(clip, tmp / ('toma%d.jpg' % t))
    final = unir(clips, tmp / ('E%02d-v%d.mp4' % (n, version)))
    fid = drive.subir(str(final), drive.ruta_carpetas(raiz, '_HISTORIAS', s['id']))
    if not fid:
        raise drive.DriveError('Drive no confirmó el video')
    return {'v': version, 'drive': fid, 'cuando': ahora(), 'segundos': 15 * tomas, 'nota_atendida': nota}


def productor(e, universo, simular, generar=None, drive=None, raiz=None):
    aj = universo['ajustes']
    tope, hecho = entero(aj.get('tope_clips_dia')), []
    if tope <= 0:
        return ['productor apagado: tope de clips en 0']
    dia = hoy()
    for sid in sorted(e['serie'], key=lambda i: str(e['serie'][i].get('creada'))):
        s, dec = e['serie'][sid], e['dec'].get(sid) or {}
        if dec.get('serie') != 'si':
            continue
        problemas = validar_serie(s, universo)
        if problemas:
            hecho.append('«%s» no se produce: %s' % (s.get('titulo'), '; '.join(problemas[:2])))
            continue
        while True:
            prod = e['prod'].setdefault(sid, {'episodios': {}, 'intentos': {}})
            sig = pendiente(s, dec, prod, bool(entero(aj.get('piloto_primero'), 1)))
            if not sig:
                break
            ep, version, nota = sig
            tomas = 2 if entero(ep.get('bloque'), 15) >= 30 else 1
            if gastado_hoy(e, dia) + tomas > tope:
                hecho.append('tope del día alcanzado (%d clips): «%s» episodio %s espera a mañana'
                             % (tope, s.get('titulo'), ep.get('n')))
                return hecho
            if simular:
                hecho.append('simulación: produciría «%s» episodio %s v%d' % (s.get('titulo'), ep.get('n'), version))
                break
            if generar is None:
                import sala_drive as drive
                from motores import escena_omni
                generar = escena_omni.generar
                raiz = str(((sala.get('reglas') or {}).get('reglas') or {}).get('drive_raiz') or '').strip()
                if not raiz:
                    raise V4Error('la REGLA drive_raiz está vacía: no hay dónde guardar el video')
            # La reserva se anota ANTES de gastar: un intento fallido también cuenta.
            prod.setdefault('intentos', {})[dia] = entero(prod['intentos'].get(dia)) + tomas
            guardar('prod', sid, prod)
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    reg = producir_episodio(universo, s, ep, version, nota, prod, pathlib.Path(tmp), generar, drive, raiz)
            except (MotorError, contenido_reglas.ContenidoVetado, drive.DriveError) as err:
                aviso = '«%s» episodio %s v%d falló: %s' % (s.get('titulo'), ep.get('n'), version,
                                                           sala.redactar(str(err))[:200])
                prod.setdefault('avisos', []).append({'cuando': ahora(), 'texto': aviso})
                prod['avisos'] = prod['avisos'][-10:]
                guardar('prod', sid, prod)
                hecho.append(aviso)
                return hecho              # un fallo detiene la corrida: no se insiste gastando
            prod['episodios'].setdefault(str(entero(ep.get('n'))), {'versiones': []})['versiones'].append(reg)
            guardar('prod', sid, prod)
            hecho.append('«%s» episodio %s v%d listo para revisar' % (s.get('titulo'), ep.get('n'), version))
    return hecho or ['nada por producir: no hay series aprobadas con episodios pendientes']


# ------------------------------------------------------------------ 3 · paquete

def completa(s, dec, prod):
    """True si TODOS los episodios tienen «sí» sobre su última versión."""
    marcas = (dec or {}).get('episodios') or {}
    for ep in s.get('episodios') or []:
        u, m = ultima(prod or {}, entero(ep.get('n'))), marcas.get(str(entero(ep.get('n')))) or {}
        if not u or m.get('marca') != 'si' or entero(m.get('v')) != entero(u.get('v')):
            return False
    return bool(s.get('episodios'))


def copy_de(s, universo):
    v = (universo.get('vertices') or {}).get(s.get('vertice')) or {}
    lineas = ['COPY · %s' % s.get('titulo', ''), '', s.get('trama', ''), '', 'Vértice: %s — %s' % (
        v.get('nombre', ''), v.get('mensaje', '')), '', 'Un episodio por día:']
    lineas += ['Día %s · %s — «%s»' % (ep.get('n'), ep.get('titulo', ''), ep.get('dialogo', ''))
               for ep in s.get('episodios') or []]
    lineas += ['', 'Borrador: revisar contra los candados antes de publicar. Publicar es el clic de Dirección.']
    return '\n'.join(lineas)


def paquete(e, universo, simular, drive=None, raiz=None):
    hecho = []
    for sid, s in e['serie'].items():
        prod = e['prod'].get(sid) or {}
        if prod.get('paquete') or not completa(s, e['dec'].get(sid), prod):
            continue
        if simular:
            hecho.append('simulación: armaría el paquete de «%s»' % s.get('titulo'))
            continue
        if drive is None:
            import sala_drive as drive
            raiz = str(((sala.get('reglas') or {}).get('reglas') or {}).get('drive_raiz') or '').strip()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            clips = [drive.bajar(ultima(prod, entero(ep.get('n')))['drive'], str(tmp / ('E%02d.mp4' % entero(ep.get('n')))))
                     for ep in s['episodios']]
            entera = unir(clips, tmp / 'HISTORIA-COMPLETA.mp4')
            texto = tmp / 'COPY.txt'
            texto.write_text(copy_de(s, universo), encoding='utf-8')
            carpeta, donde = None, str(universo['ajustes'].get('listas_carpeta') or '').strip()
            if donde:
                try:
                    carpeta = drive.asegurar_carpeta(donde, s['id'])
                except drive.DriveError:
                    carpeta = None       # sin permiso en esa carpeta: cae a la de historias
            carpeta = carpeta or drive.ruta_carpetas(raiz, '_HISTORIAS', s['id'], '_PAQUETE')
            for archivo in [str(c) for c in clips] + [str(entera), str(texto)]:
                drive.subir(archivo, carpeta)
        prod['paquete'] = {'carpeta': carpeta, 'cuando': ahora()}
        guardar('prod', sid, prod)
        hecho.append('paquete de «%s» listo en Drive' % s.get('titulo'))
    return hecho or ['ningún paquete nuevo']


# ------------------------------------------------------------------ 4 · estado

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--solo', choices=('semillero', 'productor', 'paquete'))
    a = ap.parse_args(argv)
    sala.enmascarar_en_actions()
    e = leer()                            # si la hoja no contesta, aquí se detiene con error
    universo = universo_de(e)
    if e['universo'] is None and not a.simular:
        guardar('universo', '', universo, existe=False)      # siembra una sola vez
    pasos = []
    try:
        if a.solo in (None, 'semillero'):
            pasos.append(semillero(e, universo, a.simular))
        if a.solo in (None, 'productor'):
            pasos += productor(e, universo, a.simular)
        if a.solo in (None, 'paquete'):
            pasos += paquete(e, universo, a.simular)
    finally:
        tope = entero(universo['ajustes'].get('tope_clips_dia'))
        estado = {'cuando': ahora(), 'pasos': pasos, 'clips_hoy': gastado_hoy(e), 'tope': tope,
                  'simulacion': bool(a.simular)}
        for linea in pasos:
            sala.avisar('· ' + linea)
        if not a.simular:
            guardar('estado', '', estado)
    return 0


if __name__ == '__main__':
    sys.exit(main())
