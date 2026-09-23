#!/usr/bin/env python3
"""Imagen en la nube, gratis primero. Cascada (la corta la REGLA `imagen_motores`, de fábrica
«cloudflare,gemini»):

- cloudflare: Workers AI · @cf/black-forest-labs/flux-1-schnell. Cuota diaria gratis de la
  cuenta de Cloudflare. Secrets CF_ACCOUNT_ID + CF_API_TOKEN.
- gemini: `imagen_gemini_modelo` (de fábrica gemini-2.5-flash-image) con GEMINI_API_KEY. Si
  la cuenta no tiene cuota gratis de imagen, contesta 429 y se trata como intermitente.

`mflux` sigue siendo de la Mac: aquí no existe.
"""

import base64
import json
import os
import urllib.error
import urllib.request

import sala_cliente as sala
from motores._comun import MotorError

ESPERA = 120


def _pedir(url, cuerpo, cabeceras, quien):
    pet = urllib.request.Request(url, data=json.dumps(cuerpo).encode('utf-8'),
                                 headers=dict({'Content-Type': 'application/json'}, **cabeceras),
                                 method='POST')
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA) as r:
            return r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        crudo = e.read().decode('utf-8', 'replace')
        raise MotorError('%s %s: %s' % (quien, e.code, sala.redactar(crudo[:200])),
                         intermitente=e.code in (429, 500, 502, 503, 504))
    except urllib.error.URLError as e:
        raise MotorError('%s no contestó: %s' % (quien, sala.redactar(str(e))), intermitente=True)


def cloudflare(receta, reglas):
    cuenta = os.environ.get('CF_ACCOUNT_ID', '').strip()
    token = os.environ.get('CF_API_TOKEN', '').strip()
    if not cuenta or not token:
        raise MotorError('faltan CF_ACCOUNT_ID / CF_API_TOKEN', intermitente=True)
    url = ('https://api.cloudflare.com/client/v4/accounts/%s/ai/run/'
           '@cf/black-forest-labs/flux-1-schnell' % cuenta)
    cuerpo, tipo = _pedir(url, {'prompt': receta[:2000], 'steps': 8},
                          {'Authorization': 'Bearer ' + token}, 'Cloudflare')
    if 'json' not in tipo.lower():
        return cuerpo, 'jpg'
    r = json.loads(cuerpo.decode('utf-8'))
    img = ((r.get('result') or {}).get('image')) if isinstance(r, dict) else None
    if not img:
        raise MotorError('Cloudflare contestó sin imagen: %s' % json.dumps(r)[:200])
    return base64.b64decode(img), 'jpg'


def gemini(receta, reglas):
    clave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not clave:
        raise MotorError('falta GEMINI_API_KEY', intermitente=True)
    modelo = str((reglas or {}).get('imagen_gemini_modelo') or 'gemini-3.5-flash-image').strip()
    url = ('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s'
           % (modelo, clave))
    cuerpo, _ = _pedir(url, {'contents': [{'parts': [{'text': receta}]}],
                             'generationConfig': {'responseModalities': ['IMAGE', 'TEXT']}},
                       {}, 'Gemini imagen')
    r = json.loads(cuerpo.decode('utf-8'))
    try:
        for p in r['candidates'][0]['content']['parts']:
            d = p.get('inlineData') or p.get('inline_data')
            if d and d.get('data'):
                ext = 'png' if 'png' in str(d.get('mimeType') or d.get('mime_type')) else 'jpg'
                return base64.b64decode(d['data']), ext
    except (KeyError, IndexError):
        pass
    raise MotorError('Gemini imagen contestó sin imagen', intermitente=True)


MOTORES = {'cloudflare': cloudflare, 'gemini': gemini}


SIN_LETRAS = ('. Photorealistic editorial photograph, natural light. Absolutely no text, '
              'no letters, no words, no captions, no signs, no logos, no watermark.')


def generar(receta, reglas):
    """Devuelve (bytes, extension, motor, avisos). Intermitente si ninguno pudo."""
    receta = receta.rstrip('. ') + SIN_LETRAS
    orden = [m.strip() for m in str((reglas or {}).get('imagen_motores')
                                    or 'cloudflare,gemini').split(',') if m.strip() in MOTORES]
    avisos = []
    for nombre in orden:
        try:
            datos, ext = MOTORES[nombre](receta, reglas)
            return datos, ext, nombre, avisos
        except MotorError as e:
            avisos.append(str(e))
    raise MotorError('ningún motor de imagen pudo: %s' % (' · '.join(avisos) or 'ninguno encendido'),
                     intermitente=True)
