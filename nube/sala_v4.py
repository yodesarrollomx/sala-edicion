#!/usr/bin/env python3
"""Sala 4.0 · historias en episodios de 15 segundos (9-nov-2026).

Una SERIE cuenta una historia en N episodios (de fábrica 10), uno por día. Cada episodio es
una toma continua de 15 s, o un bloque de 30 s hecho de dos tomas. Todo lo editable vive en
la hoja EXPEDIENTES, con la acción `expediente` que el Apps Script ya atiende (no se toca el
backend), en siete clases de documento con UN solo dueño cada una:

    v4:universo        editor   el CANON: formato, encuadres, reglas del mundo, temporada,
                                vértices, guionista y ajustes
    v4:mundo:<clase>   editor   los personajes, los lugares y los objetos del mundo, cada clase
                                en su propia celda (un universo sin partir los trae adentro)
    v4:serie:<id>      quien la crea (semillero o editor); después sólo el editor la edita
    v4:dec:<id>        editor   aprobar la serie y sí / cambio / no por episodio («no» = queda fuera)
    v4:prod:<id>       nube     versiones producidas, ligas de Drive, intentos, paquete, avisos
    v4:canon           nube     las imágenes de referencia (una por personaje, lugar y objeto):
                                las que pintó y los retratos que sacó de un piloto
    v4:estado          nube     qué hizo la última corrida y qué falta

La nube NUNCA escribe `dec` (decidir es de los editores, INVIOLABLE 3) ni `mundo`, ni pisa
`universo` o una `serie` que ya existe: `guardar` se niega antes de la red.

El video lo genera Gemini Omni Flash (de pago). El gasto lo limita `ajustes.tope_clips_dia`,
y la reserva se anota ANTES de llamar: un intento fallido también cuenta. No pasa por la
COLA ni por `nube_ejecuta_etapas`; la línea vieja de video sigue en pausa.

EL CANON (docs/SALA-CANON.md). Para que las historias no se vean como pedazos sueltos, cada
personaje, lugar y objeto tiene su ficha (cómo se ve, cómo viste, cómo habla, qué lo
distingue) y una IMAGEN DE REFERENCIA en Drive que viaja al motor de video en cada toma
donde aparece. La imagen la pone Dirección, la pinta la nube a partir de la ficha, o, para un
protagonista cuyo piloto se produjo sin imagen, se saca de ese piloto. Con las imágenes
encendidas un episodio no se produce hasta que lo que sale en él tenga la suya. Cada episodio
elige un encuadre de la biblioteca. La temporada es el plan de series que se cruzan; el
semillero la sigue en orden.

Pasos, en orden: semillero → referencias → productor → paquete → estado. `--simular` no
escribe ni gasta.
"""

import argparse
import datetime
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse

import contenido_reglas
import sala_cliente as sala
from motores._comun import MotorError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SEMILLA = RAIZ / 'datos' / 'universo' / 'universo.json'
IDEAS = RAIZ / 'datos' / 'ideas.json'
PREFIJO = 'v4:'
DE_LA_NUBE = ('prod', 'estado', 'canon')
CLASES_MUNDO = ('personajes', 'lugares', 'objetos')
VERSION_CANON = 2
PALABRAS_15S = 38                       # lo que cabe hablado en una toma de 15 s
USD_POR_TOMA = 1.05                     # 15 s a 0.07 USD/s en 720p; aproximado, para informar
CARPETA_VIDEOS = '_HISTORIAS'
CARPETA_LISTAS = '_LISTAS PARA PUBLICAR'   # la misma de la estación de salida (Sala corta)
CARPETA_CANON = '_CANON'                # dentro de _HISTORIAS: las imágenes de referencia y el índice
MAX_REFERENCIAS = 4                     # imágenes de referencia por toma: quién sale, objetos, lugar
USD_POR_FICHA = 0.04                    # una imagen de referencia; aproximado, para informar
LIMITE_CELDA = 45000                    # cada documento vive en UNA celda del Sheet (tope real: 50 000)
AJUSTES = {'semillero': 1, 'propuestas_en_espera': 2, 'episodios': 10, 'tope_clips_dia': 2,
           'piloto_primero': 1, 'fichas_por_dia': 6, 'modelo_guion': 'gemini-3.6-flash',
           'modelo_ficha': 'gemini-2.5-flash-image'}


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
    """{'universo':…, 'mundo':{clase:…}, 'serie':{id:…}, 'dec':{id:…}, 'prod':{id:…}, 'canon':…,
    'estado':…} de la hoja."""
    e = {'universo': None, 'mundo': {}, 'serie': {}, 'dec': {}, 'prod': {}, 'canon': None, 'estado': None}
    for llave, doc in (expedientes or {}).items():
        if not str(llave).startswith(PREFIJO) or not isinstance(doc, dict):
            continue
        clase, _, ident = str(llave)[len(PREFIJO):].partition(':')
        if clase in ('universo', 'estado', 'canon'):
            e[clase] = doc
        elif clase == 'mundo' and ident in CLASES_MUNDO:
            e['mundo'][ident] = doc
        elif clase in ('serie', 'dec', 'prod') and ident:
            e[clase][ident] = doc
    return e


def leer():
    datos = sala.get('expedientes')
    if not isinstance(datos.get('expedientes'), dict):
        raise V4Error('la hoja EXPEDIENTES no contestó con su contrato')   # «no contestó» ≠ «vacío»
    return separar(datos['expedientes'])


def guardar(clase, ident, doc, existe=False):
    """Escribe UN documento. La nube sólo es dueña de prod, canon y estado; puede CREAR una
    serie o sembrar el universo, nunca pisarlos; y jamás escribe decisiones ni el mundo."""
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


def al_canon(u, base):
    """De un universo guardado antes del canon (versión 1) a la versión 2: entra el formato
    afinado y lo que no existía (encuadres, objetos, reglas del mundo, temporada), y los
    personajes y lugares de la semilla llegan con su ficha completa. Los ajustes, los vértices
    y lo que el editor haya agregado no se tocan."""
    out = dict(u, formato=dict(base.get('formato') or {}), version=VERSION_CANON)
    for k in ('encuadres', 'objetos', 'canon', 'temporada'):
        out[k] = u.get(k) or base.get(k)
    for k in ('personajes', 'lugares'):
        out[k] = dict(u.get(k) or {}, **(base.get(k) or {}))
    return out


def universo_de(e):
    """El universo vigente; si el editor aún no guardó uno, la semilla del repo. Los personajes,
    los lugares y los objetos pueden vivir cada uno en su propia celda (v4:mundo:<clase>): así el
    mundo puede crecer sin que el universo deje de caber en la suya."""
    base = semilla()
    u = dict(e['universo'] or base)
    if entero(u.get('version'), 1) < VERSION_CANON:
        u = al_canon(u, base)
    for k in CLASES_MUNDO:
        aparte = (e.get('mundo') or {}).get(k)
        if isinstance(aparte, dict):
            u[k] = aparte
        elif not isinstance(u.get(k), dict):
            u[k] = base.get(k)                 # ni aparte ni adentro: vale el de fábrica, nunca un mundo vacío
    u['ajustes'] = dict(AJUSTES, **(u.get('ajustes') or {}))
    for k in ('vertices', 'encuadres') + CLASES_MUNDO:
        u[k] = u.get(k) if isinstance(u.get(k), dict) else {}
    u['temporada'] = [x for x in (u.get('temporada') or []) if isinstance(x, dict) and x.get('id')]
    for k in ('guionista', 'canon'):
        if not str(u.get(k) or '').strip():
            u[k] = base.get(k, '')
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


def objetos_de(universo, s):
    return dict(universo.get('objetos') or {}, **(s.get('objetos') or {}))


MUNDO = {'personajes': reparto, 'lugares': lugares_de, 'objetos': objetos_de}


def utileria(universo, s, ep):
    """Los objetos que se ven en un episodio, sin repetir ni inventar."""
    todos, out = objetos_de(universo, s), []
    for oid in ep.get('objetos') or []:
        if isinstance(oid, str) and oid in todos and oid not in out:
            out.append(oid)
    return out


def llave_canon(universo, s, clase, ident):
    """Con qué nombre se guarda la imagen de referencia de un elemento: los del universo, por
    su id (son de todas las series); los propios de una serie, con el id de la serie delante."""
    propio = ident in (s.get(clase) or {}) or ident not in (universo.get(clase) or {})
    return '%s:%s' % (s.get('id'), ident) if propio else ident


def id_drive(texto):
    """El id de un archivo de Drive, venga como id o como liga pegada. Lo que no es ninguna de
    las dos cosas (la liga de una carpeta, un texto cualquiera) no cuenta: devuelve ''."""
    t = str(texto or '').strip()
    m = re.search(r'/d/([A-Za-z0-9_-]{20,})|[?&]id=([A-Za-z0-9_-]{20,})', t)
    if m:
        return m.group(1) or m.group(2)
    return t if re.fullmatch(r'[A-Za-z0-9_-]{20,}', t) else ''


def registro_canon(clase, ident, universo, s, canon):
    """Lo que la nube tiene anotado de la imagen de un elemento: {'drive', 'huella'[, 'de']}.
    `de` existe sólo cuando la imagen es un retrato sacado de un piloto («<serie>:E01-v1»)."""
    return ((canon or {}).get(clase) or {}).get(llave_canon(universo, s, clase, ident)) or {}


def referencia_de(clase, ident, universo, s, canon, piloto=False):
    """El id de Drive de la imagen de referencia de un elemento: la que puso Dirección en la
    ficha y, si no, la del canon (la que pintó la nube o el retrato sacado de un piloto). Al
    producir el piloto de una serie (`piloto`) no cuenta el retrato que salió de ese mismo
    piloto: un piloto que se rehace no se copia a sí mismo."""
    ficha = MUNDO[clase](universo, s).get(ident) or {}
    propia = id_drive(ficha.get('referencia_drive'))
    if propia:
        return propia
    reg = registro_canon(clase, ident, universo, s, canon)
    if piloto and str(reg.get('de') or '').startswith('%s:' % s.get('id')):
        return ''
    return str(reg.get('drive') or '').strip()


def por_pintar(clase, ident, universo, s, canon):
    """True si a un elemento le falta su imagen de referencia o su ficha cambió desde que se
    hizo. Lo que Dirección puso por su cuenta nunca está por pintar."""
    ficha = MUNDO[clase](universo, s).get(ident)
    if not isinstance(ficha, dict) or id_drive(ficha.get('referencia_drive')):
        return False
    reg = registro_canon(clase, ident, universo, s, canon)
    return not (reg.get('drive') and reg.get('huella') == huella(descripcion_ficha(clase, ficha)))


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
    quien, donde, cosas = reparto(universo, s), lugares_de(universo, s), objetos_de(universo, s)
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
        for obj in ep.get('objetos') or []:
            if obj not in cosas:
                p.append('episodio %d: el objeto «%s» no existe' % (i, obj))
        if ep.get('encuadre') and ep['encuadre'] not in (universo.get('encuadres') or {}):
            p.append('episodio %d: el encuadre «%s» no existe' % (i, ep['encuadre']))
        for t in range(1, tomas_de(ep) + 1):
            suf = '' if t == 1 else '2'
            if not str(ep.get('accion' + suf) or '').strip():
                p.append('episodio %d: falta la acción%s' % (i, ' de la segunda toma' if suf else ''))
            n = len(str(ep.get('dialogo' + suf) or '').split())
            if n > PALABRAS_15S:
                p.append('episodio %d: %d palabras no caben en 15 s (máximo %d)' % (i, n, PALABRAS_15S))
    try:
        exigir_sin_veto({k: s.get(k) for k in ('titulo', 'trama', 'episodios', 'personajes', 'lugares', 'objetos')})
    except contenido_reglas.ContenidoVetado as e:
        p.append(str(e))
    return p


def prompt_toma(universo, s, ep, toma=1, nota='', refs=(), primer_cuadro=False):
    """El texto que recibe Omni para UNA toma de 15 s: formato, encuadre, lugar con sus anclas,
    cada personaje con su ficha, los objetos, la acción, la frase y cómo se dice.

    `refs` son los elementos cuya imagen viaja como referencia, [(clase, id)], en el mismo
    orden en que van las imágenes: el texto los nombra <IMAGE_REF_0>, <IMAGE_REF_1>…
    `primer_cuadro` avisa que antes de ellas va la imagen donde arranca la toma.
    """
    f = universo.get('formato') or {}
    todos, quienes = reparto(universo, s), elenco(universo, s, ep)
    lid = ep.get('lugar') or s['lugar']
    lugar = lugares_de(universo, s)[lid]
    cosas, props = objetos_de(universo, s), utileria(universo, s, ep)
    vale = {'personajes': quienes, 'objetos': props, 'lugares': [lid]}
    refs = [(c, i) for c, i in refs if i in vale.get(c, ())]
    marca = {r: '<IMAGE_REF_%d>' % k for k, r in enumerate(refs)}
    suf = '' if toma == 1 else '2'
    dialogo = str(ep.get('dialogo' + suf) or '').strip()
    tono = str(ep.get('tono' + suf) or ep.get('tono') or '').strip()
    camara = str(((universo.get('encuadres') or {}).get(ep.get('encuadre')) or {}).get('camara') or '').strip()
    declarar = ['[# Sources <FIRST_FRAME>@Image1]'] if primer_cuadro else []
    if refs:
        declarar.append('[# References %s]' % ' '.join(
            '%s@Image%d' % (marca[r], k + (2 if primer_cuadro else 1)) for k, r in enumerate(refs)))
    lineas = []
    for k, pid in enumerate(quienes):
        p = todos[pid]
        if len(quienes) == 1:
            linea = 'CHARACTER (%s): %s' % (p.get('nombre', ''), p.get('aspecto', ''))
        else:
            linea = 'CHARACTER %d (%s), %s: %s' % (k + 1, p.get('nombre', ''),
                                                    'the protagonist' if k == 0 else 'a guest who appears briefly',
                                                    p.get('aspecto', ''))
        if str(p.get('vestuario') or '').strip():
            linea += ' Always wearing: %s' % p['vestuario']
        if ('personajes', pid) in marca:
            linea += (' This is the person shown in %s: keep the same face, hair, age and clothing.'
                      % marca[('personajes', pid)])
        if k == 0:
            linea += ' Voice: %s' % p.get('voz', '')
        if str(p.get('gesto') or '').strip():
            linea += ' Habit: %s' % p['gesto']
        lineas.append(linea)
    sitio = 'LOCATION: ' + lugar.get('aspecto', '')
    if str(lugar.get('anclas') or '').strip():
        sitio += ' Always visible there: %s' % lugar['anclas']
    if ('lugares', lid) in marca:
        sitio += ' This is the place shown in %s: same street, same walls, same trees.' % marca[('lugares', lid)]
    for oid in props:
        linea = 'PROP (%s): %s It is the same object in every episode.' % (cosas[oid].get('nombre', ''), cosas[oid].get('aspecto', ''))
        if ('objetos', oid) in marca:
            linea += ' It is the object shown in %s.' % marca[('objetos', oid)]
        lineas.append(linea)
    partes = declarar + [
        f.get('estilo', ''),
        ('CAMERA: ' + camara) if camara else '',
        sitio,
    ] + lineas + [
        'Start exactly on the first frame image and continue the same scene without a cut.' if primer_cuadro else '',
        'The reference images only show who and what appears. Do not use them as the first frame '
        'and do not copy their background.' if any(c != 'lugares' for c, _ in refs) else '',
        'ACTION: ' + str(ep.get('accion' + suf) or ''),
        ('SPOKEN LINE, in Spanish, said once by %s: «%s»' % (todos[quienes[0]].get('nombre', ''), dialogo)) if dialogo
        else 'No one speaks in this shot.',
        ('DELIVERY: ' + tono) if tono and dialogo else '',
        ('ENDING: ' + ep['gancho']) if ep.get('gancho') and (toma == 2 or tomas_de(ep) == 1) else '',
        ('DIRECTOR NOTE, fix this from the previous version: ' + nota) if nota else '',
        f.get('audio', ''), f.get('prohibido', ''),
    ]
    return '\n'.join(x for x in partes if x)


# ------------------------------------------------------------------ 1 · semillero

# La FORMA de la respuesta es fija (de ella depende leerla). El criterio del guionista y las
# reglas del mundo son DATOS: `universo.guionista` y `universo.canon`, que Dirección edita.
FORMA_SERIE = (
    ' Escribe UNA historia contada en {n} episodios de 15 segundos. Devuelve SOLO un objeto JSON con '
    'esta forma exacta: {{"titulo": "...", "trama": "una línea", '
    '"personaje": "el id de un personaje del mundo; o, si es nuevo, un objeto {{"nombre": "...", "industria": '
    '"...", "aspecto": "cara, edad, complexión y pelo, EN INGLÉS, concreto y repetible", "vestuario": "lo que '
    'siempre trae puesto, EN INGLÉS", "voz": "cómo suena, EN INGLÉS", "gesto": "un gesto que lo distingue, EN '
    'INGLÉS", "quiere": "..."}}", '
    '"lugar": "el id de un lugar del mundo; o, si es nuevo, un objeto {{"nombre": "...", "aspecto": "EN INGLÉS", '
    '"anclas": "lo que siempre se ve ahí, EN INGLÉS"}}", '
    '"objeto": "el id de un objeto del mundo; o, si es nuevo, un objeto {{"nombre": "...", "aspecto": "EN '
    'INGLÉS", "significado": "qué representa en la historia"}}", '
    '"invitado_final": "nombre exacto de un personaje conocido de la lista, o cadena vacía", '
    '"episodios": [{{"titulo": "...", "accion": "qué hacen el personaje y la cámara, EN INGLÉS", "dialogo": '
    '"la frase en español, máximo 32 palabras", "gancho": "el último segundo, EN INGLÉS", "encuadre": "un id '
    'de la lista de encuadres", "tono": "cómo dice la frase, EN INGLÉS", "objetos": ["ids de los objetos que se '
    'ven"], "invitados": ["ids de personajes del mundo que aparecen un momento"]}}]}}')


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


def temporada_pendiente(universo, e):
    """La siguiente historia planeada de la temporada que todavía no tiene una serie en pie
    (propuesta o aprobada). Una serie descartada libera su lugar: se vuelve a escribir."""
    vivas = {s.get('temporada') for sid, s in e['serie'].items() if (e['dec'].get(sid) or {}).get('serie') != 'no'}
    for plan in universo.get('temporada') or []:
        if plan.get('id') not in vivas:
            return plan
    return None


def mundo_texto(universo):
    """El mundo compartido en renglones cortos, para que el guionista lo use por su id."""
    def renglones(mapa, pinta):
        return '\n'.join('- %s: %s' % (i, pinta(x)) for i, x in mapa.items() if isinstance(x, dict)) or '- (ninguno)'
    return '\n'.join([
        'PERSONAJES (id: quién es y qué quiere):',
        renglones(universo['personajes'], lambda x: '%s, %s. %s' % (x.get('nombre', ''), x.get('industria') or x.get('papel') or '', x.get('quiere', ''))),
        'LUGARES (id: nombre):', renglones(universo['lugares'], lambda x: str(x.get('nombre', ''))),
        'OBJETOS (id: nombre y qué significa):',
        renglones(universo['objetos'], lambda x: '%s. %s' % (x.get('nombre', ''), x.get('significado', ''))),
        'ENCUADRES (id: cómo se mueve la cámara):', renglones(universo['encuadres'], lambda x: str(x.get('nombre', ''))),
    ])


def plan_texto(plan, universo):
    """Una historia de la temporada, dicha al guionista con las fichas que debe respetar."""
    p = universo['personajes'].get(plan.get('protagonista')) or {}
    return '\n'.join(x for x in [
        'HISTORIA PLANEADA DE LA TEMPORADA. Escríbela como está planeada:',
        'Título: %s' % plan.get('titulo', ''),
        'Premisa: %s' % plan.get('premisa', ''),
        ('Protagonista: usa el id «%s» y no inventes otro. %s. Se ve: %s Viste: %s Gesto: %s'
         % (plan.get('protagonista'), p.get('nombre', ''), p.get('aspecto', ''), p.get('vestuario', ''), p.get('gesto', ''))) if p else '',
        ('Lugar principal: id «%s».' % plan['lugar']) if plan.get('lugar') in universo['lugares'] else '',
        ('Objeto propio de la serie: id «%s»; debe verse al menos en el primer y en el último episodio.' % plan['objeto'])
        if plan.get('objeto') in universo['objetos'] else '',
        ('Guiños obligatorios (ids de objetos del mundo; cada uno se ve en al menos un episodio y nadie lo explica): %s.'
         % ', '.join(plan['guinos'])) if plan.get('guinos') else '',
        ('Invitados (ids; aparecen un momento, repartidos en los últimos episodios): %s.' % ', '.join(plan['invitados']))
        if plan.get('invitados') else '',
        ('Lo que siembra el último episodio: %s' % plan['siembra']) if plan.get('siembra') else '',
    ] if x)


def conocidos(e, universo):
    """Personajes que ya tienen imagen y pueden volver como invitados en una serie libre: los
    del universo y los protagonistas de series aprobadas. {id: personaje con referencia_drive}:
    el invitado llega a la serie nueva con esa misma imagen."""
    out, canon = {}, e.get('canon')
    for pid, p in (universo.get('personajes') or {}).items():
        fid = isinstance(p, dict) and referencia_de('personajes', pid, universo, {}, canon)
        if fid:
            out[pid] = dict(p, referencia_drive=fid)
    for sid, s in e['serie'].items():
        if (e['dec'].get(sid) or {}).get('serie') != 'si':
            continue
        pid = s.get('personaje')
        p = reparto(universo, s).get(pid)
        fid = isinstance(p, dict) and referencia_de('personajes', pid, universo, s, canon)
        if fid and pid not in out:
            out[pid] = dict(p, referencia_drive=fid)
    return out


def _lista(valor, mapa, fuera=()):
    """Los ids de `valor` que existen en `mapa`, sin repetir y en su orden."""
    return [i for i in dict.fromkeys(x for x in (valor if isinstance(valor, list) else []) if isinstance(x, str))
            if i in mapa and i not in fuera]


def armar_serie(crudo, universo, vertice, existentes, invitables=None, plan=None):
    """De la respuesta del modelo a un documento de serie válido (o V4Error con el motivo).
    Con `plan` (una historia de la temporada) el protagonista, el lugar y el objeto son los
    planeados, y los guiños e invitados que el modelo olvidó se reparten en los episodios."""
    if not isinstance(crudo, dict):
        raise V4Error('el modelo no devolvió un objeto')
    plan = plan or {}
    titulo = str(crudo.get('titulo') or plan.get('titulo') or '').strip()
    base = '%s-%s' % (hoy().replace('-', ''), slug(titulo))
    sid, k = base, 2
    while sid in existentes:
        sid, k = '%s-%d' % (base, k), k + 1

    def elemento(clase, dato, planeado, falta):
        """(id, {id: ficha nueva}): un elemento del mundo por su id, o uno propio de la serie."""
        mapa = universo.get(clase) or {}
        if planeado in mapa:
            return planeado, {}
        if isinstance(dato, str) and dato.strip():       # por su id, o por su nombre si el modelo no puso el id
            for ident in (dato.strip(), slug(dato)):
                if ident in mapa:
                    return ident, {}
        if isinstance(dato, dict) and str(dato.get('nombre') or '').strip():
            ident = slug(dato['nombre'])
            # Uno «nuevo» que se llama igual que uno del mundo ES el del mundo: nadie cambia de cara.
            return (ident, {}) if ident in mapa else (ident, {ident: dict(dato)})
        if falta:
            raise V4Error(falta)
        return '', {}

    pid, personajes = elemento('personajes', crudo.get('personaje'), plan.get('protagonista'), 'falta el personaje')
    lid, lugares = elemento('lugares', crudo.get('lugar'), plan.get('lugar'), 'falta el lugar')
    oid, objetos = elemento('objetos', crudo.get('objeto'), plan.get('objeto'), '')
    for ficha in personajes.values():
        ficha.setdefault('papel', 'cliente')
    quien = dict(universo.get('personajes') or {}, **personajes)
    donde = dict(universo.get('lugares') or {}, **lugares)
    cosas = dict(universo.get('objetos') or {}, **objetos)
    eps = []
    for n, ep in enumerate(crudo.get('episodios') or [], 1):
        if not isinstance(ep, dict):
            raise V4Error('episodio %d mal formado' % n)
        nuevo = {'n': n, 'titulo': str(ep.get('titulo') or '').strip(), 'accion': str(ep.get('accion') or '').strip(),
                 'dialogo': str(ep.get('dialogo') or '').strip(), 'gancho': str(ep.get('gancho') or '').strip(),
                 'bloque': 15, 'continua': False,
                 'encuadre': ep.get('encuadre') if ep.get('encuadre') in (universo.get('encuadres') or {}) else '',
                 'tono': str(ep.get('tono') or '').strip(),
                 'objetos': _lista(ep.get('objetos'), cosas), 'invitados': _lista(ep.get('invitados'), quien, (pid,))}
        if isinstance(ep.get('lugar'), str) and ep['lugar'] in donde and ep['lugar'] != lid:
            nuevo['lugar'] = ep['lugar']
        eps.append(nuevo)
    if eps:
        # Lo que el plan pide y el modelo olvidó se coloca aquí, para que el cruce exista siempre.
        if oid and not any(oid in ep['objetos'] for ep in eps):
            for ep in (eps[0], eps[-1]):
                if oid not in ep['objetos']:
                    ep['objetos'].append(oid)
        faltan = [g for g in _lista(plan.get('guinos'), cosas) if not any(g in ep['objetos'] for ep in eps)]
        for j, g in enumerate(faltan):
            eps[min(len(eps) - 1, (j + 1) * len(eps) // (len(faltan) + 1))]['objetos'].append(g)
        ausentes = [i for i in _lista(plan.get('invitados'), quien, (pid,)) if not any(i in ep['invitados'] for ep in eps)]
        for j, i in enumerate(ausentes):
            eps[max(0, len(eps) - 1 - j % len(eps))]['invitados'].append(i)
    pedido = str(crudo.get('invitado_final') or '').strip()
    invitado = slug(pedido) if pedido else None
    for gid, g in (invitables or {}).items():
        # El invitado llega con su imagen: así sale igual que en su propia historia.
        if eps and invitado and gid != pid and invitado in (slug(gid), slug(g.get('nombre') or '')):
            if gid not in (universo.get('personajes') or {}):
                personajes[gid] = dict(g, papel='invitado')
            if gid not in eps[-1]['invitados']:
                eps[-1]['invitados'].append(gid)
            break
    s = {'id': sid, 'titulo': titulo, 'trama': str(crudo.get('trama') or plan.get('premisa') or '').strip(), 'vertice': vertice,
         'personaje': pid, 'lugar': lid, 'objeto': oid, 'personajes': personajes, 'lugares': lugares, 'objetos': objetos,
         'episodios': eps, 'origen': 'semillero', 'creada': ahora()}
    if plan.get('id'):
        s['temporada'] = plan['id']
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
    plan = temporada_pendiente(universo, e)
    vertice = plan['vertice'] if plan and plan.get('vertice') in universo['vertices'] else vertice_siguiente(universo, e['serie'])
    if not vertice:
        return 'el universo no tiene vértices'
    n = entero(aj.get('episodios'), 10)
    if simular:
        return 'simulación: pediría %s' % (('«%s», de la temporada' % plan.get('titulo')) if plan
                                           else 'una serie de %d episodios sobre «%s»' % (n, vertice))
    v = universo['vertices'][vertice]
    invitables = conocidos(e, universo)
    candados, aviso = candados_texto(leer_candados)
    pedido = '\n'.join(x for x in [
        'Vértice del negocio: %s — %s' % (v.get('nombre', vertice), v.get('mensaje', '')),
        ('REGLAS DEL MUNDO. Son obligatorias:\n' + str(universo.get('canon'))) if str(universo.get('canon') or '').strip() else '',
        plan_texto(plan, universo) if plan else 'HISTORIA LIBRE. Inventa un cliente nuevo, de una industria que no se haya usado, con su ficha completa.',
        'EL MUNDO COMPARTIDO. Usa estos ids tal cual; no cambies cómo se ve nadie ni nada:\n' + mundo_texto(universo),
        'Industrias de clientes ya usadas: %s' % (', '.join(sorted(
            {str(p.get('industria')) for s in e['serie'].values()
             for p in (s.get('personajes') or {}).values() if isinstance(p, dict) and p.get('industria')})) or 'ninguna'),
        'Historias ya propuestas (no las repitas): %s' % ('; '.join(str(s.get('titulo')) for s in e['serie'].values()) or 'ninguna'),
        ('Personajes conocidos de historias anteriores; UNO puede aparecer como invitado sólo en el último '
         'episodio, para entrelazar las historias:\n- ' + '\n- '.join(
             '%s (%s): %s' % (g.get('nombre', gid), g.get('industria', ''), g.get('quiere', ''))
             for gid, g in invitables.items())) if invitables and not plan else '',
        'Ideas pasadas que pueden nutrir la historia (no las copies):\n- ' + ('\n- '.join(inspiracion()) or 'ninguna'),
        ('Candados de Dirección. Son obligatorios; los de tipo veto no se negocian:\n' + candados) if candados else '',
    ] if x)
    instruccion = str(universo.get('guionista') or '').replace('{n}', str(n)) + FORMA_SERIE.format(n=n)
    pensar = pensar or pensador(universo)
    ultimo = None
    for _ in range(2):                    # un segundo intento si el JSON vino mal; no más
        try:
            s = armar_serie(pensar(pedido, instruccion), universo, vertice, e['serie'], invitables, plan)
        except (V4Error, MotorError) as err:
            ultimo = err
            continue
        guardar('serie', s['id'], s, existe=False)
        e['serie'][s['id']] = s
        return 'serie propuesta: «%s» (%s)%s' % (s['titulo'], s['id'], ' · ' + aviso if aviso else '')
    return 'no salió una serie válida: %s' % sala.redactar(str(ultimo))[:200]


# ------------------------------------------------------------------ 1b · referencias (el canon en imágenes)

SIN_LETRAS = ' No text, no letters, no captions, no logos, no watermark.'
NOMBRE_CLASE = {'personajes': 'personaje', 'lugares': 'lugar', 'objetos': 'objeto'}


def descripcion_ficha(clase, x):
    """El texto con que se pinta la imagen de referencia de un elemento del canon. Sale sólo
    de su ficha: si la ficha cambia, la imagen se vuelve a pintar."""
    if clase == 'personajes':
        return ('Vertical portrait photograph, waist up, of one person facing the camera with a calm friendly '
                'expression, in front of a plain warm light-grey wall, bright soft natural light, photorealistic, '
                'sharp focus. %s %s' % (x.get('aspecto', ''), x.get('vestuario', ''))).strip()
    if clase == 'lugares':
        return ('Vertical wide photograph of a place with no people in it, bright golden-hour natural light, '
                'photorealistic. %s %s' % (x.get('aspecto', ''), x.get('anclas', ''))).strip()
    return ('Vertical photograph of one single object and nothing else, on a plain warm wooden surface, soft natural '
            'light, photorealistic, sharp focus, no hands, no people. %s' % x.get('aspecto', '')).strip()


def huella(texto):
    return hashlib.sha1(str(texto).encode('utf-8')).hexdigest()[:12]


def necesarios(universo, s):
    """Los elementos del canon que una serie usa, [(clase, id, ficha)]: su protagonista, su
    lugar y sus objetos primero; después los invitados y los demás lugares."""
    mapas = {c: MUNDO[c](universo, s) for c in CLASES_MUNDO}
    out, vistos = [], set()

    def agrega(clase, ident):
        if isinstance(mapas[clase].get(ident), dict) and (clase, ident) not in vistos:
            vistos.add((clase, ident))
            out.append((clase, ident, mapas[clase][ident]))

    eps = [ep for ep in s.get('episodios') or [] if isinstance(ep, dict)]
    agrega('personajes', s.get('personaje'))
    agrega('lugares', s.get('lugar'))
    for ep in eps:
        for o in ep.get('objetos') or []:
            agrega('objetos', o)
    for ep in eps:
        for i in ep.get('invitados') or []:
            agrega('personajes', i)
        agrega('lugares', ep.get('lugar'))
    return out


def a_jpeg(datos, lado=1024):
    """Cualquier imagen → JPEG derecho y de lado mayor `lado`, para que viaje ligera como
    referencia. Una que ya es JPEG, ya cabe y no viene girada no se vuelve a comprimir."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(datos))
        if im.format == 'JPEG' and max(im.size) <= lado and im.getexif().get(0x0112, 1) == 1:
            return datos
        im = ImageOps.exif_transpose(im).convert('RGB')     # la foto de un teléfono trae su giro anotado aparte
    except Exception as err:                                # Pillow avisa de mil maneras; todas son «no es una imagen útil»
        raise MotorError('la imagen no se pudo leer (usa JPG o PNG): %s' % str(err)[:80])
    im.thumbnail((lado, lado))
    salida = io.BytesIO()
    im.save(salida, 'JPEG', quality=88)
    return salida.getvalue()


def _archivo_ficha(nombre, llave):
    limpio = re.sub(r'\s+', ' ', ''.join(c for c in str(nombre) if c.isprintable() and c not in '/\\')).strip()[:60]
    return '%s (%s).jpg' % (limpio or 'sin nombre', str(llave).replace(':', ' · '))


def origen_imagen(clase, ident, universo, s, canon):
    """(id de Drive, de dónde salió) de la imagen de referencia de un elemento."""
    fid = referencia_de(clase, ident, universo, s, canon)
    if not fid:
        return '', ''
    if id_drive((MUNDO[clase](universo, s).get(ident) or {}).get('referencia_drive')):
        return fid, 'la puso Dirección'
    return fid, 'salió del piloto' if registro_canon(clase, ident, universo, s, canon).get('de') else 'la pintó la nube'


def quien_es_quien(universo, e):
    """El índice del canon en texto llano: quién es quién, cómo se ve, dónde está su imagen y en
    qué series sale. Es para leerlo en Drive; lo que manda es lo guardado en Historias → Universo."""
    canon = e.get('canon') or {}
    donde = {}
    aprobadas = [s for sid, s in e['serie'].items() if (e['dec'].get(sid) or {}).get('serie') == 'si']
    for s in aprobadas:
        for clase, ident, _ in necesarios(universo, s):
            donde.setdefault((clase, llave_canon(universo, s, clase, ident)), []).append(str(s.get('titulo') or s.get('id')))
    campos = {'personajes': (('papel', 'Papel'), ('industria', 'Industria'), ('aspecto', 'Se ve'), ('vestuario', 'Viste'),
                             ('voz', 'Voz'), ('gesto', 'Gesto'), ('quiere', 'Quiere'), ('objeto', 'Su objeto')),
              'lugares': (('aspecto', 'Se ve'), ('anclas', 'Siempre se ve ahí')),
              'objetos': (('aspecto', 'Se ve'), ('significado', 'Qué significa'), ('de', 'Es de'))}
    lineas = ['CANON · quién es quién', '',
              'Lo arma la nube con lo guardado en Historias → Universo. Para cambiar algo, cámbialo allá.',
              'Para usar tu propia imagen de alguien o de algo: súbela a esta carpeta (JPG o PNG) y pega su liga en su ficha.', '']
    for clase in CLASES_MUNDO:
        fichas_ = [(i, x, {}) for i, x in (universo.get(clase) or {}).items() if isinstance(x, dict)]
        for s in aprobadas:                     # lo propio de cada serie aprobada
            fichas_ += [(i, x, s) for i, x in (s.get(clase) or {}).items() if isinstance(x, dict)]
        lineas += [clase.upper(), '']
        for ident, x, s in fichas_:
            llave = llave_canon(universo, s, clase, ident)
            lineas.append('· %s (%s)' % (x.get('nombre') or ident, llave))
            lineas += ['    %s: %s' % (etiqueta, x[c]) for c, etiqueta in campos[clase] if str(x.get(c) or '').strip()]
            fid, origen = origen_imagen(clase, ident, universo, s, canon)
            lineas.append('    Imagen: %s' % ('https://drive.google.com/file/d/%s/view (%s)' % (fid, origen) if fid else 'todavía no tiene'))
            if donde.get((clase, llave)):
                lineas.append('    Sale en: %s' % '; '.join(dict.fromkeys(donde[(clase, llave)])))
            lineas.append('')
    if universo.get('temporada'):
        lineas += ['TEMPORADA', '']
        for k, plan in enumerate(universo['temporada'], 1):
            lineas += ['%d. %s' % (k, plan.get('titulo', '')), '    %s' % plan.get('premisa', ''), '']
    return '\n'.join(lineas)


def piloto_de(s, dec, prod):
    """El número del piloto: el primer episodio que sigue en pie (0 si no queda ninguno)."""
    return entero(((en_pie(s, dec, prod) or [{}])[0]).get('n'))


def retrato_pendiente(universo, s, dec, prod, canon):
    """Cuando el piloto de una serie se produjo sin imagen de su protagonista, la cara que
    Dirección aprobó es la del piloto: su imagen de referencia se saca de ese video, no se pinta
    aparte. Devuelve qué hay que sacar ({'llave', 'nombre', 'origen', 'drive', 'ficha'}) o None
    si no hace falta: no hay piloto, el piloto ya nació de una imagen, Dirección puso la suya, o
    el retrato de esta versión del piloto ya está."""
    pid = s.get('personaje')
    ficha = reparto(universo, s).get(pid)
    n = piloto_de(s, dec, prod)
    u = ultima(prod, n)
    if not u or not isinstance(ficha, dict) or id_drive(ficha.get('referencia_drive')):
        return None
    if ('personajes:%s' % pid) in (u.get('referencias') or []):
        return None
    origen = '%s:E%02d-v%s' % (s.get('id'), n, u.get('v'))
    reg = registro_canon('personajes', pid, universo, s, canon)
    if reg.get('drive') and (reg.get('de') == origen or not str(reg.get('de') or '').startswith('%s:' % s.get('id'))):
        return None                        # ya tiene imagen: la de este mismo piloto, o una que no salió de él
    return {'llave': llave_canon(universo, s, 'personajes', pid), 'nombre': str(ficha.get('nombre') or pid),
            'origen': origen, 'drive': u['drive'], 'ficha': ficha}


def retratos_pendientes(e, universo):
    """{id de serie: lo que hay que sacar} de todas las series aprobadas."""
    canon, out = e.get('canon') or {}, {}
    for sid, s in e['serie'].items():
        if (e['dec'].get(sid) or {}).get('serie') == 'si':
            r = retrato_pendiente(universo, s, e['dec'].get(sid) or {}, e['prod'].get(sid) or {}, canon)
            if r:
                out[sid] = r
    return out


def sacar_retratos(e, universo, drive, raiz):
    """Saca de cada piloto el retrato que haga falta y lo deja en el canon, en Drive, con el
    nombre del personaje: desde ahí es su imagen en todas las series. No cuesta."""
    canon, hecho = e['canon'], []
    for sid, r in retratos_pendientes(e, universo).items():
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = pathlib.Path(tmp)
                video = drive.bajar(r['drive'], str(tmp / 'piloto.mp4'))
                archivo = tmp / _archivo_ficha(r['nombre'], r['llave'])
                # Hacia el final de la toma el personaje suele verse de frente y cerca.
                archivo.write_bytes(a_jpeg(cuadro(video, tmp / 'cuadro.jpg', antes_del_final=4.5)))
                fid = drive.subir(str(archivo), drive.ruta_carpetas(raiz, CARPETA_VIDEOS, CARPETA_CANON, 'personajes'))
        except (drive.DriveError, MotorError) as err:
            hecho.append('no pude sacar del piloto la imagen de «%s»: %s' % (r['nombre'], sala.redactar(str(err))[:160]))
            continue
        canon.setdefault('personajes', {})[r['llave']] = {'drive': fid, 'huella': huella(descripcion_ficha('personajes', r['ficha'])),
                                                          'de': r['origen']}
        guardar('canon', '', canon)
        hecho.append('imagen de referencia lista: %s (salió del piloto)' % r['nombre'])
    return hecho


def fichas(e, universo, simular, pintar=None, drive=None, raiz=None):
    """Las imágenes de referencia del canon: una por personaje, lugar y objeto que use una serie
    APROBADA. Se pintan una vez, quedan en Drive (_HISTORIAS/_CANON) y se rehacen sólo si cambia
    la ficha. De pago: lo limita «imágenes de referencia por día», la reserva se anota antes de
    pedir y un fallo detiene el paso. Lo que Dirección puso por su cuenta no se toca, y la cara
    que fijó un piloto se saca de ese piloto. La carpeta y el índice (CANON.txt) existen desde la
    primera corrida, haya o no series aprobadas: ahí puede dejar Dirección sus propias imágenes."""
    aj = universo['ajustes']
    tope, dia = entero(aj.get('fichas_por_dia')), hoy()
    canon = e['canon'] = e.get('canon') or {}
    aprobadas = [e['serie'][i] for i in sorted(e['serie'], key=lambda i: str(e['serie'][i].get('creada')))
                 if (e['dec'].get(i) or {}).get('serie') == 'si']
    retratos = retratos_pendientes(e, universo)
    del_piloto = {r['llave'] for r in retratos.values()}
    pendientes, vistos = [], set()
    for s in aprobadas:
        for clase, ident, x in necesarios(universo, s):
            llave = llave_canon(universo, s, clase, ident)
            if (clase, llave) in vistos:
                continue
            vistos.add((clase, llave))
            if clase == 'personajes' and llave in del_piloto:
                continue                   # su cara ya la fijó un piloto: se saca de ahí, no se pinta
            if por_pintar(clase, ident, universo, s, canon):
                pendientes.append((clase, llave, str(x.get('nombre') or ident), descripcion_ficha(clase, x)))
    # Una imagen que ya falló hoy con esta misma ficha no se vuelve a pedir hasta mañana (o hasta
    # que la ficha cambie): así lo que Google no quiere pintar no frena a lo demás.
    fallas = {k: f for k, f in (canon.get('fallas') or {}).items() if isinstance(f, dict)
              and any(k == '%s:%s' % (c, ll) and f.get('huella') == huella(txt) for c, ll, _, txt in pendientes)}
    hoy_no = [x for x in pendientes if (fallas.get('%s:%s' % x[:2]) or {}).get('dia') == dia]
    pendientes = [x for x in pendientes if x not in hoy_no]
    hecho = ['la imagen de «%s» falló hoy (%s): se reintenta mañana, o antes si cambias su ficha o pones la tuya'
             % (nombre, fallas['%s:%s' % (c, ll)].get('motivo') or 'sin motivo') for c, ll, nombre, _ in hoy_no]
    al_dia = 'referencias al día' if aprobadas else 'referencias: no hay series aprobadas'
    if not pendientes and not retratos and canon.get('carpeta') and canon.get('indice') == huella(quien_es_quien(universo, e)):
        return hecho or [al_dia]
    if simular:
        pintaria = ('referencias apagadas (imágenes por día en 0): %d sin pintar' % len(pendientes) if pendientes and tope <= 0
                    else 'pintaría %d imagen(es) de referencia%s' % (
                        len(pendientes), (': ' + ', '.join(n for _, _, n, _ in pendientes[:8])) if pendientes else ''))
        return hecho + ['simulación: %s%s' % (
            pintaria, ('; sacaría del piloto la de ' + ', '.join(r['nombre'] for r in retratos.values())) if retratos else '')]
    if drive is None:
        import sala_drive as drive
        raiz = regla('drive_raiz')
    if not raiz:
        if pendientes or retratos:
            raise V4Error('la REGLA drive_raiz está vacía: no hay dónde guardar las imágenes de referencia')
        return hecho + ['sin la REGLA drive_raiz no hay dónde dejar el índice del canon']
    try:
        base = drive.ruta_carpetas(raiz, CARPETA_VIDEOS, CARPETA_CANON)
        if canon.get('carpeta') != base:
            for clase in CLASES_MUNDO:         # las tres carpetas existen desde el principio
                drive.ruta_carpetas(base, clase)
    except drive.DriveError as err:
        return hecho + ['Drive no está listo y no se pintó nada: %s' % sala.redactar(str(err))[:200]]
    canon['carpeta'], canon['fallas'] = base, fallas
    canon['intentos'] = dict(sorted((canon.get('intentos') or {}).items())[-14:])
    hecho += sacar_retratos(e, universo, drive, raiz)
    if pendientes and tope <= 0:
        hecho.append('referencias apagadas (imágenes por día en 0): %d sin pintar' % len(pendientes))
        pendientes = []
    if pendientes and pintar is None:
        from motores import imagen
        modelo = str(aj.get('modelo_ficha') or '').strip() or AJUSTES['modelo_ficha']
        pintar = lambda texto: imagen.gemini(texto, {'imagen_gemini_modelo': modelo})[0]
    for k, (clase, llave, nombre, texto) in enumerate(pendientes):
        usadas = entero(canon['intentos'].get(dia))
        if usadas >= tope:
            hecho.append('tope de imágenes de referencia del día (%d): %d esperan a mañana' % (tope, len(pendientes) - k))
            break
        # La reserva se anota ANTES de pedir la imagen: un intento fallido también cuenta.
        canon['intentos'][dia] = usadas + 1
        guardar('canon', '', canon)
        try:
            exigir_sin_veto(texto)
            datos = a_jpeg(pintar(texto + SIN_LETRAS))
            with tempfile.TemporaryDirectory() as tmp:
                archivo = pathlib.Path(tmp) / _archivo_ficha(nombre, llave)
                archivo.write_bytes(datos)
                fid = drive.subir(str(archivo), drive.ruta_carpetas(base, clase))
        except (MotorError, contenido_reglas.ContenidoVetado, drive.DriveError) as err:
            motivo = sala.redactar(str(err))[:160]
            fallas['%s:%s' % (clase, llave)] = {'huella': huella(texto), 'dia': dia, 'motivo': motivo}
            hecho.append('la imagen de «%s» falló: %s' % (nombre, motivo))
            break                          # un fallo detiene el paso: no se insiste gastando
        canon.setdefault(clase, {})[llave] = {'drive': fid, 'huella': huella(texto)}
        fallas.pop('%s:%s' % (clase, llave), None)
        guardar('canon', '', canon)
        hecho.append('imagen de referencia lista: %s (%s)' % (nombre, NOMBRE_CLASE[clase]))
    indice = quien_es_quien(universo, e)
    if canon.get('indice') != huella(indice):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                archivo = pathlib.Path(tmp) / 'CANON.txt'
                archivo.write_text(indice, encoding='utf-8')
                drive.subir(str(archivo), base)
            canon['indice'] = huella(indice)
        except drive.DriveError as err:
            hecho.append('el índice del canon no se pudo subir: %s' % sala.redactar(str(err))[:160])
    guardar('canon', '', canon)
    return hecho or [al_dia]


def gastado_fichas(e, dia=None):
    return entero(((e.get('canon') or {}).get('intentos') or {}).get(dia or hoy()))


# ------------------------------------------------------------------ 2 · productor

def gastado_hoy(e, dia=None):
    dia = dia or hoy()
    return sum(entero((p.get('intentos') or {}).get(dia)) for p in e['prod'].values())


def ultima(prod, n):
    vs = (((prod or {}).get('episodios') or {}).get(str(n)) or {}).get('versiones') or []
    return vs[-1] if vs else None


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


def candidatas(universo, s, ep):
    """Lo que un episodio enseña y puede viajar como imagen, en orden: quién sale, los objetos
    y el lugar."""
    return ([('personajes', i) for i in elenco(universo, s, ep)] + [('objetos', i) for i in utileria(universo, s, ep)]
            + [('lugares', ep.get('lugar') or s.get('lugar'))])


def nombre_de(clase, ident, universo, s):
    return str((MUNDO[clase](universo, s).get(ident) or {}).get('nombre') or ident)


def esperan_imagen(universo, s, ep, canon, del_piloto=()):
    """Los nombres de lo que sale en el episodio y todavía no tiene su imagen al día. Con las
    imágenes de referencia encendidas el episodio espera a que estén: producido sin ellas saldría
    distinto de los demás. No espera por una cara que se va a sacar de un piloto (`del_piloto`)."""
    return [nombre_de(c, i, universo, s) for c, i in candidatas(universo, s, ep)[:MAX_REFERENCIAS]
            if por_pintar(c, i, universo, s, canon) and not (c == 'personajes' and llave_canon(universo, s, c, i) in del_piloto)]


def preparar_episodio(universo, s, ep, nota, prod, canon, tmp, drive, es_piloto):
    """Lo que un episodio necesita ANTES de gastar: (cuadro donde arranca, [JPEG], [(clase, id)]).
    El cuadro existe si continúa la escena del episodio anterior. Las imágenes de referencia
    llegan ya bajadas, en orden: quién sale, los objetos y el lugar; como mucho MAX_REFERENCIAS.
    Nada de esto cuesta. Si una imagen no se puede leer, o el texto trae una ubicación vetada,
    falla aquí: no se reserva ni se produce a medias un episodio que saldría distinto."""
    n, arranque = entero(ep.get('n')), None
    if ep.get('continua') and n > 1 and ultima(prod, n - 1):
        previo = drive.bajar(ultima(prod, n - 1)['drive'], str(tmp / 'previo.mp4'))
        arranque = cuadro(previo, tmp / 'previo.jpg')
    fotos, llaves = [], []
    for clase, ident in candidatas(universo, s, ep):
        if len(fotos) >= MAX_REFERENCIAS:
            break
        fid = referencia_de(clase, ident, universo, s, canon, piloto=es_piloto)
        if not fid:
            continue
        try:
            archivo = drive.bajar(fid, str(tmp / ('referencia%d' % len(fotos))))
            fotos.append(a_jpeg(pathlib.Path(archivo).read_bytes()))
        except (drive.DriveError, MotorError) as err:
            raise MotorError('no pude leer la imagen de «%s» (%s). Si es tuya, súbela como JPG o PNG a la carpeta del canon '
                             'en Drive y pega su liga en la ficha' % (nombre_de(clase, ident, universo, s), sala.redactar(str(err))[:80]))
        llaves.append((clase, ident))
    for toma in range(1, tomas_de(ep) + 1):
        exigir_sin_veto(prompt_toma(universo, s, ep, toma, nota, llaves, primer_cuadro=bool(arranque) or toma > 1))
    return arranque, fotos, llaves


def producir_episodio(universo, s, ep, version, nota, tmp, generar, drive, carpeta, arranque=None, fotos=(), llaves=()):
    """Genera las tomas de UN episodio, las une, sube el video a `carpeta` (la de la serie en
    Drive) y devuelve su registro. `arranque`, `fotos` y `llaves` vienen de `preparar_episodio`."""
    tomas, n = tomas_de(ep), entero(ep.get('n'))
    fotos, llaves, avisos = list(fotos), list(llaves), []
    gente = [(f, ll) for f, ll in zip(fotos, llaves) if ll[0] == 'personajes']
    cosas = [(f, ll) for f, ll in zip(fotos, llaves) if ll[0] != 'personajes']

    def entradas():
        """De la entrada más fiel a la más simple: (qué es, primer cuadro, imágenes, de qué son).
        Si Google no acepta la imagen de una persona, al menos viajan los objetos y el lugar."""
        if arranque and fotos:
            yield 'el último cuadro junto con las imágenes de referencia', arranque, fotos, llaves
        if arranque:                       # con primer cuadro el personaje ya está en la imagen
            yield 'el último cuadro de la toma anterior', arranque, None, []
        if fotos:
            yield 'las imágenes de referencia', None, fotos, llaves
        if gente and len(gente) < len(fotos):
            yield 'las imágenes de los personajes', None, [f for f, _ in gente], [ll for _, ll in gente]
        if cosas and len(cosas) < len(fotos):
            yield 'las imágenes de los objetos y del lugar', None, [f for f, _ in cosas], [ll for _, ll in cosas]
        yield '', None, None, []

    clips, usadas = [], []
    for t in range(1, tomas + 1):
        for que, jpg, imagenes, de_que in entradas():
            texto = prompt_toma(universo, s, ep, t, nota, de_que, primer_cuadro=bool(jpg))
            exigir_sin_veto(texto)
            try:
                video = generar(texto, 15, jpg=jpg, referencias=imagenes)
            except MotorError as err:
                if not que or getattr(err, 'http', None) != 400:
                    raise
                # Google no aceptó esas imágenes (un 400 no se cobra): la toma baja un escalón y
                # no se pierde lo que ya se pagó de este episodio.
                avisos.append('no se pudo usar %s: %s' % (que, sala.redactar(str(err))[:120]))
                continue
            usadas += [ll for ll in de_que if ll not in usadas]
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
           'con_retrato': any(c == 'personajes' for c, _ in usadas), 'referencias': ['%s:%s' % ll for ll in usadas],
           'costo_usd_aprox': round(USD_POR_TOMA * tomas, 2)}
    if avisos:
        reg['aviso'] = '; '.join(dict.fromkeys(avisos))[:400]
    return reg


def productor(e, universo, simular, generar=None, drive=None, raiz=None):
    aj = universo['ajustes']
    tope, hecho = entero(aj.get('tope_clips_dia')), []
    if tope <= 0:
        return ['productor apagado: tope de tomas por día en 0']
    dia, pinta = hoy(), entero(aj.get('fichas_por_dia')) > 0
    canon = e['canon'] = e.get('canon') or {}
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
            # Con las imágenes de referencia encendidas, un episodio espera a que lo que sale en él
            # tenga la suya: producido antes saldría distinto de los demás.
            del_piloto = {r['llave'] for r in retratos_pendientes(e, universo).values()}
            faltan = esperan_imagen(universo, s, ep, canon, del_piloto) if pinta else []
            if faltan:
                hecho.append('«%s» episodio %s espera la imagen de: %s' % (s.get('titulo'), ep.get('n'), ', '.join(faltan)))
                break
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
            es_piloto = entero(ep.get('n')) == piloto_de(s, dec, prod)
            with tempfile.TemporaryDirectory() as tmp:
                tmp = pathlib.Path(tmp)
                # Lo que no cuesta va antes de reservar: los retratos que falte sacar de un piloto,
                # el cuadro de arranque, las imágenes ya bajadas y el veto sobre el texto.
                try:
                    hecho += sacar_retratos(e, universo, drive, raiz)
                    aqui = {llave_canon(universo, s, c, i) for c, i in candidatas(universo, s, ep) if c == 'personajes'}
                    sin_sacar = [r['nombre'] for r in retratos_pendientes(e, universo).values() if r['llave'] in aqui]
                    if sin_sacar and not es_piloto:
                        raise MotorError('falta sacar del piloto la imagen de %s' % ', '.join(sin_sacar))
                    arranque, fotos, llaves = preparar_episodio(universo, s, ep, nota, prod, canon, tmp, drive, es_piloto)
                except (MotorError, contenido_reglas.ContenidoVetado, drive.DriveError) as err:
                    aviso = '«%s» episodio %s v%d no se produjo y no se gastó: %s' % (
                        s.get('titulo'), ep.get('n'), version, sala.redactar(str(err))[:260])
                    if ((prod.get('avisos') or [{}])[-1]).get('texto') != aviso:      # una vez, no en cada corrida
                        prod.setdefault('avisos', []).append({'cuando': ahora(), 'texto': aviso})
                        prod['avisos'] = prod['avisos'][-10:]
                        guardar('prod', sid, prod)
                    hecho.append(aviso)
                    break
                # La reserva se anota ANTES de gastar: un intento fallido también cuenta.
                intentos = prod.setdefault('intentos', {})
                intentos[dia] = entero(intentos.get(dia)) + tomas
                guardar('prod', sid, prod)
                try:
                    reg = producir_episodio(universo, s, ep, version, nota, tmp, generar, drive, carpeta, arranque, fotos, llaves)
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
    'el personaje. El del último día cierra con un solo paso siguiente. Es una historia de ficción: no la '
    'presentes como caso real ni como testimonio. Devuelve SOLO un objeto JSON: '
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
               'Es una historia de ficción: no se presenta como caso real ni como testimonio.',
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

def motores_listos(universo):
    """Una línea que dice si los modelos de Google que usa la 4.0 existen para esta llave.
    Preguntar la lista no cuesta; sirve para saber, antes de gastar, si un nombre ya cambió."""
    from motores import escena_omni
    aj = universo['ajustes']
    quiere = [('guion', str(aj.get('modelo_guion') or '').strip()), ('imágenes', str(aj.get('modelo_ficha') or '').strip()),
              ('video', escena_omni.MODELO)]
    try:
        nombres, pagina = set(), ''
        for _ in range(10):
            r = escena_omni.llamar('GET', 'models?pageSize=1000' + ('&pageToken=' + urllib.parse.quote(pagina) if pagina else ''))
            nombres |= {str(m.get('name') or '').split('/')[-1] for m in r.get('models') or [] if isinstance(m, dict)}
            pagina = str(r.get('nextPageToken') or '')
            if not pagina:
                break
    except MotorError as err:
        return 'motores: no pude preguntar a Google qué modelos hay (%s)' % sala.redactar(str(err))[:120]
    return 'motores: ' + ' · '.join('%s «%s» %s' % (que, m, 'está disponible' if m in nombres else 'NO aparece en la lista de Google')
                                   for que, m in quiere)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--solo', choices=('semillero', 'referencias', 'productor', 'paquete'))
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
        if a.solo in (None, 'referencias'):
            pasos += fichas(e, universo, a.simular)
        if a.solo in (None, 'productor'):
            pasos += productor(e, universo, a.simular)
        if a.solo in (None, 'paquete'):
            pasos += paquete(e, universo, a.simular)
        if a.simular:
            pasos.append(motores_listos(universo))
    except (sala.SalaError, V4Error) as err:
        pasos.append('✗ la corrida se detuvo: %s' % sala.redactar(str(err))[:300])
        codigo = 1
    tope = entero(universo['ajustes'].get('tope_clips_dia'))
    usadas = gastado_hoy(e)
    for linea in pasos:
        sala.avisar('· ' + linea)
    if not a.simular:
        try:
            imagenes = gastado_fichas(e)
            guardar('estado', '', {'cuando': ahora(), 'pasos': pasos, 'clips_hoy': usadas, 'tope': tope,
                                   'imagenes_hoy': imagenes,
                                   'gasto_usd_aprox_hoy': round(usadas * USD_POR_TOMA + imagenes * USD_POR_FICHA, 2)})
        except sala.SalaError as err:
            sala.avisar('⚠ no pude dejar el estado: %s' % sala.redactar(str(err))[:200])
            codigo = codigo or 1
    return codigo


if __name__ == '__main__':
    sys.exit(main())
