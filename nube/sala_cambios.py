#!/usr/bin/env python3
"""Órdenes de cambio de los editores sobre láminas YA APROBADAS.

El 5-sep-2026 Alejandro pidió poder reabrir una lámina aprobada: «si la abro y quiero volver a
revisarla porque Sayri o yo queremos mejorar algo que aunque pensamos que estaba bien está mal…
que se pueda pedir para rehacer». En la Mac esa petición viajaba como un «no» sobre la propuesta
original y la cosechaba `sala_publicar.py`; con la mudanza a la nube nadie la cosechaba, y las
piezas de una sola imagen (su tira de arranque no tiene base) ni siquiera podían pedirla. El
9-nov-2026 se comprobó con «Las 48 Horas» (DEC-08): Dirección decidió rehacer su imagen y la Sala
no tenía por dónde.

Aquí la orden es un registro explícito del editor, en EXPEDIENTES, con la llave `cambio:<slug>`:

    {"v": 1, "pieza": "Las 48 Horas", "tira": "<id de la tira vigente cuando se pidió>",
     "ordenes": [{"n": 1, "nota": "…", "cuando": "ISO", "por": "editor"}]}

· Un dueño por llave: la escriben los editores desde la Sala. La nube SÓLO la lee (este módulo no
  escribe en ningún lado y no decide: INVIOLABLE 3).
· La aprobación no se borra de DECISIONES: se suma una orden de cambio.
· La orden vale mientras la tira vigente de la pieza siga siendo la misma. En cuanto el montador
  rehace la lámina nace una tira nueva (id nuevo, `origen: rehecha-de`) y la orden queda como
  historia: no hay nada que limpiar ni se rehace dos veces.
"""
import copy
import re

PREFIJO = 'cambio:'
TIRA = re.compile(r'^[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}$')
MAX_NOTA = 600                                        # lo mismo que el cerebro lee de una nota
MAX_ORDENES = 20


def leer(expedientes):
    """{tira: {n: nota}} con las órdenes bien formadas.

    Lo raro se ignora: una orden ilegible no detiene a la mesa ni reabre nada."""
    out = {}
    if not isinstance(expedientes, dict):
        return out
    for clave in sorted(k for k in expedientes if isinstance(k, str) and k.startswith(PREFIJO)):
        registro = expedientes[clave]
        if not isinstance(registro, dict):
            continue
        tira, ordenes = registro.get('tira'), registro.get('ordenes')
        if not isinstance(tira, str) or not TIRA.match(tira) or not isinstance(ordenes, list):
            continue
        for orden in ordenes[:MAX_ORDENES]:
            if not isinstance(orden, dict):
                continue
            n, nota = orden.get('n'), orden.get('nota')
            if type(n) is not int or not 1 <= n <= 99 or not isinstance(nota, str):
                continue
            nota = ' '.join(nota.split())[:MAX_NOTA]
            if nota:
                out.setdefault(tira, {})[n] = nota
    return out


def de_tira(ordenes, pid):
    """Las órdenes que valen para ESTA versión de la pieza: {n: nota}."""
    return dict((ordenes or {}).get(str(pid)) or {})


def aplicar(resuelta, vigentes):
    """(tira, [n reabiertas]): las láminas APROBADAS que traen orden quedan como rechazadas con la
    nota del editor, igual que si la carta siguiera en la mesa. Sin órdenes devuelve la misma tira.

    La lámina reabierta conserva su imagen aprobada (`src`) como lo que se ve mientras tanto, pero
    ya no ofrece sus tomas de antes ni la elección: si la producción de hoy falla o topa, la
    siguiente vuelta hace tomas NUEVAS con la nota en vez de volver a presentar las viejas.
    Una lámina que no está aprobada sigue su camino normal: la orden no la toca."""
    if not vigentes:
        return resuelta, []
    out, reabiertas = copy.deepcopy(resuelta), []
    for lam in out.get('laminas') or []:
        try:
            n = int(lam.get('n'))
        except (TypeError, ValueError):
            continue
        if n in vigentes and lam.get('estado') == 'aprobada':
            lam.update(estado='rechazada', marca_previa='no', nota_previa=vigentes[n], reabierta=True)
            lam.pop('candidatas', None)
            lam.pop('seleccion', None)
            reabiertas.append(n)
    return out, sorted(reabiertas)
