"""Selección gratuita reproducible. El azar explora; nunca concede permisos."""
import hashlib
import math
import time
import sala_motores
import sala_puntajes
from motores._comun import MotorError

IMPLEMENTADOS = {'escena': {'wan_hf', 'codigo'}, 'voz': {'gemini_tts', 'kokoro'}}


def activa(reglas):
    return str(reglas.get('nube_adaptativa', '1')).lower() not in ('0', 'false', 'no')


def candidatos(etapa, trabajo, reglas, filas, cola):
    vetos = {x.strip() for x in str(reglas.get('motores_vetados', '')).split(',')}
    disponibles = []
    filas = list(filas or [])
    if etapa == 'escena' and not any(m.get('motor') == 'codigo' for m in filas):
        filas.append(dict(etapa=etapa, motor='codigo', encendido=1, costo=0, orden=90, tope_dia=0))
    for m in sala_motores.motores_de(filas, etapa):
        nombre = m.get('motor')
        if nombre not in IMPLEMENTADOS.get(etapa, set()) or nombre in vetos:
            continue
        if str(m.get('costo', '')).strip() not in ('0', '0.0', 'gratis'):
            continue
        try:
            tope = int(m.get('tope_dia') or 0)
        except (TypeError, ValueError):
            continue
        if tope > 0 and sala_motores._tope_gastado(cola, etapa, nombre) >= tope:
            continue
        recientes = [i for t in cola for i in ((t.get('evidencia') or {}).get('intentos_motores') or [])
                     if i.get('motor') == nombre and time.time()-i.get('ts', 0) < 3600]
        if any(i.get('estado') == 'cuota' for i in recientes) or sum(i.get('estado') == 'fallo' for i in recientes) >= 3:
            continue
        disponibles.append(nombre)
    orden = sala_puntajes.orden(etapa, disponibles)
    semilla = int(hashlib.sha256(str(trabajo.get('id', '')).encode()).hexdigest(), 16)
    explorar = len(orden) > 1 and semilla % 100 < 20
    if explorar:
        elegido = orden[1 + (semilla // 100) % (len(orden) - 1)]
        orden.remove(elegido)
        orden.insert(0, elegido)
    return orden, 'exploración 20%' if explorar else 'mejor puntuación disponible'


def duracion_objetivo(trabajo, cola):
    voz_id = str(trabajo.get('id') or '').replace(':escena:', ':voz:', 1)
    voz = next((x for x in cola if x.get('id') == voz_id and x.get('estado') == 'hecho'), None)
    ev = (voz or {}).get('evidencia') or {}
    try:
        segundos = float(ev.get('duracion_s', 0)) + .15
    except (ValueError, TypeError):
        segundos = 0
    if not ev.get('durable') or not math.isfinite(segundos) or not .15 < segundos <= 120:
        raise MotorError('esperando voz durable para animar su duración completa', intermitente=True)
    return segundos


def escena(trabajo, reglas, filas, cat, salida, cola, reservar=None):
    segundos = duracion_objetivo(trabajo, cola)
    nombres, motivo = candidatos('escena', trabajo, reglas, filas, cola)
    intentos = []
    for nombre in nombres:
        if nombre == 'wan_hf' and segundos > 5:
            intentos.append({'motor': nombre, 'estado': 'incompatible', 'razon': 'la voz supera los 5 s del motor'})
            continue
        try:
            if reservar:
                reservar(nombre)
            if nombre == 'codigo':
                from motores import escena_codigo
                ruta = escena_codigo.producir(trabajo, reglas, cat, salida, segundos)
            else:
                from motores import escena_wan_hf
                ruta = escena_wan_hf.producir(trabajo, dict(reglas, escena_segundos=str(segundos)), cat, salida)
            intentos.append({'motor': nombre, 'estado': 'hecho', 'ts': time.time()})
            return ruta, nombre, {'formato': 'animacion_codigo' if nombre == 'codigo' else 'video_generativo',
                'generativa': nombre == 'wan_hf', 'seleccion': motivo, 'intentos_motores': intentos,
                'cuota': 'límite interno comprobado; saldo externo desconocido', 'runtime': 'github_actions',
                'duracion_objetivo_s': segundos}
        except MotorError as error:
            intentos.append({'motor': nombre, 'estado': 'cuota' if getattr(error, 'esperar', False) else 'fallo',
                             'razon': str(error), 'ts': time.time()})
    error = MotorError('sin alternativa gratuita disponible; revisar motores/vetos o esperar cuota', intermitente=True)
    error.intentos = intentos
    raise error
