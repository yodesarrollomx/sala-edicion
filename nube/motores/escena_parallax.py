#!/usr/bin/env python3
"""parallax: escena ANIMADA hecha con código, gratis, sin GPU y sin cuota (28-sep-2026).

Entre `wan_hf` (animación de IA real, 2 al día gratis) y `camara` (sólo un acercamiento),
este motor le da a la lámina movimiento de verdad en 2.5D, como DepthFlow o el «efecto 3D»
de las fotos del teléfono:

  1. Estima la PROFUNDIDAD de cada píxel con Depth Anything V2 Small en ONNX (≈100 MB, CPU;
     se baja una vez de HuggingFace y queda en caché). Si el modelo no está, usa una
     profundidad aproximada (lo de abajo está más cerca, lo del centro-arriba más lejos) —
     nunca se detiene la producción por esto.
  2. Mueve una cámara virtual DENTRO de la lámina: lo cercano se desplaza más que lo lejano
     (paralaje), con un leve empuje hacia adelante. Cada cuadro se reproyecta con OpenCV.
  3. Asienta el resultado sobre 1080×1920 con fondo de la misma lámina desenfocada (regla 100:
     la lámina ENTERA, nunca recortada) y lo codifica con ffmpeg.

El movimiento es suave a propósito (regla del 14-sep: «que a partir de esa escena se anime,
no que cambie nada»): el texto de la lámina no se deforma de forma notoria.
"""

import os
import pathlib
import subprocess
import tempfile

import sala_cliente as sala
from motores._comun import MotorError, traer_imagen

ANCHO, ALTO, FPS = 1080, 1920, 30
MODELO_URL = ('https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/'
              'onnx/model.onnx')
CACHE = pathlib.Path(__file__).resolve().parent.parent / '.cache' / 'depth'
AMPLITUD = 0.07        # desplazamiento de lo más cercano, en fracción del ancho (28-sep: 0.022 no se notaba)
EMPUJE = 0.16          # acercamiento total a lo largo de la escena (28-sep: 0.045 no se notaba)
BASE = 1.10            # margen para que el movimiento no deje ver bordes reflejados


def _segundos(reglas):
    try:
        return max(2.0, float(str((reglas or {}).get('escena_segundos') or 5)))
    except ValueError:
        return 5.0


def _modelo():
    ruta = pathlib.Path(os.environ.get('DEPTH_MODEL_PATH') or (CACHE / 'depth-anything-v2-small.onnx'))
    if ruta.is_file() and ruta.stat().st_size > 1_000_000:
        return ruta
    try:
        import requests
        ruta.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(MODELO_URL, timeout=120)
        if r.status_code == 200 and len(r.content) > 1_000_000:
            ruta.write_bytes(r.content)
            return ruta
    except Exception:  # noqa: BLE001 — sin red o sin requests: se usa la profundidad aproximada
        pass
    return None


def profundidad(img):
    """Mapa 0..1 (1 = cerca) del tamaño de `img` (BGR). Devuelve (mapa, origen)."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    m = _modelo()
    if m is not None:
        try:
            import onnxruntime as ort
            s = ort.InferenceSession(str(m), providers=['CPUExecutionProvider'])
            x = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (518, 518)).astype(np.float32) / 255
            x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
            x = x.transpose(2, 0, 1)[None]
            d = s.run(None, {s.get_inputs()[0].name: x})[0].squeeze().astype(np.float32)
            d = cv2.resize(d, (w, h))
            d = (d - d.min()) / max(float(d.max() - d.min()), 1e-6)   # Depth Anything: mayor = cerca
            return cv2.GaussianBlur(d, (0, 0), 3), 'depth-anything-v2'
        except Exception:  # noqa: BLE001
            pass
    # aproximada: el suelo (abajo) cerca, el fondo (arriba-centro) lejos, bordes con fuerza
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None].repeat(w, 1)
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    bordes = cv2.GaussianBlur(np.abs(cv2.Laplacian(gris, cv2.CV_32F)), (0, 0), 25)
    bordes = bordes / max(float(bordes.max()), 1e-6)
    d = 0.75 * yy + 0.25 * bordes
    d = (d - d.min()) / max(float(d.max() - d.min()), 1e-6)
    return cv2.GaussianBlur(d, (0, 0), 15), 'aproximada'


def cuadros(img, dep, segundos):
    """Genera los cuadros (BGR, tamaño de la lámina) de la cámara moviéndose en la escena."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    n = int(round(segundos * FPS))
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    cx, cy = w / 2.0, h / 2.0
    for i in range(n):
        t = i / max(n - 1, 1)
        suave = 0.5 - 0.5 * np.cos(np.pi * t)            # arranca y termina despacio
        # travelling lateral de izquierda a derecha + leve subida: el frente cruza por delante
        # del fondo, que es lo que el ojo lee como «se mueve en 3D»
        dx = AMPLITUD * w * (2 * suave - 1)
        dy = -AMPLITUD * 0.35 * w * (2 * suave - 1)
        z = BASE + EMPUJE * suave
        # lo cercano (dep≈1) se mueve y se acerca más que lo lejano
        esc = BASE + (z - BASE) * (0.25 + 0.75 * dep) + (BASE - 1.0) * 0
        mx = cx + (gx - cx) / esc - dx * (dep - 0.35)
        my = cy + (gy - cy) / esc - dy * (dep - 0.35)
        yield cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def animar(imagen, destino, segundos):
    import cv2
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(str(imagen), cv2.IMREAD_COLOR)
    if img is None:
        raise MotorError('parallax: no pude leer la lámina %s' % imagen)
    lado = max(img.shape[:2])
    if lado > 1600:                                       # velocidad en CPU sin perder nitidez
        f = 1600.0 / lado
        img = cv2.resize(img, (int(img.shape[1] * f) // 2 * 2, int(img.shape[0] * f) // 2 * 2),
                         interpolation=cv2.INTER_AREA)
    else:
        img = img[: img.shape[0] // 2 * 2, : img.shape[1] // 2 * 2]
    dep, origen = profundidad(img)
    h, w = img.shape[:2]
    filtro = ('[0]split[a][b];'
              '[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=40:4[fondo];'
              '[b]scale=%d:%d:force_original_aspect_ratio=decrease[frente];'
              '[fondo][frente]overlay=(W-w)/2:(H-h)/2,format=yuv420p'
              % (ANCHO, ALTO, ANCHO, ALTO, ANCHO, ALTO))
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', '%dx%d' % (w, h), '-r', str(FPS), '-i', '-', '-filter_complex', filtro,
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-movflags', '+faststart',
           str(destino)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for c in cuadros(img, dep, segundos):
            p.stdin.write(c.tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode(errors='replace')
    if p.wait() != 0 or not destino.exists():
        raise MotorError('parallax: ffmpeg falló: %s' % err[-300:])
    return destino, origen


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    destino = pathlib.Path(salida_dir) / ('%s-L%s-escena.mp4'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    with tempfile.TemporaryDirectory() as tmp:
        origen = pathlib.Path(tmp) / 'lamina.png'
        traer_imagen(trabajo, cat, origen)
        ruta, _ = animar(origen, destino, _segundos(reglas))
        return ruta
