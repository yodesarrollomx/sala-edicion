#!/usr/bin/env python3
"""Sala 4.0 · historias en episodios de 15 segundos (9-nov-2026).

Una SERIE cuenta una historia en N episodios (de fábrica 10), uno por día. Cada episodio es
una toma continua de 15 s, o un bloque de 30 s hecho de dos tomas. Todo lo editable vive en
la hoja EXPEDIENTES, con la acción `expediente` que el Apps Script ya atiende (no se toca el
backend), en cinco clases de documento con UN solo dueño cada una:

    v4:universo        editor   formato, ajustes, vértices, personajes, lugares, guionista
    v4:serie:<id>      quien la crea (semillero o editor); después sólo el editor la edita
    v4:dec:<id>        editor   aprobar la serie y sí / cambio / no por episodio («no» = queda fuera)
    v4:prod:<id>       nube     versiones producidas, ligas de Drive, retratos, intentos, paquete
    v4:estado          nube     qué hizo la última corrida y qué falta

La nube NUNCA escribe `dec` (decidir es de los editores, INVIOLABLE 3) ni pisa `universo` o
una `serie` que ya existe: `guardar` se niega antes de la red.

El video lo genera Gemini Omni Flash (de pago). El gasto lo limita `ajustes.tope_clips_dia`,
y la reserva se anota ANTES de llamar: un intento fallido también cuenta. No pasa por la
COLA ni por `nube_ejecuta_etapas`; la línea vieja de video sigue en pausa.

El mismo personaje en todos los episodios: del episodio 1 se saca un RETRATO (un cuadro del
video) que viaja como imagen de referencia a los episodios siguientes; un personaje guardado
en el universo o tomado de otra serie trae el suyo. Así una historia puede cruzarse con otra.

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
USD_POR_TOMA = 1.05                     # 15 s a 0.07 USD/s en 720p; aproximado, para informar
CARPETA_VIDEOS = '_HISTORIAS'
CARPETA_LISTAS = '_LISTAS PARA PUBLICAR'   # la misma de la estación de salida (Sala corta)
LIMITE_CELDA = 45000                    # cada documento vive en UNA celda del Sheet (tope real: 50 000)
AJUSTES = {'semillero': 1, 'propuestas_en_espera': 2, 'episodios': 10, 'tope_clips_dia': 2,
           'piloto_primero': 1, 'modelo_guion': 'gemini-3.6-flash'}


class V4Error(RuntimeError):
    pass


def hoy():
    """La fecha de Dirección (UTC-7, sin horario de verano)."""
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=7)).strftime('%Y-%m-%d')


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def entero(v, defecto=0):
    try:
        return max(0, int(str(v).strip()))
    except (TypeError, ValueError):
        return defecto


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
    if len(json.dumps(doc, ensure_ascii=False, separators=(',', ':'))) > LIMITE_CELDA:
        raise V4Error('%s ya no cabe en una celda del Sheet (más de %d caracteres)' % (llave, LIMITE_CELDA))
    return sala.post('expediente', pieza=llave, expediente=doc)


def regla(nombre):
    """Una REGLA del Sheet; el backend la entrega como texto o como {'valor': …}."""
    v = ((sala.get('reglas') or {}).get('reglas') or {}).get(nombre)
    if isinstance(v, dict):
        v = v.get('valor')
    return str(v if v is not None else '').strip()


def semilla():
    return json.loads(SEMILLA.read_text(encoding='utf-8'))


def universo_de(e):
    """El universo vigente; si el editor aún no guardó uno, la semilla del repo."""
    u = dict(e['universo'] or semilla())
    u['ajustes'] = dict(AJUSTES, **(u.get('ajustes') or {}))
    for k in ('vertices', 'personajes', 'lugares'):
        u[k] = u.get(k) or {}
    if not str(u.get('guionista') or '').strip():
        u['guionista'] = semilla().get('guionista', '')
    return u


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


def reparto(universo, s):
    """Todos los personajes que la serie puede usar: los suyos pisan a los del universo."""
    return dict(universo.get('personajes') or {}, **(s.get('personajes') or {}))


def lugares_de(universo, s):
    return dict(universo.get('lugares') or {}, **(s.get('lugares') or {}))


def elenco(universo, s, ep):
    """Los personajes de un episodio, protagonista primero, sin repetir ni inventar."""
    todos, out = reparto(universo, s), []
    for pid in [s.get('personaje')] + [i for i in (ep.get('invitados') or []) if isinstance(i, str)]:
        if pid in todos and pid not in out:
            out.append(pid)
    return out


def tomas_de(ep):
    return 2 if entero(ep.get('bloque'), 15) >= 30 else 1


def validar_serie(s, universo):
    """Lista de problemas de una serie (vacía = se puede producir)."""
    p = []
    eps = s.get('episodios')
    if not str(s.get('titulo') or '').strip():
        p.append('falta el título')
    if not isinstance(eps, list) or not eps:
        return p + ['no trae episodios']
    quien, donde = reparto(universo, s), lugares_de(universo, s)
    if s.get('personaje') not in quien:
        p.append('el personaje «%s» no existe' % s.get('personaje'))
    for i, ep in enumerate(eps, 1):
        if not isinstance(ep, dict):
            p.append('episodio %d: mal formado' % i)
            continue
        if (ep.get('lugar') or s.get('lugar')) not in donde:
            p.append('episodio %d: el lugar no existe' % i)
        for inv in ep.get('invitados') or []:
            if inv not in quien:
                p.append('episodio %d: el invitado «%s» no existe' % (i, inv))
        for t in range(1, tomas_de(ep) + 1):
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


def prompt_toma(universo, s, ep, toma=1, nota='', con_retrato=()):
    """El texto que recibe Omni para UNA toma de 15 s.

    `con_retrato` son los personajes cuyo retrato viaja como imagen de referencia, en el mismo
    orden en que van las imágenes: el texto los nombra <IMAGE_REF_0>, <IMAGE_REF_1>…
    """
    f = universo.get('formato') or {}
    todos, quienes = reparto(universo, s), elenco(universo, s, ep)
    lugar = lugares_de(universo, s)[ep.get('lugar') or s['lugar']]
    con_retrato = [p for p in con_retrato if p in quienes]
    suf = '' if toma == 1 else '2'
    dialogo = str(ep.get('dialogo' + suf) or '').strip()
    lineas = []
    for k, pid in enumerate(quienes):
        p = todos[pid]
        if len(quienes) == 1:
            linea = 'CHARACTER (%s): %s' % (p.get('nombre', ''), p.get('aspecto', ''))
        else:
            linea = 'CHARACTER %d (%s), %s: %s' % (k + 1, p.get('nombre', ''),
                                                    'the protagonist' if k == 0 else 'a guest who appears briefly',
                                                    p.get('aspecto', ''))
        if pid in con_retrato:
            linea += (' This is the person shown in <IMAGE_REF_%d>: keep the same face, hair, age and clothing.'
                      % con_retrato.index(pid))
        if k == 0:
            linea += ' Voice: %s' % p.get('voz', '')
        lineas.append(linea)
    partes = [
        f.get('estilo', ''),
        'LOCATION: ' + lugar.get('aspecto', ''),
    ] + lineas + [
        'The reference images only show who the characters are. Do not use them as the first frame '
        'and do not copy their background.' if con_retrato else '',
        'ACTION: ' + str(ep.get('accion' + suf) or ''),
        ('SPOKEN LINE, in Spanish, said once by %s: «%s»' % (todos[quienes[0]].get('nombre', ''), dialogo)) if dialogo
        else 'No one speaks in this shot.',
        ('ENDING: ' + ep['gancho']) if ep.get('gancho') and (toma == 2 or tomas_de(ep) == 1) else '',
        ('DIRECTOR NOTE, fix this from the previous version: ' + nota) if nota else '',
        f.get('audio', ''), f.get('prohibido', ''),
    ]
    return '\n'.join(x for x in partes if x)


# ------------------------------------------------------------------ 1 · semillero

# La FORMA de la respuesta es fija (de ella depende leerla). El criterio del guionista es un
# DATO: `universo.guionista`, que Dirección edita en la pantalla Historias.
FORMA_SERIE = (
    ' Escribe UNA historia contada en {n} episodios de 15 segundos. Devuelve SOLO un objeto JSON con '
    'esta forma exacta: {{"titulo": "...", "trama": "una línea", "personaje": {{"nombre": "...", '
    '"industria": "...", "aspecto": "descripción física y de vestuario EN INGLÉS, concreta y repetible", '
    '"voz": "cómo suena, en inglés", "quiere": "..."}}, "lugar": {{"nombre": "...", "aspecto": '
    '"descripción EN INGLÉS"}}, "invitado_final": "nombre exacto de un personaje conocido de la lista, o '
    'cadena vacía", "episodios": [{{"titulo": "...", "accion": "qué hace el personaje y la cámara, EN '
    'INGLÉS", "dialogo": "la frase en español, máximo 32 palabras", "gancho": "el último segundo, EN '
    'INGLÉS"}}]}}')


def inspiracion(limite=10):
    """Títulos y bajadas de las ideas pasadas que no se descartaron: nutren, no se copian."""
    try:
        ideas = json.loads(IDEAS.read_text(encoding='utf-8')).get('ideas') or []
    except (OSError, ValueError):
        return []
    vivas = [i for i in ideas if str(i.get('estado')) != 'descartada']
    vivas.sort(key=lambda i: str(i.get('estado')) != 'en_produccion')
    return ['%s — %s' % (i.get('titulo', ''), i.get('bajada', '')) for i in vivas[:limite]]


def candados_texto(leer_candados=None):
    """Los candados activos de Dirección, para que el guionista los respete al escribir.
    Devuelve (texto, aviso): sin candados se escribe igual, pero la corrida lo dice."""
    try:
        filas = (leer_candados or (lambda: (sala.get('candados') or {}).get('candados')))()
    except sala.SalaError as err:
        return '', 'no leí los candados (%s): la serie se escribió sólo con la estrategia común' % getattr(err, 'codigo', 'sin código')
    lineas = []
    for c in filas if isinstance(filas, list) else []:
        if not isinstance(c, dict) or str(c.get('activo', '1')).strip().lower() in ('0', 'false', ''):
            continue
        texto = str(c.get('candado') or '').strip()
        if texto:
            lineas.append('- [%s · de %s] %s' % (str(c.get('tipo') or 'regla').strip(), str(c.get('de') or 'Dirección').strip(), texto))
    if not lineas:
        return '', 'no hay candados activos que aplicar'
    return '\n'.join(lineas)[:6000], ''


def vertice_siguiente(universo, series):
    """El vértice menos contado hasta ahora (empates: orden del universo)."""
    usados = [s.get('vertice') for s in series.values()]
    vs = list(universo['vertices'])
    return min(vs, key=lambda v: (usados.count(v), vs.index(v))) if vs else ''


def conocidos(e, universo):
    """Personajes que ya tienen retrato y pueden volver como invitados: los guardados en el
    universo y los protagonistas de series aprobadas. {id: personaje con referencia_drive}."""
    out = {}
    for pid, p in (universo.get('personajes') or {}).items():
        if isinstance(p, dict) and str(p.get('referencia_drive') or '').strip():
            out[pid] = dict(p)
    for sid, s in e['serie'].items():
        if (e['dec'].get(sid) or {}).get('serie') != 'si':
            continue
        pid = s.get('personaje')
        p, fid = reparto(universo, s).get(pid), retrato_de(pid, universo, s, e['prod'].get(sid))
        if isinstance(p, dict) and fid and pid not in out:
            out[pid] = dict(p, referencia_drive=fid)
    return out


def armar_serie(crudo, universo, vertice, existentes, invitables=None):
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
                    'bloque': 15, 'continua': False, 'invitados': []})
    personajes = {pid: dict(pj, papel='cliente')}
    pedido = str(crudo.get('invitado_final') or '').strip()
    invitado = slug(pedido) if pedido else None
    for gid, g in (invitables or {}).items():
        # El invitado llega con su retrato: así sale igual que en su propia historia.
        if eps and invitado and gid != pid and invitado in (slug(gid), slug(g.get('nombre') or '')):
            personajes[gid] = dict(g, papel='invitado')
            eps[-1]['invitados'] = [gid]
            break
    s = {'id': sid, 'titulo': titulo, 'trama': str(crudo.get('trama') or '').strip(), 'vertice': vertice,
         'personaje': pid, 'lugar': lid, 'personajes': personajes, 'lugares': {lid: lg},
         'episodios': eps, 'origen': 'semillero', 'creada': ahora()}
    quiere = entero(universo['ajustes'].get('episodios'), 10)
    if len(eps) != quiere:
        raise V4Error('trajo %d episodios y se pidieron %d' % (len(eps), quiere))
    problemas = validar_serie(s, universo)
    if problemas:
        raise V4Error('; '.join(problemas[:4]))
    return s


def pensador(universo):
    """El modelo de texto que escribe (Gemini, con la estrategia común de la Sala por delante)."""
    from motores import cerebro
    from motores.estrategia import con_estrategia
    reglas = {'cerebro_modelo': str(universo['ajustes'].get('modelo_guion') or '').strip()}
    return lambda texto, instr: cerebro._json_de(cerebro._gemini(texto, reglas, con_estrategia(instr, {})))


def semillero(e, universo, simular, pensar=None, leer_candados=None):
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
    if simular:
        return 'simulación: pediría una serie de %d episodios sobre «%s»' % (n, vertice)
    v = universo['vertices'][vertice]
    invitables = conocidos(e, universo)
    candados, aviso = candados_texto(leer_candados)
    pedido = '\n'.join(x for x in [
        'Vértice del negocio: %s — %s' % (v.get('nombre', vertice), v.get('mensaje', '')),
        'Industrias de clientes ya usadas (elige otra): %s' % (', '.join(sorted(
            {str(p.get('industria')) for s in e['serie'].values()
             for p in (s.get('personajes') or {}).values() if isinstance(p, dict) and p.get('industria')})) or 'ninguna'),
        'Historias ya propuestas (no las repitas): %s' % ('; '.join(str(s.get('titulo')) for s in e['serie'].values()) or 'ninguna'),
        ('Personajes conocidos de historias anteriores; UNO puede aparecer como invitado sólo en el último '
         'episodio, para entrelazar las historias:\n- ' + '\n- '.join(
             '%s (%s): %s' % (g.get('nombre', gid), g.get('industria', ''), g.get('quiere', ''))
             for gid, g in invitables.items())) if invitables else '',
        'Ideas pasadas que pueden nutrir la historia (no las copies):\n- ' + ('\n- '.join(inspiracion()) or 'ninguna'),
        ('Candados de Dirección. Son obligatorios; los de tipo veto no se negocian:\n' + candados) if candados else '',
    ] if x)
    instruccion = str(universo.get('guionista') or '').replace('{n}', str(n)) + FORMA_SERIE.format(n=n)
    pensar = pensar or pensador(universo)
    ultimo = None
    for _ in range(2):                    # un segundo intento si el JSON vino mal; no más
        try:
            s = armar_serie(pensar(pedido, instruccion), universo, vertice, e['serie'], invitables)
        except (V4Error, MotorError) as err:
            ultimo = err
            continue
        guardar('serie', s['id'], s, existe=False)
        e['serie'][s['id']] = s
        return 'serie propuesta: «%s» (%s)%s' % (s['titulo'], s['id'], ' · ' + aviso if aviso else '')
    return 'no salió una serie válida: %s' % sala.redactar(str(ultimo))[:200]


# ------------------------------------------------------------------ 2 · productor

def gastado_hoy(e, dia=None):
    dia = dia or hoy()
    return sum(entero((p.get('intentos') or {}).get(dia)) for p in e['prod'].values())


def ultima(prod, n):
    vs = (((prod or {}).get('episodios') or {}).get(str(n)) or {}).get('versiones') or []
    return vs[-1] if vs else None


def retrato_de(pid, universo, s, prod):
    """El id de Drive del retrato de un personaje: el que sacó la nube del episodio 1, o el que
    el personaje trae guardado (del universo o de otra serie)."""
    propio = (((prod or {}).get('retratos') or {}).get(pid) or {}).get('drive')
    return str(propio or (reparto(universo, s).get(pid) or {}).get('referencia_drive') or '').strip()


def marca_de(dec, prod, n):
    """La decisión vigente de un episodio: la que se tomó sobre su última versión (o, sin video,
    la que se tomó antes de producirlo). Una marca sobre una versión vieja ya no aplica."""
    m = ((dec or {}).get('episodios') or {}).get(str(n)) or {}
    return m if entero(m.get('v')) == entero((ultima(prod, n) or {}).get('v')) else {}


def en_pie(s, dec, prod):
    """Los episodios que siguen en la serie: todos menos los marcados «no va»."""
    return [ep for ep in s.get('episodios') or [] if marca_de(dec, prod, entero(ep.get('n'))).get('marca') != 'no']


def pendiente(s, dec, prod, piloto_primero=True):
    """El siguiente episodio por producir: (episodio, versión nueva, nota) o None.
    El primer episodio en pie es el piloto: hasta su «sí» no se produce ningún otro."""
    for i, ep in enumerate(en_pie(s, dec, prod)):
        n = entero(ep.get('n'))
        u, m = ultima(prod, n), marca_de(dec, prod, n)
        if not u:
            return ep, 1, ''
        if m.get('marca') == 'cambio':
            return ep, entero(u.get('v')) + 1, str(m.get('nota') or '')
        if i == 0 and piloto_primero and m.get('marca') != 'si':
            return None
    return None


def _ffmpeg(*args):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        raise MotorError('ffmpeg no pudo: %s' % sala.redactar(r.stderr)[-200:])


def cuadro(video, destino, antes_del_final=0.2):
    """Un cuadro del video como JPEG, contado desde el final (0.2 s = el último cuadro útil)."""
    _ffmpeg('-sseof', '-%s' % antes_del_final, '-i', str(video), '-frames:v', '1', '-q:v', '2', str(destino))
    return pathlib.Path(destino).read_bytes()


def _tiene_audio(video):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index',
                        '-of', 'csv=p=0', str(video)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def unir(videos, destino):
    """Une tomas o episodios. Cada clip se lleva antes al mismo formato (720×1280, 24 cuadros,
    audio estéreo; silencio si el clip vino mudo), así ninguno rompe la unión."""
    destino = pathlib.Path(destino)
    if len(videos) == 1:
        destino.write_bytes(pathlib.Path(videos[0]).read_bytes())
        return destino
    with tempfile.TemporaryDirectory() as tmp:
        tmp, partes = pathlib.Path(tmp), []
        for i, v in enumerate(videos):
            parte = tmp / ('p%02d.mp4' % i)
            mudo = not _tiene_audio(v)
            entrada = ['-i', str(v)] + (['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100'] if mudo else [])
            _ffmpeg(*entrada, '-vf', 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24',
                    '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '44100', '-ac', '2',
                    *(['-shortest'] if mudo else []), str(parte))
            partes.append(parte)
        lista = tmp / 'lista.txt'
        lista.write_text(''.join("file '%s'\n" % p for p in partes), encoding='utf-8')
        _ffmpeg('-f', 'concat', '-safe', '0', '-i', str(lista), '-c', 'copy', '-movflags', '+faststart', str(destino))
    return destino


def asegurar_retrato(universo, s, prod, tmp, drive, carpeta, piloto=1):
    """Antes de los demás episodios: saca del piloto vigente el retrato del protagonista y lo
    guarda. Si el piloto se rehízo, el retrato se vuelve a sacar de la versión nueva."""
    pid, u = s.get('personaje'), ultima(prod, piloto)
    if not u:
        return
    origen = 'E%02d-v%s' % (piloto, u.get('v'))
    actual = ((prod.get('retratos') or {}).get(pid) or {})
    if actual.get('de') == origen:
        return
    video = drive.bajar(u['drive'], str(tmp / 'episodio1.mp4'))
    archivo = tmp / ('retrato-%s.jpg' % slug(pid))
    cuadro(video, archivo, antes_del_final=4.5)     # hacia el final suele verse de frente y cerca
    fid = drive.subir(str(archivo), carpeta)
    if fid:
        prod.setdefault('retratos', {})[pid] = {'drive': fid, 'de': origen, 'cuando': ahora()}
        guardar('prod', s['id'], prod)


def producir_episodio(universo, s, ep, version, nota, prod, tmp, generar, drive, carpeta, piloto=1):
    """Genera las tomas de UN episodio, las une, sube el video a `carpeta` (la de la serie en
    Drive) y devuelve su registro. `piloto` es el número del primer episodio en pie: de él sale
    el retrato del protagonista."""
    tomas, n = tomas_de(ep), entero(ep.get('n'))
    arranque = None
    if ep.get('continua') and n > 1 and ultima(prod, n - 1):
        previo = drive.bajar(ultima(prod, n - 1)['drive'], str(tmp / 'previo.mp4'))
        arranque = cuadro(previo, tmp / 'previo.jpg')
    memoria = {}

    def retratos():
        """Los retratos del elenco, protagonista primero: ([imágenes], [personajes]). Una sola vez."""
        if 'r' not in memoria:
            if n != piloto:
                asegurar_retrato(universo, s, prod, tmp, drive, carpeta, piloto)
            fotos, quienes = [], []
            for pid in elenco(universo, s, ep):
                # El piloto no usa el retrato sacado de sí mismo: sólo el que el personaje ya traía.
                fid = retrato_de(pid, universo, s, prod if n != piloto else None)
                if fid:
                    archivo = drive.bajar(fid, str(tmp / ('retrato%d.jpg' % len(fotos))))
                    fotos.append(pathlib.Path(archivo).read_bytes())
                    quienes.append(pid)
            memoria['r'] = (fotos, quienes)
        return memoria['r']

    def entradas():
        """De la entrada más fiel a la más simple: (qué es, primer cuadro, retratos, de quién)."""
        if arranque:                       # con primer cuadro el personaje ya está en la imagen
            yield 'el último cuadro de la toma anterior', arranque, None, ()
        fotos, quienes = retratos()
        if fotos:
            yield 'el retrato del personaje', None, fotos, quienes
        yield '', None, None, ()

    clips, avisos, con_retrato = [], [], False
    for t in range(1, tomas + 1):
        for que, jpg, fotos, quienes in entradas():
            texto = prompt_toma(universo, s, ep, t, nota, quienes)
            exigir_sin_veto(texto)
            try:
                video = generar(texto, 15, jpg=jpg, referencias=fotos)
            except MotorError as err:
                if not que or getattr(err, 'http', None) != 400:
                    raise
                # Google no aceptó esa imagen (un 400 no se cobra): la toma baja un escalón y
                # no se pierde lo que ya se pagó de este episodio.
                avisos.append('no se pudo usar %s: %s' % (que, sala.redactar(str(err))[:120]))
                continue
            con_retrato = con_retrato or bool(fotos)
            break
        clip = tmp / ('toma%d.mp4' % t)
        clip.write_bytes(video)
        clips.append(clip)
        if t < tomas:
            arranque = cuadro(clip, tmp / ('toma%d.jpg' % t))
    final = unir(clips, tmp / ('E%02d-v%d.mp4' % (n, version)))
    fid = drive.subir(str(final), carpeta)
    if not fid:
        raise drive.DriveError('Drive no confirmó el video')
    reg = {'v': version, 'drive': fid, 'cuando': ahora(), 'segundos': 15 * tomas, 'nota_atendida': nota,
           'con_retrato': con_retrato, 'costo_usd_aprox': round(USD_POR_TOMA * tomas, 2)}
    if avisos:
        reg['aviso'] = '; '.join(dict.fromkeys(avisos))[:400]
    return reg


def productor(e, universo, simular, generar=None, drive=None, raiz=None):
    aj = universo['ajustes']
    tope, hecho = entero(aj.get('tope_clips_dia')), []
    if tope <= 0:
        return ['productor apagado: tope de tomas por día en 0']
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
            tomas = tomas_de(ep)
            if gastado_hoy(e, dia) + tomas > tope:
                hecho.append('tope del día alcanzado (%d tomas): «%s» episodio %s espera a mañana'
                             % (tope, s.get('titulo'), ep.get('n')))
                return hecho
            if simular:
                hecho.append('simulación: produciría «%s» episodio %s v%d' % (s.get('titulo'), ep.get('n'), version))
                break
            if generar is None:
                import sala_drive as drive
                from motores import escena_omni
                generar = escena_omni.generar
                raiz = regla('drive_raiz')
                if not raiz:
                    raise V4Error('la REGLA drive_raiz está vacía: no hay dónde guardar el video')
            # Drive primero: sin dónde guardar el video no se reserva ni se gasta.
            try:
                carpeta = drive.ruta_carpetas(raiz, CARPETA_VIDEOS, sid)
            except drive.DriveError as err:
                hecho.append('Drive no está listo y no se produjo nada: %s' % sala.redactar(str(err))[:200])
                return hecho
            # La reserva se anota ANTES de gastar: un intento fallido también cuenta.
            intentos = prod.setdefault('intentos', {})
            intentos[dia] = entero(intentos.get(dia)) + tomas
            guardar('prod', sid, prod)
            try:
                piloto = entero((en_pie(s, dec, prod) or [ep])[0].get('n'))
                with tempfile.TemporaryDirectory() as tmp:
                    reg = producir_episodio(universo, s, ep, version, nota, prod, pathlib.Path(tmp), generar, drive, carpeta, piloto)
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
            hecho.append('«%s» episodio %s v%d listo para revisar%s' % (
                s.get('titulo'), ep.get('n'), version, ' · ' + reg['aviso'] if reg.get('aviso') else ''))
    return hecho or ['nada por producir: no hay series aprobadas con episodios pendientes']


# ------------------------------------------------------------------ 3 · paquete

def aprobados(s, dec, prod):
    """Los episodios con «sí» sobre su última versión, en orden: son los que se publican."""
    return [ep for ep in s.get('episodios') or []
            if ultima(prod, entero(ep.get('n'))) and marca_de(dec, prod, entero(ep.get('n'))).get('marca') == 'si']


def completa(s, dec, prod):
    """True si la serie ya no espera nada: cada episodio tiene «sí» sobre su última versión o
    «no» (ese queda fuera del paquete), y al menos uno va."""
    van = aprobados(s, dec, prod)
    return bool(van) and len(van) == len(en_pie(s, dec, prod))


def firma(van, prod):
    """Qué episodios lleva un paquete y en qué versión. Si cambia, el paquete se rehace."""
    return {str(entero(ep.get('n'))): entero(ultima(prod, entero(ep.get('n'))).get('v')) for ep in van}


INSTRUCCION_COPY = (
    'Escribe el texto para publicar cada episodio de esta serie en Instagram y Facebook: uno por día. '
    'Cada texto tiene de 1 a 3 frases, invita a ver el episodio siguiente y no repite la frase que dice '
    'el personaje. El del último día cierra con un solo paso siguiente. Devuelve SOLO un objeto JSON: '
    '{{"episodios": ["texto del día 1", "texto del día 2", …]}} con exactamente {n} textos.')


def textos_para_publicar(s, universo, pensar=None, candados='', eps=None):
    """Un texto por día, escrito por el modelo con la estrategia común y los candados. Si no
    sale bien formado o trae una ubicación vetada, devuelve [] y el paquete lleva sólo el guion."""
    eps = (s.get('episodios') or []) if eps is None else eps
    try:
        pensar = pensar or pensador(universo)
        pedido = 'Serie: %s\nLa historia: %s\n%s' % (s.get('titulo', ''), s.get('trama', ''), '\n'.join(
            'Día %d · %s — dice: «%s»' % (i, ep.get('titulo', ''), ep.get('dialogo', '')) for i, ep in enumerate(eps, 1)))
        if candados:
            pedido += '\nCandados de Dirección. Son obligatorios; los de tipo veto no se negocian:\n' + candados
        r = pensar(pedido, INSTRUCCION_COPY.format(n=len(eps)))
        lista = [str(x).strip() for x in (r or {}).get('episodios') or []] if isinstance(r, dict) else []
        if len(lista) != len(eps) or not all(lista):
            return []
        exigir_sin_veto(lista)
        return lista
    except (MotorError, contenido_reglas.ContenidoVetado, V4Error):
        return []


def copy_de(s, universo, publicar=(), eps=None):
    v = (universo.get('vertices') or {}).get(s.get('vertice')) or {}
    lineas = ['COPY · %s' % s.get('titulo', ''), '', s.get('trama', ''), '',
              'Vértice: %s — %s' % (v.get('nombre', ''), v.get('mensaje', '')), '', 'UN EPISODIO POR DÍA', '']
    for i, ep in enumerate((s.get('episodios') or []) if eps is None else eps):
        lineas += ['Día %d · %s' % (i + 1, ep.get('titulo', '')),
                   '  Archivo: E%02d.mp4' % entero(ep.get('n')),
                   '  Texto para publicar: %s' % (publicar[i] if i < len(publicar) else '(pendiente: escríbelo o pídelo)'),
                   '  Lo que dice el personaje: «%s»' % ep.get('dialogo', ''), '']
    lineas += ['Sólo van los archivos de esta lista, en este orden.',
               'Borrador escrito por la nube: revisar contra los candados antes de publicar.',
               'Publicar es siempre el clic de Dirección.']
    return '\n'.join(lineas)


def _nombre_drive(titulo):
    t = re.sub(r'\s+', ' ', ''.join(c for c in str(titulo) if c.isprintable() and c not in '/\\')).strip()
    return 'Historia · ' + (t[:110] or 'sin título')


def paquete(e, universo, simular, drive=None, raiz=None, pensar=None, leer_candados=None):
    hecho, candados = [], None
    for sid, s in e['serie'].items():
        prod, dec = e['prod'].get(sid) or {}, e['dec'].get(sid) or {}
        if dec.get('serie') != 'si' or not completa(s, dec, prod):
            continue
        van = aprobados(s, dec, prod)
        if (prod.get('paquete') or {}).get('versiones') == firma(van, prod):
            continue                      # el paquete que hay ya es el de estas versiones
        if simular:
            hecho.append('simulación: armaría el paquete de «%s»' % s.get('titulo'))
            continue
        if drive is None:
            import sala_drive as drive
            raiz = regla('drive_raiz')
            if not raiz:
                raise V4Error('la REGLA drive_raiz está vacía: no hay dónde dejar el paquete')
        if candados is None:
            candados = candados_texto(leer_candados)[0]
        publicar = textos_para_publicar(s, universo, pensar, candados, van)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = pathlib.Path(tmp)
                clips = [drive.bajar(ultima(prod, entero(ep.get('n')))['drive'], str(tmp / ('E%02d.mp4' % entero(ep.get('n')))))
                         for ep in van]
                entera = unir(clips, tmp / 'HISTORIA-COMPLETA.mp4')
                texto = tmp / 'COPY.txt'
                texto.write_text(copy_de(s, universo, publicar, van), encoding='utf-8')
                carpeta = drive.ruta_carpetas(raiz, CARPETA_LISTAS, _nombre_drive(s.get('titulo')))
                for archivo in [str(c) for c in clips] + [str(entera), str(texto)]:
                    drive.subir(archivo, carpeta)
        except (drive.DriveError, MotorError) as err:
            # Sin paquete anotado, la siguiente corrida lo intenta de nuevo; no cuesta video.
            hecho.append('el paquete de «%s» no se pudo armar: %s' % (s.get('titulo'), sala.redactar(str(err))[:200]))
            continue
        prod['paquete'] = {'carpeta': carpeta, 'cuando': ahora(), 'con_textos': bool(publicar),
                           'versiones': firma(van, prod)}
        guardar('prod', sid, prod)
        hecho.append('paquete de «%s» listo en Drive%s' % (
            s.get('titulo'), '' if publicar else ' (sin textos para publicar: el modelo no los entregó bien)'))
    return hecho or ['ningún paquete nuevo']


# ------------------------------------------------------------------ 4 · estado

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--solo', choices=('semillero', 'productor', 'paquete'))
    a = ap.parse_args(argv)
    sala.enmascarar_en_actions()
    try:
        e = leer()                        # si la hoja no contesta, aquí se detiene con error
    except (sala.SalaError, V4Error) as err:
        sala.avisar('✗ no leí la hoja; no hago nada a ciegas: %s' % sala.redactar(str(err))[:300])
        return 2
    universo = universo_de(e)
    pasos, codigo = [], 0
    try:
        if e['universo'] is None and not a.simular:
            guardar('universo', '', universo, existe=False)      # siembra una sola vez
        if a.solo in (None, 'semillero'):
            pasos.append(semillero(e, universo, a.simular))
        if a.solo in (None, 'productor'):
            pasos += productor(e, universo, a.simular)
        if a.solo in (None, 'paquete'):
            pasos += paquete(e, universo, a.simular)
    except (sala.SalaError, V4Error) as err:
        pasos.append('✗ la corrida se detuvo: %s' % sala.redactar(str(err))[:300])
        codigo = 1
    tope = entero(universo['ajustes'].get('tope_clips_dia'))
    usadas = gastado_hoy(e)
    for linea in pasos:
        sala.avisar('· ' + linea)
    if not a.simular:
        try:
            guardar('estado', '', {'cuando': ahora(), 'pasos': pasos, 'clips_hoy': usadas, 'tope': tope,
                                   'gasto_usd_aprox_hoy': round(usadas * USD_POR_TOMA, 2)})
        except sala.SalaError as err:
            sala.avisar('⚠ no pude dejar el estado: %s' % sala.redactar(str(err))[:200])
            codigo = codigo or 1
    return codigo


if __name__ == '__main__':
    sys.exit(main())
