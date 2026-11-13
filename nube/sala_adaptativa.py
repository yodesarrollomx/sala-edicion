"""Selección gratuita reproducible. El azar explora; nunca concede permisos.

Un motor de PAGO sólo entra si Dirección lo autoriza con la REGLA `<motor>_tope_dia` > 0
(clips por día). Sin esa regla no se gasta, aunque el motor tenga fila encendida en MOTORES.
"""
import hashlib
import math
import time
import sala_motores
import sala_puntajes
from motores._comun import MotorError

IMPLEMENTADOS = {'escena': {'wan_hf', 'codigo', 'omni_flash'}, 'voz': {'gemini_tts', 'kokoro'}}
PAGO = {'escena': {'omni_flash'}}
MAX_SEGUNDOS = {'wan_hf': 5, 'omni_flash': 15}


def tope_pago(reglas, nombre):
    try:
        return max(0, int(str(reglas.get(nombre + '_tope_dia') or 0).strip()))
    except ValueError:
        return 0


def activa(reglas):
    return str(reglas.get('nube_adaptativa', '1')).lower() not in ('0', 'false', 'no')


def candidatos(etapa, trabajo, reglas, filas, cola):
    vetos = {x.strip() for x in str(reglas.get('motores_vetados', '')).split(',')}
    disponibles = []
    filas = list(filas or [])
    if etapa == 'escena' and not any(m.get('motor') == 'codigo' for m in filas):
        filas.append(dict(etapa=etapa, motor='codigo', encendido=1, costo=0, orden=90, tope_dia=0))
    for nombre in PAGO.get(etapa, ()):
        if not any(m.get('motor') == nombre for m in filas):
            filas.append(dict(etapa=etapa, motor=nombre, encendido=1, costo='pago', orden=50))
    pagos = []
    for m in sala_motores.motores_de(filas, etapa):
        nombre = m.get('motor')
        if nombre not in IMPLEMENTADOS.get(etapa, set()) or nombre in vetos:
            continue
        de_pago = nombre in PAGO.get(etapa, ())
        if de_pago:
            tope = tope_pago(reglas, nombre)        # manda la regla de Dirección, no la fila
            if tope <= 0:
                continue
        elif str(m.get('costo', '')).strip() not in ('0', '0.0', 'gratis'):
            continue
        else:
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
        (pagos if de_pago else disponibles).append(nombre)
    orden = sala_puntajes.orden(etapa, disponibles)
    semilla = int(hashlib.sha256(str(trabajo.get('id', '')).encode()).hexdigest(), 16)
    explorar = len(orden) > 1 and semilla % 100 < 20
    if explorar:
        elegido = orden[1 + (semilla // 100) % (len(orden) - 1)]
        orden.remove(elegido)
        orden.insert(0, elegido)
    motivo = 'exploración 20%' if explorar else 'mejor puntuación disponible'
    if pagos:
        # Lo gratis generativo va primero; el pago autorizado entra antes de caer a la
        # animación por código, que queda como último recurso.
        orden = [n for n in orden if n != 'codigo'] + pagos + [n for n in orden if n == 'codigo']
        motivo += '; pago autorizado con tope diario antes de la animación por código'
    return orden, motivo


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
        if segundos > MAX_SEGUNDOS.get(nombre, math.inf):
            intentos.append({'motor': nombre, 'estado': 'incompatible',
                             'razon': 'la voz supera los %d s del motor' % MAX_SEGUNDOS[nombre]})
            continue
        try:
            if reservar:
                reservar(nombre)
            if nombre == 'codigo':
                from motores import escena_codigo
                ruta = escena_codigo.producir(trabajo, reglas, cat, salida, segundos)
            elif nombre == 'omni_flash':
                from motores import escena_omni
                ruta = escena_omni.producir(trabajo, reglas, cat, salida, segundos)
            else:
                from motores import escena_wan_hf
                ruta = escena_wan_hf.producir(trabajo, dict(reglas, escena_segundos=str(segundos)), cat, salida)
            intentos.append({'motor': nombre, 'estado': 'hecho', 'ts': time.time()})
            return ruta, nombre, {'formato': 'animacion_codigo' if nombre == 'codigo' else 'video_generativo',
                'generativa': nombre != 'codigo', 'seleccion': motivo, 'intentos_motores': intentos,
                'cuota': ('motor de pago: tope diario autorizado por Dirección; costo real en la consola de Google'
                          if nombre in PAGO['escena'] else 'límite interno comprobado; saldo externo desconocido'),
                'runtime': 'github_actions',
                'duracion_objetivo_s': segundos}
        except MotorError as error:
            intentos.append({'motor': nombre, 'estado': 'cuota' if getattr(error, 'esperar', False) else 'fallo',
                             'razon': str(error), 'ts': time.time()})
    error = MotorError('sin alternativa gratuita disponible; revisar motores/vetos o esperar cuota', intermitente=True)
    error.intentos = intentos
    raise error
