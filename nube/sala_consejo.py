#!/usr/bin/env python3
"""Roast Room — el consejo que autoriza la mesa de la Sala (7-nov-2026).

Por qué existe: la Sala se atoraba esperando a Alejandro. El 7-nov él decidió que «quienes
den la autorización va a ser el roast room», en vivo desde ese día, con su veto y el de Sayri
por encima. Este módulo es ese consejo: lee la mesa, junta a seis jueces y firma lo que
deciden como «Roast Room».

Los seis jueces (elección de Alejandro, 7-nov):
  · Alex Hormozi ........ oferta y conversión al Plan de Potencial Personalizado
  · Chris Do ............ marca, diseño y claridad de la idea
  · Mark Zuckerberg ..... lo que premia el feed de Instagram/Facebook
  · Especialista ........ el oficio de la etapa (director de arte o editor de video)
  · Alejandro virtual ... sus candados al pie de la letra; su «no» por candado de veto, veta
  · Sayri virtual ....... sus candados y su ojo de diseñadora

Motores (7-nov: «Sol u Opus, lo que esté disponible, en competencia»): cada carta se le
asigna AL AZAR a uno de los motores disponibles (`consejo_motores` en REGLAS) y los seis
jueces de esa carta piensan con ese motor. El motor viaja en el `envio_id`, así el marcador
puede medir después cuál acierta más (cuántas veces Alejandro o Sayri lo contradicen).

Las cuatro reglas que gobiernan este archivo:

  · El consejo NO es el agente. Decide con su propia llave (`SALA_CLAVE_CONSEJO`, rol
    `consejo` en el GAS) y firma «Roast Room». La llave del agente jamás decide: eso sigue
    siendo INVIOLABLE 3 y `verificar.py` lo comprueba con un `ast`.
  · El veto humano manda. El GAS da prioridad a la marca de Alejandro o de Sayri sobre la del
    consejo en la misma lámina; aquí, además, nunca se juzga una lámina que un humano ya marcó.
  · Publicar no es de nadie aquí. El consejo autoriza cartas de la mesa; publicar sigue siendo
    sólo el clic de Alejandro.
  · «No contestó» nunca es «aprobado». Si faltan jueces, si el material no baja o si los
    motores fallan, el consejo se abstiene y la carta se queda para los humanos.
"""

import base64
import concurrent.futures
import datetime
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sala_cliente as sala                          # noqa: E402

NOMBRE = 'Roast Room'
PAGES = 'https://yodesarrollomx.github.io/sala-edicion/'
ESPERA_MOTOR = 150
MAX_IMAGEN = 8 * 1024 * 1024
MAX_VIDEO = 400 * 1024 * 1024
MAX_INLINE_GEMINI = 18 * 1024 * 1024
LLAMADAS_POR_CARTA = 7                                 # seis jueces + el oído de los cortes

JUECES = (
    ('alejandro', 'Alejandro virtual',
     'Eres Alejandro, director de YoDesarrollo, en versión virtual. Juzgas con SUS candados, '
     'escritos con sus propias palabras. Si la pieza rompe un candado de tipo veto, votas «no» '
     'y lo citas por su id. No inventas reglas que él no haya dicho. Eres exigente: si no se '
     'entiende a la primera o no engancha, no va.'),
    ('hormozi', 'Hormozi',
     'Juzgas con la lente de Alex Hormozi: gancho en el primer segundo, ecuación de valor '
     '(resultado soñado × probabilidad ÷ tiempo × esfuerzo), una sola llamada a la acción hacia '
     'el Plan de Potencial Personalizado, demostrar antes que prometer, nada vago.'),
    ('chris_do', 'Chris Do',
     'Juzgas con la lente de Chris Do: la idea se entiende en un vistazo, jerarquía visual '
     'clara, tipografía legible, coherencia de marca YoDesarrollo, posicionamiento premium y '
     'que imagen y texto digan exactamente lo mismo.'),
    ('zuckerberg', 'Zuckerberg',
     'Juzgas con la lente de Mark Zuckerberg sobre el feed de Instagram y Facebook: ¿detiene el '
     'scroll?, ¿retiene hasta el final?, ¿es original y no reciclado?, ¿la guardarían o se la '
     'mandarían a alguien?, ¿es nativa del formato vertical?'),
    ('especialista', 'Especialista',
     None),                                          # se arma según la etapa (ver _especialista)
    ('sayri', 'Sayri virtual',
     'Eres Sayri, diseñadora y editora de la Sala, en versión virtual. Aplicas sus candados y '
     'tu ojo de diseño: que el entorno y las personas se vean como dice el texto, buena luz, '
     'composición limpia. Tu historial de decisiones es corto: no inventes gustos suyos.'),
)

ORDEN_NOTAS = ('alejandro', 'especialista', 'hormozi', 'chris_do', 'sayri', 'zuckerberg')


class ConsejoError(RuntimeError):
    pass


# ── llaves y transporte ────────────────────────────────────────────────────────────────────

def _clave_consejo():
    k = os.environ.get('SALA_CLAVE_CONSEJO', '').strip()
    if not k:
        raise ConsejoError('falta SALA_CLAVE_CONSEJO (secret de Actions con la llave del Roast Room)')
    return k


def _leer_como_consejo(recurso, **params):
    q = {'recurso': recurso, 'clave': _clave_consejo()}
    q.update({k: v for k, v in params.items() if v is not None})
    url = sala._exec_url() + '?' + urllib.parse.urlencode(q)
    return sala._pedir(url, None, 'GET ?recurso=' + recurso, espera=sala.ESPERA_SHEET,
                       intentos=2, solo_curl=True)


def _escribir_como_consejo(cuerpo, donde):
    return sala._pedir(sala._exec_url(), json.dumps(cuerpo), donde, espera=sala.ESPERA_SHEET)


def enviar_decision(fecha, envio_id, propuestas):
    """El único lugar del repo que decide. Firma con la llave del consejo, nunca con la del
    agente; `verificar.py` lo exige así."""
    cuerpo = {'accion': 'decidir', 'clave': _clave_consejo(), 'fecha': fecha,
              'envio_id': envio_id, 'propuestas': propuestas, 'nota_general': ''}
    r = _escribir_como_consejo(cuerpo, 'POST decidir (Roast Room)')
    if not isinstance(r, dict) or not r.get('ok'):
        raise ConsejoError('el GAS no confirmó la decisión del consejo: %s' % sala.redactar(str(r)[:200]))
    return r


def registrar(filas):
    """Bitácora del consejo en la pestaña CONSEJO. Si falla, se avisa y se sigue: la decisión ya
    quedó en DECISIONES, que es lo que manda."""
    if not filas:
        return
    try:
        _escribir_como_consejo({'accion': 'consejo_registro', 'clave': _clave_consejo(), 'filas': filas},
                               'POST consejo_registro')
    except Exception as e:                           # noqa: BLE001
        sala.avisar('⚠ no se pudo escribir la pestaña CONSEJO:', e)


# ── reglas, candados y mesa ────────────────────────────────────────────────────────────────

def _regla(reglas, nombre, defecto):
    v = str((reglas or {}).get(nombre, '') or '').strip()
    return v or defecto


def leer_reglas():
    r = sala.get('reglas')
    reglas = r.get('reglas') or {}
    return {k: (v.get('valor') if isinstance(v, dict) else v) for k, v in reglas.items()}


def leer_candados():
    r = _leer_como_consejo('candados')
    filas = r.get('candados') if isinstance(r, dict) else None
    if not isinstance(filas, list) or not filas:
        raise ConsejoError('el GAS no entregó candados; sin candados el consejo no juzga')
    out = []
    for f in filas:
        if not isinstance(f, dict) or str(f.get('activo', '1')).strip() in ('0', 'false', 'FALSE', ''):
            continue
        cid, texto = str(f.get('id') or '').strip(), str(f.get('candado') or '').strip()
        if cid and texto:
            out.append({'id': cid, 'de': str(f.get('de') or ''), 'candado': texto,
                        'tipo': str(f.get('tipo') or 'criterio').strip().lower(),
                        'aplica': str(f.get('aplica') or 'todo')})
    if not out:
        raise ConsejoError('CANDADOS vino vacío')
    return out


def _n_items(p):
    if p.get('tipo') == 'eje':
        op = p.get('opciones')
        return len(op) if isinstance(op, list) else len((op or {}).get('candidatas') or [])
    return len(p.get('laminas') or [])


def cartas_pendientes(dia):
    """Cartas de la mesa con al menos una lámina que nadie ha marcado. Una carta que el consejo
    ya firmó no se vuelve a juzgar (si un humano la contradice, manda el humano)."""
    dec = ((dia or {}).get('decisiones') or {}).get('propuestas') or {}
    out = []
    for p in (dia or {}).get('propuestas') or []:
        pid, tipo = str(p.get('id') or ''), str(p.get('tipo') or 'laminas')
        if not pid or tipo not in ('laminas', 'eje'):
            continue
        n = _n_items(p)
        if not n:
            continue
        f = dec.get(pid) or {}
        firmas = f.get('firmas') or []
        if any(isinstance(x, dict) and x.get('quien') == NOMBRE for g in firmas for x in (g or [])):
            continue
        abiertas = []
        for i in range(n):
            g = firmas[i] if i < len(firmas) else []
            marcada = any(isinstance(x, dict) and x.get('marca') in ('si', 'no') for x in (g or []))
            if not marcada and (f.get('laminas') or [None] * n)[i:i + 1] in ([None], [], ['']):
                abiertas.append(i)
        if abiertas:
            out.append({'p': p, 'n': n, 'abiertas': abiertas, 'notas_previas': f.get('notas') or []})
    return out


# ── material: lo que los jueces ven y oyen ─────────────────────────────────────────────────

def _bajar(url, tope):
    pet = urllib.request.Request(url, headers={'User-Agent': 'sala-roast-room'})
    with urllib.request.urlopen(pet, timeout=60) as r:
        datos = r.read(tope + 1)
    if len(datos) > tope:
        raise ConsejoError('archivo demasiado grande: %s' % url[:80])
    return datos


_MEDIOS = None


def _url_imagen(ruta):
    global _MEDIOS
    if _MEDIOS is None:
        try:
            m = json.loads(_bajar(PAGES + 'datos/medios-publicos.json', 3 * 1024 * 1024))
            _MEDIOS = {k: v.get('url') for k, v in (m.get('entries') or {}).items() if isinstance(v, dict)}
        except Exception:                            # noqa: BLE001 — sin manifiesto, Pages directo
            _MEDIOS = {}
    if re.match(r'^https?://', str(ruta)):
        return str(ruta)
    return _MEDIOS.get(ruta) or (PAGES + str(ruta).lstrip('/'))


def _jpg_b64(datos):
    return base64.b64encode(datos).decode('ascii')


_TIRAS = {}


def _tira(pid):
    """La tira de una carta. Desde mediados de octubre las tiras nuevas ya no se guardan en main:
    viajan en el snapshot público y se leen de Pages. Primero el checkout, luego Pages."""
    pid = str(pid)
    if pid in _TIRAS:
        return _TIRAS[pid]
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'datos', 'tiras', pid + '.json')
    tira = None
    try:
        with open(p, encoding='utf-8') as f:
            tira = json.load(f)
    except (OSError, ValueError):
        if re.match(r'^[A-Za-z0-9._-]{1,200}$', pid):
            try:
                tira = json.loads(_bajar(PAGES + 'datos/tiras/' + pid + '.json', 2 * 1024 * 1024))
            except Exception:                        # noqa: BLE001 — sin tira, quien llama decide
                tira = None
    _TIRAS[pid] = tira if isinstance(tira, dict) else None
    return _TIRAS[pid]


# ── las tomas: aprobar una lámina es aprobar UNA imagen ────────────────────────────────────
# El contrato de producción (`sala_produccion.resolver_tira`) no acepta un «sí» sobre una lámina
# con tomas si su nota no dice cuál: `[toma elegida: k]`, lo mismo que escribe la Sala al tocar
# «Ésta». Un «sí» del consejo sin esa marca tumbaba la corrida entera del montador.

def _ruta(x):
    return str((x.get('src') if isinstance(x, dict) else x) or '')


def laminas_de_carta(p, tira):
    """La lámina de la tira que corresponde a cada posición de la carta (None si no aparece)."""
    tira = tira or {}
    mapa = tira.get('mapa') or {str(k + 1): n for k, n in enumerate(tira.get('decidir') or [])}
    por_n = {str(l.get('n')): l for l in tira.get('laminas') or [] if isinstance(l, dict)}
    return [por_n.get(str(mapa.get(str(i + 1), i + 1))) for i in range(len(p.get('laminas') or []))]


def tomas_de(lam):
    return [c for c in (lam or {}).get('candidatas') or [] if isinstance(c, dict)]


def toma_de_portada(lam, ruta):
    """En base 1, cuál de las tomas es la imagen que la carta enseña. 0 si la lámina no trae
    tomas (no hace falta marca); None si trae tomas y ninguna es la que se juzgó."""
    tomas = tomas_de(lam)
    if not tomas:
        return 0
    for k, c in enumerate(tomas):
        if ruta and ruta in (str(c.get('src') or ''), str(c.get('original') or '')):
            return k + 1
    return None


def sellar_tomas(p, res, elegidas=None):
    """Pone `[toma elegida: k]` en la nota de cada «sí» sobre una lámina con tomas. `elegidas`
    ({posición: k}) es la toma que el jurado votó; sin ella vale la que la carta enseña, que es la
    única que vieron. Devuelve False si algún «sí» no se puede acreditar: entonces no se firma."""
    if p.get('tipo') != 'laminas' or not any(r['marca'] == 'si' for r in res.values()):
        return True
    tira = _tira(p.get('id'))
    if not tira:
        return False
    lams = laminas_de_carta(p, tira)
    rutas = [_ruta(x) for x in p.get('laminas') or []]
    for i, r in res.items():
        if r['marca'] != 'si':
            continue
        lam = lams[i] if i < len(lams) else None
        if lam is None:
            return False
        tomas = tomas_de(lam)
        if not tomas:
            continue
        if elegidas is not None:
            try:
                k = int(elegidas.get(i, elegidas.get(str(i))))
            except (TypeError, ValueError):
                return False
        else:
            k = toma_de_portada(lam, rutas[i] if i < len(rutas) else '')
        if not k or not 0 < k <= len(tomas):
            return False
        r['nota'] = '[toma elegida: %d]' % k
    return True


def _id_drive(url):
    m = re.search(r'/file/d/([A-Za-z0-9_-]{10,})', str(url or '')) or re.search(r'[?&]id=([A-Za-z0-9_-]{10,})', str(url or ''))
    return m.group(1) if m else None


def _ffmpeg(*args):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y'] + list(args),
                       capture_output=True, timeout=300)
    if r.returncode:
        raise ConsejoError('ffmpeg falló: %s' % r.stderr.decode('utf-8', 'replace')[-200:])


def _duracion(ruta):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                        'default=nw=1:nk=1', ruta], capture_output=True, timeout=60)
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        raise ConsejoError('no se pudo medir la duración del corte')


def _oido(video, reglas):
    """Gemini ve y oye el corte completo (gratis) y entrega un informe técnico al jurado.
    Los jueces no oyen; sin este informe no se aprueba un corte."""
    clave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not clave:
        raise ConsejoError('sin GEMINI_API_KEY no hay quien escuche el corte')
    ligero = video + '.ligero.mp4'
    _ffmpeg('-i', video, '-vf', 'scale=360:-2', '-r', '12', '-c:v', 'libx264', '-b:v', '280k',
            '-c:a', 'aac', '-b:a', '64k', ligero)
    datos = open(ligero, 'rb').read()
    if len(datos) > MAX_INLINE_GEMINI:
        raise ConsejoError('el corte ligero sigue siendo muy pesado para el oído')
    instruccion = (
        'Eres el oído técnico de un consejo editorial. Mira y escucha el video completo y responde '
        'SÓLO JSON con estas llaves: video_real (bool: hay movimiento real filmado o generado, no '
        'fotos fijas con zoom, paneo o parallax), fotos_animadas (bool), voz_natural (1 a 5), '
        'voz_robotica (bool), sincronia_ok (bool: la voz entra junto con su imagen), '
        'ruido_fondo (bool), musica_fondo (bool), lugares_mencionados (lista de ciudades, estados o '
        'países que se oyen o se leen), transcripcion (texto completo de la voz), '
        'observaciones (máx. 400 caracteres, en español, concretas).')
    modelos = []
    for m in (_regla(reglas, 'consejo_oido', 'gemini-flash-latest'), 'gemini-flash-latest', 'gemini-3.6-flash'):
        if m not in modelos:
            modelos.append(m)
    ultimo = None
    for modelo in modelos:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s' % (modelo, clave)
        cuerpo = {'contents': [{'parts': [{'inline_data': {'mime_type': 'video/mp4', 'data': _jpg_b64(datos)}},
                                          {'text': instruccion}]}],
                  'generationConfig': {'responseMimeType': 'application/json'}}
        try:
            r = _post(url, cuerpo, {}, 'Oído ' + modelo)
            texto = ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts'] if not p.get('thought'))
            return modelo, _json_de(texto)
        except Exception as e:                       # noqa: BLE001
            ultimo = e
    raise ConsejoError('el oído no contestó: %s' % sala.redactar(str(ultimo)[:200]))


def material(carta, reglas, tmp):
    """Lo que el jurado ve: imágenes en base64 y, para los cortes, cuadros + informe del oído."""
    p = carta['p']
    imagenes, texto, oido = [], [], None
    if p.get('tipo') == 'laminas':
        for i, ruta in enumerate(p.get('laminas') or []):
            datos = _bajar(_url_imagen(ruta), MAX_IMAGEN)
            imagenes.append(('Lámina %d' % i, datos))
    else:
        op = p.get('opciones')
        cands = op if isinstance(op, list) else (op or {}).get('candidatas') or []
        porque = '' if isinstance(op, list) else str((op or {}).get('porque') or '')
        if porque:
            texto.append('Lo que se pide revisar: ' + porque)
        for i, c in enumerate(cands):
            c = c if isinstance(c, dict) else {'titulo': str(c)}
            texto.append('Opción %d · %s · %s' % (i, c.get('titulo') or '', c.get('texto') or c.get('dice') or ''))
            if c.get('src'):
                try:
                    imagenes.append(('Opción %d' % i, _bajar(_url_imagen(c['src']), MAX_IMAGEN)))
                except Exception:                    # noqa: BLE001
                    pass
        fid = _id_drive(p.get('video'))
        if fid:
            import sala_drive
            video = os.path.join(tmp, 'corte.mp4')
            sala_drive.bajar(fid, video)
            if os.path.getsize(video) > MAX_VIDEO:
                raise ConsejoError('el corte pesa demasiado para revisarlo')
            dur = _duracion(video)
            for k in range(6):
                cuadro = os.path.join(tmp, 'cuadro%d.jpg' % k)
                _ffmpeg('-ss', '%.2f' % (dur * (k + 0.5) / 6), '-i', video, '-frames:v', '1',
                        '-vf', 'scale=432:-2', cuadro)
                imagenes.append(('Cuadro %d de 6 (segundo %.1f)' % (k + 1, dur * (k + 0.5) / 6), open(cuadro, 'rb').read()))
            modelo, oido = _oido(video, reglas)
            texto.append('Duración del corte: %.1f s.' % dur)
            texto.append('Informe del oído (%s, vio y escuchó el corte completo): %s'
                         % (modelo, json.dumps(oido, ensure_ascii=False)[:3000]))
        elif p.get('video'):
            raise ConsejoError('el corte no está en Drive; el consejo no lo puede ver')
    tira = _tira(str(p.get('id')))
    if tira:
        if tira.get('promesa'):
            texto.append('Promesa de la pieza: ' + str(tira['promesa']))
        for lam in (tira.get('laminas') or [])[:12]:
            if isinstance(lam, dict):
                texto.append('Guion L%s · dice: %s · se ve: %s' % (lam.get('n'), lam.get('dice') or '', lam.get('ve') or ''))
    return imagenes, texto, oido


# ── motores ────────────────────────────────────────────────────────────────────────────────

def _post(url, cuerpo, cabeceras, quien):
    pet = urllib.request.Request(url, data=json.dumps(cuerpo).encode('utf-8'),
                                 headers=dict({'Content-Type': 'application/json'}, **cabeceras), method='POST')
    try:
        # Por Hermes cada juez es una corrida completa del agente: se le da más tiempo.
        with urllib.request.urlopen(pet, timeout=ESPERA_MOTOR * (3 if _hermes()[0] else 1)) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        crudo = e.read().decode('utf-8', 'replace')
        raise ConsejoError('%s %s: %s' % (quien, e.code, sala.redactar(crudo[:240])))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise ConsejoError('%s no contestó: %s' % (quien, sala.redactar(str(e)[:200])))


def _json_de(texto):
    t = str(texto or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if not m:
            raise ConsejoError('el juez no contestó JSON')
        return json.loads(m.group(0))


def _hermes():
    """7-nov (Alejandro): «¿esto no lo pudiera hacer Hermes a través de mi suscripción?». Si hay
    HERMES_API_URL, Sol y Opus se piden a la API local de Hermes (en la Chromebook), que cobra contra
    sus suscripciones y no contra créditos de API. Hermes recibe imágenes en base64 y honra
    `provider` + `model` en cada petición."""
    url = os.environ.get('HERMES_API_URL', '').strip().rstrip('/')
    clave = os.environ.get('HERMES_API_KEY', '').strip()
    return (url, clave) if url and clave else (None, None)


MOTOR_NUBE = 'claude'                                  # el consejo de nube (tarea programada), ver más abajo


def motores_pedidos(reglas):
    return [m.strip() for m in _regla(reglas, 'consejo_motores', 'sol,opus').split(',') if m.strip()]


def motores_disponibles(reglas):
    pedidos = motores_pedidos(reglas)
    if _hermes()[0]:
        return [m for m in pedidos if m in ('sol', 'opus')]
    hay = {'sol': bool(os.environ.get('OPENAI_API_KEY', '').strip()),
           'opus': bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())}
    return [m for m in pedidos if hay.get(m)]


def proveedor_de(motor, reglas):
    return _regla(reglas, 'consejo_proveedor_' + motor, {'sol': 'openai-codex', 'opus': 'anthropic'}[motor])


def modelo_de(motor, reglas):
    return _regla(reglas, 'consejo_modelo_' + motor, {'sol': 'gpt-6.1-sol', 'opus': 'claude-opus-5-5'}[motor])


FAMILIA = {'sol': ('gpt', 'sol', 'codex'), 'opus': ('claude', 'opus')}


def llamar(motor, modelo, sistema, texto, imagenes, reglas=None):
    url, clave = _hermes()
    if url:
        contenido = [{'type': 'text', 'text': texto}]
        for rotulo, datos in imagenes:
            contenido.append({'type': 'text', 'text': rotulo + ':'})
            contenido.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (_mime(datos), _jpg_b64(datos))}})
        r = _post(url + '/v1/chat/completions',
                  {'model': modelo, 'provider': proveedor_de(motor, reglas), 'stream': False,
                   'messages': [{'role': 'system', 'content': sistema + (
                       ' Contesta sólo con el JSON pedido. No uses herramientas, no abras archivos ni '
                       'navegues: todo lo que necesitas está en este mensaje.')},
                                {'role': 'user', 'content': contenido}]},
                  {'Authorization': 'Bearer ' + clave}, 'Hermes %s %s' % (motor, modelo))
        # Si el perfil no tiene la cuenta de ese motor, Hermes puede contestar con otro modelo y
        # dar 200 igual (7-nov, Chromebook). Ese voto no se apunta al motor pedido: el marcador
        # Sol contra Opus dejaría de decir la verdad. Sin voto, la carta se abstiene.
        devuelto = str((r or {}).get('model') or '').lower()
        if devuelto and not any(f in devuelto for f in FAMILIA[motor]):
            raise ConsejoError('Hermes contestó con %s en vez de %s' % (devuelto, motor))
        try:
            return _json_de(r['choices'][0]['message']['content'])
        except (KeyError, IndexError, TypeError):
            raise ConsejoError('Hermes contestó sin mensaje')
    if motor == 'sol':
        contenido = [{'type': 'input_text', 'text': texto}]
        for rotulo, datos in imagenes:
            contenido.append({'type': 'input_text', 'text': rotulo + ':'})
            contenido.append({'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + _jpg_b64(datos)})
        esquema = {'type': 'object', 'additionalProperties': False, 'required': ['piezas'], 'properties': {
            'piezas': {'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False, 'required': ['i', 'voto', 'candados', 'nota'],
                'properties': {'i': {'type': 'integer'}, 'voto': {'type': 'string', 'enum': ['si', 'no']},
                               'candados': {'type': 'array', 'items': {'type': 'string'}},
                               'nota': {'type': 'string'}}}}}}
        r = _post('https://api.openai.com/v1/responses',
                  {'model': modelo, 'instructions': sistema, 'max_output_tokens': 4000,
                   'reasoning': {'effort': 'low'}, 'store': False,
                   'text': {'format': {'type': 'json_schema', 'name': 'votos_roast_room', 'strict': True, 'schema': esquema}},
                   'input': [{'role': 'user', 'content': contenido}]},
                  {'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'].strip()}, 'Sol ' + modelo)
        salida = r.get('output_text') or ''.join(
            c.get('text', '') for o in (r.get('output') or []) if o.get('type') == 'message'
            for c in (o.get('content') or []) if c.get('type') == 'output_text')
        return _json_de(salida)
    if motor == 'opus':
        contenido = []
        for rotulo, datos in imagenes:
            contenido.append({'type': 'text', 'text': rotulo + ':'})
            contenido.append({'type': 'image', 'source': {'type': 'base64', 'media_type': _mime(datos), 'data': _jpg_b64(datos)}})
        contenido.append({'type': 'text', 'text': texto})
        r = _post('https://api.anthropic.com/v1/messages',
                  {'model': modelo, 'max_tokens': 3000, 'system': sistema,
                   'messages': [{'role': 'user', 'content': contenido}]},
                  {'x-api-key': os.environ['ANTHROPIC_API_KEY'].strip(), 'anthropic-version': '2023-06-01'},
                  'Opus ' + modelo)
        return _json_de(''.join(c.get('text', '') for c in (r.get('content') or []) if c.get('type') == 'text'))
    raise ConsejoError('motor desconocido: %s' % motor)


def _mime(datos):
    if datos[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if datos[:4] == b'RIFF' and datos[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'


# ── el jurado ──────────────────────────────────────────────────────────────────────────────

def _especialista(carta):
    if carta['p'].get('tipo') == 'laminas':
        return ('Eres el especialista de esta etapa: director de arte y redactor publicitario. Juzgas '
                'composición, luz, calidad de imagen, rostros bien resueltos, legibilidad y ortografía '
                'del texto de cada lámina y que la serie se vea como una sola campaña.')
    if carta['p'].get('video'):
        return ('Eres el especialista de esta etapa: editor de video y diseñador sonoro. Juzgas que sea '
                'video real y no fotos animadas, el ritmo, la sincronía de voz e imagen, que la voz sea '
                'natural y no robótica, el ruido y la música de fondo. Te apoyas en el informe del oído.')
    return ('Eres el especialista de esta etapa: guionista. Juzgas claridad, gancho, continuidad del '
            'relato y que cada opción se entienda a la primera.')


def _candados_texto(candados, juez):
    filtro = {'alejandro': 'Alejandro', 'sayri': 'Sayri'}.get(juez)
    lineas = []
    for c in candados:
        if filtro and c['de'] != filtro:
            continue
        lineas.append('%s [%s · aplica: %s] %s' % (c['id'], c['tipo'], c['aplica'], c['candado']))
    return '\n'.join(lineas)


def _pedido(carta, juez, candados, texto_material):
    p = carta['p']
    piezas = ', '.join(str(i) for i in carta['abiertas'])
    previas = [n for n in carta.get('notas_previas') or [] if n]
    partes = [
        'Sala de Edición de YoDesarrollo · Roast Room. Carta: «%s» (id %s, tipo %s).' % (p.get('titulo'), p.get('id'), p.get('tipo')),
        'Origen: %s' % (p.get('origen') or 'nueva'),
        'Objetivo de toda pieza: que el dueño de un terreno pida su Plan de Potencial Personalizado (PPP) de YoDesarrollo.',
        'Candados que se aplican (los de tipo veto no se negocian):\n' + _candados_texto(candados, juez),
    ]
    if previas:
        partes.append('Notas que ya dejaron los editores sobre esta pieza (la versión nueva debe atenderlas):\n- ' + '\n- '.join(previas[:8]))
    partes += texto_material
    partes.append(
        'Vota cada una de estas piezas: %s. Responde SÓLO un JSON así: {"piezas": [{"i": <número>, '
        '"voto": "si" o "no", "candados": [ids de candados que rompe, si alguno], "nota": "qué cambiar, '
        'concreto, en español, máx. 220 caracteres"}]}. Vota «si» sólo si la publicarías tal cual. '
        'Si algo no lo puedes comprobar con lo que ves, dilo en la nota.' % piezas)
    return '\n\n'.join(partes)


def juzgar(carta, motor, modelo, candados, imagenes, texto_material, reglas=None):
    """Seis llamadas independientes, en paralelo. Devuelve {juez: {i: voto}} sólo con los que
    contestaron bien."""
    def uno(j):
        clave, nombre, persona = j
        sistema = (persona or _especialista(carta)) + (
            ' Formas parte del Roast Room, un consejo de seis que autoriza o regresa piezas de '
            'contenido. Eres directo y exigente; no adulas. Escribes en español.')
        r = llamar(motor, modelo, sistema, _pedido(carta, clave, candados, texto_material), imagenes, reglas)
        votos = {}
        for v in (r.get('piezas') if isinstance(r, dict) else None) or []:
            try:
                i = int(v.get('i'))
            except (TypeError, ValueError):
                continue
            if i in carta['abiertas'] and v.get('voto') in ('si', 'no'):
                votos[i] = {'voto': v['voto'], 'nota': str(v.get('nota') or '')[:300],
                            'candados': [str(x) for x in (v.get('candados') or []) if isinstance(x, (str, int))][:8]}
        if set(votos) != set(carta['abiertas']):
            raise ConsejoError('%s no votó todas las piezas' % nombre)
        return clave, votos
    out, fallas = {}, []
    # En la Chromebook la memoria es corta: Hermes atiende pocos jueces a la vez (consejo_paralelo).
    paralelo = max(1, min(6, int(_regla(reglas, 'consejo_paralelo', '2' if _hermes()[0] else '6'))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=paralelo) as ex:
        for fut in [ex.submit(uno, j) for j in JUECES]:
            try:
                k, v = fut.result()
                out[k] = v
            except Exception as e:                   # noqa: BLE001
                fallas.append(sala.redactar(str(e))[:160])
    return out, fallas


def veredicto(votos, abiertas, candados, umbral, minimo=5):
    """Regla del consejo: aprueba con `umbral` votos a favor y sin veto de Alejandro virtual (un
    «no» suyo que cite un candado de tipo veto). Con menos de `minimo` jueces, se abstiene."""
    if len(votos) < minimo:
        return None
    vetos = {c['id'] for c in candados if c['tipo'] == 'veto' and c['de'] == 'Alejandro'}
    nombres = {k: n for k, n, _ in JUECES}
    res = {}
    for i in abiertas:
        si = sum(1 for j in votos.values() if j[i]['voto'] == 'si')
        a = votos.get('alejandro', {}).get(i)
        veto = bool(a and a['voto'] == 'no' and set(a['candados']) & vetos)
        marca = 'si' if si >= umbral and not veto else 'no'
        nota = ''
        if marca == 'no':
            partes = ['%d de %d a favor%s' % (si, len(votos), ' · veto de Alejandro virtual' if veto else '')]
            for k in ORDEN_NOTAS:
                v = votos.get(k, {}).get(i)
                if v and v['voto'] == 'no' and v['nota'] and len(partes) < 4:
                    partes.append('%s: %s' % (nombres[k], v['nota']))
            nota = ' · '.join(partes)[:700]
        res[i] = {'marca': marca, 'nota': nota, 'a_favor': si, 'veto': veto}
    return res


# ── la firma: el único camino por el que una decisión del consejo llega al Sheet ───────────

def _resumen(res, votos):
    return ', '.join('L%d %s (%d/%d)' % (i, r['marca'], r['a_favor'], len(votos)) for i, r in sorted(res.items()))


def firmar(carta, motor, modelo, votos, res, fecha, oido=None, reglas=None):
    """Manda la decisión con la llave del consejo y deja la bitácora en CONSEJO. Lo usan las dos
    rutas (Hermes y la tarea de nube); ninguna decide por otro lado. El registro público sólo
    lleva marcas y conteos: las notas viven en el Sheet."""
    p = carta['p']
    pid = str(p['id'])
    marcas, notas = [None] * carta['n'], [''] * carta['n']
    for i, r in res.items():
        marcas[i], notas[i] = r['marca'], r['nota']
    envio_id = 'consejo-%s-%s-%s' % (motor, fecha, hashlib.sha256(
        (pid + json.dumps(marcas) + datetime.datetime.utcnow().isoformat()).encode()).hexdigest()[:10])
    # Un corte regresado lleva su «NO VA» a nivel carta, igual que lo escribe Alejandro: es lo
    # que `revision_video.firma` exige para rehacerlo. En láminas la nota va por lámina.
    nota_carta = ''
    if p.get('tipo') == 'eje' and p.get('video') and marcas == ['no']:
        nota_carta = 'NO VA — ' + notas[0]
    enviar_decision(fecha, envio_id, {pid: {'laminas': marcas, 'notas': notas, 'nota': nota_carta}})
    sala.avisar('· %s [%s]: %s' % (pid, motor, _resumen(res, votos)))
    sello = sala.hoy_hermosillo() + ' ' + (datetime.datetime.utcnow() - datetime.timedelta(hours=7)).strftime('%H:%M:%S')
    corrida_id = os.environ.get('GITHUB_RUN_ID', 'local')
    filas = []
    for i, r in sorted(res.items()):
        for k, nombre, _ in JUECES:
            v = votos.get(k, {}).get(i)
            if v:
                filas.append([sello, corrida_id, pid, i, p.get('tipo'), motor, modelo, nombre,
                              v['voto'], v['nota'], '', '', envio_id, ''])
        filas.append([sello, corrida_id, pid, i, p.get('tipo'), motor, modelo, 'VEREDICTO',
                      '', r['nota'], '%d de %d%s' % (r['a_favor'], len(votos), ' · veto' if r['veto'] else ''),
                      r['marca'], envio_id, ''])
    if oido:
        filas.append([sello, corrida_id, pid, '', p.get('tipo'), 'oido', _regla(reglas, 'consejo_oido', ''),
                      'OÍDO', '', json.dumps(oido, ensure_ascii=False)[:1500], '', '', envio_id, ''])
    registrar(filas)
    return envio_id


# ── la corrida ─────────────────────────────────────────────────────────────────────────────

def _llamadas_hoy(fecha):
    try:
        filas = (sala.get('envios', f=fecha) or {}).get('filas') or []
    except Exception:                                # noqa: BLE001
        return 0
    envios = {str(f.get('envio')) for f in filas if str(f.get('envio', '')).startswith('consejo-')}
    return len(envios) * LLAMADAS_POR_CARTA


def corrida(ensayo=False):
    sala.enmascarar_en_actions()
    reglas = leer_reglas()
    if _regla(reglas, 'consejo_activo', '0') != '1':
        sala.avisar('Roast Room apagado (REGLAS consejo_activo≠1); no vota nadie.')
        return 0
    motores = motores_disponibles(reglas)
    if not motores:
        if set(motores_pedidos(reglas)) == {MOTOR_NUBE}:
            sala.avisar('Roast Room en reserva: REGLAS consejo_motores sólo pide «claude», el consejo de nube.')
            return 0
        sala.avisar('✗ ningún motor del consejo está disponible (HERMES_API_URL, o bien OPENAI_API_KEY / ANTHROPIC_API_KEY).')
        return 2
    candados = leer_candados()
    fecha = sala.hoy_hermosillo()
    dia = sala.get('dia', fresco='1')
    cartas = cartas_pendientes(dia)
    tope_cartas = int(_regla(reglas, 'consejo_cartas_por_corrida', '12'))
    tope_dia = int(_regla(reglas, 'consejo_tope_llamadas_dia', '240'))
    umbral = int(_regla(reglas, 'consejo_aprobar_con', '4'))
    usadas = _llamadas_hoy(fecha)
    sala.avisar('Roast Room · %d carta(s) por juzgar · motores: %s · llamadas hoy ≈%d de %d'
                % (len(cartas), ','.join(motores), usadas, tope_dia))
    juzgadas = 0
    for carta in cartas[:tope_cartas]:
        if usadas + LLAMADAS_POR_CARTA > tope_dia:
            sala.avisar('Tope diario de llamadas alcanzado; lo demás espera a mañana o a los editores.')
            break
        pid = str(carta['p']['id'])
        candidatos = list(motores)
        random.shuffle(candidatos)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                imagenes, texto_material, oido = material(carta, reglas, tmp)
            except Exception as e:                   # noqa: BLE001
                sala.avisar('· %s: me abstengo, no pude ver el material (%s)' % (pid, sala.redactar(str(e))[:160]))
                continue
            for motor in candidatos:
                modelo = modelo_de(motor, reglas)
                votos, fallas = juzgar(carta, motor, modelo, candados, imagenes, texto_material, reglas)
                usadas += LLAMADAS_POR_CARTA
                res = veredicto(votos, carta['abiertas'], candados, umbral)
                if res is not None:
                    break
                sala.avisar('· %s: con %s contestaron %d de 6 jueces (%s)' % (pid, motor, len(votos), '; '.join(fallas[:2])))
            else:
                sala.avisar('· %s: me abstengo, ningún motor reunió al jurado' % pid)
                continue
        # Por Hermes el jurado sólo vio la imagen que la carta enseña: ésa es la toma que aprueba.
        if not sellar_tomas(carta['p'], res):
            sala.avisar('· %s: me abstengo, no pude acreditar qué toma se aprobó' % pid)
            continue
        if ensayo:
            sala.avisar('· ENSAYO %s [%s]: %s' % (pid, motor, _resumen(res, votos)))
            continue
        firmar(carta, motor, modelo, votos, res, fecha, oido, reglas)
        juzgadas += 1
    sala.avisar('Roast Room · %d carta(s) autorizadas o regresadas en esta corrida.' % juzgadas)
    return 0


# ── el consejo de nube: la tarea programada juzga; aquí se valida y se firma ───────────────
# 9-nov-2026 · Sala corta. Dirección: «Al frente y en la nube», con su suscripción y sin créditos
# de API. Una tarea programada de Claude hace de jurado. Como ninguna llave pasa por un modelo,
# el trabajo se parte en dos y las dos mitades corren en Actions:
#
#   expediente  lee la mesa con las llaves de siempre y deja en Drive (YOD Editorial/_consejo/
#               expediente.txt) lo que hay por juzgar: cartas, tomas, guion y candados.
#   aplicar     recibe los votos de los seis jueces, los valida contra la mesa VIVA, calcula el
#               veredicto con la misma regla de siempre (`veredicto`) y firma con `firmar`.
#
# Los votos son dato, no instrucción: lo que no cuadra con la mesa se ignora y el registro
# público sólo lleva marcas y conteos.
CARPETA_DRIVE = '_consejo'
ARCHIVO_EXPEDIENTE = 'expediente.txt'
MAX_VEREDICTOS = 60000                                 # los inputs de workflow_dispatch topan en 65 535
ID_SEGURO = re.compile(r'^[A-Za-z0-9._-]{1,200}$')


def nube_encendida(reglas):
    return _regla(reglas, 'consejo_activo', '0') == '1' and MOTOR_NUBE in motores_pedidos(reglas)


def _opciones(p):
    op = p.get('opciones')
    return op if isinstance(op, list) else (op or {}).get('candidatas') or []


def sello_de_carta(carta, tira):
    """Ata un veredicto a la carta exacta que se juzgó: su id, lo que enseña y sus tomas. No es
    la identidad de una lámina (ésa es su catálogo, invariante 29): sólo dice «esto fue lo que
    vio el jurado»."""
    p = carta['p']
    if p.get('tipo') == 'laminas':
        cuerpo = [[_ruta(x)] + [str(c.get('src') or '') for c in tomas_de(lam)]
                  for x, lam in zip(p.get('laminas') or [], laminas_de_carta(p, tira))]
    else:
        cuerpo = [json.dumps(c, ensure_ascii=False, sort_keys=True) if isinstance(c, dict) else str(c)
                  for c in _opciones(p)]
    return hashlib.sha256(json.dumps([str(p.get('id')), p.get('tipo'), cuerpo],
                                     ensure_ascii=False).encode()).hexdigest()[:12]


def carta_para_expediente(carta):
    """Lo que el jurado necesita de una carta, o (None, motivo) si no se puede juzgar."""
    p = carta['p']
    pid = str(p['id'])
    base = {'id': pid, 'titulo': str(p.get('titulo') or ''), 'tipo': p.get('tipo'),
            'origen': str(p.get('origen') or ''), 'abiertas': list(carta['abiertas']),
            'notas_previas': [str(n)[:700] for n in carta.get('notas_previas') or [] if n][:8],
            'especialista': _especialista(carta)}
    tira = None
    if p.get('tipo') == 'laminas':
        tira = _tira(pid)
        if not tira:
            return None, 'sin tira publicada'
        lams = laminas_de_carta(p, tira)
        piezas = []
        for i, x in enumerate(p.get('laminas') or []):
            lam = lams[i]
            if lam is None:
                if i in carta['abiertas']:
                    return None, 'la tira no trae la lámina de la posición %d' % i
                lam = {}
            piezas.append({
                'i': i, 'n': lam.get('n'), 'abierta': i in carta['abiertas'],
                'dice': str(lam.get('dice') or ''), 've': str(lam.get('ve') or ''),
                'entiende': str(lam.get('entiende') or ''),
                'nota_previa': str(lam.get('nota_previa') or '')[:700],
                'url': _url_imagen(_ruta(x)),
                'tomas': [{'toma': k + 1, 'titulo': str(c.get('titulo') or ''),
                           'dice': str(c.get('dice') or lam.get('dice') or ''), 've': str(c.get('ve') or ''),
                           'porque': str(c.get('texto') or '')[:400],
                           'url': _url_imagen(str(c.get('src') or c.get('original') or ''))}
                          for k, c in enumerate(tomas_de(lam))]})
        guion = tira.get('guion')
        base.update({
            'pieza': str(tira.get('pieza') or ''), 'promesa': str(tira.get('promesa') or ''),
            'formato': str(tira.get('formato') or ''), 'nota_de_la_carta': str(tira.get('nota') or '')[:600],
            'piezas': piezas,
            'serie': [{'n': l.get('n'), 'dice': str(l.get('dice') or ''), 'estado': str(l.get('estado') or '')}
                      for l in tira.get('laminas') or [] if isinstance(l, dict)][:12],
            'guion': ([{'n': g.get('n'), 'dice': str(g.get('dice') or ''), 've': str(g.get('ve') or ''),
                        'entiende': str(g.get('entiende') or '')} for g in guion if isinstance(g, dict)][:12]
                      if isinstance(guion, list) else str(guion or '')[:3000])})
    else:
        op = p.get('opciones')
        base['porque'] = '' if isinstance(op, list) else str((op or {}).get('porque') or '')[:600]
        base['opciones'] = []
        for i, c in enumerate(_opciones(p)):
            c = c if isinstance(c, dict) else {'titulo': str(c)}
            base['opciones'].append({'i': i, 'abierta': i in carta['abiertas'], 'titulo': str(c.get('titulo') or ''),
                                     'texto': str(c.get('texto') or c.get('dice') or '')[:1500],
                                     'url': _url_imagen(c['src']) if c.get('src') else ''})
    base['sello'] = sello_de_carta(carta, tira)
    return base, ''


def _guardar_expediente(doc, reglas):
    import sala_drive
    raiz = _regla(reglas, 'drive_raiz', '')
    if not raiz:
        raise ConsejoError('falta drive_raiz en REGLAS; sin Drive el jurado de nube no recibe el expediente')
    try:
        carpeta = sala_drive.ruta_carpetas(raiz, CARPETA_DRIVE)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, ARCHIVO_EXPEDIENTE)
            with open(ruta, 'w', encoding='ascii') as f:   # ASCII puro: se lee igual desde cualquier conector
                json.dump(doc, f, ensure_ascii=True, indent=1)
            return sala_drive.subir(ruta, carpeta, ARCHIVO_EXPEDIENTE)
    except sala_drive.DriveError as e:
        raise ConsejoError('no se pudo dejar el expediente en Drive: %s' % sala.redactar(str(e))[:200])


def expediente():
    """Deja en Drive lo que el jurado de nube tiene que ver. No decide nada."""
    sala.enmascarar_en_actions()
    reglas = leer_reglas()
    doc = {'esquema': 1, 'generado': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'fecha': sala.hoy_hermosillo(), 'corrida': os.environ.get('GITHUB_RUN_ID', 'local'),
           'activo': nube_encendida(reglas), 'motor': MOTOR_NUBE,
           'reglas': {'aprobar_con': int(_regla(reglas, 'consejo_aprobar_con', '4')), 'jueces_minimos': 5},
           'jueces': [{'juez': k, 'nombre': n, 'lente': lente or 'ver «especialista» en cada carta'}
                      for k, n, lente in JUECES],
           'candados': [], 'cartas': [], 'omitidas': [], 'pendientes_en_mesa': 0}
    if doc['activo']:
        doc['candados'] = leer_candados()
        cartas = cartas_pendientes(sala.get('dia', fresco='1'))
        tope = max(1, int(_regla(reglas, 'consejo_nube_cartas', '5')))
        doc['pendientes_en_mesa'] = len(cartas)
        for carta in cartas:
            pid = str(carta['p']['id'])
            if carta['p'].get('video'):
                doc['omitidas'].append({'id': pid, 'motivo': 'corte de video: en pausa, lo ven los editores'})
            elif len(doc['cartas']) >= tope:
                doc['omitidas'].append({'id': pid, 'motivo': 'tope por sesión; entra en la siguiente'})
            else:
                c, motivo = carta_para_expediente(carta)
                if c is None:
                    doc['omitidas'].append({'id': pid, 'motivo': motivo})
                else:
                    doc['cartas'].append(c)
    else:
        sala.avisar('Consejo de nube apagado (REGLAS consejo_activo≠1 o consejo_motores sin «claude»).')
    archivo = _guardar_expediente(doc, reglas)
    sala.avisar('Expediente del consejo de nube · %d carta(s) para juzgar · %d omitida(s) · %d pendientes en la mesa · Drive %s/%s (%s)'
                % (len(doc['cartas']), len(doc['omitidas']), doc['pendientes_en_mesa'], CARPETA_DRIVE,
                   ARCHIVO_EXPEDIENTE, archivo))
    return 0


def leer_veredictos(crudo):
    """Valida la FORMA de lo que mandó el jurado de nube. Devuelve (modelo, cartas)."""
    crudo = str(crudo or '')
    if len(crudo) > MAX_VEREDICTOS:
        raise ConsejoError('los veredictos pesan más de lo que cabe en una sesión')
    try:
        d = json.loads(crudo)
    except ValueError:
        raise ConsejoError('los veredictos no son JSON')
    if not isinstance(d, dict) or d.get('esquema') != 1 or d.get('motor') != MOTOR_NUBE:
        raise ConsejoError('veredictos sin esquema 1 o de un motor que no es «claude»')
    cartas = d.get('cartas')
    if not isinstance(cartas, list) or len(cartas) > 20:
        raise ConsejoError('los veredictos no traen una lista de cartas (máx. 20)')
    for c in cartas:
        if not isinstance(c, dict) or not isinstance(c.get('id'), str) or not isinstance(c.get('votos'), dict):
            raise ConsejoError('carta mal formada en los veredictos')
    modelo = str(d.get('modelo') or '')
    return (modelo if re.match(r'^[A-Za-z0-9._\[\]-]{1,60}$', modelo) else 'sin-declarar'), cartas


def votos_validos(crudo, abiertas, conocidos):
    """{juez: {posición: voto}} sólo con los jueces que votaron TODAS las piezas abiertas, igual
    que `juzgar`. Un candado que no existe en CANDADOS se descarta: no puede vetar."""
    out = {}
    for clave, _, _ in JUECES:
        lista = (crudo or {}).get(clave)
        if not isinstance(lista, list):
            continue
        votos = {}
        for v in lista:
            if not isinstance(v, dict) or isinstance(v.get('i'), bool):
                continue
            try:
                i = int(v.get('i'))
            except (TypeError, ValueError):
                continue
            if i in abiertas and v.get('voto') in ('si', 'no'):
                votos[i] = {'voto': v['voto'], 'nota': str(v.get('nota') or '')[:300],
                            'candados': [str(x) for x in (v.get('candados') or [])
                                         if isinstance(x, (str, int)) and str(x) in conocidos][:8]}
        if set(votos) == set(abiertas):
            out[clave] = votos
    return out


def aplicar(crudo, ensayo=False):
    """Convierte los votos del jurado de nube en decisiones del consejo, o se abstiene."""
    sala.enmascarar_en_actions()
    reglas = leer_reglas()
    if not nube_encendida(reglas):
        sala.avisar('Consejo de nube apagado (REGLAS consejo_activo≠1 o consejo_motores sin «claude»); no se aplica nada.')
        return 0
    modelo, entrada = leer_veredictos(crudo)
    if not entrada:
        sala.avisar('Consejo de nube · sesión sin veredictos.')
        return 0
    candados = leer_candados()
    conocidos = {c['id'] for c in candados}
    fecha = sala.hoy_hermosillo()
    pendientes = {str(c['p']['id']): c for c in cartas_pendientes(sala.get('dia', fresco='1'))}
    umbral = int(_regla(reglas, 'consejo_aprobar_con', '4'))
    firmadas, vistas = 0, set()
    for v in entrada:
        pid = v['id']
        if pid in vistas:
            continue                                   # una carta, un veredicto
        vistas.add(pid)
        carta = pendientes.get(pid)
        if not carta:
            sala.avisar('· %s: ya no está pendiente en la mesa; se ignora'
                        % (pid if ID_SEGURO.match(pid) else '(id que no es de la mesa)'))
            continue
        p = carta['p']
        if p.get('video'):
            sala.avisar('· %s: es un corte de video; el consejo de nube no lo juzga' % pid)
            continue
        tira = _tira(pid) if p.get('tipo') == 'laminas' else None
        if p.get('tipo') == 'laminas' and not tira:
            sala.avisar('· %s: me abstengo, no encontré su tira' % pid)
            continue
        if sello_de_carta(carta, tira) != str(v.get('sello') or ''):
            sala.avisar('· %s: cambió desde el expediente; se juzga en la siguiente sesión' % pid)
            continue
        votos = votos_validos(v['votos'], carta['abiertas'], conocidos)
        res = veredicto(votos, carta['abiertas'], candados, umbral)
        if res is None:
            sala.avisar('· %s: me abstengo, sólo %d de 6 jueces votaron todas las piezas' % (pid, len(votos)))
            continue
        if not sellar_tomas(p, res, elegidas=v.get('tomas') if isinstance(v.get('tomas'), dict) else {}):
            sala.avisar('· %s: me abstengo, un «sí» no dice qué toma aprueba' % pid)
            continue
        if ensayo:
            sala.avisar('· ENSAYO %s [%s]: %s' % (pid, MOTOR_NUBE, _resumen(res, votos)))
            continue
        firmar(carta, MOTOR_NUBE, modelo, votos, res, fecha, None, reglas)
        firmadas += 1
    sala.avisar('Consejo de nube · %d carta(s) autorizadas o regresadas.' % firmadas)
    return 0


# ── el marcador Sol contra Opus ────────────────────────────────────────────────────────────

def marcador(dias=14):
    """Cuántas veces Alejandro o Sayri contradijeron al consejo, por motor. Lee DECISIONES vía
    `envios` (sólo lectura) y deja una fila MARCADOR en CONSEJO."""
    sala.enmascarar_en_actions()
    hoy = datetime.date.fromisoformat(sala.hoy_hermosillo())
    cuenta = {}
    for k in range(dias):
        f = (hoy - datetime.timedelta(days=k)).isoformat()
        try:
            filas = (sala.get('envios', f=f) or {}).get('filas') or []
        except Exception:                            # noqa: BLE001
            continue
        consejo, humanos = {}, {}
        for x in filas:
            if x.get('lamina') is None or x.get('marca') not in ('si', 'no'):
                continue
            llave = (x.get('prop'), x.get('lamina'))
            if str(x.get('envio', '')).startswith('consejo-'):
                consejo[llave] = (x['envio'].split('-')[1], x['marca'])
            elif x.get('quien') in ('editor', 'editor2'):
                humanos[llave] = x['marca']
        for llave, (motor, m) in consejo.items():
            c = cuenta.setdefault(motor, {'votadas': 0, 'revisadas_por_humano': 0, 'contradichas': 0})
            c['votadas'] += 1
            if llave in humanos:
                c['revisadas_por_humano'] += 1
                c['contradichas'] += int(humanos[llave] != m)
    sala.avisar('Marcador Roast Room (%d días): %s' % (dias, json.dumps(cuenta, ensure_ascii=False)))
    sello = sala.hoy_hermosillo()
    registrar([[sello, os.environ.get('GITHUB_RUN_ID', 'local'), '', '', '', m, '', 'MARCADOR', '',
                json.dumps(c, ensure_ascii=False), '', '', '', ''] for m, c in sorted(cuenta.items())])
    return 0


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else 'corrida'
    try:
        if modo == 'marcador':
            sys.exit(marcador())
        if modo == 'expediente':
            sys.exit(expediente())
        if modo == 'aplicar':
            sys.exit(aplicar(os.environ.get('CONSEJO_VEREDICTOS', ''),
                             ensayo=os.environ.get('CONSEJO_ENSAYO', '').strip().lower() in ('1', 'true', 'si')))
        if modo not in ('corrida', 'ensayo'):
            raise ConsejoError('modo desconocido: %s' % modo[:40])
        sys.exit(corrida(ensayo=(modo == 'ensayo')))
    except (sala.SalaError, ConsejoError) as e:
        sala.avisar('✗ Roast Room:', e)
        sys.exit(2)
