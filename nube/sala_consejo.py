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


def _tira(pid):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'datos', 'tiras', pid + '.json')
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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


def motores_disponibles(reglas):
    pedidos = [m.strip() for m in _regla(reglas, 'consejo_motores', 'sol,opus').split(',') if m.strip()]
    if _hermes()[0]:
        return [m for m in pedidos if m in ('sol', 'opus')]
    hay = {'sol': bool(os.environ.get('OPENAI_API_KEY', '').strip()),
           'opus': bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())}
    return [m for m in pedidos if hay.get(m)]


def proveedor_de(motor, reglas):
    return _regla(reglas, 'consejo_proveedor_' + motor, {'sol': 'openai-codex', 'opus': 'anthropic'}[motor])


def modelo_de(motor, reglas):
    return _regla(reglas, 'consejo_modelo_' + motor, {'sol': 'gpt-6.1-sol', 'opus': 'claude-opus-5-5'}[motor])


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
        marcas, notas = [None] * carta['n'], [''] * carta['n']
        for i, r in res.items():
            marcas[i], notas[i] = r['marca'], r['nota']
        envio_id = 'consejo-%s-%s-%s' % (motor, fecha, hashlib.sha256(
            (pid + json.dumps(marcas) + datetime.datetime.utcnow().isoformat()).encode()).hexdigest()[:10])
        resumen = ', '.join('L%d %s (%d/%d)' % (i, r['marca'], r['a_favor'], len(votos)) for i, r in sorted(res.items()))
        if ensayo:
            sala.avisar('· ENSAYO %s [%s]: %s' % (pid, motor, resumen))
            continue
        # Un corte regresado lleva su «NO VA» a nivel carta, igual que lo escribe Alejandro: es lo
        # que `revision_video.firma` exige para rehacerlo. En láminas la nota va por lámina.
        nota_carta = ''
        if carta['p'].get('tipo') == 'eje' and carta['p'].get('video') and marcas == ['no']:
            nota_carta = 'NO VA — ' + notas[0]
        enviar_decision(fecha, envio_id, {pid: {'laminas': marcas, 'notas': notas, 'nota': nota_carta}})
        juzgadas += 1
        sala.avisar('· %s [%s]: %s' % (pid, motor, resumen))
        sello = sala.hoy_hermosillo() + ' ' + (datetime.datetime.utcnow() - datetime.timedelta(hours=7)).strftime('%H:%M:%S')
        corrida_id = os.environ.get('GITHUB_RUN_ID', 'local')
        filas = []
        for i, r in sorted(res.items()):
            for k, nombre, _ in JUECES:
                v = votos.get(k, {}).get(i)
                if v:
                    filas.append([sello, corrida_id, pid, i, carta['p'].get('tipo'), motor, modelo, nombre,
                                  v['voto'], v['nota'], '', '', envio_id, ''])
            filas.append([sello, corrida_id, pid, i, carta['p'].get('tipo'), motor, modelo, 'VEREDICTO',
                          '', r['nota'], '%d de %d%s' % (r['a_favor'], len(votos), ' · veto' if r['veto'] else ''),
                          r['marca'], envio_id, ''])
        if oido:
            filas.append([sello, corrida_id, pid, '', carta['p'].get('tipo'), 'oido', _regla(reglas, 'consejo_oido', ''),
                          'OÍDO', '', json.dumps(oido, ensure_ascii=False)[:1500], '', '', envio_id, ''])
        registrar(filas)
    sala.avisar('Roast Room · %d carta(s) autorizadas o regresadas en esta corrida.' % juzgadas)
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
        sys.exit(corrida(ensayo=(modo == 'ensayo')))
    except (sala.SalaError, ConsejoError) as e:
        sala.avisar('✗ Roast Room:', e)
        sys.exit(2)
