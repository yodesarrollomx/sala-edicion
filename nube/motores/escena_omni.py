#!/usr/bin/env python3
"""omni_flash: escena generativa con Gemini Omni Flash, por la API oficial de Gemini y la
misma `GEMINI_API_KEY` que ya usa la voz. Anima UNA lámina (imagen → video vertical).

**ES DE PAGO** (~0.07 USD por segundo en 720p; sin nivel gratuito: una llave sin facturación
es rechazada). Por eso nace APAGADO: sólo entra si Dirección pone la REGLA
`omni_flash_tope_dia` en un número mayor que cero (clips por día). Ese gobierno vive en
`sala_adaptativa.candidatos`, no aquí; este archivo sólo sabe producir.

Para qué sirve: Wan (gratis) sólo cubre voces de hasta 5 s; Omni cubre de 3 a 15 s, que es
el hueco donde hoy la Sala cae a la animación por código.

**Qué está comprobado en vivo** (corrida 42726461524 del 9-nov-2026, llave con prepago): texto
a video de 15 s con `response_format.duration`, y la respuesta con el video. **No comprobado:**
imagen a video (`image_to_video`), imágenes de referencia (`reference_to_video`, etiquetas
`<IMAGE_REF_N>` en el texto: personas, objetos y estilo) ni las dos juntas; salen de la guía
oficial, que ese día documentaba 1.1. La guía no ofrece referencia de voz ni de audio: la
voz de un personaje sólo se sostiene describiéndola igual en cada toma.
Si Google rechaza un campo, el error llega íntegro (tachado) a la evidencia del trabajo.

El audio que genera Omni se descarta: la voz de la Sala es la aprobada (Kokoro/Gemini TTS) y
la monta el corte. Regla 100 (lámina ENTERA): se asienta igual que Wan, sin recortar.
"""

import base64
import io
import json
import math
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.request

import sala_cliente as sala
from motores._comun import MotorError, traer_imagen
from motores.escena_wan_hf import FIDELIDAD, _asentar

BASE = 'https://generativelanguage.googleapis.com/v1beta/'
MODELO = 'gemini-omni-1.2-flash'
MIN_S, MAX_S = 3, 15
USD_POR_SEGUNDO = 0.07          # 720p, precio publicado el 5-nov-2026; sólo para la evidencia
ESPERA = 600                    # una generación tarda minutos
SILENCIO = ' No dialogue, no music, no sound effects.'


def duracion(segundos):
    """Segundos enteros que cubren la voz completa, dentro de lo que el modelo acepta."""
    return max(MIN_S, min(MAX_S, math.ceil(float(segundos))))


def peticion(jpg, prompt, segundos, modelo, referencias=None):
    """Cuatro formas de pedir un video:

    · sólo texto;
    · con `jpg`: esa imagen es el PRIMER cuadro y se anima (`image_to_video`);
    · con `referencias` (lista de JPEG): son imágenes de quién y qué sale, no cuadros. El texto
      las nombra <IMAGE_REF_0>, <IMAGE_REF_1>… en ese orden (`reference_to_video`);
    · con las dos: primero va el primer cuadro y después las referencias. Ahí no se declara
      tarea: el texto dice qué es cada imagen («[# Sources <FIRST_FRAME>@Image1]
      [# References <IMAGE_REF_0>@Image2]», como en la guía oficial).
    """
    cuerpo = {'model': modelo, 'input': prompt,
              'response_format': {'type': 'video', 'duration': '%ds' % segundos,
                                  'aspect_ratio': '9:16', 'resolution': '720p'}}
    referencias = list(referencias or [])
    imagenes = ([jpg] if jpg else []) + referencias
    if imagenes:
        cuerpo['input'] = [{'type': 'image', 'data': base64.b64encode(i).decode('ascii'), 'mime_type': 'image/jpeg'}
                           for i in imagenes] + [{'type': 'text', 'text': prompt}]
        if not (jpg and referencias):
            cuerpo['generation_config'] = {'video_config': {'task': 'image_to_video' if jpg else 'reference_to_video'}}
    return cuerpo


def generar(prompt, segundos, modelo=MODELO, jpg=None, referencias=None):
    """Los bytes del MP4 tal como lo entrega Omni, CON su audio."""
    resp = _terminar(llamar('POST', 'interactions',
                            peticion(jpg, prompt, duracion(segundos), modelo, referencias)))
    return extraer_video(resp, _bajar)


def llamar(metodo, ruta, cuerpo=None, crudo=False):
    clave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not clave:
        raise MotorError('falta GEMINI_API_KEY (secret de Actions)', intermitente=True)

    def limpio(texto):
        return sala.redactar(str(texto)).replace(clave, '«tachado»')[:300]

    # La llave va en cabecera, nunca en la URL: una URL acaba en logs y mensajes de error.
    pet = urllib.request.Request(
        BASE + ruta, data=None if cuerpo is None else json.dumps(cuerpo).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': clave}, method=metodo)
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA) as r:
            datos = r.read()
            return datos if crudo else json.loads(datos.decode('utf-8'))
    except urllib.error.HTTPError as e:
        texto = e.read().decode('utf-8', 'replace')
        try:
            err = json.loads(texto).get('error') or {}
        except ValueError:
            err = {}
        # La API nombra sus errores con texto («too_many_requests»); lo que clasifica es el HTTP.
        error = MotorError('omni_flash %s: %s' % (err.get('code') or e.code, limpio(err.get('message') or texto)),
                           intermitente=e.code in (429, 500, 502, 503))
        error.http = e.code
        error.esperar = e.code == 429            # cuota o saldo: pausa el motor, no es fallo técnico
        raise error
    except (urllib.error.URLError, TimeoutError) as e:
        raise MotorError('omni_flash no contestó: %s' % limpio(e), intermitente=True)
    except ValueError:
        raise MotorError('omni_flash contestó algo que no es JSON', intermitente=True)


def _videos(nodo):
    if isinstance(nodo, dict):
        if nodo.get('type') == 'video' and (nodo.get('data') or nodo.get('uri')):
            yield nodo
        for v in nodo.values():
            yield from _videos(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _videos(v)


def extraer_video(resp, bajar):
    """Los bytes del MP4: en línea (base64) o por `uri` de la Files API."""
    video = next(_videos(resp.get('steps') or resp), None)
    if not video:
        raise MotorError('omni_flash contestó sin video: %s' % sala.redactar(json.dumps(resp))[:300],
                         intermitente=True)
    return base64.b64decode(video['data']) if video.get('data') else bajar(video['uri'])


def _bajar(uri):
    return llamar('GET', '%s:download?alt=media' % uri.split('/v1beta/')[-1], crudo=True)


def _terminar(resp):
    """Si la interacción vuelve en curso, se consulta hasta que termine (o venza la espera)."""
    limite = time.time() + ESPERA
    while (not next(_videos(resp), None) and resp.get('id')
           and str(resp.get('status', '')).lower() in ('in_progress', 'queued', 'pending', 'running')):
        if time.time() > limite:
            raise MotorError('omni_flash no terminó a tiempo', intermitente=True)
        time.sleep(10)
        resp = llamar('GET', 'interactions/%s' % resp['id'])
    return resp


def producir(trabajo, reglas, cat, salida_dir, segundos):
    from PIL import Image
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    modelo = str((reglas or {}).get('escena_omni_modelo') or '').strip() or MODELO
    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        lam = traer_imagen(trabajo, cat, origen)
        jpg = io.BytesIO()
        Image.open(origen).convert('RGB').save(jpg, 'JPEG', quality=90)
        prompt = FIDELIDAD + (lam['ve'] or lam['dice']).strip() + SILENCIO
        crudo = pathlib.Path(tmp) / 'crudo.mp4'
        crudo.write_bytes(generar(prompt, segundos, modelo, jpg.getvalue()))
        _asentar(crudo, destino)
    return destino
