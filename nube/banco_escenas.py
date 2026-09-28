#!/usr/bin/env python3
"""Banco de escenas (28-sep-2026): las MISMAS láminas por TODOS los motores de escena, para
comparar consistencia antes de decidir el orden. Nada de esto toca la COLA ni la mesa.

Motores: wan_hf (IA real, cuota gratis diaria), parallax con profundidad de IA, parallax
aproximado (sin modelo), camara (zoom). Por cada lámina sale un video por motor y un
comparativo lado a lado con el nombre del motor encima; todo sube a Drive:
YOD Editorial/_BANCO/<fecha-hora>/. Un motor que falla (p. ej. cuota) queda anotado, no
detiene a los demás.
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_cliente as sala          # noqa: E402
import sala_drive as drive          # noqa: E402
from motores import escena_camara, escena_parallax, escena_wan_hf  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / '.banco'
DEFAULT = ['laminas/mesa-vacia-g1/L3.png', 'laminas/mesa-vacia-g1/L7.png',
           'laminas/dato-servilleta-3-a2026-09-27/L1-1.png']


def wan(img, dest, seg, reglas):
    prompt = escena_wan_hf.FIDELIDAD + 'Subtle natural motion of people and light.'
    ultimo = None
    for space in escena_wan_hf._spaces(reglas):
        try:
            crudo = escena_wan_hf._animar(space, img, prompt, int(seg))
            tmp = dest.with_suffix('.crudo.mp4')
            shutil.copyfile(crudo, tmp)
            escena_wan_hf._asentar(tmp, dest)
            return 'wan_hf (%s)' % space
        except Exception as e:  # noqa: BLE001
            ultimo = sala.redactar(str(e))[:300]
    raise RuntimeError(ultimo or 'sin Space')


def parallax_ia(img, dest, seg, reglas):
    _, origen = escena_parallax.animar(img, dest, seg)
    if origen != 'depth-anything-v2':
        raise RuntimeError('el modelo de profundidad no cargó (salió %s)' % origen)
    return 'parallax · profundidad IA'


def parallax_aprox(img, dest, seg, reglas):
    viejo = escena_parallax._modelo
    escena_parallax._modelo = lambda: None
    try:
        escena_parallax.animar(img, dest, seg)
    finally:
        escena_parallax._modelo = viejo
    return 'parallax · aproximado'


def camara(img, dest, seg, reglas):
    escena_camara.animar(img, dest, seg)
    return 'camara (zoom)'


MOTORES = [('wan', wan), ('parallax-ia', parallax_ia), ('parallax-aprox', parallax_aprox),
           ('camara', camara)]


def comparativo(videos, dest):
    """Lado a lado, cada uno con su etiqueta. `videos` = [(ruta, etiqueta)]."""
    entradas, filtros = [], []
    for i, (v, etq) in enumerate(videos):
        entradas += ['-i', str(v)]
        etq = etq.replace(':', ' ').replace("'", '')
        filtros.append("[%d]scale=540:960,drawtext=text='%s':x=20:y=20:fontsize=30:"
                       "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10[v%d]" % (i, etq, i))
    n = len(videos)
    filtros.append('%shstack=inputs=%d[s]' % (''.join('[v%d]' % i for i in range(n)), n) if n > 1
                   else '[v0]copy[s]')
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *entradas, '-filter_complex',
                        ';'.join(filtros), '-map', '[s]', '-shortest', '-c:v', 'libx264',
                        '-preset', 'veryfast', '-crf', '23', str(dest)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('laminas', nargs='*')
    ap.add_argument('--segundos', type=float, default=5.0)
    a = ap.parse_args()
    laminas = [x for x in (a.laminas or DEFAULT) if x.strip()]
    reglas = (sala.get('reglas') or {}).get('reglas') or {}
    raiz = str(reglas.get('drive_raiz') or '').strip()
    sello = time.strftime('%Y-%m-%d_%H%M', time.gmtime())
    carpeta = drive.ruta_carpetas(raiz, '_BANCO', sello) if raiz else None
    SALIDA.mkdir(exist_ok=True)
    informe = []
    for lam in laminas:
        img = RAIZ / lam
        nombre = sala.slug_seguro(lam.replace('laminas/', '').rsplit('.', 1)[0])
        hechos = []
        for clave, fn in MOTORES:
            dest = SALIDA / ('%s__%s.mp4' % (nombre, clave))
            t0 = time.time()
            try:
                etq = fn(img, dest, a.segundos, reglas)
                seg = round(time.time() - t0, 1)
                fid = drive.subir(str(dest), carpeta) if carpeta else None
                hechos.append((dest, etq))
                informe.append({'lamina': lam, 'motor': clave, 'ok': True, 'segundos': seg,
                                'etiqueta': etq, 'drive_id': fid})
                print('✓ %s · %s · %.1fs' % (lam, etq, seg))
            except Exception as e:  # noqa: BLE001
                informe.append({'lamina': lam, 'motor': clave, 'ok': False,
                                'error': sala.redactar(str(e))[:300]})
                print('✗ %s · %s · %s' % (lam, clave, sala.redactar(str(e))[:300]))
                traceback.print_exc(limit=1)
        if hechos:
            comp = SALIDA / ('%s__COMPARATIVO.mp4' % nombre)
            try:
                comparativo(hechos, comp)
                fid = drive.subir(str(comp), carpeta) if carpeta else None
                informe.append({'lamina': lam, 'motor': 'COMPARATIVO', 'ok': True, 'drive_id': fid})
                print('▣ comparativo %s → %s' % (lam, fid))
            except Exception as e:  # noqa: BLE001
                print('✗ comparativo %s: %s' % (lam, e))
    (SALIDA / 'informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=1))
    if carpeta:
        drive.subir(str(SALIDA / 'informe.json'), carpeta)
        print('carpeta Drive:', carpeta)
    print(json.dumps(informe, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
