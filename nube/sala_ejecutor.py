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
from motores._comun import MotorError, lamina_de
from contenido_reglas import ContenidoVetado, exigir
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
            exigir({'dice': lamina_de(trabajo).get('dice')}, reglas, 'escena')
            # wan_hf (animación real, gratis e intermitente) primero; si no puede, la cámara
            # sobre la lámina (ffmpeg, siempre sale). `escena_respaldo_camara`=0 la apaga.
            m, razon = motores.elegir_motor('escena', motores_resp, [])
            avisos = []
            ruta = None
            # 24-sep (Alejandro): el orden lo pone lo que él aprueba. Si la cámara va mejor
            # calificada que Wan (sala_puntajes), se empieza por la cámara.
            import sala_puntajes
            if m and m['motor'] == 'wan_hf' and sala_puntajes.orden('escena', ['wan_hf', 'camara'])[0] == 'camara':
                avisos.append('la cámara va mejor calificada que wan_hf por tus decisiones')
                m = None
            if m and m['motor'] == 'wan_hf':
                from motores import escena_wan_hf
                try:
                    ruta = escena_wan_hf.producir(trabajo, reglas, cat, SALIDA)
                    motor_usado = 'wan_hf'
                except MotorError as e:
                    if not e.intermitente:
                        raise
                    # Cuota del día agotada: esperar a mañana en vez de gastar el trabajo en
                    # la cámara, salvo que la REGLA escena_camara_si_cuota diga lo contrario.
                    # 24-sep (Alejandro: «nunca te frenes, siempre usa tu máxima posibilidad de
                    # producción»): por omisión la cámara ENTRA cuando Wan se queda sin cuota; si él
                    # no quiere cámara, la REGLA escena_camara_si_cuota=0 vuelve a esperar.
                    if getattr(e, 'esperar', False) and str(
                            reglas.get('escena_camara_si_cuota', '1')).strip() in ('0', 'no', 'false'):
                        raise
                    avisos.append(str(e))
            else:
                avisos.append('wan_hf no disponible: %s' % (razon if not m else m['motor']))
            # 28-sep · modal_ltx: animación de IA REAL (LTX-Video en Modal, centavos por escena,
            # crédito gratis mensual de Modal). Entra si Wan no pudo; `escena_modal`=0 la apaga.
            if ruta is None and str(reglas.get('escena_modal', '1')).strip() not in ('0', 'no', 'false'):
                from motores import escena_modal
                if escena_modal.disponible():
                    try:
                        ruta = escena_modal.producir(trabajo, reglas, cat, SALIDA)
                        motor_usado = 'modal_ltx'
                    except Exception as e:  # noqa: BLE001
                        avisos.append('modal_ltx: %s' % e)
            # 28-sep · parallax: animación 2.5D hecha con código (profundidad + cámara virtual),
            # gratis y sin cuota. Va entre Wan y la cámara; `escena_parallax`=0 la apaga.
            if ruta is None and str(reglas.get('escena_parallax', '1')).strip() not in ('0', 'no', 'false'):
                try:
                    from motores import escena_parallax
                    ruta = escena_parallax.producir(trabajo, reglas, cat, SALIDA)
                    motor_usado = 'parallax'
                except Exception as e:  # noqa: BLE001 — si falla, la cámara sigue saliendo
                    avisos.append('parallax: %s' % e)
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
            if tira:
                exigir(tira, reglas, 'corte')
            ruta = montador.ensamblar(trabajo, reglas, cat, SALIDA, cola)
            motor_usado = 'ffmpeg'

        else:
            raise MotorError('etapa «%s» no soportada en la nube' % etapa)

    except ContenidoVetado as e:
        return 'fallo', {'motor': None, 'error': str(e), 'segundos': round(time.time() - inicio, 1)}
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
    """Compatibilidad: devuelve trabajos huérfanos, sin reencolarlos a ciegas."""
    from cola_salud import propuestas_rescate
    cambios, _ = propuestas_rescate(cola, habilitadas, ahora_utc=ahora_utc,
                                    minutos=minutos)
    ids = {c['id'] for c in cambios}
    return [t for t in cola if t.get('id') in ids]


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

    from cola_salud import propuestas_rescate
    cambios, ilegibles = propuestas_rescate(cola, habilitadas)
    if ilegibles:
        sala.avisar('⚠ trabajos con fecha ilegible (no se tocan): %s' % ', '.join(ilegibles[:10]))
    if cambios:
        # La segunda lectura evita sobrescribir una fila que otro operador ya cambió.
        try:
            actual = (sala.get('cola') or {}).get('cola') or []
        except sala.SalaError as e:
            sala.avisar('✗ sin segunda lectura no se concilia COLA: %s' % e)
            return 2
        vigentes = {(str(t.get('id')), str(t.get('actualizado'))) for t in actual
                    if t.get('estado') == 'corriendo'}
        seguros = [c for c in cambios
                   if (c['id'], c['evidencia']['actualizado_anterior']) in vigentes]
        for c in seguros:
            sala.avisar('⏸ trabajo huérfano %s: revisión necesaria antes de reintentar' % c['id'])
        if seguros and not args.simular:
            r = sala.post('cola', op='estado', filas=[
                {k: c[k] for k in ('id', 'estado', 'evidencia', 'bloqueado_por')}
                for c in seguros])
            if not r.get('ok') or r.get('ignoradas'):
                sala.avisar('✗ GAS no confirmó toda la conciliación; revisar COLA')
                return 2
        if seguros:
            ids_seguros = {c['id'] for c in seguros}
            # No dejar que una fila aún cacheada se cuele como pendiente.
            for t in cola:
                if t.get('id') in ids_seguros:
                    t['estado'] = 'fallo'

    # 23-sep: lo que se produjo pero NO subió a Drive (la llave de la cuenta de servicio
    # fallaba) queda «hecho» y el corte nunca lo encuentra. Escena y voz son gratis y tardan
    # segundos: se rehacen, una vez por día, hasta que suban.
    if drive_raiz:
        hoy = sala.hoy_hermosillo()
        sin_drive = [t for t in cola if str(t.get('estado')) == 'hecho'
                     and str(t.get('etapa')) in ('escena', 'voz')
                     and isinstance(t.get('evidencia'), dict)
                     and not t['evidencia'].get('drive_id') and t['evidencia'].get('aviso_subida')
                     and (t['evidencia'].get('reintento_drive') != hoy
                          or int(t['evidencia'].get('reintentos_hoy') or 0) < 3)]
        for t in sin_drive:
            t['estado'] = 'pendiente'
            # 23-sep: una vez al día no alcanzó — Drive se arregló a media tarde y el corte del Apodo
            # se quedó esperando hasta mañana. Hasta 3 intentos por día (escena/voz tardan segundos).
            n = int(t['evidencia'].get('reintentos_hoy') or 0) if t['evidencia'].get('reintento_drive') == hoy else 0
            t['evidencia'] = dict(t['evidencia'], reintento_drive=hoy, reintentos_hoy=n + 1)
        if sin_drive and not args.simular:
            sala.avisar('↺ %d producto(s) sin subir a Drive se rehacen para que el corte los '
                        'encuentre' % len(sin_drive))
            sala.post('cola', op='estado', filas=[{'id': t['id'], 'estado': 'pendiente',
                                                    'evidencia': t['evidencia']} for t in sin_drive])

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
            sala.avisar('  ✓ hecho · motor=%s · %ss%s' % (ev.get('motor'), ev.get('segundos_produccion'),
                        (' · ⚠ NO subió a Drive: %s' % sala.redactar(str(ev['aviso_subida']))[:300])
                        if ev.get('aviso_subida') else ' · en Drive'))
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
