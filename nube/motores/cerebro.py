#!/usr/bin/env python3
"""El cerebro: texto que la nube necesita pensar (por ahora, la receta de una candidata nueva
cuando el editor dijo «no» a una lámina). Cascada de costo:

1. Gemini (`cerebro_modelo`, de fábrica gemini-2.5-flash-lite) — cuota gratis diaria.
2. OpenAI (`cerebro_respaldo_modelo`, de fábrica gpt-4o-mini) — de pago, SÓLO si Gemini no
   contestó, y con tope: `cerebro_pago_tope_dia` llamadas al día (de fábrica 30 ≈ centavos,
   muy por debajo de 1 USD). El conteo vive en la COLA (evidencia.cerebro), no en memoria.

Si ninguno contesta, se usa la receta sin reescribir: un prospecto nunca se queda sin salir
por falta de cerebro — sólo sale menos pulido, y la evidencia lo dice.
"""

import json
import os
import urllib.error
import urllib.request

import sala_cliente as sala
from motores._comun import MotorError

ESPERA = 60

INSTRUCCION = (
    'Eres director de arte de piezas publicitarias cortas de una desarrolladora inmobiliaria '
    'en Hermosillo, Sonora. Reescribe la receta de UNA ilustración para un generador de '
    'imágenes. Mantén el estilo de la receta base. Atiende la nota del editor al pie de la '
    'letra. Nada de texto dentro de la imagen, nada de cifras de dinero. Devuelve SOLO la '
    'receta, en inglés, en un párrafo de máximo 90 palabras.')


def _regla(reglas, nombre, defecto):
    v = str((reglas or {}).get(nombre) or '').strip()
    return v or defecto


def _post_json(url, cuerpo, cabeceras, quien):
    pet = urllib.request.Request(url, data=json.dumps(cuerpo).encode('utf-8'),
                                 headers=dict({'Content-Type': 'application/json'}, **cabeceras),
                                 method='POST')
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        crudo = e.read().decode('utf-8', 'replace')
        raise MotorError('%s %s: %s' % (quien, e.code, sala.redactar(crudo[:200])),
                         intermitente=e.code in (429, 500, 502, 503))
    except urllib.error.URLError as e:
        raise MotorError('%s no contestó: %s' % (quien, sala.redactar(str(e))), intermitente=True)


def _gemini(texto, reglas, instruccion=None):
    clave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not clave:
        raise MotorError('falta GEMINI_API_KEY', intermitente=True)
    # 23-sep: Google retiró gemini-2.5-flash-lite para cuentas nuevas (404 «no longer
    # available»). La REGLA manda, pero si su modelo ya no existe se prueba el siguiente.
    modelos = []
    for m in (_regla(reglas, 'cerebro_modelo', ''), 'gemini-3.5-flash-lite', 'gemini-3.5-flash'):
        if m and m not in modelos:
            modelos.append(m)
    ultimo = None
    for modelo in modelos:
        url = ('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s'
               % (modelo, clave))
        try:
            r = _post_json(url, {'systemInstruction': {'parts': [{'text': instruccion or INSTRUCCION}]},
                                 'contents': [{'parts': [{'text': texto}]}]}, {}, 'Gemini ' + modelo)
            break
        except MotorError as e:
            ultimo = e
            if ' 404' not in str(e) and ' 400' not in str(e):
                raise
    else:
        raise ultimo
    try:
        return ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts']).strip()
    except (KeyError, IndexError):
        raise MotorError('Gemini contestó sin texto', intermitente=True)


def _pagadas_hoy(cola):
    hoy = sala.hoy_hermosillo()
    n = 0
    for t in cola or []:
        ev = t.get('evidencia') or {}
        if ev.get('cerebro') == 'openai' and str(ev.get('fecha') or '').startswith(str(hoy)):
            n += 1
    return n


def _openai(texto, reglas, cola, instruccion=None):
    clave = os.environ.get('OPENAI_API_KEY', '').strip()
    if not clave:
        raise MotorError('sin OPENAI_API_KEY (respaldo de pago no configurado)', intermitente=True)
    tope = int(float(_regla(reglas, 'cerebro_pago_tope_dia', '30')))
    if _pagadas_hoy(cola) >= tope:
        raise MotorError('tope diario del respaldo de pago alcanzado (%d)' % tope,
                         intermitente=True)
    r = _post_json('https://api.openai.com/v1/chat/completions',
                   {'model': _regla(reglas, 'cerebro_respaldo_modelo', 'gpt-4o-mini'),
                    'max_tokens': 220,
                    'messages': [{'role': 'system', 'content': instruccion or INSTRUCCION},
                                 {'role': 'user', 'content': texto}]},
                   {'Authorization': 'Bearer ' + clave}, 'OpenAI')
    try:
        return r['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError):
        raise MotorError('OpenAI contestó sin texto', intermitente=True)


def receta(base, ve, dice, nota, reglas, cola, variante=1):
    """Devuelve (receta, cerebro_usado, avisos)."""
    pedido = ('RECETA BASE: %s\nLO QUE MUESTRA LA LÁMINA: %s\nLO QUE DICE: %s\n'
              'NOTA DEL EDITOR (motivo del rechazo): %s\nVARIANTE número %d: propón una '
              'composición distinta a las anteriores.'
              % (base or '(sin receta base)', ve or '-', dice or '-', nota or '(sin nota)', variante))
    avisos = []
    for nombre, fn in (('gemini', lambda: _gemini(pedido, reglas)),
                       ('openai', lambda: _openai(pedido, reglas, cola))):
        try:
            texto = fn()
            if texto:
                return texto, nombre, avisos
        except MotorError as e:
            avisos.append(str(e))
    crudo = ' '.join(x for x in (base, ve, nota) if x).strip()
    if not crudo:
        raise MotorError('ni cerebro ni receta base para esta lámina', intermitente=True)
    return crudo, 'sin-cerebro', avisos



INSTRUCCION_LAMINA = (
    'Eres director creativo de piezas cortas (carrusel de Instagram) de una desarrolladora '
    'inmobiliaria en Hermosillo, Sonora. El editor RECHAZÓ una lámina y dejó una nota. Rehazla '
    'obedeciendo la nota al pie de la letra. Reglas de la casa: el texto le habla al público en '
    'segunda persona y de preferencia es pregunta; una sola idea; máximo 14 palabras; nada de '
    'cifras de dinero, nada de «gratis», sin plazos ni garantías; áreas en m²; la pareja '
    'protagonista es de estatus medio-alto y ella 2-3 años más joven; la imagen tiene que '
    'sostener el texto (que se vea lo que dice). Si la nota NO pide cambiar el texto, deja el '
    'texto igual. Contesta SOLO un JSON: {"texto": "...", "receta": "...", "porque": "..."} '
    'donde receta es una descripción fotográfica en inglés de máximo 90 palabras, sin texto '
    'dentro de la imagen, y porque dice en una línea cómo atiende la nota.')


def _json_de(texto):
    import re
    m = re.search(r'\{.*\}', texto or '', re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def lamina(pieza, promesa, dice, ve, nota, vetadas, reglas, cola=None, variante=1, referencia=''):
    """Devuelve ({texto, receta, porque}, cerebro_usado, avisos). Sin cerebro: el texto se
    queda y la receta sale de lo que la lámina ya mostraba + la nota."""
    pedido = ('PIEZA: %s\nPROMESA DE LA PIEZA: %s\nTEXTO ACTUAL: %s\nLO QUE MOSTRABA: %s\n'
              'NOTA DEL EDITOR: %s\nPALABRAS VETADAS (nunca las uses): %s\n'
              'REFERENCIA VISUAL (mismos personajes, lugar y luz; descríbelos igual en la receta): %s\n'
              'VARIANTE %d: propón una composición distinta a las anteriores.'
              % (pieza, promesa or '-', dice or '-', ve or '-', nota or '(sin nota)',
                 ', '.join(vetadas) or '-', referencia or '-', variante))
    avisos = []
    for nombre, fn in (('gemini', lambda: _gemini(pedido, reglas, INSTRUCCION_LAMINA)),
                       ('openai', lambda: _openai(pedido, reglas, cola, INSTRUCCION_LAMINA))):
        try:
            d = _json_de(fn())
            if d and d.get('receta'):
                d['texto'] = str(d.get('texto') or dice).strip()
                return d, nombre, avisos
            avisos.append('%s contestó sin JSON útil' % nombre)
        except MotorError as e:
            avisos.append(str(e))
    # Sin cerebro NO se inventa receta: el 23-sep una receta cruda (la nota en español)
    # hizo que FLUX dibujara hojas con letras sin sentido. Mejor no producir que producir basura.
    raise MotorError('sin cerebro disponible (%s): la lámina espera a la próxima corrida'
                     % ' · '.join(avisos)[:300], intermitente=True)

