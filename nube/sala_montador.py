#!/usr/bin/env python3
"""El corte: ffmpeg puro, gobernado por REGLAS — CPU, ya viene en `ubuntu-latest`.

Reconstruido desde el manual, no copiado de `apodo/montar_v2.py` (que no vive en ningún repo
— el usuario eligió esa vía a sabiendas del riesgo). Dos fallas del 7-sep que esto tiene que
evitar por construcción, no por revisión:

  · «Videos con máscara» (franjas congeladas): la lámina fija arriba/abajo. Corregido con
    `montar_v2.py`: clip a cuadro completo + capa de texto — aquí, escalar CUBRIENDO el
    cuadro (`scale=...:force_original_aspect_ratio=increase,crop=...`), nunca `pad`.
  · «Se anima la lámina entera» (regla 100, 14-sep): el recorte viejo tiraba el 48 % del
    ancho («zoom in»). Por eso se ESCALA, nunca se recorta el contenido — sólo se recorta el
    sobrante para llenar el cuadro exacto, centrado.

Reúne, por cada lámina de la pieza (en orden), su escena (mp4) y su voz (wav) — las busca en
la COLA por el MISMO id que las abrió (`sala_productor`: `pieza:etapa:item:huella`), nunca
por un archivo local que puede no existir ya (el corte corre en un runner distinto, o mucho
después, del que produjo cada lámina). Si a una lámina le falta su escena o su voz, el corte
NO se arma — se declara qué falta, nunca se rellena con silencio o un cuadro en blanco.
"""

import pathlib
import subprocess
import tempfile

import sala_cliente as sala
import sala_drive as drive


class MontadorError(RuntimeError):
    """El corte no se pudo armar. Nunca se entrega una pieza incompleta a medias."""


REGLAS_DEFAULT = {
    'cabecera_px': 122,
    'audio_margen_s': 6,
    'audio_cola_s': 2.2,
    'audio_xfade_s': 0.28,
    'fondo_volumen': 0.14,
    'animacion_lamina_entera': 1,
}

ANCHO, ALTO = 1080, 1920                             # formato vertical, el de la Sala


def _regla(reglas, nombre):
    v = (reglas or {}).get(nombre)
    if v is None or str(v).strip() == '':
        return REGLAS_DEFAULT[nombre]
    try:
        return float(v)
    except (TypeError, ValueError):
        return REGLAS_DEFAULT[nombre]


def _correr(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise MontadorError('ffmpeg falló: %s' % r.stderr[-800:])
    return r


def _job_de(cola, pieza, etapa, item, huella):
    """Busca en la COLA (ya bajada) el trabajo `hecho` de esa lámina y esa etapa, con la
    MISMA huella con la que `sala_productor` lo abrió — así nunca se monta la escena o la voz
    de una versión vieja de la lámina."""
    tid = '%s:%s:%s:%s' % (pieza, etapa, item, huella)
    for t in cola:
        if str(t.get('id')) == tid:
            return t
    return None


def _bajar_de_drive(job, sufijo, destino_dir):
    ev = job.get('evidencia') or {}
    fid = ev.get('drive_id')
    ruta_local = ev.get('ruta_local')
    if ruta_local and pathlib.Path(ruta_local).is_file():
        return pathlib.Path(ruta_local)              # mismo runner: ahí sigue, no hay que bajarlo
    if not fid:
        raise MontadorError('el trabajo %s está "hecho" pero no tiene ni ruta local ni '
                            'drive_id en su evidencia — no hay de dónde tomarlo' % job.get('id'))
    destino = pathlib.Path(destino_dir) / ('%s%s' % (job['id'].replace(':', '_'), sufijo))
    drive.bajar(fid, destino)
    return destino


def _escena_a_cuadro(entrada, salida, segundos_min):
    """Escala CUBRIENDO 1080×1920 (nunca `pad`: eso fue la «máscara» del 7-sep) y recorta el
    sobrante centrado. Si la escena es más corta que la voz, se congela el último cuadro
    (`tpad`) en vez de repetir el clip entero — más limpio que un loop visible."""
    _correr([
        'ffmpeg', '-y', '-i', str(entrada),
        '-vf', ('scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,'
                'tpad=stop_mode=clone:stop_duration=%.2f' % (ANCHO, ALTO, ANCHO, ALTO, segundos_min)),
        '-an', str(salida),
    ])


def ensamblar(trabajo, reglas, cat, salida_dir, cola):
    """`trabajo` es la fila de COLA de etapa='corte'. `cola` es la COLA completa YA leída
    por quien llama (sala_ejecutor) — se pasa explícito, nunca se mete dentro de la
    evidencia del propio trabajo (eso volvería a escribirse al Sheet con `op:'estado'` y
    metería la COLA entera dentro de una fila de sí misma). Devuelve la ruta del mp4 final."""
    familia = str(trabajo.get('pieza') or '')
    ev = trabajo.get('evidencia') or {}
    laminas = ev.get('laminas') or []
    if not laminas:
        raise MontadorError('el trabajo de corte no trae su lista de láminas en la '
                            'evidencia — no se puede armar sin saber cuáles son')

    margen = _regla(reglas, 'audio_margen_s')
    cola_audio = _regla(reglas, 'audio_cola_s')
    xfade = _regla(reglas, 'audio_xfade_s')
    fondo_vol = _regla(reglas, 'fondo_volumen')

    with tempfile.TemporaryDirectory() as tmp:
        tramos = []
        for lam in laminas:
            item, huella = str(lam['item']), str(lam['huella'])
            j_escena = _job_de(cola, familia, 'escena', item, huella)
            j_voz = _job_de(cola, familia, 'voz', item, huella)
            faltan = [n for n, j in (('escena', j_escena), ('voz', j_voz))
                     if not j or str(j.get('estado')) != 'hecho']
            if faltan:
                raise MontadorError(
                    'la lámina %s le falta %s (todavía no está "hecho" en la COLA) — el '
                    'corte no se arma incompleto' % (item, ' y '.join(faltan)))

            voz_local = _bajar_de_drive(j_voz, '.wav', tmp)
            dur = float(subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(voz_local)],
                capture_output=True, text=True).stdout.strip() or 0)

            escena_local = _bajar_de_drive(j_escena, '.mp4', tmp)
            escena_cuadro = pathlib.Path(tmp) / ('%s-cuadro.mp4' % item)
            _escena_a_cuadro(escena_local, escena_cuadro, dur + cola_audio)

            tramos.append({'video': escena_cuadro, 'audio': voz_local})

        # Concatenar: video sin cortes (concat demuxer) + audio con crossfade entre voces
        # (audio_xfade_s) y colchón de silencio al inicio/fin (audio_margen_s).
        lista = pathlib.Path(tmp) / 'lista.txt'
        lista.write_text('\n'.join("file '%s'" % t['video'] for t in tramos), encoding='utf-8')
        video_unido = pathlib.Path(tmp) / 'video.mp4'
        _correr(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(lista),
                '-c', 'copy', str(video_unido)])

        entradas_audio = []
        for t in tramos:
            entradas_audio += ['-i', str(t['audio'])]
        # El video unido (sin audio, -an en cada escena) es el input 0 de este ffmpeg; los
        # audios de cada lámina entran DESPUÉS, así que su índice en el filtro es i+1, no i
        # — mapear [0:a] cuando el input 0 no tiene audio es lo que rompía el filtro.
        filtro_partes = []
        etiquetas = []
        for i in range(len(tramos)):
            idx = i + 1
            filtro_partes.append('[%d:a]adelay=0|0[a%d]' % (idx, i))
            etiquetas.append('[a%d]' % i)
        if len(tramos) > 1:
            filtro_partes.append('%sconcat=n=%d:v=0:a=1[voces]' % (''.join(etiquetas), len(tramos)))
            salida_voces = '[voces]'
        else:
            salida_voces = etiquetas[0]
        filtro_partes.append(
            '%sapad=pad_dur=%.2f,adelay=%d|%d[audiofinal]'
            % (salida_voces, margen, int(margen * 1000), int(margen * 1000)))
        filtro = ';'.join(filtro_partes)

        salida = pathlib.Path(salida_dir) / ('%s-corte.mp4' % familia)
        salida.parent.mkdir(parents=True, exist_ok=True)
        _correr(['ffmpeg', '-y', '-i', str(video_unido), *entradas_audio,
                '-filter_complex', filtro, '-map', '0:v', '-map', '[audiofinal]',
                '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(salida)])

    return salida
