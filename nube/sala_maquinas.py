#!/usr/bin/env python3
"""El semáforo de centinelas, traducido a la nube.

En la Mac, «las máquinas» eran los agentes de launchd (`mx.yodesarrollo.relevo`,
`.maquinas`, `.productor`) y su salud se leía de si el plist había corrido. En la nube los
centinelas son los workflows de Actions, así que la salud se lee de la API de Actions: cuándo
corrió cada uno y cómo le fue.

No borra nada de lo que ya hay. Las máquinas de la Mac siguen en el archivo con su id de
siempre; éstas se agregan con el prefijo `nube:`. Si un día la Mac deja de publicar las suyas,
se verá que están viejas — que es justo lo que un semáforo tiene que dejar ver.

INVIOLABLE 4 aplica igual: si la API no contesta, no se escribe un archivo vacío. Se sale
con código 2 y el semáforo viejo se queda, que sigue diciendo más que uno en blanco.
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / 'datos' / 'maquinas.json'
PREFIJO = 'nube:'

# Qué hace cada centinela de la nube y qué se pierde si se apaga. El texto va en llano
# a propósito: esto se lee desde la franja «Las máquinas» de la Sala, no desde una consola.
QUE_HACE = {
    'sala-relevo.yml': ('Relevo de la Sala',
                        'Rehace el respaldo espejo del día (datos/manifiesto.json).',
                        'que la Sala se quede sin plan B si el Sheet no contesta',
                        '6, 9, 12, 15 y 18 h'),
    'sala-productor.yml': ('Productor',
                           'Abre las compuertas de lo aprobado y lo anota en la COLA.',
                           'que un «sí» de la mesa no dispare nada',
                           'cada hora'),
    'sala-maquinas.yml': ('Semáforo',
                          'Escribe este mismo tablero de salud.',
                          'quedarse sin saber si los demás corrieron',
                          'cada 2 h'),
    'verificar.yml': ('Verificador',
                      'Corre las pruebas del repo en cada push y cada pull request.',
                      'publicar una Sala rota',
                      'en cada guardado'),
    'publicar.yml': ('Publicador',
                     'Sube la Sala a GitHub Pages cuando el verificador pasa.',
                     'que un arreglo no llegue a producción',
                     'en cada guardado a main'),
}

VIEJO_HORAS = 26          # un cron diario que lleva más de esto sin correr está caído


def api(ruta):
    repo = os.environ.get('GITHUB_REPOSITORY', 'yodesarrollomx/sala-edicion')
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    pet = urllib.request.Request('https://api.github.com/repos/%s%s' % (repo, ruta),
                                 headers={'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'sala-maquinas'})
    if token:
        pet.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(pet, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def ahora_hermosillo():
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')


def salud_de(corrida, cada_cuanto):
    """Devuelve (salud, porque) en llano."""
    if not corrida:
        return 'sin noticias', 'todavía no ha corrido ni una vez'
    concl = corrida.get('conclusion')
    cuando = corrida.get('run_started_at') or corrida.get('created_at') or ''
    horas = None
    try:
        t = datetime.datetime.fromisoformat(cuando.replace('Z', '+00:00'))
        horas = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600
    except (ValueError, AttributeError):
        pass
    if concl in ('failure', 'timed_out'):
        return 'mal', 'su última corrida falló'
    if concl == 'cancelled':
        return 'regular', 'su última corrida se canceló'
    if horas is not None and 'hora' not in cada_cuanto and horas > VIEJO_HORAS:
        return 'mal', 'lleva %d h sin correr' % int(horas)
    if concl == 'success':
        return 'bien', 'su última corrida salió bien%s' % (
            ' hace %d h' % int(horas) if horas is not None else '')
    return 'regular', 'está corriendo ahora mismo' if not concl else 'terminó en «%s»' % concl


def main():
    try:
        wfs = api('/actions/workflows').get('workflows') or []
    except (urllib.error.URLError, OSError, ValueError) as e:
        print('✗ la API de Actions no contestó: %s' % e)
        print('  No se escribe el semáforo. Uno vacío diría «todo apagado», que es mentira '
              '(INVIOLABLE 4).')
        return 2

    nuevas = []
    for wf in wfs:
        archivo = (wf.get('path') or '').split('/')[-1]
        if archivo not in QUE_HACE:
            continue
        nombre, hace, evita, cuando = QUE_HACE[archivo]
        try:
            corridas = api('/actions/workflows/%s/runs?per_page=1' % wf['id']).get('workflow_runs') or []
        except (urllib.error.URLError, OSError, ValueError):
            corridas = []
        ultima = corridas[0] if corridas else None
        salud, porque = salud_de(ultima, cuando)
        nuevas.append({
            'id': PREFIJO + archivo,
            'nombre': nombre,
            'hace': hace,
            'evita': evita,
            'cuando': cuando,
            'corrio': (ultima or {}).get('run_started_at') or (ultima or {}).get('created_at'),
            'dijo': (ultima or {}).get('display_title', '') or '',
            'salud': salud,
            'porque': porque,
        })

    if not nuevas:
        print('✗ no encontré ninguno de los workflows de la Sala. No se escribe nada.')
        return 2

    previo = {'maquinas': []}
    if ARCHIVO.exists():
        try:
            previo = json.loads(ARCHIVO.read_text(encoding='utf-8'))
        except ValueError:
            pass
    # Las de la Mac se conservan tal cual: este script sólo manda sobre las suyas.
    de_la_mac = [m for m in (previo.get('maquinas') or [])
                 if not str(m.get('id', '')).startswith(PREFIJO)]

    salida = {'actualizado': ahora_hermosillo(), 'maquinas': de_la_mac + nuevas}
    antes = json.dumps(previo.get('maquinas'), sort_keys=True, ensure_ascii=False)
    if antes == json.dumps(salida['maquinas'], sort_keys=True, ensure_ascii=False):
        print('✓ el semáforo ya estaba al día.')
        return 0

    ARCHIVO.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for m in nuevas:
        print('  %-28s %-12s %s' % (m['nombre'], m['salud'], m['porque']))
    print('✓ semáforo escrito: %d de la nube, %d de la Mac conservadas'
          % (len(nuevas), len(de_la_mac)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
