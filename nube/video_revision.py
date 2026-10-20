#!/usr/bin/env python3
"""Copia ligera cifrada: original en Drive, llave sólo en backend privado de Sala."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import sala_cliente as sala
import sala_drive as drive
from snapshots_online import GitHub, OnlineError

REPO = 'yodesarrollomx/sala-edicion'
BRANCH = 'media/sala-video-privado-v1'
MAX = 4 * 1024 * 1024

class VideoError(RuntimeError):
    pass

def exigir(ok, error):
    if not ok:
        raise VideoError(error)

def identidad(p):
    pid, src = str(p.get('id') or ''), str(p.get('video') or '')
    m = re.fullmatch(r'https://drive\.google\.com/file/d/([A-Za-z0-9_-]{10,128})/preview', src)
    h = re.search(r'-corte-nube-([a-f0-9]{12})$', pid)
    exigir(m and h and re.fullmatch(r'[a-zA-Z0-9_-]{1,240}', pid), 'video_identidad_invalida')
    return pid, src, m[1], h[1]

def original(p, destino):
    pid, src, fid, prefix = identidad(p)
    meta = drive._peticion('GET', drive.API+'/files/'+fid, params={'fields':'id,mimeType,size,md5Checksum,trashed'}).json()
    md5 = str(meta.get('md5Checksum') or '')
    exigir(meta.get('trashed') is False and meta.get('mimeType')=='video/mp4' and
           re.fullmatch(r'[a-f0-9]{32}',md5) and md5.startswith(prefix) and
           0<int(meta.get('size') or 0)<=256*1024*1024, 'video_original_distinto')
    drive.bajar(fid,destino)
    exigir(destino.stat().st_size==int(meta['size']) and hashlib.md5(destino.read_bytes()).hexdigest()==md5,'video_bytes_distintos')
    return md5

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name,width,height:format=duration','-of','json',str(path)],timeout=30))

def ligera(src, dst):
    before=probe(src)
    exigir({'audio','video'}<={s.get('codec_type') for s in before['streams']},'video_sin_audio')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(src),'-map','0:v:0','-map','0:a:0',
       '-vf','scale=min(360\\,iw):-2','-c:v','libx264','-preset','fast','-crf','30','-maxrate','240k','-bufsize','480k',
       '-pix_fmt','yuv420p','-c:a','aac','-b:a','48k','-ac','1','-movflags','+faststart','-map_metadata','-1',str(dst)],check=True,timeout=180)
    after=probe(dst)
    exigir({'audio','video'}<={s.get('codec_type') for s in after['streams']} and
           abs(float(before['format']['duration'])-float(after['format']['duration']))<1 and
           any(s.get('codec_name')=='h264' for s in after['streams']) and 12<=dst.stat().st_size<=MAX,'video_copia_invalida')
    return dst.read_bytes()

def cifrar(data, key=None, iv=None):
    exigir(12<=len(data)<=MAX and data[4:8]==b'ftyp','video_copia_invalida')
    key,iv=key or os.urandom(32),iv or os.urandom(12)
    payload=AESGCM(key).encrypt(iv,data,None)
    return payload, {'key':base64.b64encode(key).decode(),'iv':base64.b64encode(iv).decode(),
      'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'cipher_bytes':len(payload),'cipher_sha256':hashlib.sha256(payload).hexdigest()}

def publicar_cifrado(api, payload):
    digest=hashlib.sha256(payload).hexdigest(); name='video-revision-cifrado/'+digest+'.bin'
    try:
        api.request('git/ref/heads/'+BRANCH)
    except OnlineError as e:
        exigir('404' in str(e),'video_rama_sin_confirmar')
        sha=api.request('git/ref/heads/main')['object']['sha']
        try:api.request('git/refs',{'ref':'refs/heads/'+BRANCH,'sha':sha})
        except OnlineError:api.request('git/ref/heads/'+BRANCH)
    gitsha=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
    try:
        result=api.request('contents/'+name,{'message':'cache: derivado de video cifrado e inmutable','branch':BRANCH,'content':base64.b64encode(payload).decode()},method='PUT')
        exigir(result['content']['sha']==gitsha,'video_publicacion_distinta')
        commit=result['commit']['sha']
    except OnlineError:
        item=api.request('contents/'+name+'?ref='+urllib.parse.quote(BRANCH,safe=''))
        exigir(item.get('sha')==gitsha,'video_publicacion_sin_acuse')
        commit=api.request('git/ref/heads/'+BRANCH)['object']['sha']
    exigir(re.fullmatch(r'[a-f0-9]{40}',commit),'video_commit_invalido')
    url='https://raw.githubusercontent.com/'+REPO+'/'+commit+'/'+name
    response=requests.get(url,timeout=25);response.raise_for_status()
    exigir(hashlib.sha256(response.content).hexdigest()==digest,'video_cifrado_distinto')
    return url

def main():
    sala.enmascarar_en_actions()
    exigir(os.environ.get('GITHUB_REPOSITORY')==REPO,'video_repositorio_invalido')
    api=GitHub(REPO,os.environ['GH_TOKEN'])
    day=sala.get('dia')
    items=[p for p in day.get('propuestas',[]) if '-corte-nube-' in str(p.get('id')) and 'drive.google.com' in str(p.get('video'))]
    prepared=existing=0
    for p in items:
        pid,src,_,_=identidad(p)
        state=sala.post('video_revision_preparar',op='estado',prop_id=pid,video=src)
        exigir(state.get('ok') is True,'video_backend_no_disponible')
        if state.get('preparado') is True:
            existing+=1;continue
        with tempfile.TemporaryDirectory(prefix='sala-video-') as tmp:
            original_path=Path(tmp)/'original.mp4';copy_path=Path(tmp)/'ligero.mp4'
            md5=original(p,original_path); data=ligera(original_path,copy_path)
            payload,descriptor=cifrar(data)
            exigir(AESGCM(base64.b64decode(descriptor['key'])).decrypt(base64.b64decode(descriptor['iv']),payload,None)==data,'video_cifrado_no_reversible')
            descriptor.update(source_md5=md5,url=publicar_cifrado(api,payload))
            # Un acuse incierto se concilia; la escritura idempotente no se repite aquí.
            try:ack=sala.post('video_revision_preparar',prop_id=pid,video=src,copia=descriptor)
            except sala.SalaError:ack=sala.post('video_revision_preparar',op='estado',prop_id=pid,video=src)
            exigir(ack.get('ok') is True and ack.get('preparado') is True,'video_copia_sin_acuse')
            prepared+=1
    print(json.dumps({'copias_preparadas':prepared,'existentes':existing,'cortes':len(items)}))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (VideoError,OnlineError,sala.SalaError,drive.DriveError,requests.RequestException,subprocess.SubprocessError):
        print('video_revision_no_confirmada');raise SystemExit(2)
