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


def _gemini(texto, reglas):
    clave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not clave:
        raise MotorError('falta GEMINI_API_KEY', intermitente=True)
    modelo = _regla(reglas, 'cerebro_modelo', 'gemini-2.5-flash-lite')
    url = ('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s'
           % (modelo, clave))
    r = _post_json(url, {'systemInstruction': {'parts': [{'text': INSTRUCCION}]},
                         'contents': [{'parts': [{'text': texto}]}]}, {}, 'Gemini')
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


def _openai(texto, reglas, cola):
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
                    'messages': [{'role': 'system', 'content': INSTRUCCION},
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

