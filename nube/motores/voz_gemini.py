#!/usr/bin/env python3
"""Gemini TTS: el respaldo de voz, encendido en la hoja MOTORES real (`gemini_tts`,
`tope_dia` 12) desde antes de Kokoro. `sala_motores.elegir_motor_voz` lo usa cuando
`voz_motor` no pide Kokoro, o cuando Alejandro apaga Kokoro desde REGLAS.

Endpoint confirmado en vivo (no adivinado): POST a
`https://generativelanguage.googleapis.com/v1beta/models/<modelo>:generateContent`
con una clave inválida devuelve el error estructurado real de Google
(`error.code/message/status`) — así se probó el manejo de errores de este archivo sin
gastar cuota de una clave de verdad.

La respuesta trae el audio en `candidates[0].content.parts[0].inlineData.data` (base64),
PCM de 16 bits mono — el `mimeType` lo confirma (`audio/L16;codec=pcm;rate=<sr>`); de ahí se
lee el sample rate real en vez de asumirlo.
"""

import base64
import json
import os
import pathlib
import urllib.error
import urllib.request

import sala_cliente as sala
import sala_guion as guion
from motores._comun import MotorError

MODELO = os.environ.get('GEMINI_TTS_MODELO', 'gemini-2.5-flash-preview-tts')
URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent' % MODELO
ESPERA = 60


def _clave():
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if not k:
        raise MotorError('falta GEMINI_API_KEY (secret de Actions)', intermitente=True)
    return k


def _pedir(texto, voz):
    cuerpo = json.dumps({
        'contents': [{'parts': [{'text': texto}]}],
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voz}}},
        },
    }).encode('utf-8')
    pet = urllib.request.Request(
        URL + '?key=' + _clave(), data=cuerpo,
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        crudo = e.read().decode('utf-8', 'replace')
        try:
            err = json.loads(crudo).get('error') or {}
        except ValueError:
            err = {}
        mensaje = err.get('message') or crudo[:200]
        codigo = err.get('code') or e.code
        # 429 (cuota) y 503 (ocupado) son intermitentes: el trabajo se queda pendiente y se
        # reintenta; el resto (clave inválida, request mal formado) es un fallo real.
        raise MotorError('Gemini TTS %s: %s' % (codigo, sala.redactar(mensaje)),
                         intermitente=(codigo in (429, 503)))
    except urllib.error.URLError as e:
        raise MotorError('Gemini TTS no contestó: %s' % sala.redactar(str(e)), intermitente=True)


def _decodificar_pcm(resp):
    try:
        partes = resp['candidates'][0]['content']['parts']
        inline = next(p['inlineData'] for p in partes if 'inlineData' in p)
    except (KeyError, IndexError, StopIteration):
        raise MotorError('Gemini TTS contestó sin audio: %s' % json.dumps(resp)[:200])
    datos = base64.b64decode(inline['data'])
    tipo = inline.get('mimeType', '')
    sr = 24000
    if 'rate=' in tipo:
        try:
            sr = int(tipo.split('rate=')[1].split(';')[0])
        except (ValueError, IndexError):
            pass
    return datos, sr


def _escribir_wav(ruta, pcm_bytes, sr):
    import wave
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm_bytes)


def producir(trabajo, reglas, cat, salida_dir):
    familia = str(trabajo.get('pieza') or '')
    item = str(trabajo.get('item') or '')
    g = guion.cargar(familia) or guion.desde_lamina(trabajo)
    if not g:
        raise MotorError('no hay guion de video para «%s»' % familia, intermitente=True)
    partes = guion.partes_de(g, item)
    if not partes:
        raise MotorError('el guion de «%s» no tiene escena para la lámina %s'
                         % (familia, item), intermitente=True)
    if len(partes) > 1:
        # Gemini TTS de una sola voz por llamada: para una lámina con narrador Y vecino se
        # necesitarían llamadas separadas + mezcla, que es justo lo que Kokoro ya resuelve
        # nativo. Se declara la limitación en vez de fingir que se resolvió.
        raise MotorError('la lámina %s de %s tiene %d voces distintas; el respaldo Gemini '
                         'sólo hace una voz por llamada — usa Kokoro para ésta'
                         % (item, familia, len(partes)))
    rol, texto = partes[0]
    voz = guion.voz_de(reglas, rol, g)
    resp = _pedir(texto, voz)
    pcm, sr = _decodificar_pcm(resp)
    destino = pathlib.Path(salida_dir) / ('%s-L%s-voz.wav'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    _escribir_wav(destino, pcm, sr)
    return destino
