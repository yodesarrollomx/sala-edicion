"""La calificación de los motores (24-sep, pedido de Alejandro).

«Nunca te frenes, usa tu máxima posibilidad de producción; si algo no me gusta lo devuelvo.
Pon el orden según lo que voy aprobando: si desapruebo un video, va perdiendo calificación.»

Cómo se califica: por cada propuesta de la mesa que trae video (un eje con `video`), se ve qué
motor hizo sus escenas (COLA · evidencia.motor) y cómo la marcaron los editores (sí / no).
Puntaje = (sí + 1) / (sí + no + 2): arranca en 0.5 y se mueve con cada decisión, sin que una sola
marque la vida del motor. Cada propuesta cuenta UNA vez (se guarda por id en `vistas`).

`datos/motores_puntaje.json` (repo público: sólo conteos, ningún texto de los editores).
Lo escribe el puente de cada hora; el Ejecutor lo lee para decidir con qué motor empezar.
"""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / 'datos' / 'motores_puntaje.json'


def leer():
    try:
        return json.loads(ARCHIVO.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'etapas': {}, 'vistas': {}}


def puntaje(c):
    return round((c.get('si', 0) + 1) / (c.get('si', 0) + c.get('no', 0) + 2), 3)


def orden(etapa, candidatos):
    """Los candidatos, del mejor calificado al peor (empate: el orden dado)."""
    et = (leer().get('etapas') or {}).get(etapa) or {}
    return sorted(candidatos, key=lambda m: -puntaje(et.get(m) or {}))


def _marca(dec):
    """sí / no de una propuesta, desde las decisiones del Sheet (cualquier editor)."""
    if not isinstance(dec, dict):
        return None
    marcas = [str(x) for x in (dec.get('laminas') or []) if x]
    for fs in dec.get('firmas') or []:
        for f in fs or []:
            if isinstance(f, dict) and f.get('marca'):
                marcas.append(str(f['marca']))
    if 'si' in marcas:
        return 'si'
    if 'no' in marcas:
        return 'no'
    return None


def actualizar(dia, cola):
    """Suma las decisiones nuevas sobre videos. Devuelve True si el archivo cambió."""
    datos = leer()
    datos.setdefault('etapas', {})
    vistas = datos.setdefault('vistas', {})
    decs = ((dia or {}).get('decisiones') or {}).get('propuestas') or {}
    cambio = False
    for p in (dia or {}).get('propuestas') or []:
        pid = str(p.get('id') or '')
        if not pid or not p.get('video') or pid in vistas:
            continue
        m = _marca(decs.get(pid))
        if not m:
            continue
        # el trabajo de COLA se llama «<slug>:escena:…»; la propuesta, «<slug>-vN-…»
        motores = sorted({str((t.get('evidencia') or {}).get('motor') or '') for t in cola or []
                          if ':escena:' in str(t.get('id') or '')
                          and pid.startswith(str(t.get('id')).split(':')[0])
                          and isinstance(t.get('evidencia'), dict) and (t.get('evidencia') or {}).get('motor')})
        for mo in motores:
            c = datos['etapas'].setdefault('escena', {}).setdefault(mo, {'si': 0, 'no': 0})
            c[m] += 1
            c['puntaje'] = puntaje(c)
        vistas[pid] = {'marca': m, 'motores': motores}
        cambio = True
    if cambio:
        ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return cambio
