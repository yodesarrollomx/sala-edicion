#!/usr/bin/env python3
"""prospecto: una candidata nueva para una lámina que el editor rechazó. El productor abre
N por cada «no» (`prospectos_por_rechazo`); cada una es una variante distinta.

receta base (hoja PROMPTS) + lo que muestra/dice la lámina + la nota del «no»
  → cerebro (Gemini gratis; OpenAI con tope si Gemini no contesta)
  → imagen (Cloudflare FLUX gratis → Gemini imagen)
  → archivo local, que el ejecutor sube a Drive como cualquier producto.

Montarla en la mesa del editor NO es de este motor: el agente propone, el editor decide
(INVIOLABLE 3), y montar sigue el camino de siempre (accion:proponer).
"""

import pathlib

import sala_cliente as sala
from motores import cerebro, imagen
from motores._comun import lamina_de


def _receta_base(familia, n):
    try:
        r = sala.get('prompts', pieza=familia) or {}
    except sala.SalaError:
        return ''
    filas = r.get('prompts') or []
    for f in filas:
        if str(f.get('lamina')) == str(n):
            return ' '.join(x for x in (f.get('prompt_base'), f.get('acento')) if x)
    for f in filas:
        if str(f.get('lamina')) in ('', '*', '0'):
            return ' '.join(x for x in (f.get('prompt_base'), f.get('acento')) if x)
    return ''


def producir(trabajo, reglas, cat, salida_dir, cola=None):
    """Devuelve (ruta, extra_evidencia)."""
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    n, _, variante = item.partition('-')
    lam = lamina_de(trabajo)
    base = _receta_base(familia, n)
    texto, quien, avisos = cerebro.receta(base, lam['ve'], lam['dice'], lam['nota'],
                                          reglas, cola, int(variante or 1))
    datos, ext, motor, avisos_img = imagen.generar(texto, reglas)
    destino = pathlib.Path(salida_dir) / ('%s-L%s-prospecto.%s'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item), ext))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return destino, {'motor': motor, 'cerebro': quien, 'receta': texto[:600],
                     'fecha': str(sala.hoy_hermosillo()),
                     'avisos': (avisos + avisos_img)[:4]}
