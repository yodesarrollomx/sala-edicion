#!/usr/bin/env python3
"""Prueba aislada: anima láminas con Wan 2.2 en un Space ZeroGPU gratis de HuggingFace.

No toca el Sheet ni la cola: sólo produce los .mp4 y los deja como artifact del workflow,
para comparar contra el motor «camara» y contra Higgsfield antes de conectar nada.
Usa HF_TOKEN si existe (cuota de cuenta gratis, ~3.5 min GPU/día); si no, anónimo (~2 min).
"""
import os
import shutil
import sys
import time

from gradio_client import Client, handle_file

SPACES = ['zerogpu-aoti/wan2-2-fp8da-aoti-faster', 'zerogpu-aoti/wan2-2-fp8da-aoti-image']
PROMPT = ('Animate this exact image without changing its composition, text or colors. '
          'Slow, subtle cinematic push-in. Golden hour light, gentle natural motion: '
          'dry grass and leaves moving softly in a light breeze, people moving slowly and '
          'naturally. Documentary feel, film grain. Keep any title text perfectly static '
          'and legible.')
LAMINAS = [a for a in sys.argv[1:]]
SALIDA = os.environ.get('SALIDA', 'salida')


def conectar():
    token = os.environ.get('HF_TOKEN') or None
    for space in SPACES:
        try:
            try:
                c = Client(space, token=token)
            except TypeError:
                c = Client(space, hf_token=token)
            print('== conectado a', space, '(con token)' if token else '(anónimo)')
            return c
        except Exception as e:  # noqa: BLE001
            print('!! no se pudo conectar a', space, ':', e)
    sys.exit(1)


def endpoint(c):
    info = c.view_api(return_format='dict', print_info=False)
    nombres = list(info.get('named_endpoints', {}))
    print('== endpoints:', nombres)
    for n in nombres:
        params = [p.get('parameter_name') for p in info['named_endpoints'][n]['parameters']]
        if any('image' in (p or '') for p in params):
            print('== uso', n, 'params:', params)
            return n, params
    sys.exit('!! ningún endpoint recibe imagen')


def argumentos(params, lamina):
    kw = {}
    for p in params:
        if p is None:
            continue
        if 'image' in p:
            kw[p] = handle_file(lamina)
        elif p == 'prompt':
            kw[p] = PROMPT
        elif 'duration' in p:
            kw[p] = 5
    return kw


def main():
    os.makedirs(SALIDA, exist_ok=True)
    c = conectar()
    api, params = endpoint(c)
    ok = 0
    for lam in LAMINAS:
        nombre = lam.replace('laminas/', '').replace('/', '-').rsplit('.', 1)[0]
        t0 = time.time()
        try:
            r = c.predict(api_name=api, **argumentos(params, lam))
        except Exception as e:  # noqa: BLE001
            print('!! %s falló tras %.0fs: %s' % (nombre, time.time() - t0, e))
            continue
        video = r[0] if isinstance(r, (list, tuple)) else r
        if isinstance(video, dict):
            video = video.get('video') or video.get('path')
        destino = os.path.join(SALIDA, 'WAN-HF-%s.mp4' % nombre)
        shutil.copy(video, destino)
        ok += 1
        print('OK %s -> %s (%.0fs)' % (nombre, destino, time.time() - t0))
    print('== %d/%d escenas producidas' % (ok, len(LAMINAS)))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
