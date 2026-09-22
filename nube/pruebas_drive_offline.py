#!/usr/bin/env python3
"""Prueba offline de `sala_drive.py`: cuenta de servicio FALSA (RSA propio, nunca habla con
Google) + un servidor de Drive simulado en memoria. Verifica lo que sí se puede verificar sin
credenciales reales: parseo de la cuenta de servicio, manejo de errores, y que
subir/bajar/asegurar_carpeta hacen exactamente lo que dicen (idempotencia incluida).

Esto NO reemplaza la sonda de Drive real (`sala_drive.py` ejecutado directo, con
`GDRIVE_SA_JSON` real) — eso sólo se puede correr con secrets de verdad, en el workflow. Pero
esta prueba SÍ corre en cada push (la llama `verificar.py`, `prueba_drive_logica`), porque no
toca la red y no necesita ningún secret: genera su propia llave RSA de mentira.

`revisar()` es la función que otros usan; `main()` es sólo para correr esto suelto y ver el
detalle con `python3 nube/pruebas_drive_offline.py`.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import sala_drive as sd


def _credencial_falsa():
    d = tempfile.mkdtemp()
    key_path = os.path.join(d, 'k.pem')
    subprocess.run(['openssl', 'genrsa', '-out', key_path, '2048'],
                    capture_output=True, check=True)
    pem = open(key_path).read()
    return {
        "type": "service_account", "project_id": "prueba", "private_key_id": "abc123",
        "private_key": pem, "client_email": "nube-sala@prueba.iam.gserviceaccount.com",
        "client_id": "123", "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/x",
    }


class _RespuestaFalsa:
    def __init__(self, cuerpo, contenido=b''):
        self._cuerpo = cuerpo
        self.content = contenido
        self.status_code = 200
        self.text = json.dumps(cuerpo)

    def json(self):
        return self._cuerpo


def _servidor_falso():
    """Un Drive de mentira que guarda todo en un dict. Devuelve `_peticion` y el estado, para
    poder inspeccionar cuántas carpetas/archivos se crearon."""
    estado = {'carpetas': {}, 'archivos': {}, 'siguiente_id': 1}

    def peticion_falsa(metodo, url, **kw):
        if metodo == 'GET' and url.endswith('/files'):
            import re
            nombre = re.search(r"name = '([^']*)'", kw['params']['q']).group(1)
            for fid, meta in {**estado['carpetas'], **estado['archivos']}.items():
                if meta['name'] == nombre:
                    return _RespuestaFalsa({'files': [{'id': fid, 'name': nombre}]})
            return _RespuestaFalsa({'files': []})
        if metodo in ('POST', 'PATCH') and '/upload/drive/v3/files' in url:
            metadatos = json.loads(kw['files'][0][1][1])
            contenido = kw['files'][1][1][1]
            if metodo == 'PATCH':
                fid = url.rsplit('/', 1)[-1]
            else:
                fid = 'f%d' % estado['siguiente_id']; estado['siguiente_id'] += 1
            estado['archivos'][fid] = {'name': metadatos['name'], 'contenido': contenido}
            return _RespuestaFalsa({'id': fid})
        if metodo == 'POST' and url.endswith('/files'):
            fid = 'c%d' % estado['siguiente_id']; estado['siguiente_id'] += 1
            estado['carpetas'][fid] = {'name': kw['json']['name']}
            return _RespuestaFalsa({'id': fid})
        if metodo == 'GET' and '/files/' in url and kw.get('params', {}).get('alt') == 'media':
            fid = url.rsplit('/', 1)[-1]
            return _RespuestaFalsa({}, contenido=estado['archivos'][fid]['contenido'])
        raise AssertionError('llamada no esperada: %s %s %r' % (metodo, url, kw))

    return peticion_falsa, estado


def revisar():
    """Corre todas las comprobaciones y devuelve una lista de mensajes de FALLA (vacía si
    todo pasó). Restaura sala_drive a su estado original al salir, para no dejar residuo si
    algo más en el mismo proceso vuelve a usar el módulo de verdad."""
    resultados = []            # (ok: bool, msg: str)

    def ok(cond, msg):
        resultados.append((bool(cond), msg))

    _credenciales_original = sd._credenciales_cache
    _token_original = sd._token
    _peticion_original = sd._peticion
    _env_original = os.environ.get('GDRIVE_SA_JSON')

    try:
        sa = _credencial_falsa()
        os.environ['GDRIVE_SA_JSON'] = json.dumps(sa)
        sd._credenciales_cache = None
        cred = sd._credenciales()
        ok(cred.service_account_email == sa['client_email'], 'credenciales parseadas de verdad')

        sd._credenciales_cache = None
        os.environ['GDRIVE_SA_JSON'] = 'esto no es json'
        try:
            sd._credenciales()
            ok(False, 'JSON inválido debió fallar')
        except sd.DriveError:
            ok(True, 'JSON inválido -> DriveError (no un traceback crudo)')

        sd._credenciales_cache = None
        del os.environ['GDRIVE_SA_JSON']
        try:
            sd._credenciales()
            ok(False, 'sin secret debió fallar')
        except sd.DriveError:
            ok(True, 'falta GDRIVE_SA_JSON -> DriveError')

        os.environ['GDRIVE_SA_JSON'] = json.dumps(sa)
        sd._credenciales_cache = None
        sd._token = lambda: 'token-falso'
        peticion_falsa, estado = _servidor_falso()
        sd._peticion = peticion_falsa

        raiz = sd.asegurar_carpeta('RAIZ', 'YOD Editorial')
        otra_vez = sd.asegurar_carpeta('RAIZ', 'YOD Editorial')
        ok(raiz == otra_vez, 'asegurar_carpeta es idempotente (invariante 12 trasladada a Drive)')

        pieza = sd.ruta_carpetas(raiz, 'APODO', 'APODO-L01')
        ok(len(estado['carpetas']) == 3, 'ruta_carpetas creó la cadena completa (3 carpetas)')

        tmp = tempfile.mkdtemp()
        origen = os.path.join(tmp, '_prueba_subida.png')
        with open(origen, 'wb') as f:
            f.write(b'contenido-de-prueba-original')
        fid1 = sd.subir(origen, pieza, 'APODO-L01-r1-original.png')
        fid2 = sd.subir(origen, pieza, 'APODO-L01-r1-original.png')
        ok(fid1 == fid2, 'subir el mismo nombre dos veces NO duplica (reemplaza, mismo id)')
        ok(len(estado['archivos']) == 1, 'sigue habiendo un solo archivo tras la segunda subida')

        destino = sd.bajar(fid1, os.path.join(tmp, '_prueba_bajada.png'))
        ok(open(destino, 'rb').read() == b'contenido-de-prueba-original',
           'el contenido llega íntegro tras subir y bajar')
    finally:
        sd._credenciales_cache = _credenciales_original
        sd._token = _token_original
        sd._peticion = _peticion_original
        if _env_original is None:
            os.environ.pop('GDRIVE_SA_JSON', None)
        else:
            os.environ['GDRIVE_SA_JSON'] = _env_original

    return [msg for cond, msg in resultados if not cond], resultados


def main():
    fallas, resultados = revisar()
    for cond, msg in resultados:
        print(('✓ ' if cond else '✗ ') + msg)
    if fallas:
        print('\n✗ %d falla(s)' % len(fallas))
        return 1
    print('\n✓✓✓ sala_drive.py: lógica completa probada sin tocar Google de verdad')
    return 0


if __name__ == '__main__':
    sys.exit(main())
