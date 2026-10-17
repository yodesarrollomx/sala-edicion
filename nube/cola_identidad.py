"""Identidades de trabajo únicas; nunca elegir contenido contradictorio por orden."""
import copy
import json
from collections import Counter


def consolidar_plan(trabajos):
    grupos = {}
    for trabajo in trabajos:
        grupos.setdefault(trabajo['id'], []).append(trabajo)
    unicos, bloqueados = [], []
    for tid, grupo in sorted(grupos.items()):
        firmas, fuentes = set(), set()
        for trabajo in grupo:
            normal = copy.deepcopy(trabajo)
            ev = normal.setdefault('evidencia', {})
            fuente = ev.pop('de', '')
            if fuente:
                fuentes.add(fuente)
            fuentes.update(ev.pop('fuentes_equivalentes', []))
            firmas.add(json.dumps(normal, sort_keys=True, ensure_ascii=False))
        if len(firmas) != 1:
            bloqueados.append(tid)
            continue
        unico = json.loads(next(iter(firmas)))
        if fuentes:
            unico['evidencia']['de'] = min(fuentes)
            if len(fuentes) > 1:
                unico['evidencia']['fuentes_equivalentes'] = sorted(fuentes)
        unicos.append(unico)
    return unicos, bloqueados


def cola_segura(cola):
    """Obsoletos son historia; dos filas activas de un ID nunca se ejecutan."""
    activas = [copy.deepcopy(t) for t in cola if t.get('estado') != 'obsoleto']
    conteos = Counter(t.get('id') for t in activas)
    repetidos = {tid for tid, n in conteos.items() if n > 1}
    for trabajo in activas:
        if trabajo.get('id') in repetidos:
            trabajo.update(estado='bloqueado', bloqueado_por='cola_id_duplicado')
    return activas, len(repetidos)
