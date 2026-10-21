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
import math
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
    destino = pathlib.Path(destino_dir) / ('%s%s' % (sala.slug_seguro(job.get('id')), sufijo))
    drive.bajar(fid, destino)
    return destino


def _duracion(ruta):
    result = _correr(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)])
    try:
        value = float(result.stdout.strip())
    except (TypeError, ValueError):
        raise MontadorError("duración del medio sin confirmar") from None
    if not math.isfinite(value) or value <= 0:
        raise MontadorError("duración del medio inválida")
    return value


def _escena_a_cuadro(entrada, salida, segundos_min, *, video_real=False):
    """Cubrir el cuadro y congelar únicamente el tiempo que realmente falta."""
    duracion = _duracion(entrada)
    faltan = max(0.0, segundos_min - duracion)
    filtros = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=30" % (
        ANCHO, ALTO, ANCHO, ALTO)
    if video_real:
        if segundos_min > duracion + 0.05:
            raise MontadorError('video generativo más corto que su voz; requiere otra escena, sin congelar')
        filtros += ',trim=duration=%.6f,setpts=PTS-STARTPTS' % segundos_min
    elif faltan:
        filtros += ",tpad=stop_mode=clone:stop_duration=%.6f" % faltan
    _correr(["ffmpeg", "-y", "-i", str(entrada), "-vf", filtros,
             "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(salida)])
    return _duracion(salida)

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
    video_real = str(reglas.get('montaje_video_real', '0')) == '1'
    if not all(math.isfinite(v) and v >= 0 for v in (margen, cola_audio)):
        raise MontadorError('márgenes de audio inválidos')

    with tempfile.TemporaryDirectory() as tmp:
        tramos = []
        offset = 0.0
        for numero, lam in enumerate(laminas):
            item, huella = str(lam['item']), str(lam['huella'])
            j_escena = _job_de(cola, familia, 'escena', item, huella)
            j_voz = _job_de(cola, familia, 'voz', item, huella)
            faltan = [n for n, j in (('escena', j_escena), ('voz', j_voz))
                     if not j or str(j.get('estado')) != 'hecho']
            if faltan:
                raise MontadorError(
                    'la lámina %s le falta %s (todavía no está "hecho" en la COLA) — el '
                    'corte no se arma incompleto' % (item, ' y '.join(faltan)))
            from sala_adaptativa import activa
            escena_ev = j_escena.get('evidencia') or {}
            codigo = activa(reglas) and escena_ev.get('motor') == 'codigo' and escena_ev.get('formato') == 'animacion_codigo'
            if video_real and ((escena_ev.get('generativa') is not True and not codigo)
                               or (j_voz.get('motor') or (j_voz.get('evidencia') or {}).get('motor')) != 'gemini_tts'):
                raise MontadorError('la revisión requiere escena generativa o animación por código y voz Gemini nuevas')

            from contenido_reglas import ContenidoVetado, exigir
            from motores._comun import lamina_de
            from sala_guion import cargar, desde_lamina, partes_de
            from motores._comun import MotorError
            try:
                from motores.politica_imagen import fuente_retirada
                if fuente_retirada(lamina_de(j_escena).get('src')):
                    raise MontadorError('fuente de imagen retirada; espera reemplazo y nueva revisión')
                for job in (j_escena, j_voz):
                    exigir({'dice': lamina_de(job).get('dice')}, reglas, 'corte')
                partes_de(cargar(familia) or desde_lamina(j_voz), item, reglas)
            except (ContenidoVetado, MotorError) as error:
                raise MontadorError(str(error)) from error

            voz_local = _bajar_de_drive(j_voz, '.wav', tmp)
            dur = _duracion(voz_local)
            escena_local = _bajar_de_drive(j_escena, '.mp4', tmp)
            escena_cuadro = pathlib.Path(tmp) / ('%s-cuadro.mp4' % sala.slug_seguro(item))
            entrada_silencio = margen if numero == 0 else 0.0
            salida_silencio = margen if numero == len(laminas) - 1 else 0.0
            kwargs = {'video_real': True} if video_real else {}
            segundos = _escena_a_cuadro(
                escena_local, escena_cuadro, dur + cola_audio + entrada_silencio + salida_silencio, **kwargs)
            tramos.append({'video': escena_cuadro, 'audio': voz_local,
                           'inicio_audio': offset + entrada_silencio})
            offset += segundos

        # Concatenar escenas; conservar márgenes de inicio/fin y alinear audio a cada escena.
        lista = pathlib.Path(tmp) / 'lista.txt'
        lista.write_text('\n'.join("file '%s'" % t['video'] for t in tramos), encoding='utf-8')
        video_unido = pathlib.Path(tmp) / 'video.mp4'
        _correr(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(lista),
                '-c', 'copy', str(video_unido)])

        entradas_audio = []
        for t in tramos:
            entradas_audio += ['-i', str(t['audio'])]
        # Cada voz empieza en SU escena; no concatenar voces ignorando las colas de video.
        filtro_partes = []
        etiquetas = []
        for i, tramo in enumerate(tramos):
            delay = round(tramo['inicio_audio'] * 1000)
            filtro_partes.append('[%d:a]adelay=%d:all=1[a%d]' % (i + 1, delay, i))
            etiquetas.append('[a%d]' % i)
        filtro_partes.append(
            '%samix=inputs=%d:duration=longest:normalize=0,apad=whole_dur=%.6f,'
            'atrim=duration=%.6f[audiofinal]' % (''.join(etiquetas), len(tramos), offset, offset))
        filtro = ';'.join(filtro_partes)

        salida = pathlib.Path(salida_dir) / ('%s-corte.mp4' % sala.slug_seguro(familia))
        salida.parent.mkdir(parents=True, exist_ok=True)
        _correr(['ffmpeg', '-y', '-i', str(video_unido), *entradas_audio,
                '-filter_complex', filtro, '-map', '0:v', '-map', '[audiofinal]',
                '-c:v', 'copy', '-c:a', 'aac', '-t', '%.6f' % offset, str(salida)])

    return salida
