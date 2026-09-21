#!/usr/bin/env python3
"""El catálogo: la identidad canónica de cada lámina. Lo que `sala_productor.py` debió usar
desde el principio.

Por qué existe: una lámina se identifica por su SERIAL (invariante 27: «cada lámina tiene un
serial que no cambia nunca») y cada revisión por su HUELLA — nunca por el nombre del archivo
ni por su posición en una carpeta (invariante 29: «el número de lámina lo dice la TIRA, no el
nombre del archivo» — derivarlo del nombre corrompió 8 seriales el 8-sep).

Antes de este archivo, `sala_productor.huella_insumo()` le sacaba md5 al archivo del REPO.
Funcionaba por accidente casi siempre (la ligera del repo y la de Drive suelen coincidir),
pero la fuente de verdad es Drive + el catálogo, no el repo — que es sólo respaldo. Este
módulo corrige eso.

El Sheet manda (`recurso=catalogo`); `datos/catalogo.json` es el respaldo espejo, mismo patrón
que `sala_relevo.py` con el manifiesto: si el Sheet no contesta, se usa el respaldo y se dice
en el log — nunca se calla.
"""

import json
import pathlib

import sala_cliente as sala

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RESPALDO = RAIZ / 'datos' / 'catalogo.json'

_cache = None


def cargar(fresco=False):
    """Devuelve el catálogo como {serial: {..., revisiones:[...]}}. Intenta el Sheet primero
    (fuente de verdad); si no contesta, cae al respaldo del repo y lo dice."""
    global _cache
    if _cache is not None and not fresco:
        return _cache
    try:
        r = sala.get('catalogo', fresco='1' if fresco else None)
        _cache = r.get('catalogo') or {}
        return _cache
    except sala.SalaError as e:
        sala.avisar('⚠ catálogo: el Sheet no contestó (%s); uso el respaldo del repo. '
                    'Puede ir atrás de Drive — no se usa para decidir, sólo para identidad.' % e)
        if RESPALDO.exists():
            _cache = json.loads(RESPALDO.read_text(encoding='utf-8'))
            return _cache
        raise


def _revision_mas_reciente(entrada):
    revs = (entrada or {}).get('revisiones') or []
    if not revs:
        return None
    return max(revs, key=lambda r: r.get('r', 0))


def por_ruta(catalogo=None):
    """Índice {ruta_del_repo: (serial, revision)} — así una lámina que trae `src` en la tira
    se puede identificar sin adivinar nada. Una ruta puede repetirse (`tambien_en`, cuando la
    misma imagen vive en varias carpetas de grupo): todas apuntan al mismo serial."""
    catalogo = catalogo if catalogo is not None else cargar()
    idx = {}
    for serial, entrada in catalogo.items():
        for rev in (entrada or {}).get('revisiones') or []:
            for ruta in [rev.get('src')] + list(rev.get('tambien_en') or []):
                if ruta:
                    idx[ruta] = (serial, rev)
    return idx


def huella_de(ruta_repo, catalogo=None):
    """La identidad canónica de una lámina a partir de su ruta en el repo: (huella, serial,
    revisión) de la revisión MÁS RECIENTE que el catálogo conoce para esa ruta. `None` si el
    catálogo no la conoce — y entonces quien llama decide: nunca se inventa una huella."""
    idx = por_ruta(catalogo)
    par = idx.get(ruta_repo)
    if not par:
        return None
    serial, rev = par
    huella = rev.get('huella')
    if not huella:
        return None
    return {'huella': huella, 'serial': serial, 'revision': rev.get('r'),
           'drive_original': rev.get('drive_original'), 'drive_prueba': rev.get('drive_prueba')}


def drive_de(ruta_repo, catalogo=None):
    """Sólo los ids de Drive de la revisión más reciente conocida para esa ruta, o None."""
    d = huella_de(ruta_repo, catalogo)
    if not d:
        return None
    return {'original': d['drive_original'], 'prueba': d['drive_prueba']}


def serial_de(pieza, lamina, catalogo=None):
    """El serial de la lámina N de una pieza, tal como lo asignó el catálogo — nunca derivado
    de un nombre de archivo (invariante 29). `pieza` es el código corto (p. ej. «APODO»)."""
    catalogo = catalogo if catalogo is not None else cargar()
    pieza = str(pieza).upper()
    for serial, entrada in catalogo.items():
        if str(entrada.get('pieza', '')).upper() == pieza and entrada.get('lamina') == lamina:
            return serial
    return None


if __name__ == '__main__':                          # prueba de humo contra el respaldo local
    import sys
    sala.enmascarar_en_actions()
    if not RESPALDO.exists():
        sala.avisar('✗ no hay datos/catalogo.json de respaldo para probar')
        sys.exit(2)
    cat = json.loads(RESPALDO.read_text(encoding='utf-8'))
    idx = por_ruta(cat)
    sala.avisar('✓ catálogo local: %d serial(es), %d ruta(s) indexadas' % (len(cat), len(idx)))
    ejemplo = next(iter(idx))
    sala.avisar('  ejemplo:', ejemplo, '->', huella_de(ejemplo, cat))
