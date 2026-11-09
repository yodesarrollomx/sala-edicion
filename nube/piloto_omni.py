#!/usr/bin/env python3
"""Piloto de UNA historia de 15 segundos con Gemini Omni Flash (voz y labios del propio modelo).

Corre sólo a mano (`sala-piloto-omni.yml`, workflow_dispatch). No pasa por la COLA ni por
`nube_ejecuta_etapas`: no reactiva la producción de video, que sigue en pausa. Cada corrida
real cuesta alrededor de 1 USD y necesita una GEMINI_API_KEY con facturación.

La historia, su personaje y su lugar viven en `datos/universo/universo.json`; aquí no hay
texto de contenido. `--simular` arma e imprime el prompt sin llamar a nadie.
"""
import argparse
import json
import pathlib
import sys

import contenido_reglas
import sala_cliente as sala
from motores import escena_omni
from motores._comun import MotorError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
UNIVERSO = RAIZ / 'datos' / 'universo' / 'universo.json'


def armar(universo, hid):
    """(prompt, segundos) de una historia. KeyError con nombre claro si falta una pieza."""
    h = universo['historias'][hid]
    f = universo['formato']
    quienes = [universo['personajes'][p] for p in h['personajes']]
    lugar = universo['lugares'][h['lugar']]
    partes = [
        f['estilo'],
        'LOCATION: ' + lugar['aspecto'],
        ' '.join('CHARACTER (%s): %s Voice: %s' % (p['nombre'], p['aspecto'], p['voz']) for p in quienes),
        'ACTION: ' + h['accion'],
        'SPOKEN LINE, in Spanish, said once by %s: «%s»' % (quienes[0]['nombre'], h['dialogo']),
        'ENDING: ' + h['gancho'] if h.get('gancho') else '',
        f['audio'],
        f['prohibido'],
    ]
    return '\n'.join(x for x in partes if x), int(f.get('segundos') or 15)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('historia')
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--drive', action='store_true', help='subir el video a Drive (_PILOTOS)')
    ap.add_argument('--salida', default=str(RAIZ / 'nube' / 'salida' / 'piloto'))
    a = ap.parse_args(argv)
    universo = json.loads(UNIVERSO.read_text(encoding='utf-8'))
    if a.historia not in universo['historias']:
        sala.avisar('✗ no existe la historia «%s»; hay: %s' % (a.historia, ', '.join(universo['historias'])))
        return 2
    prompt, segundos = armar(universo, a.historia)
    contenido_reglas.exigir({'prompt': prompt}, None, 'piloto')   # ubicaciones vetadas
    sala.avisar('— prompt (%d s) —\n%s' % (segundos, prompt))
    if a.simular:
        return 0
    try:
        video = escena_omni.generar(prompt, segundos)
    except MotorError as e:
        sala.avisar('✗ %s' % e)
        return 3
    destino = pathlib.Path(a.salida) / ('%s.mp4' % sala.slug_seguro(a.historia))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(video)
    sala.avisar('✓ %s (%d KB) · costo estimado %.2f USD' % (destino, len(video) // 1024,
                                                            segundos * escena_omni.USD_POR_SEGUNDO))
    if a.drive:
        # Drive es donde Dirección lo ve; el artefacto de Actions queda como respaldo.
        import sala_drive as drive
        try:
            raiz = str(((sala.get('reglas') or {}).get('reglas') or {}).get('drive_raiz') or '').strip()
            if not raiz:
                raise drive.DriveError('la REGLA drive_raiz está vacía')
            fid = drive.subir(str(destino), drive.ruta_carpetas(raiz, '_PILOTOS'))
            sala.avisar('✓ Drive: https://drive.google.com/file/d/%s/view' % fid)
        except (drive.DriveError, sala.SalaError) as e:
            sala.avisar('⚠ no se subió a Drive (%s); el video queda en el artefacto de la corrida' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
