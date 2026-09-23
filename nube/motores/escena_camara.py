#!/usr/bin/env python3
"""camara: la escena gratis que siempre sale. Un movimiento lento de cámara (acercamiento
suave) sobre la lámina completa, con ffmpeg en el propio runner. Costo 0, sin cuota, sin GPU.

No sustituye a una animación real: es el BORRADOR que deja armar el corte completo hoy,
mientras wan_hf no contesta o no tiene modelo configurado. La evidencia dice `motor=camara`,
así que en la Sala se distingue de una escena animada de verdad.

Regla 100 (animar la lámina ENTERA): la lámina se ve completa, centrada sobre un fondo hecho
de ella misma desenfocada, nunca recortada a 9:16. El acercamiento se queda en 6 % para que
los bordes de la lámina no se pierdan.
"""

import pathlib
import subprocess
import tempfile

import sala_cliente as sala
from motores._comun import MotorError, traer_imagen

ANCHO, ALTO, FPS = 1080, 1920, 30
ZOOM_MAX = 1.06


def _segundos(reglas):
    try:
        return max(2.0, float(str((reglas or {}).get('escena_segundos') or 5)))
    except ValueError:
        return 5.0


def filtro(segundos):
    cuadros = int(round(segundos * FPS))
    paso = (ZOOM_MAX - 1) / max(cuadros, 1)
    return (
        '[0]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=40:4[fondo];'
        '[0]scale=%d:%d:force_original_aspect_ratio=decrease[frente];'
        '[fondo][frente]overlay=(W-w)/2:(H-h)/2,'
        "zoompan=z='min(1+%.6f*on,%.3f)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        ':s=%dx%d:fps=%d,format=yuv420p'
        % (ANCHO, ALTO, ANCHO, ALTO, ANCHO, ALTO, paso, ZOOM_MAX, ANCHO, ALTO, FPS))


def animar(imagen, destino, segundos):
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-i', str(imagen),
           '-filter_complex', filtro(segundos), '-t', '%.2f' % segundos,
           '-r', str(FPS), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
           '-movflags', '+faststart', str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists():
        raise MotorError('ffmpeg no pudo animar la lámina: %s' % (r.stderr or '')[-300:])
    return destino


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        traer_imagen(trabajo, cat, origen)
        return animar(origen, destino, _segundos(reglas))
