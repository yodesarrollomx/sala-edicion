#!/usr/bin/env python3
"""El guion de video: dónde vive el TEXTO que la voz tiene que decir.

Por qué existe: una tira dice QUÉ se ve (`dice`/`ve`/`entiende` por lámina); el guion de
video dice CÓMO se reparte esa línea entre dos voces (`datos/guiones/<PIEZA>-VIDEO.json`,
`escenas[].partes[].{rol,dice}`, confirmado en el único ejemplo real del repo —
`APODO-VIDEO.json`, 6 escenas). `_voces.narrador`/`_voces.vecino` documentan quién es cada
rol («ella»/«el») y con qué voz se grabó — hoy nombres de Gemini (Aoede/Algenib), de antes
del cambio a Kokoro el 14-sep; por eso las voces vigentes se leen de REGLAS
(`voz_narrador`/`voz_vecino`), no de este archivo.

Convención observada (un solo ejemplo real, documentada como tal — no una regla escrita en
ningún otro lado): el archivo se llama `<FAMILIA-EN-MAYÚSCULAS>-VIDEO.json`, y la escena `n`
corresponde a la lámina `n` (E1→L1 … E6→L6 en el Apodo). Si algún día una pieza rompe ese
supuesto, esto lo dirá con claridad — nunca inventa una escena que no está.
"""

import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
GUIONES = RAIZ / 'datos' / 'guiones'

DEFAULTS_VOZ = {
    # Kokoro-82M trae voces con prefijo por idioma/género. Éstas son un punto de partida
    # razonable (narrador mujer, vecino hombre — igual que `_voces` del guion real) y
    # AJUSTABLE por Alejandro vía `accion:'regla'` sin tocar código.
    'voz_narrador': 'af_heart',
    'voz_vecino': 'am_adam',
}


def ruta_guion(familia):
    return GUIONES / ('%s-VIDEO.json' % str(familia).upper())


def cargar(familia):
    """El guion de video de una pieza, o None si no existe todavía. Nunca se inventa: una
    pieza sin guion de video se queda `pendiente` para que alguien lo escriba."""
    p = ruta_guion(familia)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except ValueError:
        return None


def escena_de_lamina(guion, item):
    """La escena cuyo número `n` == el número de lámina (item, 1-based). Ver docstring del
    módulo: es la convención observada en el único ejemplo real, no una garantía del formato."""
    try:
        n = int(str(item).split('-')[0])            # 'apodo:voz:3:...' -> item '3'
    except ValueError:
        return None
    for e in (guion or {}).get('escenas') or []:
        if e.get('n') == n:
            return e
    return None


def voz_de(reglas, rol, guion=None):
    """El nombre de voz para un rol (narrador/vecino). Orden: REGLA explícita (`voz_narrador`/
    `voz_vecino`) → el default de Kokoro de este módulo → lo que diga `_voces` del guion (útil
    sólo si el motor activo es el mismo que grabó ese guion, p. ej. gemini_tts con Aoede)."""
    clave = 'voz_narrador' if rol == 'narrador' else 'voz_vecino'
    if clave in (reglas or {}) and str(reglas[clave]).strip():
        return str(reglas[clave]).strip()
    if guion and (guion.get('_voces') or {}).get(rol, {}).get('voz'):
        return guion['_voces'][rol]['voz']
    return DEFAULTS_VOZ[clave]


def partes_de(guion, item):
    """Las líneas a sintetizar para una lámina: [(rol, texto), ...] en orden. Vacío si el
    guion existe pero esa lámina no tiene escena — nunca falla con una excepción críptica."""
    e = escena_de_lamina(guion, item)
    if not e:
        return []
    return [(str(p.get('rol') or 'narrador'), str(p.get('dice') or ''))
            for p in (e.get('partes') or []) if str(p.get('dice') or '').strip()]


if __name__ == '__main__':                          # prueba de humo contra el guion real
    g = cargar('apodo')
    if not g:
        print('✗ no hay datos/guiones/APODO-VIDEO.json')
    else:
        for item in ('1', '2', '3'):
            print('lámina', item, '->', partes_de(g, item))
        print('voz narrador (sin REGLAS) ->', voz_de({}, 'narrador', g))
        print('voz vecino (con REGLA) ->', voz_de({'voz_vecino': 'am_michael'}, 'vecino', g))
