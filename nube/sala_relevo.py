#!/usr/bin/env python3
"""El relevo diario, en la nube.

Qué hace: cosecha el día del Sheet y reescribe `datos/manifiesto.json`, el RESPALDO ESPEJO
que la Sala lee cuando el Sheet no contesta. Corre 6, 9, 12, 15 y 18 h (hora de Hermosillo).

Qué NO hace, y por qué importa: **no monta piezas nuevas**. Montar exige producir —láminas,
tiras, video—, y eso no cabe en un runner sin GPU. Además ya no hace falta para que la mesa
amanezca llena: desde el 8-sep `armarDia_` (gas/Code.gs) hace el relevo virtual del lado del
Sheet — si hoy no hay filas, sirve lo pendiente de los 14 días previos y lo marca `de_antes`.
Lo que el relevo de la Mac seguía aportando, y que la Mac dejaba de aportar cuando se dormía,
es exactamente esto: mantener vivo el plan B.

Las reglas que cuida:

  · INVIOLABLE 4 — «no contestó» nunca es «no hay nada». Si el Sheet no habla, sale con
    código 2 y NO toca el manifiesto. Un respaldo vacío es peor que un respaldo viejo.
  · INVIOLABLE 10 — PASO 0: las peticiones abiertas se leen y se reportan antes que nada.
  · INVIOLABLE 12 — idempotente. Los crons de Actions se repiten y se retrasan; correr esto
    diez veces seguidas deja el mismo archivo y un solo commit.
"""

import argparse
import json
import pathlib
import sys

import sala_cliente as sala

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MANIFIESTO = RAIZ / 'datos' / 'manifiesto.json'

# Lo que el día trae y el respaldo copia tal cual.
DEL_DIA = ('fecha', 'dias', 'propuestas', 'parrilla', 'control', 'retro',
           'produccion', 'bitacora', 'decisiones')
# Lo que vive SÓLO en el respaldo y el día no conoce: se conserva, nunca se inventa.
DEL_REPO = ('_que_es', 'historial', 'peticiones', 'conexion', 'sugerencias')

SIN_RESPUESTA = 2        # el Sheet no contestó
SIN_MARCAS = 3           # contestó, pero sin las marcas: no se puede confiar en el día


def paso_cero(previo):
    """INVIOLABLE 10 — nada avanza sobre una pieza con petición abierta.
    El relevo no produce, así que no se detiene por esto; lo reporta para que quede en el log
    y para que el productor —que sí abre compuertas— lo encuentre en el manifiesto."""
    pet = previo.get('peticiones') or []
    abiertas = [p for p in pet if isinstance(p, dict) and p.get('estado') != 'cumplida']
    sala.avisar('PASO 0 · peticiones: %d registradas, %d abiertas' % (len(pet), len(abiertas)))
    for p in abiertas:
        sala.avisar('   · abierta (%s): %s' % (p.get('fecha', '?'), str(p.get('pedido'))[:110]))
    return abiertas


def armar(dia, previo):
    nuevo = {}
    for k in DEL_REPO:
        if k in previo:
            nuevo[k] = previo[k]
    for k in DEL_DIA:
        if k in dia:
            nuevo[k] = dia[k]
    # Ni el rol, ni quién preguntó, ni una clave renovada entran al respaldo: es un archivo
    # de un repo PÚBLICO (INVIOLABLE 2).
    for prohibido in ('rol', 'quien', 'clave_nueva', 'aviso_llave', 'cache'):
        nuevo.pop(prohibido, None)
    return nuevo


def igual(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == \
           json.dumps(b, sort_keys=True, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description='El relevo diario de la Sala, desde la nube.')
    ap.add_argument('--simular', action='store_true',
                    help='dice qué haría y no escribe nada')
    args = ap.parse_args()

    sala.enmascarar_en_actions()

    previo = {}
    if MANIFIESTO.exists():
        try:
            previo = json.loads(MANIFIESTO.read_text(encoding='utf-8'))
        except ValueError as e:
            sala.avisar('✗ el respaldo espejo actual no parsea: %s' % e)
            return SIN_MARCAS

    paso_cero(previo)

    try:
        dia = sala.get('dia', fresco='1')        # fresco: el respaldo nunca se hace de cache
    except sala.SalaError as e:
        sala.avisar('✗ el Sheet no contestó: %s' % e)
        sala.avisar('  NO se toca el respaldo espejo. «No contestó» no es «no hay nada» '
                    '(INVIOLABLE 4). El respaldo viejo sigue sirviendo; uno vacío no.')
        return SIN_RESPUESTA

    if 'decisiones' not in dia or not isinstance(dia.get('decisiones'), dict):
        sala.avisar('✗ el día vino sin marcas (sin «decisiones»). No se escribe nada: un '
                    'respaldo sin marcas volvería a preguntar lo ya decidido (invariante 2).')
        return SIN_MARCAS

    props = dia.get('propuestas') or []
    sala.avisar('cosechado: día %s · %d propuesta(s) en la mesa · relevo_virtual=%s'
                % (dia.get('fecha'), len(props), dia.get('relevo_virtual')))
    de_antes = [p for p in props if isinstance(p, dict) and p.get('de_antes')]
    if de_antes:
        sala.avisar('   · %d vienen de días previos (las suma el GAS, no las sustituye: '
                    'invariante 18)' % len(de_antes))

    nuevo = armar(dia, previo)
    if igual(nuevo, previo):
        sala.avisar('✓ el respaldo espejo ya estaba al día. Nada que commitear.')
        return 0

    if args.simular:
        sala.avisar('— simulación — el respaldo CAMBIARÍA. No se escribió nada.')
        return 0

    # indent=1 a propósito: es como está escrito el manifiesto de hoy. Con indent=2 el
    # primer relevo produciría un diff de 2 700 líneas de puro espacio en blanco y
    # taparía el cambio de verdad.
    MANIFIESTO.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1) + '\n',
                          encoding='utf-8')
    sala.avisar('✓ respaldo espejo reescrito: %s' % MANIFIESTO.relative_to(RAIZ))
    return 0


if __name__ == '__main__':
    sys.exit(main())
