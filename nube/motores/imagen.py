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
from motores.politica_imagen import vetada

ESPERA = 120

class CupoImagen(MotorError):
    """Los proveedores nuevos agotaron cupo: no gastar recetas en el resto del lote."""
    pass

MODELO_FLUX2 = '@cf/black-forest-labs/flux-2-klein-9b'
MODELO_GEMINI_PRO = 'gemini-3-pro-image'

def cloudflare_flux2(receta, reglas):
    """FLUX 2 Klein 9B: REST requiere multipart, no un JSON plano."""
    import requests
    cuenta = os.environ.get('CF_ACCOUNT_ID', '').strip()
    token = os.environ.get('CF_API_TOKEN', '').strip()
    if not cuenta or not token:
        raise MotorError('faltan CF_ACCOUNT_ID / CF_API_TOKEN', intermitente=True)
    url = 'https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s' % (cuenta, MODELO_FLUX2)
    try:
        r = requests.post(url, headers={'Authorization': 'Bearer ' + token},
                          files={k: (None, str(v)) for k, v in
                                 {'prompt': receta[:4000], 'width': 1024, 'height': 1280,
                                  'steps': 8}.items()}, timeout=ESPERA)
    except requests.RequestException as e:
        raise MotorError('Cloudflare FLUX2 no contestó: ' + sala.redactar(str(e)),
                         intermitente=True) from None
    if r.status_code != 200:
        raise MotorError('Cloudflare FLUX2 %s: %s' % (r.status_code, sala.redactar(r.text[:280])),
                         intermitente=r.status_code in (429, 500, 502, 503, 504))
    if 'json' not in r.headers.get('Content-Type', '').lower():
        return r.content, 'png' if 'png' in r.headers.get('Content-Type', '') else 'jpg'
    try:
        data = r.json()['result']['image']
        return base64.b64decode(data, validate=True), 'png'
    except (KeyError, TypeError, ValueError):
        raise MotorError('Cloudflare FLUX2 contestó sin imagen', intermitente=True) from None

def gemini_pro(receta, reglas):
    return gemini(receta, dict(reglas or {}, imagen_gemini_modelo=MODELO_GEMINI_PRO))

def modelo_de(motor, reglas=None):
    return {'openai_broker': 'gpt-image-1.5', 'cloudflare_flux2': MODELO_FLUX2, 'gemini_pro': MODELO_GEMINI_PRO,
            'cloudflare': '@cf/black-forest-labs/flux-1-schnell',
            'gemini': str((reglas or {}).get('imagen_gemini_modelo') or 'gemini-2.5-flash-image'),
            'pollinations': 'pollinations/flux', 'hf': 'black-forest-labs/FLUX.1-schnell',
            'cpu': 'segmind/tiny-sd'}.get(motor, motor)



def _pedir(url, cuerpo, cabeceras, quien, espera=ESPERA):
    pet = urllib.request.Request(url, data=json.dumps(cuerpo).encode('utf-8'),
                                 headers=dict({'Content-Type': 'application/json'}, **cabeceras),
                                 method='POST')
    try:
        with urllib.request.urlopen(pet, timeout=espera) as r:
            return r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        crudo = e.read().decode('utf-8', 'replace')
        raise MotorError('%s %s: %s' % (quien, e.code, sala.redactar(crudo[:200])),
                         intermitente=e.code in (429, 500, 502, 503, 504))
    except urllib.error.URLError as e:
        raise MotorError('%s no contestó: %s' % (quien, sala.redactar(str(e))), intermitente=True)


def openai_broker(receta, reglas):
    """GPT Image en el servidor propio: la clave OpenAI permanece allí."""
    import hashlib
    import hmac
    token = hmac.new(sala._clave().encode(), b'yod:sala:image-broker:v1', hashlib.sha256).hexdigest()
    url = 'https://yod-cloud-room.onrender.com/sala/image'
    request_id = str((reglas or {}).get('_imagen_request_id') or hashlib.sha256(receta.encode()).hexdigest())
    # Reconcilia un resultado confirmado antes de pedir otra generación.
    req = urllib.request.Request(url+'/result/'+request_id, headers={'Authorization': 'Bearer '+token})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.load(r)
    except urllib.error.HTTPError as e:
        raw = json.loads(e.read() or b'{}')
        if e.code not in (404,409) or raw.get('error') not in ('not_confirmed', 'not_found'):
            raise MotorError('GPT Image: '+str(raw.get('error') or e.code), intermitente=True) from None
        result = None
    except urllib.error.URLError:
        raise MotorError('GPT Image: recibo sin confirmar', intermitente=True) from None
    if result is None:
        raw, _ = _pedir(url, {'request_id':request_id,'prompt':receta},
                       {'Authorization':'Bearer '+token}, 'GPT Image', espera=240)
        result = json.loads(raw)
    if not result.get('ok') or result.get('model') != 'gpt-image-1.5':
        raise MotorError('GPT Image contestó sin imagen confirmada', intermitente=True)
    if isinstance(reglas, dict):
        reglas['_receta_proveedor_sha256'] = result.get('recipe_sha')
        reglas['_imagen_recibo_id'] = request_id
    return base64.b64decode(result['image'], validate=True), 'png'

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
    modelo = str((reglas or {}).get('imagen_gemini_modelo') or 'gemini-2.5-flash-image').strip()
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


def pollinations(receta, reglas):
    """Pollinations (FLUX), gratis y sin llave (28-sep: respaldo cuando Cloudflare agota su cuota
    diaria y Gemini no contesta). 4:5 como la lámina."""
    import random
    import urllib.parse
    url = ('https://image.pollinations.ai/prompt/%s?width=720&height=960&model=flux&nologo=true'
           '&private=true&seed=%d' % (urllib.parse.quote(receta[:1500]), random.randint(1, 10 ** 9)))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'sala-yod'}),
                                    timeout=ESPERA) as r:
            datos, tipo = r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        raise MotorError('Pollinations %s' % e.code, intermitente=True)
    except urllib.error.URLError as e:
        raise MotorError('Pollinations no contestó: %s' % sala.redactar(str(e)), intermitente=True)
    if 'image' not in tipo or len(datos) < 5000:
        raise MotorError('Pollinations contestó sin imagen (%s)' % tipo, intermitente=True)
    # El pedido720×960 fue verificado con el proveedor;1080×1440 respondió402.
    # Se conserva el recorte a4:5 antes de componer al tamaño de la casa.
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(datos)).convert('RGB')
        w, h = im.size
        corte = max(0, h - int(round(w * 1350 / 1080)))
        im = im.crop((0, 0, w, h - max(corte, int(h * 0.06))))
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=92)
        return buf.getvalue(), 'jpg'
    except Exception:  # noqa: BLE001 — sin PIL se entrega tal cual
        return datos, ('png' if 'png' in tipo else 'jpg')


def hf(receta, reglas):
    """FLUX.1-schnell en la inferencia de HuggingFace con HF_TOKEN (créditos gratis de la cuenta)."""
    token = os.environ.get('HF_TOKEN', '').strip()
    if not token:
        raise MotorError('falta HF_TOKEN', intermitente=True)
    url = 'https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell'
    datos, tipo = _pedir(url, {'inputs': receta[:1500], 'parameters': {'width': 1024, 'height': 1280}},
                         {'Authorization': 'Bearer ' + token, 'Accept': 'image/jpeg'}, 'HF FLUX')
    if 'image' not in (tipo or '') and len(datos) < 5000:
        raise MotorError('HF FLUX contestó sin imagen', intermitente=True)
    return datos, 'jpg'


def cpu(receta, reglas):
    from motores.imagen_cpu import generar as generar_cpu
    return generar_cpu(receta, reglas)


MOTORES = {'openai_broker': openai_broker, 'cloudflare_flux2': cloudflare_flux2, 'gemini_pro': gemini_pro,
           'cloudflare': cloudflare, 'gemini': gemini, 'pollinations': pollinations, 'hf': hf, 'cpu': cpu}


SIN_LETRAS = ('. Photorealistic editorial photograph, natural light. Absolutely no text, '
              'no letters, no words, no captions, no signs, no logos, no watermark.')


def generar(receta, reglas):
    """Devuelve (bytes, extension, motor, avisos). Intermitente si ninguno pudo."""
    from contenido_reglas import ContenidoVetado, exigir
    try:
        exigir(receta, reglas, 'receta de imagen')
    except ContenidoVetado as e:
        raise MotorError(str(e)) from e
    receta = receta.rstrip('. ') + SIN_LETRAS
    orden = [m.strip() for m in str((reglas or {}).get('imagen_motores')
                                    or 'cloudflare_flux2,gemini_pro').split(',') if m.strip() in MOTORES]
    # Veto de Dirección: ni el orden explícito ni el respaldo heredado lo reactivan.
    orden = [m for m in orden if not vetada({'motor': m})]
    avisos = []
    sin_cupo = False
    for nombre in orden:
        try:
            datos, ext = MOTORES[nombre](receta, reglas)
            return datos, ext, nombre, avisos
        except MotorError as e:
            avisos.append(str(e))
            sin_cupo = sin_cupo or bool(__import__('re').search(r'\b429\b|daily free allocation|exceeded.*quota', str(e), __import__('re').I))
    error = CupoImagen if sin_cupo else MotorError
    raise error('ningún motor de imagen pudo: %s' % (' · '.join(avisos) or 'ninguno encendido'),
                     intermitente=True)
