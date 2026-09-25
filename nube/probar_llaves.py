#!/usr/bin/env python3
"""Prueba de SOLO LECTURA de las tres llaves de la nube (25-sep-2026).

Después de la fuga del 22-sep las tres llaves se repusieron el 23-sep. Esto confirma que
sirven sin producir nada: Drive pide un token (la firma de la llave), Gemini lista modelos
y Hugging Face pregunta «¿quién soy?». No genera, no sube, no escribe en el Sheet.
Imprime solo ✅/⛔ y, de Drive, los primeros 8 caracteres del id de la llave (no es secreto:
Google lo muestra en la consola). Nunca imprime una llave.
"""
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
malas = 0


def pide(url, cabeceras=None):
    req = urllib.request.Request(url, headers=cabeceras or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode() or '{}')


def informa(nombre, ok, detalle):
    global malas
    if not ok:
        malas += 1
    print(('✅ ' if ok else '⛔ ') + nombre + ' — ' + detalle)


# 1 · Drive: pedir un token con la cuenta de servicio (falla si la firma es de una llave borrada)
try:
    import sala_drive
    sala_drive._token()
    informa('Drive (GDRIVE_SA_JSON)', True, 'la llave %s… firma y Google entrega token' % sala_drive._llave_id)
except Exception as e:
    informa('Drive (GDRIVE_SA_JSON)', False, '%s: %s' % (type(e).__name__, str(e)[:160]))

# 2 · Gemini: listar modelos (gratis, no genera nada)
k = os.environ.get('GEMINI_API_KEY', '').strip()
try:
    if not k:
        raise ValueError('secreto vacío')
    st, j = pide('https://generativelanguage.googleapis.com/v1beta/models?pageSize=1',
                 {'x-goog-api-key': k})
    informa('Gemini (GEMINI_API_KEY)', st == 200, 'la API contesta (%d modelo(s) en la muestra)' % len(j.get('models', [])))
except urllib.error.HTTPError as e:
    informa('Gemini (GEMINI_API_KEY)', False, 'HTTP %d' % e.code)
except Exception as e:
    informa('Gemini (GEMINI_API_KEY)', False, str(e)[:160])

# 3 · Hugging Face: ¿quién soy?
k = os.environ.get('HF_TOKEN', '').strip()
try:
    if not k:
        raise ValueError('secreto vacío')
    st, j = pide('https://huggingface.co/api/whoami-v2', {'Authorization': 'Bearer ' + k})
    rol = ((j.get('auth') or {}).get('accessToken') or {}).get('role', '?')
    informa('Hugging Face (HF_TOKEN)', st == 200, 'cuenta «%s», permiso %s' % (j.get('name', '?'), rol))
except urllib.error.HTTPError as e:
    informa('Hugging Face (HF_TOKEN)', False, 'HTTP %d (token vencido o inválido)' % e.code)
except Exception as e:
    informa('Hugging Face (HF_TOKEN)', False, str(e)[:160])

print('resumen: %d de 3 llaves con problema' % malas)
sys.exit(1 if malas else 0)
