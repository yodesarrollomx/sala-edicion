#!/usr/bin/env python3
"""El ejecutor: toma trabajos `pendiente` de la COLA y los produce de verdad — escena, voz,
corte. Es la pieza que la Fase 1 dejó sin construir a propósito (la invariante 54 exige que
ejecutar lo encienda Alejandro) y que esta fase habilita, con el seguro puesto de fábrica:
`nube_ejecuta_etapas` nace VACÍA. Sin esa REGLA con algo adentro, este script no toca nada.

Lo que NO ejecuta nunca, aunque se lo pidan: `imagen` (mflux, local) y `prospecto` (también
depende de mflux). Sólo `escena`, `voz` y `corte` pasan por aquí — son los que corren en un
runner sin GPU (API o CPU pura).

Reglas que cuida, las mismas que `sala_productor.py` y en el mismo orden:

  · INVIOLABLE 10 / PASO 0 — con una petición abierta, no se ejecuta nada.
  · Invariante 53 — nunca dos ejecutores a la vez: `concurrency:` en el workflow.
  · Invariante 48 — la evidencia de cada trabajo (md5, segundos, motor, código) se escribe en
    la misma fila de COLA, con `accion:'cola'` `op:'estado'` — nunca inventa un trabajo nuevo.
  · Un motor intermitente (`MotorError(intermitente=True)`) deja el trabajo en `pendiente`,
    NUNCA en `fallo` — para que el siguiente intento (o la Mac) lo recoja. Un fallo real sí
    se marca `fallo`, con el motivo en la evidencia, para que no se reintente a ciegas.
"""

import argparse
import json
import hashlib
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_catalogo as catalogo
import sala_cliente as sala
import sala_drive as drive
import sala_montador as montador
import sala_motores as motores
from sala_productor import en_silencio, entero, regla
from motores._comun import MotorError
from motores import voz_gemini, voz_kokoro

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MANIFIESTO = RAIZ / 'datos' / 'manifiesto.json'
SALIDA = RAIZ / '.producido'                        # nunca se commitea (ver .gitignore)

ETAPAS_SOPORTADAS = {'escena', 'voz', 'corte', 'prospecto'}
MOTORES_VOZ = {'kokoro': voz_kokoro, 'gemini_tts': voz_gemini}


def etapas_habilitadas(reglas):
    crudo = str((reglas or {}).get('nube_ejecuta_etapas') or '').strip()
    pedidas = {x.strip() for x in crudo.split(',') if x.strip()}
    ignoradas = pedidas - ETAPAS_SOPORTADAS
    return pedidas & ETAPAS_SOPORTADAS, ignoradas


def duracion_de(ruta):
    """Segundos de un audio/video, vía ffprobe — para la evidencia (regla 48)."""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(ruta)],
            capture_output=True, text=True, timeout=30)
        return round(float(r.stdout.strip()), 2)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def subir_producto(ruta, familia, drive_raiz, cat_reglas):
    """Sube el archivo producido a `YOD Editorial/<PIEZA>/_producidos/`. No es una revisión
    del catálogo (eso lo sigue haciendo `accion:catalogar` desde `sala_publicar.py`, en la
    Mac) — es un artefacto de producción, separado a propósito."""
    if not drive_raiz:
        return None, 'sin drive_raiz configurado (REGLA): no se sube, se deja sólo local'
    try:
        carpeta = drive.ruta_carpetas(drive_raiz, familia.upper(), '_producidos')
        fid = drive.subir(str(ruta), carpeta)
        return fid, None
    except drive.DriveError as e:
        return None, str(e)


def _leer_tira(pid):
    try:
        return json.loads((RAIZ / 'datos' / 'tiras' / ('%s.json' % pid)).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None


def ejecutar_uno(trabajo, reglas, motores_resp, cat, drive_raiz, cola):
    """Devuelve (estado_nuevo, evidencia_dict)."""
    etapa = str(trabajo.get('etapa'))
    inicio = time.time()
    extra = {}

    try:
        if etapa == 'voz':
            m, razon = motores.elegir_motor_voz(reglas, motores_resp, [])
            if not m:
                raise MotorError('ningún motor de voz disponible: %s' % razon, intermitente=True)
            impl = MOTORES_VOZ.get(m['motor'])
            if not impl:
                raise MotorError('motor de voz «%s» no tiene implementación en la nube'
                                 % m['motor'], intermitente=True)
            ruta = impl.producir(trabajo, reglas, cat, SALIDA)
            motor_usado = m['motor']

        elif etapa == 'escena':
            # wan_hf (animación real, gratis e intermitente) primero; si no puede, la cámara
            # sobre la lámina (ffmpeg, siempre sale). `escena_respaldo_camara`=0 la apaga.
            m, razon = motores.elegir_motor('escena', motores_resp, [])
            avisos = []
            ruta = None
            if m and m['motor'] == 'wan_hf':
                from motores import escena_wan_hf
                try:
                    ruta = escena_wan_hf.producir(trabajo, reglas, cat, SALIDA)
                    motor_usado = 'wan_hf'
                except MotorError as e:
                    if not e.intermitente:
                        raise
                    avisos.append(str(e))
            else:
                avisos.append('wan_hf no disponible: %s' % (razon if not m else m['motor']))
            if ruta is None:
                if str(reglas.get('escena_respaldo_camara', '1')).strip() in ('0', 'no', 'false'):
                    raise MotorError('sin animación y la cámara de respaldo está apagada: %s'
                                     % ' · '.join(avisos), intermitente=True)
                from motores import escena_camara
                ruta = escena_camara.producir(trabajo, reglas, cat, SALIDA)
                motor_usado = 'camara'

        elif etapa == 'prospecto':
            from motores import prospecto
            ruta, extra = prospecto.producir(trabajo, reglas, cat, SALIDA, cola)
            motor_usado = extra.pop('motor')

        elif etapa == 'corte':
            ev0 = trabajo.get('evidencia') or {}
            tira = _leer_tira(ev0.get('de'))
            if not ev0.get('laminas'):
                # Un corte que perdió su lista (por el bug de arriba) la rehace desde la tira
                # viva de su pieza, con la misma huella que usa el productor para escena/voz.
                from sala_mesa import tiras_por_pieza
                from sala_productor import huella_insumo
                tid_tira, tira = (tiras_por_pieza().get(str(trabajo.get('pieza'))) or (None, None))
                if tira:
                    ev0 = dict(ev0, de=ev0.get('de') or tid_tira, laminas=[
                        {'item': str(l.get('n')), 'huella': huella_insumo(l, cat)[0]}
                        for l in tira.get('laminas') or []])
                    trabajo['evidencia'] = ev0
            if tira and len(ev0.get('laminas') or []) < len(tira.get('laminas') or []):
                raise MotorError('corte incompleto: trae %d de las %d láminas de la pieza — lo '
                                 'abrió un productor viejo; el nuevo abre el corte de la pieza entera'
                                 % (len(ev0.get('laminas') or []), len(tira.get('laminas') or [])))
            ruta = montador.ensamblar(trabajo, reglas, cat, SALIDA, cola)
            motor_usado = 'ffmpeg'

        else:
            raise MotorError('etapa «%s» no soportada en la nube' % etapa)

    except MotorError as e:
        ev = {'motor': None, 'error': str(e), 'segundos': round(time.time() - inicio, 1)}
        return ('pendiente' if e.intermitente else 'fallo'), ev
    except montador.MontadorError as e:
        # El montador nunca es "intermitente": si a una lámina le falta su escena o su voz,
        # reintentar el corte YA MISMO no cambia nada — hace falta que ESA lámina termine
        # primero. Se queda pendiente (no es un fallo del corte en sí) para que el propio
        # ejecutor lo retome cuando las demás piezas estén listas.
        ev = {'motor': 'ffmpeg', 'error': str(e), 'segundos': round(time.time() - inicio, 1)}
        return 'pendiente', ev

    segundos = round(time.time() - inicio, 1)
    md5 = hashlib.md5(pathlib.Path(ruta).read_bytes()).hexdigest()
    duracion = duracion_de(ruta)
    drive_id, error_subida = subir_producto(ruta, str(trabajo.get('pieza') or ''),
                                            drive_raiz, reglas)
    ev = {'motor': motor_usado, 'md5': md5, 'segundos_produccion': segundos,
          'duracion_s': duracion, 'ruta_local': str(ruta), 'drive_id': drive_id}
    ev.update(extra)
    if error_subida:
        ev['aviso_subida'] = error_subida
    return 'hecho', ev


ATORADO_MIN = 180


def atorados(cola, habilitadas, ahora_utc=None, minutos=ATORADO_MIN):
    """Trabajos en `corriendo` que nadie está trabajando: sólo corre un ejecutor a la vez
    (invariante 53), así que un `corriendo` que no se ha tocado en horas es de una corrida que
    murió (tope del runner, cancelada, o la Mac antes de la mudanza del 21-sep). Sin rescate se
    quedan así para siempre: la Sala los cuenta como «en producción» y nadie los vuelve a tomar.
    Sin fecha legible no se toca (lado seguro). `actualizado` viene en hora de Hermosillo."""
    import datetime
    ahora_utc = ahora_utc or datetime.datetime.now(datetime.timezone.utc)
    fuera = []
    for t in cola:
        if str(t.get('estado')) != 'corriendo' or str(t.get('etapa')) not in habilitadas:
            continue
        try:
            f = datetime.datetime.strptime(str(t.get('actualizado') or '')[:19], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            continue
        f = f.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-7)))
        if (ahora_utc - f).total_seconds() > minutos * 60:
            fuera.append(t)
    return fuera


def main():
    ap = argparse.ArgumentParser(description='El ejecutor de la Sala: produce de verdad.')
    ap.add_argument('--simular', action='store_true', help='dice qué ejecutaría y no ejecuta nada')
    ap.add_argument('--ignorar-silencio', action='store_true', help='sólo para pruebas a mano')
    ap.add_argument('--limite', type=int, default=5, help='trabajos por corrida como máximo')
    args = ap.parse_args()

    sala.enmascarar_en_actions()
    SALIDA.mkdir(exist_ok=True)

    if MANIFIESTO.exists():
        import json
        try:
            pet = json.loads(MANIFIESTO.read_text(encoding='utf-8')).get('peticiones') or []
        except ValueError:
            pet = []
        abiertas = [x for x in pet if isinstance(x, dict) and x.get('estado') != 'cumplida']
        if abiertas:
            sala.avisar('PASO 0 · %d petición(es) abierta(s). No se ejecuta nada '
                        '(INVIOLABLE 10).' % len(abiertas))
            return 0

    try:
        r = sala.get('reglas')
        reglas, motores_resp = r.get('reglas') or {}, r.get('motores') or []
        cola = (sala.get('cola') or {}).get('cola') or []
        for t in cola:   # 23-sep: el Sheet devuelve la evidencia como TEXTO JSON; aquí es un dict
            if isinstance(t.get('evidencia'), str):
                try:
                    t['evidencia'] = json.loads(t['evidencia'] or '{}')
                except ValueError:
                    t['evidencia'] = {'crudo': t['evidencia']}
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer REGLAS/COLA: %s' % e)
        return 2

    habilitadas, ignoradas = etapas_habilitadas(reglas)
    if ignoradas:
        sala.avisar('⚠ nube_ejecuta_etapas pide «%s», que la nube no soporta (sólo %s) — '
                    'se ignoran' % (', '.join(sorted(ignoradas)), ', '.join(sorted(ETAPAS_SOPORTADAS))))
    if not habilitadas:
        sala.avisar('nube_ejecuta_etapas está vacía: el seguro de fábrica sigue puesto '
                    '(invariante 54). Nada que ejecutar.')
        return 0

    desde = entero(regla(reglas, 'productor_silencio_desde')[0], 23)
    hasta = entero(regla(reglas, 'productor_silencio_hasta')[0], 7)
    hora = sala.hora_hermosillo()
    if en_silencio(desde, hasta, hora) and not args.ignorar_silencio:
        sala.avisar('horario quieto (%d-%d h Hermosillo, ahora %d h): el ejecutor se calla.'
                    % (desde, hasta, hora))
        return 0

    try:
        cat = catalogo.cargar()
    except sala.SalaError as e:
        sala.avisar('✗ sin catálogo, no se ejecuta nada: %s' % e)
        return 2

    drive_raiz = str(reglas.get('drive_raiz') or '').strip() or None

    viejos = atorados(cola, habilitadas)
    if viejos:
        for t in viejos:
            sala.avisar('↺ rescatado · %s (en «corriendo» sin tocar desde %s)' % (t.get('id'), t.get('actualizado')))
            t['estado'] = 'pendiente'
        if not args.simular:
            sala.post('cola', op='estado', filas=[{'id': t.get('id'), 'estado': 'pendiente',
                'evidencia': {'rescatado': 'corriendo sin tocar desde %s' % t.get('actualizado')}} for t in viejos])

    pendientes = [t for t in cola if str(t.get('estado')) == 'pendiente'
                  and str(t.get('etapa')) in habilitadas]
    # Sin esto, --limite cortaba en el orden que devolviera el Sheet — casi siempre orden de
    # inserción, no de importancia. Con la COLA llena, un corte (prioridad 7: termina una
    # pieza entera) podía quedarse dos horas detrás de varios prospectos (prioridad 3: abren
    # candidatas de una lámina rechazada) sólo por haber llegado después. Mayor prioridad
    # primero; a igual prioridad, se respeta el orden en que ya venían (sort estable).
    pendientes.sort(key=lambda t: -entero(t.get('prioridad'), 5))
    sala.avisar('COLA: %d trabajo(s) pendiente(s) en %s (de %d totales)'
               % (len(pendientes), sorted(habilitadas), len(cola)))

    if not pendientes:
        sala.avisar('✓ nada que ejecutar.')
        return 0

    if args.simular:
        for t in pendientes[:args.limite]:
            sala.avisar('  — simulación —  %s' % t.get('id'))
        return 0

    tope_min = entero(regla(reglas, 'nube_tope_minutos')[0], 15)
    limite_ts = time.time() + tope_min * 60
    hechos = fallados = pendientes_de_nuevo = 0

    for t in pendientes[:args.limite]:
        if time.time() >= limite_ts:
            sala.avisar('⏱ tope de %d min alcanzado; el resto se queda para la próxima corrida'
                       % tope_min)
            break

        tid = t.get('id')
        sala.post('cola', op='estado', filas=[{'id': tid, 'estado': 'corriendo'}])
        sala.avisar('▶ %s' % tid)

        try:
            estado, ev = ejecutar_uno(t, reglas, motores_resp, cat, drive_raiz, cola)
        except Exception as e:   # 23-sep: una excepción dejaba el trabajo en «corriendo» y tumbaba la corrida
            estado, ev = 'fallo', {'error': 'excepción %s: %s' % (type(e).__name__, str(e)[:300])}
        # 23-sep: la evidencia NUEVA se suma a la de entrada, no la reemplaza. Antes un intento
        # intermitente escribía sólo {motor, error} y borraba de qué carta y qué lámina era el
        # trabajo (o la lista de láminas de un corte): el siguiente intento ya no sabía qué hacer.
        entrada = t.get('evidencia') if isinstance(t.get('evidencia'), dict) else {}
        entrada = {k: v for k, v in entrada.items() if k not in ('error', 'segundos', 'rescatado')}
        sala.post('cola', op='estado', filas=[{'id': tid, 'estado': estado, 'evidencia': {**entrada, **ev},
                                               'motor': ev.get('motor') or ''}])

        if estado == 'hecho':
            hechos += 1
            sala.avisar('  ✓ hecho · motor=%s · %ss' % (ev.get('motor'), ev.get('segundos_produccion')))
        elif estado == 'fallo':
            fallados += 1
            sala.avisar('  ✗ fallo · %s' % ev.get('error'))
        else:
            pendientes_de_nuevo += 1
            sala.avisar('  … sigue pendiente (intermitente) · %s' % ev.get('error'))

    sala.avisar('resumen: %d hecho(s) · %d fallo(s) · %d sigue(n) pendiente(s)'
               % (hechos, fallados, pendientes_de_nuevo))
    # Un fallo de UN trabajo no tumba la corrida ni abre un issue: ya queda escrito en su
    # propia fila de COLA (evidencia.error), visible desde Ajustes de la Sala, y un motor
    # intermitente lo reintenta solo. El código de salida (y el aviso al issue del workflow)
    # se reserva para cuando la corrida ENTERA no pudo trabajar — REGLAS, COLA o el catálogo
    # no contestaron — que es el fallo del que nadie más se entera si no se avisa aquí.
    return 0


if __name__ == '__main__':
    sys.exit(main())
