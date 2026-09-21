#!/usr/bin/env python3
"""Kokoro-82M local, por ONNX Runtime — el motor de voz que Alejandro eligió a oído el
14-sep, tras escuchar cinco. Corre en CPU, sin API, sin cuota: por eso es el que se intenta
primero (`sala_motores.elegir_motor_voz`) cuando `voz_motor=kokoro`.

Paquete real: `kokoro-onnx` (PyPI, MIT). Confirmado desde este mismo repo de herramientas:
  pip install kokoro-onnx
  Kokoro(model_path, voices_path).create(texto, voz, speed=1.0, lang='es') -> (muestras, sr)

Los pesos NO viven en el repo (serían ~300 MB en un repo que además es público) ni se
inventan aquí: se descargan una vez y se cachean entre corridas (`actions/cache`,
`sala-ejecutor.yml`) desde las liga oficiales del proyecto (confirmadas en el propio README
del paquete, vía `pip show`):
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin

**Límite honesto:** esta descarga no se pudo probar desde el sandbox de desarrollo — la
política de red de esa sesión bloquea github.com salvo los repos ya adjuntos. El paquete SÍ
se instaló y se introspeccionó de verdad (la firma de `Kokoro()`/`.create()` de este archivo
es la real, no una adivinada). La primera síntesis real sólo se puede confirmar en el propio
workflow, con internet normal — por eso la Fase E pide escuchar una voz de verdad antes de
encender el resto.
"""

import os
import pathlib
import wave

import numpy as np

import sala_guion as guion
from motores._comun import MotorError

MODELO = os.environ.get('KOKORO_MODEL_PATH', str(pathlib.Path(__file__).resolve()
                                                  .parent.parent / '.cache' / 'kokoro' / 'kokoro-v1.0.onnx'))
VOCES = os.environ.get('KOKORO_VOICES_PATH', str(pathlib.Path(__file__).resolve()
                                                  .parent.parent / '.cache' / 'kokoro' / 'voices-v1.0.bin'))

_kokoro = None


def _instancia():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    if not pathlib.Path(MODELO).is_file() or not pathlib.Path(VOCES).is_file():
        raise MotorError(
            'faltan los pesos de Kokoro (%s / %s) — se descargan una vez y se cachean en el '
            'workflow, no viven en el repo' % (MODELO, VOCES), intermitente=True)
    try:
        from kokoro_onnx import Kokoro
    except ImportError as e:
        raise MotorError('falta el paquete kokoro-onnx: %s' % e)
    try:
        _kokoro = Kokoro(MODELO, VOCES)
    except Exception as e:
        raise MotorError('Kokoro no pudo cargar sus pesos: %s' % e)
    return _kokoro


def _escribir_wav(ruta, muestras, sr):
    """WAV plano por `wave` (stdlib): sin depender de `soundfile` para una sola conversión
    float32 [-1,1] -> int16 PCM."""
    pcm = np.clip(muestras, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def producir(trabajo, reglas, cat, salida_dir):
    """`trabajo` es una fila de COLA (etapa='voz'). Sintetiza CADA parte de la lámina
    (narrador/vecino, en orden) y las concatena con el margen de la REGLA `audio_xfade_s`
    entre ellas — el montador vuelve a mezclar esto con el video, así que aquí basta un
    empalme simple, no el crossfade fino del corte completo."""
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    g = guion.cargar(familia)
    if not g:
        raise MotorError('no hay guion de video para «%s» (datos/guiones/%s-VIDEO.json)'
                         % (familia, familia.upper()), intermitente=True)
    partes = guion.partes_de(g, item)
    if not partes:
        raise MotorError('el guion de «%s» no tiene una escena para la lámina %s'
                         % (familia, item), intermitente=True)

    k = _instancia()
    xfade = float((reglas or {}).get('audio_xfade_s') or 0.28)
    sr_final = None
    tramos = []
    for rol, texto in partes:
        voz = guion.voz_de(reglas, rol, g)
        try:
            muestras, sr = k.create(texto, voz, speed=1.0, lang='es')
        except Exception as e:
            raise MotorError('Kokoro falló sintetizando «%s…» con la voz %s: %s'
                             % (texto[:40], voz, e))
        sr_final = sr_final or sr
        tramos.append(muestras)

    silencio = np.zeros(int(xfade * sr_final), dtype=np.float32)
    completo = tramos[0]
    for t in tramos[1:]:
        completo = np.concatenate([completo, silencio, t])

    destino = pathlib.Path(salida_dir) / ('%s-L%s-voz.wav' % (familia, item))
    _escribir_wav(destino, completo, sr_final)
    return destino
