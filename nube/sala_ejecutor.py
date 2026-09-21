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

ETAPAS_SOPORTADAS = {'escena', 'voz', 'corte'}
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


def ejecutar_uno(trabajo, reglas, motores_resp, cat, drive_raiz, cola):
    """Devuelve (estado_nuevo, evidencia_dict)."""
    etapa = str(trabajo.get('etapa'))
    inicio = time.time()

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
            m, razon = motores.elegir_motor('escena', motores_resp, [])
            if not m or m['motor'] != 'wan_hf':
                raise MotorError('sin motor de escena disponible en la nube: %s'
                                 % (razon if not m else 'sólo "%s" implementado' % m['motor']),
                                 intermitente=True)
            from motores import escena_wan_hf
            ruta = escena_wan_hf.producir(trabajo, reglas, cat, SALIDA)
            motor_usado = 'wan_hf'

        elif etapa == 'corte':
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
    if error_subida:
        ev['aviso_subida'] = error_subida
    return 'hecho', ev


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

    pendientes = [t for t in cola if str(t.get('estado')) == 'pendiente'
                  and str(t.get('etapa')) in habilitadas]
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

        estado, ev = ejecutar_uno(t, reglas, motores_resp, cat, drive_raiz, cola)
        sala.post('cola', op='estado', filas=[{'id': tid, 'estado': estado, 'evidencia': ev,
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
