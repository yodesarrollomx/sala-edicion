#!/usr/bin/env python3
"""Cliente de Drive de la Sala: cuenta de servicio, tres operaciones y nada más.

Por qué existe: `datos/catalogo.json` ya trae 114 revisiones con sus IDs de Drive
(`drive_original`, `drive_prueba`), e `index.html` ya pinta desde ahí (`deDrive()`,
`index.html:744`). Lo que faltaba era que la NUBE pudiera subir y bajar como otro cliente más
— hasta hoy sólo la Mac lo hacía.

Identidad: una CUENTA DE SERVICIO, no la cuenta personal de Alejandro. La carpeta
«YOD Editorial» se comparte UNA vez con su correo (…@…iam.gserviceaccount.com) como Editor;
desde ahí la nube sube/baja/organiza sin tocar el resto de ningún Drive personal.

INVIOLABLE 2 aplica igual aquí: el JSON de la cuenta de servicio llega SIEMPRE por
`GDRIVE_SA_JSON` (secret de Actions), nunca por archivo del repo, nunca impreso.

Estructura que se respeta (invariante 28, «las imágenes viven en Drive; el Sheet sólo lleva
letras»): `YOD Editorial/<PIEZA>/<SERIAL>/` con `-original.png` (maestro) y `-prueba.jpg`
(ligera, sellada). **Una prueba nunca se publica** — subir_revision() lo exige por firma:
pide las dos rutas, no una.
"""

import json
import mimetypes
import os
import pathlib
import time

try:
    import requests
except ImportError:                                # pragma: no cover — se instala en el workflow
    requests = None

import sala_cliente as sala

ALCANCE = 'https://www.googleapis.com/auth/drive'
API = 'https://www.googleapis.com/drive/v3'
API_SUBIDA = 'https://www.googleapis.com/upload/drive/v3'
ESPERA = 30
INTENTOS = 3

_credenciales_cache = None
_token_cache = {'token': None, 'vence': 0.0}


class DriveError(RuntimeError):
    """Drive no contestó o contestó mal. Mismo espíritu que SalaError (sala_cliente.py):
    nunca se traduce en silencio a «no había nada que subir»."""


def _credenciales():
    """Carga la cuenta de servicio UNA vez por proceso. Nunca cachea entre procesos: cada
    corrida del workflow es un runner nuevo, así que no hay archivo de credenciales que
    pudiera quedar tirado en disco entre corridas."""
    global _credenciales_cache
    if _credenciales_cache is not None:
        return _credenciales_cache
    crudo = os.environ.get('GDRIVE_SA_JSON', '').strip()
    if not crudo:
        raise DriveError('falta GDRIVE_SA_JSON (secret de Actions con la cuenta de servicio)')
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        raise DriveError('faltan las librerías de Drive (google-auth): %s' % e)
    try:
        info = json.loads(crudo)
    except ValueError as e:
        raise DriveError('GDRIVE_SA_JSON no es JSON válido: %s' % e)
    try:
        _credenciales_cache = service_account.Credentials.from_service_account_info(
            info, scopes=[ALCANCE])
    except (ValueError, KeyError) as e:
        raise DriveError('GDRIVE_SA_JSON no es una cuenta de servicio válida: %s' % e)
    return _credenciales_cache


def _token():
    """Token cacheado: pedir uno nuevo en cada llamada sería lento y, en una corrida que sube
    114 archivos, ruidoso contra la cuota de OAuth."""
    ahora = time.time()
    if _token_cache['token'] and ahora < _token_cache['vence'] - 60:
        return _token_cache['token']
    from google.auth.transport.requests import Request
    cred = _credenciales()
    try:
        cred.refresh(Request())
    except Exception as e:                          # cualquier fallo de red o de firma
        raise DriveError('no se pudo obtener el token de la cuenta de servicio: %s' % e)
    _token_cache['token'] = cred.token
    _token_cache['vence'] = cred.expiry.timestamp() if cred.expiry else ahora + 3000
    return cred.token


def _peticion(metodo, url, **kw):
    """El único lugar que habla HTTP con Drive. Aislado a propósito: las pruebas monkeypatchean
    esta función y nunca necesitan credenciales reales para probar la lógica de arriba."""
    if requests is None:
        raise DriveError('falta el paquete «requests» (se instala en el workflow)')
    cab = kw.pop('headers', {}) or {}
    cab['Authorization'] = 'Bearer ' + _token()
    ultimo = None
    for intento in range(1, INTENTOS + 1):
        try:
            r = requests.request(metodo, url, headers=cab, timeout=ESPERA, **kw)
        except requests.RequestException as e:
            ultimo = DriveError('%s %s: %s' % (metodo, url, sala.redactar(str(e))))
        else:
            if r.status_code < 300:
                return r
            if r.status_code in (429, 500, 502, 503) and intento < INTENTOS:
                ultimo = DriveError('Drive %s en %s: %s' % (r.status_code, url, r.text[:200]))
            else:
                raise DriveError('Drive %s en %s %s: %s'
                                 % (metodo, url, r.status_code, r.text[:300]))
        if intento < INTENTOS:
            time.sleep(2 ** intento)
    raise DriveError('Drive no contestó tras %d intentos: %s' % (INTENTOS, ultimo))


def buscar_hijo(padre_id, nombre, solo_carpetas=False):
    """Devuelve el id del primer hijo de `padre_id` que se llame `nombre`, o None."""
    tipo = " and mimeType = 'application/vnd.google-apps.folder'" if solo_carpetas else ''
    q = ("'%s' in parents and name = '%s' and trashed = false%s"
         % (padre_id, nombre.replace("'", "\\'"), tipo))
    r = _peticion('GET', API + '/files', params={'q': q, 'fields': 'files(id,name)',
                                                  'pageSize': 1})
    archivos = r.json().get('files') or []
    return archivos[0]['id'] if archivos else None


def asegurar_carpeta(padre_id, nombre):
    """Idempotente a propósito, como el resto del ciclo: si la carpeta ya existe, la usa; si
    no, la crea. Correr esto diez veces no deja diez carpetas gemelas."""
    existente = buscar_hijo(padre_id, nombre, solo_carpetas=True)
    if existente:
        return existente
    r = _peticion('POST', API + '/files',
                  json={'name': nombre, 'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [padre_id]},
                  headers={'Content-Type': 'application/json'})
    return r.json()['id']


def ruta_carpetas(raiz_id, *nombres):
    """asegurar_carpeta encadenada: ruta_carpetas(raiz, 'APODO', 'APODO-L01') ->
    YOD Editorial/APODO/APODO-L01, creando lo que falte."""
    actual = raiz_id
    for n in nombres:
        actual = asegurar_carpeta(actual, n)
    return actual


def subir(ruta_local, carpeta_id, nombre=None):
    """Sube UN archivo. Si ya existe un archivo con ese nombre en esa carpeta, lo REEMPLAZA
    (actualiza contenido, mismo id) en vez de duplicarlo — mismo espíritu que «montar es
    idempotente» (invariante 12): una segunda subida del mismo archivo no dispara un gemelo."""
    p = pathlib.Path(ruta_local)
    if not p.is_file():
        raise DriveError('no existe el archivo a subir: %s' % ruta_local)
    nombre = nombre or p.name
    tipo, _ = mimetypes.guess_type(nombre)
    tipo = tipo or 'application/octet-stream'
    datos = p.read_bytes()

    existente = buscar_hijo(carpeta_id, nombre)
    metadatos = {'name': nombre}
    if not existente:
        metadatos['parents'] = [carpeta_id]

    limites = [('metadata', (None, json.dumps(metadatos), 'application/json')),
               ('file', (nombre, datos, tipo))]
    if existente:
        r = _peticion('PATCH', API_SUBIDA + '/files/%s' % existente,
                      params={'uploadType': 'multipart'}, files=limites)
    else:
        r = _peticion('POST', API_SUBIDA + '/files',
                      params={'uploadType': 'multipart'}, files=limites)
    return r.json()['id']


def bajar(id_archivo, destino):
    """Baja UN archivo por su id a una ruta local. Usa el contenido tal cual (alt=media):
    para una imagen basta; Drive no reencodea."""
    r = _peticion('GET', API + '/files/%s' % id_archivo, params={'alt': 'media'})
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.content)
    return destino


def borrar(id_archivo):
    """Sólo para limpieza de pruebas (la sonda de Drive). El ciclo normal nunca borra: una
    versión retirada se queda en Drive igual que se queda en git (regla de la Sala: la
    historia no se pisa)."""
    _peticion('DELETE', API + '/files/%s' % id_archivo)


if __name__ == '__main__':                          # sonda mínima: sube, baja, compara, borra
    import hashlib
    import sys

    sala.enmascarar_en_actions()
    raiz = os.environ.get('DRIVE_RAIZ_PRUEBA', '').strip()
    if not raiz:
        sala.avisar('✗ falta DRIVE_RAIZ_PRUEBA (el id de una carpeta de prueba en Drive)')
        sys.exit(2)
    try:
        c = asegurar_carpeta(raiz, '_prueba_nube')
        origen = pathlib.Path('/tmp/_sonda_drive.txt')
        origen.write_text('sonda de la Sala · %s\n' % sala.hora_hermosillo())
        md5_local = hashlib.md5(origen.read_bytes()).hexdigest()
        fid = subir(str(origen), c, 'sonda.txt')
        destino = pathlib.Path('/tmp/_sonda_drive_bajada.txt')
        bajar(fid, destino)
        md5_bajado = hashlib.md5(destino.read_bytes()).hexdigest()
        borrar(fid)
        if md5_local == md5_bajado:
            sala.avisar('✓ Drive: subida, bajada y borrado OK · md5 %s' % md5_local)
        else:
            sala.avisar('✗ el md5 no coincide tras el viaje a Drive')
            sys.exit(1)
    except DriveError as e:
        sala.avisar('✗', e)
        sys.exit(2)
