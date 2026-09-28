#!/usr/bin/env python3
"""modal_ltx: animación de IA REAL con LTX-Video en Modal, por centavos (28-sep-2026).

Lo que hace, respetando que el texto es una CAPA aparte (Alejandro, 28-sep):
  1. Separa la lámina: `capa_texto` (la misma de parallax) detecta las letras y la franja
     oscura; la foto se limpia de texto con inpaint.
  2. Manda SOLO la foto limpia a LTX-Video en Modal (`nube/modal_ltx.py`, ya desplegado) con
     un prompt de movimiento sutil sacado de lo que la lámina «ve».
  3. Recibe el video animado, lo lleva al tamaño de la lámina y le pone ENCIMA la capa de texto
     original, fija y nítida, cuadro por cuadro.
  4. Asienta sobre 1080×1920 con fondo desenfocado (regla 100), igual que los otros motores.

Sin MODAL_TOKEN_ID / MODAL_TOKEN_SECRET (o sin la app desplegada) lanza MotorError
intermitente y la Sala sigue con parallax → cámara: nunca detiene la producción.
"""

import os
import pathlib
import subprocess
import tempfile

import sala_cliente as sala
from motores._comun import MotorError, traer_imagen

ANCHO, ALTO, FPS = 1080, 1920, 24
MOVIMIENTO = ('Cinematic, subtle natural motion: people breathe, blink and make small gestures, '
              'light shifts softly, gentle slow camera push-in. Keep the exact same people, faces, '
              'clothes, place and colors. ')


def disponible():
    return bool(os.environ.get('MODAL_TOKEN_ID') and os.environ.get('MODAL_TOKEN_SECRET'))


def _segundos(reglas):
    try:
        return max(2.0, min(8.0, float(str((reglas or {}).get('escena_segundos') or 5))))
    except ValueError:
        return 5.0


def animar(imagen, destino, segundos, que_se_ve=''):
    import cv2
    import numpy as np
    from motores.escena_parallax import capa_texto
    if not disponible():
        raise MotorError('modal_ltx: faltan MODAL_TOKEN_ID / MODAL_TOKEN_SECRET', intermitente=True)
    img = cv2.imread(str(imagen), cv2.IMREAD_COLOR)
    if img is None:
        raise MotorError('modal_ltx: no pude leer la lámina %s' % imagen)
    img = img[: img.shape[0] // 2 * 2, : img.shape[1] // 2 * 2]
    h, w = img.shape[:2]
    letras, capa = capa_texto(img)
    limpia = cv2.inpaint(img, letras, 7, cv2.INPAINT_TELEA)
    ok, png = cv2.imencode('.png', limpia)
    try:
        import modal
        LTX = modal.Cls.from_name('sala-ltx', 'LTX')
        datos = LTX().animar.remote(png.tobytes(), MOVIMIENTO + (que_se_ve or ''), segundos,
                                    512, int(round(512 * h / w / 32)) * 32)
    except Exception as e:  # noqa: BLE001 — cuota, red, app sin desplegar
        raise MotorError('modal_ltx: %s' % sala.redactar(str(e))[:300], intermitente=True)

    with tempfile.TemporaryDirectory() as tmp:
        crudo = pathlib.Path(tmp) / 'ltx.mp4'
        crudo.write_bytes(datos)
        cap = cv2.VideoCapture(str(crudo))
        fps = cap.get(cv2.CAP_PROP_FPS) or FPS
        img_f, capa_f = img.astype(np.float32), capa.astype(np.float32)
        filtro = ('[0]split[a][b];'
                  '[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=40:4[fondo];'
                  '[b]scale=%d:%d:force_original_aspect_ratio=decrease[frente];'
                  '[fondo][frente]overlay=(W-w)/2:(H-h)/2,format=yuv420p'
                  % (ANCHO, ALTO, ANCHO, ALTO, ANCHO, ALTO))
        destino = pathlib.Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo',
                              '-pix_fmt', 'bgr24', '-s', '%dx%d' % (w, h), '-r', '%.3f' % fps,
                              '-i', '-', '-filter_complex', filtro, '-c:v', 'libx264',
                              '-preset', 'veryfast', '-crf', '20', '-movflags', '+faststart',
                              str(destino)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        n = 0
        while True:
            ok, f = cap.read()
            if not ok:
                break
            f = cv2.resize(f, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
            p.stdin.write((f * (1 - capa_f) + img_f * capa_f).astype(np.uint8).tobytes())
            n += 1
        p.stdin.close()
        err = p.stderr.read().decode(errors='replace')
        if p.wait() != 0 or n == 0 or not destino.exists():
            raise MotorError('modal_ltx: no se pudo componer (%d cuadros): %s' % (n, err[-200:]))
    return destino


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        lam = traer_imagen(trabajo, cat, origen)
        return animar(origen, destino, _segundos(reglas), (lam or {}).get('ve') or '')
