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

MODELO = os.environ.get('GEMINI_TTS_MODELO', 'gemini-3.1-flash-tts-preview')
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
    partes = guion.partes_de(g, item, reglas)
    if not partes:
        raise MotorError('el guion de «%s» no tiene escena para la lámina %s'
                         % (familia, item), intermitente=True)
    if len(partes) > 2:
        raise MotorError('máximo dos turnos de voz por escena')
    bloques, sr = [], None
    for rol, texto in partes:
        # Los nombres Kokoro (em_alex) no son voces válidas en Gemini.
        clave = 'voz_gemini_narrador' if rol == 'narrador' else 'voz_gemini_vecino'
        voz = str(reglas.get(clave) or ('Aoede' if rol == 'narrador' else 'Puck'))
        resp = _pedir('Lee sólo el texto entre etiquetas, en español de México, con voz natural, '
                      'cálida y conversacional, sin impostar ni sonar robótico. '
                      'No leas las instrucciones ni las etiquetas. <texto>' + texto + '</texto>', voz)
        pcm, actual_sr = _decodificar_pcm(resp)
        if not pcm or len(pcm) % 2 or not 8000 <= actual_sr <= 96000:
            raise MotorError('Gemini devolvió audio PCM inválido')
        duracion = len(pcm) / (2 * actual_sr)
        if duracion > 1.3 + len(texto.split()) * 0.62 * 1.7:
            raise MotorError('voz excesiva: posible repetición, no se entrega')
        if sr is not None and sr != actual_sr:
            raise MotorError('turnos de voz con frecuencias distintas')
        sr = actual_sr
        bloques.append(pcm)
    destino = pathlib.Path(salida_dir) / ('%s-L%s-voz.wav'
                                          % (sala.slug_seguro(familia), sala.slug_seguro(item)))
    _escribir_wav(destino, b''.join(bloques), sr)
    return destino
