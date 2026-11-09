#!/usr/bin/env python3
"""Estación de salida de la Sala corta: de «láminas aprobadas» a «paquete listo para publicar».

9-nov-2026 · Dirección: «más que la publicación quiero el proceso de creación de inicio a final
completo… no me borres nada de lo pasado de ideas ya aprobadas… sólo quiero orden para poderlas
desatorar». Lo medido ese día: las 27 piezas vivas tenían TODAS sus láminas aprobadas y ninguna
avanzaba, porque la línea no tenía quién hiciera la etapa «copy» ni quién entregara.

Reparto (el mismo del consejo de nube: ninguna llave pasa por un modelo):
  · el jurado de nube ESCRIBE el texto de la publicación —eso es juicio— y lo manda como dato;
  · esta estación hace lo demás sin juicio: comprueba qué pieza está completa, valida el texto
    contra los candados que se pueden comprobar con una regla, sube a Drive las imágenes
    aprobadas en orden con su documento y lo anota en la Sala (EXPEDIENTES y PRODUCCION).

No decide (INVIOLABLE 3), no publica y no borra. Publicar es el clic de Dirección; cuando la Sala
anota «publicada», esta estación guarda el paquete en `_PUBLICADAS` y cierra su expediente.

Uso (workflow sala-consejo.yml):
  python3 nube/sala_salida.py lista      # sólo dice qué hay; no escribe
  python3 nube/sala_salida.py paquete    # textos en SALIDA_PAQUETES; SALIDA_ENSAYO=1 no escribe
"""

import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request

import contenido_reglas
import sala_cliente as sala
import sala_produccion as produccion

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PAGES = 'https://yodesarrollomx.github.io/sala-edicion/'
CARPETA = '_LISTAS PARA PUBLICAR'
CARPETA_PUBLICADAS = '_PUBLICADAS'
LIGA = 'https://yodesarrollo.github.io/plan-potencial/'
CIERRE_IG = '(la liga te espera en el primer comentario)'
MAX_PAQUETES = 60000                                  # los inputs de workflow_dispatch topan en 65 535
MAX_POR_CORRIDA = 40
MAX_IMAGEN = 12 * 1024 * 1024
TEXTO_MIN, TEXTO_MAX = 120, 1900                       # Instagram admite 2 200; el cierre y la liga caben

ID = re.compile(r'^[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}$')
SELLO = re.compile(r'^[0-9a-f]{12}$')
RUTA = re.compile(r'^laminas/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.(png|jpg|jpeg|webp)$')
NO_PIEZA = re.compile(r'(corte|video|prueba|coherencia)', re.I)   # igual que el montador
DINERO = re.compile(r'(\$\s*\d|\d[\d.,]*\s*(pesos|mil|mdp|millones|usd|d[oó]lares)\b|\bgratis\b|\bgratuit[oa]s?\b)', re.I)
PLAZO = re.compile(r'\b\d+\s*(horas?|hrs?|d[ií]as?|semanas?|minutos?|meses)\b', re.I)
LIGA_EN_TEXTO = re.compile(r'(https?://|www\.|\b[a-z0-9-]+\.(com|mx|io|net|org)\b)', re.I)
PALABRAS = ('pleito', 'pleitos', 'estorba', 'estorbar', 'estorbo', 'gremio', 'gremios', 'nacer en tu terreno')
RECETA = (
    'Texto (caption) de la publicación para Instagram y Facebook de Yo Desarrollo. '
    'Le habla de tú al dueño de un terreno, de 40 a 60 años. Renglones cortos, bloques de dos o tres '
    'renglones separados por un renglón en blanco. Abre con una frase que esa persona reconozca como '
    'suya. Cuenta lo mismo que cuentan las láminas, con otras palabras. Nombra lo que entregamos sólo '
    'si la pieza lo menciona: los m² que permite la norma, los giros que caben, vialidad, '
    'estacionamiento, agua y drenaje. Cierra con el producto por su nombre completo, «Plan de Potencial '
    'Personalizado», y con un solo paso: «Tú traes la ubicación. El primer paso es una videollamada 👇». '
    'Propón, no ordenes. Sin ciudades, estados ni países; sin cifras de dinero, sin «gratis», sin '
    'plazos; sin palabras negativas o rebuscadas. Entre 400 y 900 caracteres. Sin ligas (la liga '
    'medible la pone la estación) y sin hashtags.')


class SalidaError(RuntimeError):
    """La estación no pudo comprobar algo. Nunca se convierte en «no había nada que entregar»."""


# ── reglas ─────────────────────────────────────────────────────────────────────────────────

def _regla(reglas, nombre, defecto=''):
    v = (reglas or {}).get(nombre, '')
    if isinstance(v, dict):
        v = v.get('valor', '')
    v = str(v if v is not None else '').strip()
    return v or defecto


def _lista(reglas, nombre):
    return [x.strip() for x in _regla(reglas, nombre).split(',') if x.strip()]


def _entero(reglas, nombre, defecto):
    try:
        return int(float(_regla(reglas, nombre, str(defecto))))
    except ValueError:
        return defecto


def activa(reglas):
    return _regla(reglas, 'salida_activa', '1').lower() not in ('0', 'no', 'false', 'pausa')


def video_en_pausa(reglas):
    """El video está en pausa mientras la nube no ejecute escena y corte (REGLAS nube_ejecuta_etapas)."""
    return not {'escena', 'corte'} <= set(_lista(reglas, 'nube_ejecuta_etapas'))


def formato_de_salida(tira, cuantas, reglas):
    """(formato, nota) con que sale la pieza, o (None, motivo) si su salida no es de esta estación."""
    f = _sin_acentos(str(tira.get('formato') or ''))
    if cuantas == 1 or f in ('lamina', 'imagen'):
        return 'Lámina', ''
    if f in ('carrusel', ''):                         # sin formato declarado: son imágenes en orden
        return 'Carrusel', ''
    if _regla(reglas, 'salida_reels_como_carrusel', '1') in ('0', 'no') or not video_en_pausa(reglas):
        return None, 'es de video: su salida es el corte'
    return 'Carrusel', 'nació para video; mientras el video está en pausa sale como carrusel'


# ── texto ──────────────────────────────────────────────────────────────────────────────────

def _sin_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto or '').casefold())
                   if not unicodedata.combining(c)).strip()


def limpiar(texto):
    """Fines de línea parejos, sin espacios colgando ni más de un renglón en blanco seguido."""
    t = unicodedata.normalize('NFC', str(texto or '')).replace('\r\n', '\n').replace('\r', '\n')
    t = '\n'.join(r.rstrip() for r in t.split('\n'))
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def revisar_texto(texto, reglas=None):
    """Los candados que una regla sí puede comprobar. Devuelve códigos, nunca el texto.

    A01 ubicaciones · A11 palabras que dejan mala imagen · A13 «Plan de Potencial Personalizado» ·
    A14 dinero, «gratis» y plazos · A15 sólo la marca Yo Desarrollo. Lo demás (que enganche, que
    cuente lo que cuentan las láminas) es juicio del jurado y de Dirección."""
    if not isinstance(texto, str):
        return ['sin_texto']
    fallas = []
    if any(ord(c) < 32 and c != '\n' for c in texto) or '\x7f' in texto:
        fallas.append('caracteres_de_control')
    t = limpiar(texto)
    if len(t) < TEXTO_MIN:
        fallas.append('corto')
    if len(t) > TEXTO_MAX:
        fallas.append('largo')
    if contenido_reglas.prohibidas(t, reglas):
        fallas.append('ubicacion')
    if DINERO.search(t):
        fallas.append('dinero_o_gratis')
    if PLAZO.search(t):
        fallas.append('plazo')
    if LIGA_EN_TEXTO.search(t):
        fallas.append('liga')
    plano = _sin_acentos(t)
    if re.search(r'(?<!\w)aurum(?!\w)', plano):
        fallas.append('otra_marca')
    vetadas = [_sin_acentos(p) for p in (*PALABRAS, *_lista(reglas, 'salida_palabras_vetadas'))]
    if any(re.search(r'(?<!\w)' + re.escape(p) + r'(?!\w)', plano) for p in vetadas if p):
        fallas.append('palabra_vetada')
    # El nombre del producto: completo y con sus tres mayúsculas, siempre.
    for m in re.finditer(r'plan(?:\s+de)?\s+potencial(\s+personalizado)?', t, re.I):
        if m.group(0) != 'Plan de Potencial Personalizado':
            fallas.append('nombre_del_plan')
            break
    return fallas


def _liga(base, red, corto, fecha, slug):
    if not re.match(r'^https://[A-Za-z0-9.-]+/[^\s"<>]*$', base):
        raise SalidaError('REGLAS salida_liga no es una dirección https válida')
    return base + ('&' if '?' in base else '?') + urllib.parse.urlencode(
        {'utm_source': red, 'utm_medium': 'social', 'utm_campaign': '%s-%s' % (corto, fecha), 'utm_content': slug})


def componer(texto, slug, fecha, reglas=None):
    """El texto del jurado más lo que no es juicio: el cierre de Instagram y las ligas medibles."""
    base = _regla(reglas, 'salida_liga', LIGA)
    cierre = _regla(reglas, 'salida_cierre_ig', CIERRE_IG)
    ig, fb = _liga(base, 'instagram', 'ig', fecha, slug), _liga(base, 'facebook', 'fb', fecha, slug)
    t = limpiar(texto)
    return {'texto': t, 'instagram': t + '\n' + cierre, 'comentario': ig, 'facebook': t + '\n' + fb}


# ── qué pieza está completa ────────────────────────────────────────────────────────────────

def _fecha_de(tira):
    fechas = [str(tira.get('fecha') or '')]
    for lam in tira.get('laminas') or []:
        fechas.append(str(lam.get('fecha') or ''))
        fechas += [str(v.get('fecha') or '') for v in lam.get('versiones') or [] if isinstance(v, dict)]
    return max(fechas)


_TIRAS = {}


def leer_tira(pid):
    """Primero el checkout, luego Pages: las tiras nuevas viajan en el snapshot público."""
    pid = str(pid)
    if not ID.match(pid):
        return None
    if pid not in _TIRAS:
        tira = None
        try:
            tira = json.loads((RAIZ / 'datos' / 'tiras' / (pid + '.json')).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            try:
                tira = json.loads(_bajar(PAGES + 'datos/tiras/' + pid + '.json', 2 * 1024 * 1024))
            except Exception:                        # noqa: BLE001 — sin tira, quien llama decide
                tira = None
        _TIRAS[pid] = tira if isinstance(tira, dict) and isinstance(tira.get('laminas'), list) else None
    return _TIRAS[pid]


def piezas_vigentes(dia, lector=None):
    """{slug: (pid, tira, carta)} — de cada pieza, la tira viva más reciente del Sheet."""
    lector = lector or leer_tira
    mejores = {}
    for p in dia.get('propuestas') or []:
        pid = str(p.get('id') or '')
        if not ID.match(pid) or NO_PIEZA.search(pid) or p.get('video') or p.get('tipo') not in (None, '', 'laminas'):
            continue
        tira = lector(pid)
        if not tira or not tira.get('laminas'):
            continue
        slug = str(tira.get('pieza_slug') or pid.split('-')[0])
        clave = (str(p.get('fecha_fuente') or p.get('de_antes') or ''), _fecha_de(tira), pid)
        if slug not in mejores or clave > mejores[slug][0]:
            mejores[slug] = (clave, pid, tira, p)
    return {s: (pid, t, p) for s, (_, pid, t, p) in mejores.items()}


def _original(lam):
    """La imagen que se publica: el original, nunca la prueba ligera."""
    ruta = str(lam.get('src') or '')
    for c in lam.get('candidatas') or []:
        if isinstance(c, dict) and ruta and ruta == c.get('src') and c.get('original'):
            return str(c['original'])
    return ruta


def laminas_aprobadas(resuelta):
    """([{n, ruta, dice, ve, toma, huella}], '') si TODA la pieza está aprobada; (None, motivo) si no."""
    lams = [l for l in resuelta.get('laminas') or [] if isinstance(l, dict)]
    if not lams:
        return None, 'sin láminas'
    guion = resuelta.get('guion')
    if isinstance(guion, list):                       # un guion heredado en texto no declara láminas
        try:
            faltan = produccion.guion_faltante(resuelta)
        except sala.SalaError:
            return None, 'guion sin contrato'
        if faltan:
            return None, 'faltan %d lámina(s) del guion' % len(faltan)
    out = []
    for lam in sorted(lams, key=lambda l: (l.get('n') if isinstance(l.get('n'), int) else 0)):
        n = lam.get('n')
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            return None, 'lámina sin número'
        if lam.get('estado') != 'aprobada':
            return None, 'la lámina %d no está aprobada' % n
        ruta = _original(lam)
        if not RUTA.match(ruta):
            return None, 'la lámina %d no trae una imagen publicable' % n
        sel = lam.get('seleccion') or {}
        out.append({'n': n, 'ruta': ruta, 'dice': str(lam.get('dice') or ''), 've': str(lam.get('ve') or ''),
                    'toma': sel.get('toma') if isinstance(sel.get('toma'), int) else None,
                    'huella': str(sel.get('huella') or '')})
    if len({l['n'] for l in out}) != len(out):
        return None, 'números de lámina repetidos'
    return out, ''


def sello_de_pieza(pid, laminas):
    """Ata un texto a la pieza exacta para la que se escribió: su tira y sus imágenes, en orden."""
    cuerpo = [str(pid), [[l['n'], l['ruta'], l['huella']] for l in laminas]]
    return hashlib.sha256(json.dumps(cuerpo, ensure_ascii=False).encode()).hexdigest()[:12]


def _es_publicada(e):
    if not isinstance(e, dict):
        return False
    if e.get('estado') == 'publicada' or e.get('post'):
        return True
    return any(re.search(r'publicad|IG \d{6,}', str(h.get('que') or ''), re.I)
               for h in e.get('hitos') or [] if isinstance(h, dict))


def _publicadas_del_repo():
    """Lo que la casa ya registró como publicado antes de la nube («una publicada no vuelve»)."""
    out = set()
    for nombre, clave in (('piezas.json', None), ('embudo.json', None)):
        try:
            d = json.loads((RAIZ / 'datos' / nombre).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for x in d.get('piezas') or []:
            if isinstance(x, dict) and (nombre == 'embudo.json' or str(x.get('etapa')) == 'publicada'):
                out.add(_sin_acentos(x.get('pieza')))
    return out - {''}


def filas_publicada(dia):
    """Filas de PRODUCCION con que un editor anotó «ya la publiqué» (o la casa lo registró)."""
    out = {}
    for f in dia.get('produccion') or []:
        if isinstance(f, dict) and re.match(r'^publicad', str(f.get('estado') or ''), re.I) and f.get('pieza'):
            out.setdefault(_sin_acentos(f['pieza']), f)       # la más reciente primero (así llega el día)
    return out


def estado_de_piezas(dia_produccion, dia, reglas, expedientes, lector=None, proyeccion=None):
    """Una fila por pieza viva, con el estado que la Sala le enseña a Dirección.

    estados: publicada · lista (paquete hecho y vigente) · completa (todo aprobado, falta empacar) ·
    en_laminas · video · excluida. `proyeccion` es la lista de ids que la propia mesa publicó como
    vigentes: si viene y una pieza completa no está ahí, se espera a la siguiente ronda de la mesa."""
    excluir = set(_lista(reglas, 'salida_excluir'))
    ya = _publicadas_del_repo() | set(filas_publicada(dia))
    decisiones = ((dia_produccion.get('decisiones') or {}).get('propuestas')) or {}
    filas = []
    for slug, (pid, tira, carta) in sorted(piezas_vigentes(dia_produccion, lector).items()):
        nombre = str(tira.get('pieza') or slug).strip()
        exp = (expedientes or {}).get(nombre)
        fila = {'slug': slug, 'pieza': nombre, 'id': pid, 'promesa': str(tira.get('promesa') or ''),
                'paquete': (exp or {}).get('paquete') if isinstance(exp, dict) else None}
        if _es_publicada(exp) or _sin_acentos(nombre) in ya:
            filas.append(dict(fila, estado='publicada', motivo=''))
            continue
        try:
            resuelta = produccion.resolver_tira(tira, decisiones.get(pid) or {}, carta)
        except sala.SalaError:
            filas.append(dict(fila, estado='en_laminas', motivo='decisión sin contrato; la revisa la mesa'))
            continue
        laminas, motivo = laminas_aprobadas(resuelta)
        if laminas is None:
            filas.append(dict(fila, estado='en_laminas', motivo=motivo))
            continue
        formato, nota = formato_de_salida(tira, len(laminas), reglas)
        fila.update(laminas=laminas, sello=sello_de_pieza(pid, laminas), formato=formato or '', nota_formato=nota)
        if formato is None:
            filas.append(dict(fila, estado='video', motivo=nota))
        elif slug in excluir:
            filas.append(dict(fila, estado='excluida', motivo='REGLAS salida_excluir'))
        elif isinstance(fila['paquete'], dict) and fila['paquete'].get('sello') == fila['sello']:
            filas.append(dict(fila, estado='lista', motivo=''))
        elif proyeccion is not None and pid not in proyeccion:
            filas.append(dict(fila, estado='en_laminas', motivo='la mesa todavía no publica esta versión'))
        else:
            filas.append(dict(fila, estado='completa', motivo=''))
    return filas


def resumen(filas):
    cuenta = {}
    for f in filas:
        cuenta[f['estado']] = cuenta.get(f['estado'], 0) + 1
    return cuenta


# ── lecturas ───────────────────────────────────────────────────────────────────────────────

def _bajar(url, tope):
    pet = urllib.request.Request(url, headers={'User-Agent': 'sala-salida', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(pet, timeout=60) as r:
        datos = r.read(tope + 1)
    if len(datos) > tope:
        raise SalidaError('archivo demasiado grande')
    return datos


_MEDIOS = None


def medios():
    """ruta → {url, sha256} de las imágenes que viven en releases públicos."""
    global _MEDIOS
    if _MEDIOS is None:
        try:
            m = json.loads(_bajar(PAGES + 'datos/medios-publicos.json', 4 * 1024 * 1024))
            _MEDIOS = {k: v for k, v in (m.get('entries') or {}).items()
                       if isinstance(v, dict) and str(v.get('url') or '').startswith('https://github.com/yodesarrollomx/sala-edicion/releases/download/')}
        except Exception:                            # noqa: BLE001 — sin manifiesto, Pages directo
            _MEDIOS = {}
    return _MEDIOS


def url_de(ruta):
    m = medios().get(ruta)
    return m['url'] if m else PAGES + ruta


def proyeccion_de_la_mesa():
    """Los ids que la mesa publicó como vigentes, o None si no se pudo leer (no bloquea la salida)."""
    try:
        m = json.loads(_bajar(PAGES + 'datos/mesa-estado.json', 2 * 1024 * 1024))
        ids = {str(p.get('id')) for p in m.get('publicaciones') or [] if isinstance(p, dict)}
        return ids or None
    except Exception:                                # noqa: BLE001
        return None


def traer_imagen(lam):
    """Los bytes del original aprobado, comprobados contra lo que la casa ya sabe de ese archivo."""
    ruta = lam['ruta']
    if not RUTA.match(ruta):
        raise SalidaError('ruta de imagen no autorizada')
    local = RAIZ / ruta
    m = medios().get(ruta)
    if local.is_file():
        datos = local.read_bytes()
    else:
        datos = _bajar(m['url'] if m else PAGES + ruta, MAX_IMAGEN)
    if not datos.startswith((b'\x89PNG', b'\xff\xd8', b'RIFF')):
        raise SalidaError('la lámina %d no llegó como imagen' % lam['n'])
    if m and m.get('sha256') and not local.is_file() and hashlib.sha256(datos).hexdigest() != m['sha256']:
        raise SalidaError('la lámina %d no coincide con su recibo público' % lam['n'])
    if lam.get('huella') and hashlib.md5(datos).hexdigest() != lam['huella']:
        raise SalidaError('la lámina %d no es la toma que se aprobó' % lam['n'])
    return datos


def leer_expedientes():
    r = sala.get('expedientes')
    exp = r.get('expedientes') if isinstance(r, dict) else None
    if not isinstance(exp, dict):
        raise SalidaError('el Sheet no entregó los expedientes')
    return exp


def receta(reglas=None):
    """Cómo se escribe el texto. Dirección la cambia en el Sheet: PROMPTS, fila `_copy`."""
    try:
        filas = (sala.get('prompts', pieza='_copy') or {}).get('prompts') or []
        propia = next((str(f.get('prompt_base') or '').strip() for f in filas
                       if isinstance(f, dict) and str(f.get('pieza')) == '_copy'), '')
    except sala.SalaError:
        propia = ''
    return propia[:4000] or RECETA


def leer_mesa():
    """Las tres lecturas del Sheet que necesita la estación. Si una falla, no se inventa nada."""
    reglas = (sala.get('reglas') or {}).get('reglas') or {}
    reglas = {k: (v.get('valor') if isinstance(v, dict) else v) for k, v in reglas.items()}
    return reglas, produccion.cargar(), sala.get('dia', fresco='1'), leer_expedientes()


# ── lo que ve el jurado ────────────────────────────────────────────────────────────────────

def para_el_jurado(reglas, filas, receta_texto):
    """La parte «salida» del expediente: las piezas completas que esperan su texto."""
    tope = max(0, _entero(reglas, 'salida_piezas_por_sesion', 3))
    completas = [f for f in filas if f['estado'] == 'completa']
    orden = {'Carrusel': 0, 'Lámina': 1}
    completas.sort(key=lambda f: (bool(f.get('nota_formato')), orden.get(f['formato'], 2), f['slug']))
    return {
        'activa': activa(reglas), 'tope': tope, 'receta': receta_texto,
        'limites': {'minimo': TEXTO_MIN, 'maximo': TEXTO_MAX},
        'resumen': resumen(filas),
        'pendientes': [{
            'id': f['id'], 'sello': f['sello'], 'pieza': f['pieza'], 'slug': f['slug'], 'formato': f['formato'],
            'nota_formato': f.get('nota_formato') or '', 'promesa': f['promesa'][:600],
            'laminas': [{'n': l['n'], 'dice': l['dice'], 've': l['ve'][:400], 'url': url_de(l['ruta'])}
                        for l in f['laminas']]} for f in (completas[:tope] if activa(reglas) else [])],
        'en_espera': max(0, len(completas) - tope)}


def lista():
    """Sólo dice cómo está la salida. No escribe en ningún lado."""
    sala.enmascarar_en_actions()
    reglas, dia_p, dia, exp = leer_mesa()
    filas = estado_de_piezas(dia_p, dia, reglas, exp, proyeccion=proyeccion_de_la_mesa())
    for f in filas:
        sala.avisar('· %-38s %-11s %s' % (f['slug'][:38], f['estado'], f.get('motivo') or ''))
    sala.avisar('Salida %s · %s' % ('activa' if activa(reglas) else 'EN PAUSA (REGLAS salida_activa)',
                                    ' · '.join('%s %d' % kv for kv in sorted(resumen(filas).items())) or 'sin piezas'))
    return 0


# ── el paquete ─────────────────────────────────────────────────────────────────────────────

def leer_paquetes(crudo):
    """El JSON del jurado: {"esquema":1,"paquetes":[{"id","sello","texto","revision":[…]}]}."""
    crudo = (crudo or '').strip()
    if not crudo:
        return []
    if len(crudo) > MAX_PAQUETES:
        raise SalidaError('los textos pesan más de %d caracteres' % MAX_PAQUETES)
    try:
        doc = json.loads(crudo)
    except ValueError:
        raise SalidaError('los textos no llegaron como JSON')
    paquetes = doc.get('paquetes') if isinstance(doc, dict) else None
    if not isinstance(doc, dict) or doc.get('esquema') != 1 or not isinstance(paquetes, list):
        raise SalidaError('los textos no traen el formato esperado (esquema 1, lista «paquetes»)')
    if len(paquetes) > MAX_POR_CORRIDA:
        raise SalidaError('más de %d paquetes en una corrida' % MAX_POR_CORRIDA)
    out, vistos = [], set()
    for p in paquetes:
        if (not isinstance(p, dict) or not ID.match(str(p.get('id') or '')) or p['id'] in vistos
                or not SELLO.match(str(p.get('sello') or '')) or not isinstance(p.get('texto'), str)):
            raise SalidaError('un paquete viene sin id, sello o texto válidos')
        vistos.add(p['id'])
        notas = p.get('revision') or []
        if not isinstance(notas, list) or len(notas) > 8 or not all(isinstance(n, str) for n in notas):
            raise SalidaError('la revisión de un paquete no es una lista corta de textos')
        out.append({'id': p['id'], 'sello': p['sello'], 'texto': p['texto'],
                    'revision': [limpiar(n)[:300] for n in notas if n.strip()]})
    return out


def _nombre_drive(titulo):
    t = re.sub(r'\s+', ' ', ''.join(c for c in str(titulo) if c.isprintable() and c not in '/\\')).strip()
    return t[:120] or 'Pieza'


_CREADAS = {}                                         # carpetas hechas en esta corrida: Drive tarda en listarlas


def carpeta_del_paquete(drive, raiz, titulo):
    """La carpeta de la pieza dentro de «listas para publicar»: la que ya exista, o la siguiente
    del orden. Nunca hay dos carpetas para la misma pieza."""
    clave = _sin_acentos(titulo)
    hijos = [(str(h.get('name') or ''), h.get('id')) for h in drive.listar(raiz)
             if h.get('mimeType') == 'application/vnd.google-apps.folder']
    mayor = 0
    for nombre, fid in hijos + list(_CREADAS.get(raiz, {}).items()):
        m = re.match(r'^(\d+) · (.+)$', nombre)
        if m:
            mayor = max(mayor, int(m.group(1)))
            if _sin_acentos(m.group(2)) == clave:
                return fid, nombre
    nombre = '%d · %s' % (mayor + 1, titulo)
    fid = drive.asegurar_carpeta(raiz, nombre)
    _CREADAS.setdefault(raiz, {})[nombre] = fid
    return fid, nombre


def documento(fila, copy, revision, carpeta, fecha):
    """El documento que acompaña a las imágenes: lo abre quien publica y copia."""
    e = html.escape
    parrafos = lambda t: ''.join('<p>%s</p>' % (e(r) or '&nbsp;') for r in t.split('\n'))
    partes = [
        '<h2>%s · %s de %d %s</h2>' % (e(fila['pieza']), e(fila['formato'].lower()), len(fila['laminas']),
                                        'imagen' if len(fila['laminas']) == 1 else 'imágenes'),
        '<p>Orden: como están en esta carpeta, de la 01 en adelante. Publicar es tu clic.</p>',
        '<p><i>Este documento lo escribe la Sala al empacar (%s). Si quieres otro texto, cámbialo en '
        'la Sala antes de copiarlo.</i></p>' % e(fecha),
        '<h3>Instagram · texto</h3>', parrafos(copy['instagram']),
        '<h3>Instagram · primer comentario</h3>', '<p>%s</p>' % e(copy['comentario']),
        '<h3>Facebook · texto</h3>', parrafos(copy['facebook'])]
    if revision:
        partes += ['<h3>Antes de publicar, mira esto</h3>', '<ul>%s</ul>' % ''.join('<li>%s</li>' % e(n) for n in revision)]
    if fila.get('nota_formato'):
        partes.append('<p><i>%s.</i></p>' % e(fila['nota_formato'][0].upper() + fila['nota_formato'][1:]))
    partes += ['<h3>Origen</h3>',
               '<p>%s</p>' % e(' · '.join('L%d%s' % (l['n'], (' toma %d' % l['toma']) if l['toma'] else '')
                                          for l in fila['laminas'])),
               '<p>Tarjeta de la Sala: %s · carpeta: %s</p>' % (e(fila['id']), e(carpeta))]
    return '<html><body>%s</body></html>' % ''.join(partes)


def construir(drive, fila, copy, revision, reglas, fecha):
    """Sube a Drive lo que falte del paquete y devuelve su ficha. Repetirlo no duplica nada."""
    raiz_id = _regla(reglas, 'drive_raiz')
    if not raiz_id:
        raise SalidaError('falta drive_raiz en REGLAS; sin Drive no hay paquete')
    titulo = _nombre_drive(fila['pieza'])
    raiz = drive.ruta_carpetas(raiz_id, CARPETA)
    carpeta, nombre_carpeta = carpeta_del_paquete(drive, raiz, titulo)
    presentes = {h.get('name'): h for h in drive.listar(carpeta)}
    imagenes, subidas = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for k, lam in enumerate(fila['laminas'], 1):
            datos = traer_imagen(lam)
            ext = 'png' if datos.startswith(b'\x89PNG') else 'jpg' if datos.startswith(b'\xff\xd8') else 'webp'
            nombre = '%02d.%s' % (k, ext)
            ya = presentes.get(nombre)
            if ya and ya.get('md5Checksum') == hashlib.md5(datos).hexdigest():
                fid = ya['id']                            # idéntica = no se sube otra vez
            else:
                ruta = os.path.join(tmp, nombre)
                with open(ruta, 'wb') as f:
                    f.write(datos)
                fid = drive.subir(ruta, carpeta, nombre)
                subidas += 1
            imagenes.append({'n': lam['n'], 'src': lam['ruta'], 'archivo': nombre, 'drive': fid,
                             'toma': lam['toma'], 'dice': lam['dice']})
    doc = drive.subir_documento('COPY · ' + titulo, documento(fila, copy, revision, nombre_carpeta, fecha), carpeta)
    sobran = sorted(n for n in presentes if re.match(r'^\d\d\.(png|jpg|webp)$', str(n))
                    and n not in {i['archivo'] for i in imagenes})
    orden = re.match(r'^(\d+) · ', nombre_carpeta)
    return {'carpeta': nombre_carpeta, 'carpeta_id': carpeta, 'orden': int(orden.group(1)) if orden else 0,
            'url': 'https://drive.google.com/drive/folders/' + carpeta,
            'doc': doc, 'doc_url': 'https://docs.google.com/document/d/%s/edit' % doc,
            'imagenes': imagenes, 'formato': fila['formato'], 'nota_formato': fila.get('nota_formato') or '',
            'id': fila['id'], 'slug': fila['slug'], 'sello': fila['sello'], 'hecho': fecha,
            'subidas': subidas, 'sobran': sobran}


def _hito(exp, hito):
    """Agrega un hito sin repetirlo (misma `_k`) y sin tocar los que ya estaban."""
    hitos = [h for h in exp.get('hitos') or [] if isinstance(h, dict)]
    if not any(h.get('_k') == hito['_k'] for h in hitos):
        hitos.append(hito)
    exp['hitos'] = hitos


def expediente_con_paquete(previo, fila, paquete, copy, revision, fecha, corrida):
    """El expediente de la pieza con su paquete. Conserva TODO lo que ya decía (historia, reglas,
    versiones, las palabras de los editores): sólo agrega."""
    exp = json.loads(json.dumps(previo)) if isinstance(previo, dict) else {}
    exp.update({
        'pieza': fila['pieza'], 'estado': 'lista', 'portada': fila['laminas'][0]['ruta'],
        'paquete': {k: v for k, v in paquete.items() if k not in ('subidas', 'sobran')},
        'copy': dict(copy, revision=revision, por='consejo', hecho=fecha),
        'ahora': 'Lista para publicar: %d %s y su texto están en Drive. Falta tu clic.' % (
            len(fila['laminas']), 'imagen' if len(fila['laminas']) == 1 else 'imágenes')})
    _hito(exp, {'_k': [fecha, 'paquete', fila['sello']], 'fecha': fecha, 'quien': 'yo',
                'que': 'Paquete listo para publicar',
                'hecho': '%d %s en orden y el texto, en YOD Editorial/%s/%s' % (
                    len(fila['laminas']), 'imagen' if len(fila['laminas']) == 1 else 'imágenes', CARPETA, paquete['carpeta']),
                'fuente': 'Estación de salida · corrida %s' % corrida})
    return exp


def doblar_publicadas(drive, dia, expedientes, reglas, fecha, ensayo=False):
    """Lo que un editor anotó como «ya la publiqué» se asienta en el expediente y su paquete se
    guarda en `_PUBLICADAS`. Devuelve (cuántas cerró, cuántas no pudo anotar)."""
    cerradas = fallas = 0
    for clave, f in filas_publicada(dia).items():
        nombre = next((n for n in expedientes if _sin_acentos(n) == clave), None)
        exp = expedientes.get(nombre) if nombre else None
        if not isinstance(exp, dict) or not isinstance(exp.get('paquete'), dict) or exp.get('estado') == 'publicada':
            continue                                    # sólo cierra lo que esta estación entregó
        cerradas += 1
        if ensayo:
            continue
        nuevo = json.loads(json.dumps(exp))
        liga = str(f.get('enlace') or '').strip()
        cuando = str(f.get('fecha') or fecha)[:10]
        nuevo.update({'estado': 'publicada', 'publicada_el': cuando,
                      'ahora': 'Publicada. Sus números llegan con la siguiente lectura de métricas.'})
        if re.match(r'^https://[^\s"<>]{4,300}$', liga):
            nuevo['post'] = liga
        try:
            det = json.loads(str(f.get('detalle') or ''))
            if isinstance(det, dict) and isinstance(det.get('texto_final'), str) and det['texto_final'].strip():
                nuevo.setdefault('copy', {})['publicado'] = limpiar(det['texto_final'])[:2200]
        except ValueError:
            pass
        _hito(nuevo, {'_k': [cuando, 'publicada'], 'fecha': cuando, 'quien': 'tu', 'que': 'Publicada',
                      'hecho': 'Anotada desde la Sala' + (' con su liga.' if nuevo.get('post') else '.'),
                      'fuente': 'Sheet · PRODUCCION'})
        paquete = nuevo['paquete']
        try:
            raiz_id = _regla(reglas, 'drive_raiz')
            if raiz_id and paquete.get('carpeta_id') and not paquete.get('guardado_en'):
                origen = drive.ruta_carpetas(raiz_id, CARPETA)
                destino = drive.ruta_carpetas(raiz_id, CARPETA_PUBLICADAS)
                drive.mover(paquete['carpeta_id'], origen, destino)
                paquete['guardado_en'] = CARPETA_PUBLICADAS
        except Exception as e:                           # noqa: BLE001 — Drive no detiene el registro
            sala.avisar('· aviso: el paquete publicado no se pudo mover de carpeta (%s)' % type(e).__name__)
        try:
            sala.post('expediente', pieza=nombre, expediente=nuevo)
        except sala.SalaError:
            cerradas -= 1
            fallas += 1
            sala.avisar('✗ una publicada no se pudo asentar; se reintenta en la próxima sesión')
            continue
        expedientes[nombre] = nuevo
    return cerradas, fallas


def empacar(crudo, ensayo=False):
    """Aplica los textos del jurado a las piezas completas. No decide, no publica."""
    sala.enmascarar_en_actions()
    paquetes = leer_paquetes(crudo)
    reglas, dia_p, dia, exp = leer_mesa()
    fecha, corrida = sala.hoy_hermosillo(), os.environ.get('GITHUB_RUN_ID', 'local')
    import sala_drive as drive
    cerradas, fallas = doblar_publicadas(drive, dia, exp, reglas, fecha, ensayo)
    if not activa(reglas):
        sala.avisar('Salida en pausa (REGLAS salida_activa = 0): no empaco. Publicadas asentadas: %d.' % cerradas)
        return 2 if fallas else 0
    filas = estado_de_piezas(dia_p, dia, reglas, exp, proyeccion=proyeccion_de_la_mesa())
    por_id = {f['id']: f for f in filas}
    hechos = ignorados = rechazados = 0
    for p in paquetes:
        fila = por_id.get(p['id'])
        if fila is None or fila['estado'] != 'completa':
            ignorados += 1
            sala.avisar('· ignorado: %s' % ('no es una pieza viva de la mesa' if fila is None else
                                           '%s está %s' % (fila['slug'], fila['estado'].replace('_', ' '))))
            continue
        if fila['sello'] != p['sello']:
            ignorados += 1
            sala.avisar('· ignorado: %s cambió desde que se escribió su texto' % fila['slug'])
            continue
        malas = revisar_texto(p['texto'], reglas)
        if malas:
            rechazados += 1
            sala.avisar('· texto regresado · %s · %s' % (fila['slug'], ', '.join(malas)))
            continue
        copy = componer(p['texto'], fila['slug'], fecha, reglas)
        if ensayo:
            hechos += 1
            sala.avisar('· ensayo · %s · empacaría %d imagen(es) con su texto' % (fila['slug'], len(fila['laminas'])))
            continue
        try:
            paquete = construir(drive, fila, copy, p['revision'], reglas, fecha)
            nuevo = expediente_con_paquete(exp.get(fila['pieza']), fila, paquete, copy, p['revision'], fecha, corrida)
            sala.post('expediente', pieza=fila['pieza'], expediente=nuevo)
            exp[fila['pieza']] = nuevo
            sala.post('produccion', fecha=fecha, pieza=fila['pieza'], estado='paquete listo',
                      detalle='%d imagen(es) y su texto · %s' % (len(fila['laminas']), paquete['carpeta']),
                      enlace=paquete['url'])
        except (SalidaError, sala.SalaError, drive.DriveError, OSError) as e:
            fallas += 1
            sala.avisar('✗ %s no quedó empacada: %s' % (fila['slug'], sala.redactar(str(e))[:160]))
            continue
        hechos += 1
        sala.avisar('✓ %s · %s · %d imagen(es) (%d subidas)%s' % (
            fila['slug'], paquete['carpeta'], len(fila['laminas']), paquete['subidas'],
            ' · sobran archivos viejos en la carpeta' if paquete['sobran'] else ''))
    sala.avisar('Salida%s · %d paquete(s) %s · %d texto(s) regresado(s) · %d ignorado(s) · %d falla(s) · %d publicada(s) asentada(s)'
                % (' (ensayo)' if ensayo else '', hechos, 'se harían' if ensayo else 'listos', rechazados, ignorados, fallas, cerradas))
    return 2 if fallas else 0


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        if modo == 'lista':
            sys.exit(lista())
        if modo == 'paquete':
            sys.exit(empacar(os.environ.get('SALIDA_PAQUETES', ''), ensayo=os.environ.get('SALIDA_ENSAYO') == '1'))
        raise SalidaError('modo desconocido: usa «lista» o «paquete»')
    except (SalidaError, sala.SalaError) as e:
        sala.avisar('✗ %s — «no contestó» nunca es «no hay nada»' % sala.redactar(str(e))[:300])
        sys.exit(2)
