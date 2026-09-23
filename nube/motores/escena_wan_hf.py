#!/usr/bin/env python3
"""wan_hf: el motor de escena de la hoja MOTORES real (`etapa=escena`, `orden=1`, «nube
gratis, intermitente; se intenta primero»). Anima UNA lámina con Wan 2.2 en un Space ZeroGPU
gratis de HuggingFace, vía `gradio_client`.

**Comprobado el 23-sep-2026** (rama `claude/prueba-wan-hf`, corrida 35898229982): el Space
`zerogpu-aoti/wan2-2-fp8da-aoti-faster` expone `/generate_video` con `input_image, prompt,
steps, negative_prompt, duration_seconds, guidance_scale, guidance_scale_2, seed,
randomize_seed`; animó apodo L4 y L5 (~2 min cada una) con HF_TOKEN de cuenta gratis. La
cuota gratis es ~3.5 min de GPU al día → **2 escenas diarias**; la tercera contestó
«You have exceeded your free ZeroGPU quota … Try again in 23:55:41».

La versión anterior llamaba a `api-inference.huggingface.co/models/<id>`: esa API no sirve
Wan, por eso la REGLA `escena_wan_hf_modelo` se quedó vacía y todo caía a `camara`. Ahora
la REGLA guarda el/los **Space** a intentar, separados por coma; vacía = los comprobados.

Cuota agotada → `MotorError(intermitente=True, esperar=True)`: el trabajo se queda
`pendiente` para el día siguiente en vez de gastarse en la cámara de respaldo (Alejandro,
23-sep: la animación real es la que vale). La REGLA `escena_camara_si_cuota`=1 lo revierte.

Regla 100 (lámina ENTERA): la salida de Wan se asienta sobre 1080×1920 con un fondo de ella
misma desenfocada, igual que `camara`; nunca se recorta.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile

import sala_cliente as sala
from motores._comun import MotorError, traer_imagen

SPACES_DEFAULT = ['zerogpu-aoti/wan2-2-fp8da-aoti-faster']
ANCHO, ALTO = 1080, 1920
FIDELIDAD = ('Animate this exact image without changing its composition, text or colors. '
             'Slow, subtle cinematic motion; keep any title text perfectly static and legible. ')


def _spaces(reglas):
    m = str((reglas or {}).get('escena_wan_hf_modelo') or '').strip()
    return [s.strip() for s in m.split(',') if s.strip()] or SPACES_DEFAULT


def _segundos(reglas):
    try:
        return max(2, min(8, int(float(str((reglas or {}).get('escena_segundos') or 5)))))
    except ValueError:
        return 5


def _cliente(space):
    from gradio_client import Client
    token = os.environ.get('HF_TOKEN', '').strip() or None
    try:
        return Client(space, token=token, verbose=False)
    except TypeError:                                   # gradio_client viejo
        return Client(space, hf_token=token)


def _es_cuota(texto):
    t = texto.lower()
    return 'quota' in t or 'exceeded' in t or 'try again in' in t


def _animar(space, imagen, prompt, segundos):
    from gradio_client import handle_file
    c = _cliente(space)
    r = c.predict(api_name='/generate_video', input_image=handle_file(str(imagen)),
                  prompt=prompt, duration_seconds=segundos)
    video = r[0] if isinstance(r, (list, tuple)) else r
    if isinstance(video, dict):
        video = video.get('video') or video.get('path')
    if not video or not pathlib.Path(str(video)).is_file():
        raise MotorError('wan_hf (%s) no devolvió un video: %r' % (space, r), intermitente=True)
    return pathlib.Path(str(video))


def _asentar(crudo, destino):
    """La animación completa sobre 1080×1920, fondo de ella misma desenfocada (regla 100)."""
    f = ('[0]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=40:4[fondo];'
         '[0]scale=%d:%d:force_original_aspect_ratio=decrease[frente];'
         '[fondo][frente]overlay=(W-w)/2:(H-h)/2,format=yuv420p'
         % (ANCHO, ALTO, ANCHO, ALTO, ANCHO, ALTO))
    p = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(crudo), '-filter_complex', f,
                        '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                        str(destino)], capture_output=True, text=True)
    if p.returncode != 0:
        raise MotorError('ffmpeg no pudo asentar la escena de wan_hf: %s' % p.stderr[-300:])


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    destino.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        lam = traer_imagen(trabajo, cat, origen)
        prompt = FIDELIDAD + (lam['ve'] or lam['dice']).strip()
        errores = []
        for space in _spaces(reglas):
            try:
                crudo = _animar(space, origen, prompt, _segundos(reglas))
            except MotorError:
                raise
            except Exception as e:  # noqa: BLE001 — gradio_client lanza AppError, ValueError…
                texto = sala.redactar(str(e))
                if _es_cuota(texto):
                    err = MotorError('wan_hf: cuota gratis de ZeroGPU agotada hoy (%s)'
                                     % texto[:200], intermitente=True)
                    err.esperar = True
                    raise err
                errores.append('%s: %s' % (space, texto[:200]))
                continue
            copia = pathlib.Path(tmp) / 'crudo.mp4'
            shutil.copyfile(crudo, copia)
            _asentar(copia, destino)
            return destino
    raise MotorError('wan_hf no pudo con ningún Space: %s' % ' · '.join(errores),
                     intermitente=True)
