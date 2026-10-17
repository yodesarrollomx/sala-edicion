"""La publicación acreditada cierra producción; no modifica la historia editorial."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def nombre(value):
    return ' '.join(str(value or '').casefold().split())


def registro_publicadas():
    """Mismo registro publicado que consulta Mesa, hidratado por snapshots_online."""
    out = set()
    for filename in ('piezas.json', 'embudo.json'):
        path = ROOT / 'datos' / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        for row in data.get('piezas') or []:
            if filename == 'piezas.json' and row.get('etapa') != 'publicada':
                continue
            if filename == 'embudo.json' and not any(
                    r.get('permalink') and r.get('id_post') for r in (row.get('redes') or {}).values()):
                continue
            for key in ('pieza', 'pieza_slug'):
                if row.get(key):
                    out.add(nombre(row[key]))
    return out


def publicada(prop, tira=None, registro=None):
    registro = registro_publicadas() if registro is None else registro
    # El separador editorial delimita el título de la pieza y su ronda.
    # Una coincidencia parcial nunca cierra otra pieza ni su secuela.
    names = [(tira or {}).get('pieza'), (tira or {}).get('pieza_slug'),
             str(prop.get('titulo') or '').split(' · ', 1)[0]]
    return any(nombre(x) in registro for x in names if x)


def cola_sin_publicadas(cola, dia, registro=None):
    sources = {p['id'] for p in dia.get('propuestas') or [] if publicada(p, registro=registro)}
    result, count = copy.deepcopy(cola), 0
    for row in result:
        ev = row.get('evidencia') or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except ValueError:
                continue
        if ev.get('de') in sources and row.get('estado') not in ('hecho', 'obsoleto'):
            row.update(estado='obsoleto', bloqueado_por='pieza_publicada_no_reproducir')
            count += 1
    return result, count
