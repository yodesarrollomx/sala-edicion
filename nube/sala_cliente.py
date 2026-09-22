#!/usr/bin/env python3
"""Cliente único de la Sala contra el Apps Script /exec.

Por qué existe: hasta hoy el ciclo diario vivía sólo en la Mac (`~/yod_audit/`), con las
llaves en `~/.sala_gas_claves.json` y los disparadores en launchd. Si la Mac se dormía, la
Sala amanecía sin mesa y nadie se enteraba. Este módulo es la misma conversación con el
mismo /exec, pero desde un runner de GitHub Actions.

Las dos reglas que gobiernan este archivo:

  · INVIOLABLE 2 — el repo es PÚBLICO. La liga y la clave llegan SIEMPRE por variable de
    entorno (secrets de Actions), nunca por argumento ni por archivo del repo. `redactar()`
    tacha la clave de cualquier texto antes de que toque un log.
  · INVIOLABLE 3 — la nube entra como `agente`. El agente propone, retira y reporta; NUNCA
    decide. `post()` rechaza `accion:'decidir'` aquí mismo, antes de la red, para que un
    error de programación no pueda siquiera intentarlo.

Nota de campo (CLAUDE.md): para POST al GAS hay que seguir la redirección — `urllib` dio 404
una vez. Aquí se sigue con `curl -L` de respaldo si la vía de Python no entrega JSON.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INTENTOS = 3
ESPERA = 12          # segundos de tope por intento (el presupuesto del manual)

# Acciones que la nube tiene prohibidas por diseño, no por configuración.
PROHIBIDAS = {'decidir', 'parrilla_decision'}


class SalaError(RuntimeError):
    """Algo no contestó o contestó mal. NUNCA se traduce a «no hay nada» (INVIOLABLE 4)."""


def _exec_url():
    u = os.environ.get('SALA_GAS_EXEC', '').strip()
    if not u:
        raise SalaError('falta SALA_GAS_EXEC (secret de Actions con la liga /exec)')
    return u


def _clave():
    k = os.environ.get('SALA_CLAVE_AGENTE', '').strip()
    if not k:
        raise SalaError('falta SALA_CLAVE_AGENTE (secret de Actions con la clave del agente)')
    return k


# Todos los secrets que puede llegar a ver un script de nube/ — no sólo los de la Sala.
# Fase A/B añadieron Drive, HuggingFace y Gemini; sus claves merecen la MISMA protección que
# SALA_CLAVE_AGENTE desde el primer día, no una añadida después de que algo se filtrara.
# (Hallazgo de una auto-revisión de seguridad el 21-sep: redactar() y enmascarar_en_actions()
# sólo conocían las dos primeras — un error futuro que imprimiera GEMINI_API_KEY, por
# ejemplo la URL de voz_gemini.py con su `?key=` armada a mano, no se habría tachado en el
# log de un repo PÚBLICO.)
VARIABLES_SECRETAS = ('SALA_CLAVE_AGENTE', 'SALA_GAS_EXEC', 'GDRIVE_SA_JSON',
                      'HF_TOKEN', 'GEMINI_API_KEY')


def redactar(texto):
    """Tacha cualquier secret conocido de un texto antes de imprimirlo."""
    t = str(texto)
    for var in VARIABLES_SECRETAS:
        s = os.environ.get(var, '').strip()
        if len(s) >= 6:
            t = t.replace(s, '«tachado»')
            t = t.replace(urllib.parse.quote(s, safe=''), '«tachado»')
    return t


def avisar(*partes):
    """Imprime al log, siempre redactado."""
    print(redactar(' '.join(str(p) for p in partes)), flush=True)


def enmascarar_en_actions():
    """Le dice a Actions que tache estos valores en TODO el log, incluso el que no pase
    por avisar() — un traceback crudo de una librería, por ejemplo. Se llama al arrancar
    cualquier script de la nube."""
    if not os.environ.get('GITHUB_ACTIONS'):
        return
    for var in VARIABLES_SECRETAS:
        v = os.environ.get(var, '').strip()
        if len(v) >= 6:
            print('::add-mask::' + v, flush=True)


def _leer_json(crudo, donde):
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        raise SalaError('%s no devolvió JSON: %s' % (donde, redactar(str(crudo)[:300])))
    if isinstance(datos, dict) and datos.get('error'):
        raise SalaError('%s contestó con error: %s' % (donde, redactar(datos['error'])))
    return datos


def _curl(url, cuerpo=None):
    """Respaldo con curl -L: sigue la redirección de Apps Script como manda CLAUDE.md."""
    cmd = ['curl', '-sS', '-L', '--max-time', str(ESPERA)]
    if cuerpo is not None:
        cmd += ['-X', 'POST', '-H', 'Content-Type: application/json', '--data-binary', '@-']
    cmd.append(url)
    r = subprocess.run(cmd, input=(cuerpo or ''), capture_output=True, text=True)
    if r.returncode != 0:
        raise SalaError('curl falló (%s): %s' % (r.returncode, redactar(r.stderr[:300])))
    return r.stdout


def _urllib(url, cuerpo=None):
    datos = cuerpo.encode('utf-8') if cuerpo is not None else None
    cab = {'Content-Type': 'application/json'} if datos else {}
    pet = urllib.request.Request(url, data=datos, headers=cab)
    with urllib.request.urlopen(pet, timeout=ESPERA) as r:
        return r.read().decode('utf-8', 'replace')


def _pedir(url, cuerpo, donde):
    """3 intentos. Cada intento prueba urllib y, si no entregó JSON usable, curl -L."""
    ultimo = None
    for intento in range(1, INTENTOS + 1):
        for via, fn in (('urllib', _urllib), ('curl -L', _curl)):
            try:
                return _leer_json(fn(url, cuerpo), donde)
            except SalaError as e:
                ultimo = e                       # contestó, pero mal: se prueba la otra vía
            except (urllib.error.URLError, OSError, subprocess.SubprocessError) as e:
                ultimo = SalaError('%s por %s: %s' % (donde, via, redactar(e)))
        if intento < INTENTOS:
            time.sleep(2 ** intento)             # 2 s, 4 s
    raise SalaError('%s no contestó en %d intentos · último: %s' % (donde, INTENTOS, ultimo))


def get(recurso, **params):
    """Lectura. `recurso` es uno de los que atiende doGet: dia, reglas, cola, catalogo,
    bitacora, envios, expedientes, prompts."""
    q = {'recurso': recurso, 'clave': _clave()}
    q.update({k: v for k, v in params.items() if v is not None})
    url = _exec_url() + '?' + urllib.parse.urlencode(q)
    return _pedir(url, None, 'GET ?recurso=' + recurso)


def post(accion, **campos):
    """Escritura. Se niega en seco a las acciones que son de los editores (INVIOLABLE 3)."""
    if accion in PROHIBIDAS:
        raise SalaError(
            "la nube entra como «agente» y el agente NO decide (INVIOLABLE 3): «%s» está "
            "prohibida aquí. Decidir es de Alejandro y Sayri, en la Sala." % accion)
    cuerpo = {'accion': accion, 'clave': _clave()}
    cuerpo.update(campos)
    return _pedir(_exec_url(), json.dumps(cuerpo), 'POST accion=' + accion)


def slug_seguro(texto, si_vacio='x'):
    """Un `pieza`/`item` de COLA convertido a nombre de archivo seguro.

    Por qué existe: `familia` e `item` llegan de filas de COLA que, en el flujo normal,
    escribe nuestro propio productor — pero COLA es una hoja que cualquiera con la clave del
    agente puede escribir (`accion:'cola'`), y los motores los usan tal cual para nombrar
    archivos locales (`nube/motores/*.py`, `sala_montador.py`). Si esa clave se filtrara
    algún día (el mismo escenario que `redactar()` existe para prevenir), una fila con
    `pieza:'../../../tmp/algo'` no debe poder escribir fuera de la carpeta de salida. Se
    queda sólo con letras, números, guion y guion bajo — nada de `/`, `.` ni espacios."""
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(texto))
    limpio = limpio.strip('_.')
    return limpio or si_vacio


def hoy_hermosillo():
    """La fecha de la casa. TZ fija UTC-7, sin horario de verano, igual que `hoy()` del GAS.
    Nunca el reloj del runner, que corre en UTC."""
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=7)).strftime('%Y-%m-%d')


def hora_hermosillo():
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=7)).hour


if __name__ == '__main__':                        # prueba de humo: sólo lee, nunca escribe
    enmascarar_en_actions()
    try:
        d = get('dia')
    except SalaError as e:
        avisar('✗', e)
        sys.exit(2)
    avisar('✓ el Sheet contestó el día', d.get('fecha'),
           '·', len(d.get('propuestas') or []), 'propuesta(s)',
           '· rol:', d.get('rol'), '· relevo_virtual:', d.get('relevo_virtual'))
