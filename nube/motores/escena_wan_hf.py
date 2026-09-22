#!/usr/bin/env python3
"""wan_hf: el motor de escena de la hoja MOTORES real (`etapa=escena`, `orden=1`, «nube
gratis, intermitente; se intenta primero»). Anima UNA lámina a partir de su imagen (Drive) y
su descripción de escena (`ve`, en la tira).

**Éste es el menos verificado de los tres motores nuevos.** `sala_drive.py` y `voz_gemini.py`
se probaron contra Google de verdad (endpoints reales, aunque con clave falsa); Kokoro se
introspeccionó desde el paquete real instalado. La política de red del entorno donde se
escribió esto bloquea huggingface.co por completo (`connect_rejected`, confirmado con curl),
así que este archivo NO se pudo probar contra la API real de HuggingFace, ni siquiera para
ver la forma de un error. Se construyó contra la convención documentada de la Inference API
(`Authorization: Bearer <token>`, error JSON `{"error": "..."}`, o el binario crudo si no es
JSON) — pero es lectura, no comprobación.

Por lo mismo, **no se adivina un modelo de HuggingFace concreto**: inventar un id de modelo
que nadie confirmó que sirve para esto sería peor que no tener el motor. Vive en la REGLA
`escena_wan_hf_modelo` (vacía de fábrica a propósito); sin ella, el trabajo se queda
`pendiente` — nunca intenta una llamada a ciegas.
"""

import json
import os
import pathlib
import tempfile
import urllib.error
import urllib.request

import sala_catalogo as catalogo
import sala_cliente as sala
import sala_drive as drive
from motores._comun import MotorError

ESPERA = 120                                        # una animación tarda; el tope real lo
                                                      # pone el workflow (nube_tope_minutos)


def _token():
    t = os.environ.get('HF_TOKEN', '').strip()
    if not t:
        raise MotorError('falta HF_TOKEN (secret de Actions)', intermitente=True)
    return t


def _modelo(reglas):
    m = str((reglas or {}).get('escena_wan_hf_modelo') or '').strip()
    if not m:
        raise MotorError(
            'falta la REGLA escena_wan_hf_modelo (el id del modelo en HuggingFace). No se '
            'adivina uno: siémbrala con accion:regla una vez que Alejandro confirme cuál '
            'usar.', intermitente=True)
    return m


def _pedir(modelo, imagen_bytes, prompt):
    url = 'https://api-inference.huggingface.co/models/%s' % modelo
    pet = urllib.request.Request(
        url, data=imagen_bytes, method='POST',
        headers={'Authorization': 'Bearer ' + _token(),
                 'Content-Type': 'application/octet-stream',
                 'X-Wait-For-Model': 'true',
                 'X-Prompt': prompt})
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA) as r:
            return r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        crudo = e.read()
        try:
            err = json.loads(crudo.decode('utf-8', 'replace'))
            mensaje = err.get('error', crudo[:200])
        except ValueError:
            mensaje = crudo[:200]
        # 503 = el modelo se está cargando (frío) o está ocupado: intermitente, por diseño
        # de la hoja MOTORES («intermitente; se intenta primero»). 429 = cuota del momento.
        raise MotorError('wan_hf (HuggingFace) %s: %s' % (e.code, sala.redactar(str(mensaje))),
                         intermitente=(e.code in (503, 429)))
    except urllib.error.URLError as e:
        raise MotorError('wan_hf no contestó: %s' % sala.redactar(str(e)), intermitente=True)


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    modelo = _modelo(reglas)                          # falla rápido si no está configurado

    ev = trabajo.get('evidencia') or {}
    src = str(ev.get('src') or '')
    d = catalogo.drive_de(src, cat) if src else None
    if not d or not d.get('original'):
        raise MotorError('sin id de Drive para la lámina %s de %s — el catálogo no la '
                         'conoce todavía (accion:catalogar)' % (item, familia),
                         intermitente=True)

    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        drive.bajar(d['original'], origen)
        prompt = str(ev.get('ve') or ev.get('descripcion') or '').strip()
        cuerpo, tipo = _pedir(modelo, origen.read_bytes(), prompt)

    if 'json' in tipo.lower():
        raise MotorError('wan_hf devolvió JSON en vez de video: %s' % cuerpo[:200].decode('utf-8', 'replace'))

    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cuerpo)
    return destino
