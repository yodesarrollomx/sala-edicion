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

Nota de campo (CLAUDE.md): GAS redirige la respuesta a un recurso GET. Se usa `curl -L`
una sola vez por intento; una escritura sin recibo no se vuelve a enviar a ciegas.
"""

import json
import os
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INTENTOS = 3
# 21-sep: 12 s bastaba para `dia` y `catalogo` (los dos tienen caché en el GAS,
# CacheService) pero se quedó corto para `reglas` y `cola` — los dos únicos
# recursos SIN caché — confirmado en la sonda real: curl (28) timeout a los
# 12002 ms, tres intentos seguidos, en los dos mismos recursos. El propio
# manual documenta que una lectura sin caché de varias pestañas llegó a tardar
# hasta 12 s (era el presupuesto de `dia` ANTES de que le agregaran caché,
# 5-sep) — así que 12 s como tope duro para el resto era optimista.
ESPERA = 25          # segundos de tope por intento
# Productor y Mesa también leen el día fresco. El run 38666752617 agotó ambos
# intentos de 60 s; el presupuesto incluye /exec y su redirección. No recurrir a
# un día viejo para abrir compuertas. Cola/reglas también leen Sheets sin caché.
ESPERA_RELEVO = 120
INTENTOS_RELEVO = 2
ESPERA_SHEET = 60

# Acciones que la nube tiene prohibidas por diseño, no por configuración.
PROHIBIDAS = {'decidir', 'parrilla_decision'}


HTTP_DIAGNOSTICO = frozenset({400, 401, 403, 404, 405, 408, 409, 413, 429, 500, 502, 503, 504})
CODIGOS_DIAGNOSTICO = frozenset({"sala_sin_confirmar", "sala_clave_ausente", "sala_url_ausente",
    "sala_json_invalido", "sala_objeto_invalido", "sala_error_backend", "sala_clave_rechazada",
    "sala_permiso_rechazado", "sala_recurso_no_disponible", "sala_rechazada", "sala_contrato_lectura", "sala_tiempo_agotado",
    "sala_red_sin_confirmar", "sala_transporte_sin_confirmar", "sala_telemetria_sin_confirmar"}
    | {"sala_http_" + str(x) for x in HTTP_DIAGNOSTICO})
RECURSOS_DIAGNOSTICO = frozenset({"dia", "cola", "reglas", "catalogo", "bitacora", "envios", "expedientes", "prompts"})
TIPOS_RESPUESTA = frozenset({"vacia", "html", "no_json", "json_objeto", "json_no_objeto", "json_error", "sin_respuesta"})


def metadatos_publicos(datos):
    """Sólo nombres constantes y métricas numéricas; nunca texto remoto o URLs."""
    out = {}
    if not isinstance(datos, dict):
        return out
    for field, allowed in (("recurso", RECURSOS_DIAGNOSTICO), ("tipo_respuesta", TIPOS_RESPUESTA)):
        value = datos.get(field)
        if isinstance(value, str) and value in allowed:
            out[field] = value
    for field, limit in (("timeout_segundos", 120), ("latencia_ms", 600000),
                         ("duracion_total_ms", 1000000), ("bytes", 100000000),
                         ("intentos", 3), ("curl_codigo", 99), ("estado_http", 599)):
        value = datos.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= limit:
            out[field] = round(value, 3)
    return out


class SalaError(RuntimeError):
    """Fallo explícito con metadatos seguros; nunca equivale a cero pendientes."""
    def __init__(self, *args, codigo="sala_sin_confirmar", metadatos=None):
        super().__init__(*args)
        self.codigo = codigo if isinstance(codigo, str) and codigo in CODIGOS_DIAGNOSTICO else "sala_sin_confirmar"
        self.metadatos = metadatos_publicos(metadatos)


class _TextoRespuesta(str):
    def __new__(cls, value, metadatos):
        obj = super().__new__(cls, value)
        obj.metadatos = metadatos_publicos(metadatos)
        return obj


def _exec_url():
    u = os.environ.get('SALA_GAS_EXEC', '').strip()
    if not u:
        raise SalaError('falta SALA_GAS_EXEC (secret de Actions con la liga /exec)', codigo='sala_url_ausente')
    return u


def _clave():
    k = os.environ.get('SALA_CLAVE_AGENTE', '').strip()
    if not k:
        raise SalaError('falta SALA_CLAVE_AGENTE (secret de Actions con la clave del agente)', codigo='sala_clave_ausente')
    return k


# Todos los secrets que puede llegar a ver un script de nube/ — no sólo los de la Sala.
# Fase A/B añadieron Drive, HuggingFace y Gemini; sus claves merecen la MISMA protección que
# SALA_CLAVE_AGENTE desde el primer día, no una añadida después de que algo se filtrara.
# (Hallazgo de una auto-revisión de seguridad el 21-sep: redactar() y enmascarar_en_actions()
# sólo conocían las dos primeras — un error futuro que imprimiera GEMINI_API_KEY, por
# ejemplo la URL de voz_gemini.py con su `?key=` armada a mano, no se habría tachado en el
# log de un repo PÚBLICO.)
VARIABLES_SECRETAS = ('SALA_CLAVE_AGENTE', 'SALA_GAS_EXEC', 'GDRIVE_SA_JSON',
                      'HF_TOKEN', 'GEMINI_API_KEY', 'CF_API_TOKEN', 'CF_ACCOUNT_ID', 'OPENAI_API_KEY')


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
    meta = dict(getattr(crudo, 'metadatos', {}))
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        text = crudo.strip().lower() if isinstance(crudo, str) else ''
        meta['tipo_respuesta'] = 'vacia' if not text else ('html' if text.startswith(('<!doctype html', '<html', '<body')) else 'no_json')
        raise SalaError('%s no devolvió JSON' % donde,
                        codigo='sala_json_invalido', metadatos=meta)
    if not isinstance(datos, dict):
        meta['tipo_respuesta'] = 'json_no_objeto'
        raise SalaError('%s no devolvió un objeto JSON' % donde, codigo='sala_objeto_invalido', metadatos=meta)
    meta['tipo_respuesta'] = 'json_objeto'
    if datos.get('error'):
        meta['tipo_respuesta'] = 'json_error'
        code = {'clave incorrecta': 'sala_clave_rechazada', 'solo el agente': 'sala_permiso_rechazado',
                'solo el agente o un editor': 'sala_permiso_rechazado', 'recurso desconocido': 'sala_recurso_no_disponible'}.get(datos['error']) if isinstance(datos['error'], str) else None
        raise SalaError('%s contestó con error de backend' % donde,
                        codigo=code or 'sala_error_backend', metadatos=meta)
    if datos.get('ok') is False:
        raise SalaError('%s rechazó la solicitud (ok:false)' % donde, codigo='sala_rechazada', metadatos=meta)
    return datos


def _curl(url, cuerpo=None, espera=ESPERA):
    """curl sigue 302 con GET; su trailer separa métricas sin imprimir cuerpo o URL."""
    cmd = ['curl', '-sS', '-L', '--max-time', str(espera), '--write-out',
           '\nSALA_TRANSPORTE_V1:%{http_code}:%{time_total}:%{size_download}\n']
    if cuerpo is not None:
        cmd += ['-H', 'Content-Type: text/plain;charset=utf-8', '--data-binary', '@-']
    cmd.append(url)
    started = time.monotonic()
    r = subprocess.run(cmd, input=(cuerpo or ''), capture_output=True, text=True)
    body, marker, trailer = r.stdout.rpartition('\nSALA_TRANSPORTE_V1:')
    meta = {'curl_codigo': r.returncode, 'timeout_segundos': espera,
            'latencia_ms': round((time.monotonic() - started) * 1000), 'tipo_respuesta': 'sin_respuesta'}
    fields = re.fullmatch(r'(\d{3}):(\d+(?:\.\d+)?):(\d+)\n?', trailer) if marker else None
    if fields:
        meta.update(estado_http=int(fields.group(1)), latencia_ms=round(float(fields.group(2))*1000), bytes=int(fields.group(3)))
    if r.returncode != 0:
        raise SalaError('curl falló (%s)' % r.returncode,
                        codigo='sala_tiempo_agotado' if r.returncode == 28 else 'sala_transporte_sin_confirmar', metadatos=meta)
    if not fields:
        raise SalaError('curl sin telemetría confirmada', codigo='sala_telemetria_sin_confirmar', metadatos=meta)
    if meta['estado_http'] >= 400:
        code = 'sala_http_' + str(meta['estado_http'])
        raise SalaError('curl HTTP sin respuesta aceptada', codigo=code, metadatos=meta)
    return _TextoRespuesta(body, meta)


def _urllib(url, cuerpo=None, espera=ESPERA):
    datos = cuerpo.encode('utf-8') if cuerpo is not None else None
    cab = {'Content-Type': 'application/json'} if datos else {}
    pet = urllib.request.Request(url, data=datos, headers=cab)
    with urllib.request.urlopen(pet, timeout=espera) as r:
        return r.read().decode('utf-8', 'replace')


def _pedir(url, cuerpo, donde, espera=ESPERA, intentos=INTENTOS, solo_curl=False,
           validar=None):
    """Reintenta sin aceptar como vacío un fallo de transporte o de JSON.

    Las lecturas lentas usan curl -L sin duplicar cada intento con urllib.
    Una escritura usa un único envío: perder la respuesta no prueba que GAS
    no la aplicó. Su consumidor debe conciliar el estado antes de repetirla.
    """
    ultimo = None
    started = time.monotonic()
    if cuerpo is not None:
        intentos, solo_curl = 1, True
    vias = (('curl -L', _curl),) if solo_curl else (
        ('urllib', _urllib), ('curl -L', _curl))
    for intento in range(1, intentos + 1):
        for via, fn in vias:
            try:
                raw = fn(url, cuerpo, espera)
                datos = _leer_json(raw, donde)
                if validar:
                    try:
                        validar(datos)
                    except SalaError as error:
                        error.metadatos = metadatos_publicos({**getattr(raw, 'metadatos', {}), **error.metadatos})
                        raise
                return datos
            except SalaError as e:
                ultimo = e
            except (urllib.error.URLError, OSError, subprocess.SubprocessError) as e:
                ultimo = SalaError('%s por %s sin lectura confirmada' % (donde, via), codigo='sala_red_sin_confirmar')
        if intento < intentos:
            time.sleep(2 ** intento)
    meta = dict(ultimo.metadatos) if ultimo else {}
    meta.update(intentos=intentos, duracion_total_ms=round((time.monotonic()-started)*1000))
    resource = {"GET ?recurso=" + x: x for x in RECURSOS_DIAGNOSTICO}.get(donde)
    if resource:
        meta['recurso'] = resource
    code = ultimo.codigo if ultimo else 'sala_sin_confirmar'
    if cuerpo is not None:
        raise SalaError('%s sin recibo confirmado; no se reenvió. Conciliar el estado '
                        'antes de repetir · código: %s' % (donde, code), codigo=code, metadatos=meta)
    raise SalaError('%s no contestó en %d intentos · código: %s' % (
        donde, intentos, code), codigo=code, metadatos=meta)


def _validar_lectura(recurso, datos):
    """Una respuesta incompleta no acredita un día, cola o reglas vacíos."""
    campos = {
        'dia': (('propuestas', list), ('decisiones', dict)),
        'cola': (('cola', list),),
        'reglas': (('reglas', dict), ('motores', list)),
    }
    if any(not isinstance(datos.get(campo), tipo)
           for campo, tipo in campos.get(recurso, ())):
        raise SalaError('GET ?recurso=%s sin contrato de lectura' % recurso, codigo='sala_contrato_lectura', metadatos={'tipo_respuesta': 'json_objeto'})


def _leer_sheet(url, recurso, validar):
    """Recupera un 404 de lectura con el presupuesto restante, nunca con datos de sonda."""
    started = time.monotonic()
    presupuesto = ESPERA_SHEET * INTENTOS_RELEVO + sum(2 ** i for i in range(1, INTENTOS_RELEVO))
    try:
        return _pedir(url, None, 'GET ?recurso=' + recurso,
                      espera=ESPERA_SHEET, intentos=INTENTOS_RELEVO,
                      solo_curl=True, validar=validar)
    except SalaError as error:
        restante = presupuesto - (time.monotonic() - started)
        if error.codigo != 'sala_http_404' or restante < 1:
            raise
    # Sólo cola/reglas llaman este helper. Un tercer GET fresco ocupa como máximo
    # 20 s de los 122 s originales; ni tiempo adicional ni reenvío de escrituras.
    tope = min(20, restante)
    try:
        data = _pedir(url, None, 'GET ?recurso=' + recurso,
                      espera=tope, intentos=1, solo_curl=True, validar=validar)
    except SalaError as error:
        error.metadatos = metadatos_publicos({**error.metadatos, 'intentos': INTENTOS_RELEVO + 1,
            'duracion_total_ms': round((time.monotonic()-started)*1000)})
        raise
    avisar('SALA_LECTURA_RECUPERADA ' + json.dumps({
        'recurso': recurso, 'causa_previa': 'sala_http_404', 'intentos': INTENTOS_RELEVO + 1,
        'presupuesto_total_segundos': presupuesto, 'timeout_recuperacion_segundos': round(tope, 3),
        'duracion_total_ms': round((time.monotonic()-started)*1000)}, sort_keys=True))
    return data


def get(recurso, **params):
    """Lectura. `recurso` es uno de los que atiende doGet: dia, reglas, cola, catalogo,
    bitacora, envios, expedientes, prompts."""
    q = {'recurso': recurso, 'clave': _clave()}
    q.update({k: v for k, v in params.items() if v is not None})
    url = _exec_url() + '?' + urllib.parse.urlencode(q)
    validar = lambda datos: _validar_lectura(recurso, datos)
    # fresco=1 nunca permite caché: el respaldo conserva sólo datos verificados.
    # Un día sin caché puede tardar más que un recurso ordinario (6 pestañas).
    if recurso == 'dia' and str(params.get('fresco')) == '1':
        return _pedir(url, None, 'GET ?recurso=dia',
                      espera=ESPERA_RELEVO, intentos=INTENTOS_RELEVO,
                      solo_curl=True, validar=validar)
    if recurso in ('cola', 'reglas'):
        return _leer_sheet(url, recurso, validar)
    return _pedir(url, None, 'GET ?recurso=' + recurso,
                  solo_curl=True, validar=validar)


def sonda_get(recurso, espera=20):
    """Una lectura diagnóstica acotada, sin reintentos, POST ni payload público."""
    if recurso not in ('cola', 'reglas') or not isinstance(espera, int) or isinstance(espera, bool) or not 1 <= espera <= 20:
        raise ValueError('sonda_fuera_de_alcance')
    meta = {'recurso': recurso, 'timeout_segundos': espera, 'intentos': 1}
    started = time.monotonic()
    try:
        url = _exec_url() + '?' + urllib.parse.urlencode({'recurso': recurso, 'clave': _clave()})
        raw = _curl(url, None, espera)
        meta.update(getattr(raw, 'metadatos', {}))
        data = _leer_json(raw, 'sonda')
        _validar_lectura(recurso, data)
        meta['tipo_respuesta'] = 'json_objeto'
        result = {'ok': True, 'codigo': 'lectura_confirmada'}
    except SalaError as error:
        meta.update(error.metadatos)
        result = {'ok': False, 'codigo': error.codigo}
    meta['duracion_total_ms'] = round((time.monotonic()-started)*1000)
    return {**result, **metadatos_publicos(meta)}


def post(accion, **campos):
    """Escritura. Se niega en seco a las acciones que son de los editores (INVIOLABLE 3)."""
    if accion in PROHIBIDAS:
        raise SalaError(
            "la nube entra como «agente» y el agente NO decide (INVIOLABLE 3): «%s» está "
            "prohibida aquí. Decidir es de Alejandro y Sayri, en la Sala." % accion)
    if accion in {'proponer', 'ideas', 'arbol'}:
        from contenido_reglas import ContenidoVetado, exigir
        try:
            exigir(campos, ruta=accion)
        except ContenidoVetado as e:
            raise SalaError(str(e)) from e
    cuerpo = {'accion': accion, 'clave': _clave()}
    cuerpo.update(campos)
    return _pedir(_exec_url(), json.dumps(cuerpo), 'POST accion=' + accion,
                  espera=ESPERA_SHEET)


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
