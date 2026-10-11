#!/usr/bin/env python3
"""Canario aislado de motores/Drive. Sin cola, decisiones, correos ni medios de negocio."""
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import urllib.error
import wave

import numpy as np
from PIL import Image, ImageDraw
import sala_cliente as sala
import sala_drive as drive
import sala_montador as montador
from motores import escena_parallax, voz_kokoro

REPO="yodesarrollomx/sala-edicion"
BRANCH="salud-canario"

def metadata(path):
    p=subprocess.run(["ffprobe","-v","error","-show_format","-show_streams",
                      "-of","json",str(path)],check=True,capture_output=True,text=True,timeout=45)
    return json.loads(p.stdout)

def video_correcto(meta, audio=False):
    duration=float(meta.get("format",{}).get("duration",0))
    videos=[s for s in meta.get("streams",[]) if s.get("codec_type")=="video"]
    audios=[s for s in meta.get("streams",[]) if s.get("codec_type")=="audio"]
    if not (math.isfinite(duration) and 1<=duration<=60 and len(videos)==1
            and videos[0].get("codec_name")=="h264"
            and videos[0].get("width")==1080 and videos[0].get("height")==1920):
        raise ValueError("video_sin_contrato")
    if audio and not any(s.get("codec_name")=="aac" for s in audios):
        raise ValueError("audio_sin_contrato")
    return round(duration,3)

def audio_correcto(path):
    with wave.open(str(path),"rb") as w:
        if w.getsampwidth()!=2 or w.getnchannels()!=1:
            raise ValueError("voz_sin_contrato")
        duration=w.getnframes()/w.getframerate()
        samples=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype(np.float64)/32768
    if not (0.2<duration<30 and samples.size and np.sqrt(np.mean(samples**2))>0.001):
        raise ValueError("voz_silenciosa_o_invalida")
    return round(duration,3)

def probar_drive(root,parent,client=drive):
    """Sólo se borra el ID del archivo nuevo de esta prueba, nunca originales."""
    source=root/"canario-transferencia.txt"
    source.write_bytes(b"SALA canario aislado\n")
    folder=client.asegurar_carpeta(parent,"_prueba_nube")
    fid=client.subir(source,folder,"salud-"+os.environ.get("GITHUB_RUN_ID","local")+".txt")
    try:
        got=client.bajar(fid,root/"transferencia-leida.txt").read_bytes()
        if got!=source.read_bytes():
            raise ValueError("transferencia_diferente")
    finally:
        client.borrar(fid)
    return {"bytes":len(got),"sha256":hashlib.sha256(got).hexdigest(),"limpieza":True}

def record(ident,ok,now,detail):
    t=datetime.fromisoformat(now.replace("Z","+00:00"))
    return {"id":ident,"estado":"ok" if ok else "fallo","revisado_en":now,
            "vence_en":(t+timedelta(hours=36)).isoformat(),"detalle":detail}

def api(path,body=None,method=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,
        data=data,method=method or ("POST" if body else "GET"),
        headers={"Accept":"application/vnd.github+json","User-Agent":"sala-salud",
                 "Authorization":"Bearer "+os.environ["GH_TOKEN"],
                 "Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as r:
        return json.loads(r.read())

def publish(report):
    path="contents/estado-canario.json?ref="+BRANCH
    previous=None
    try:
        previous=api(path)
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
        try:
            api("git/ref/heads/"+BRANCH)
        except urllib.error.HTTPError as missing:
            if missing.code!=404: raise
            head=api("git/ref/heads/main")["object"]["sha"]
            api("git/refs",{"ref":"refs/heads/"+BRANCH,"sha":head})
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()
    body={"message":"Registrar canario aislado de motores y Drive","branch":BRANCH,
          "content":base64.b64encode(raw).decode()}
    if previous: body["sha"]=previous["sha"]
    out=api("contents/estado-canario.json",body,"PUT")
    # Relectura de los bytes exactos antes de confirmar el estado publicado.
    check=api(path)
    if base64.b64decode(check["content"])!=raw:
        raise ValueError("recibo_no_confirmado")
    return out["commit"]["sha"]

def main():
    sala.enmascarar_en_actions()
    now=datetime.now(timezone.utc).isoformat()
    checks=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);voice=None;scene=None
        try:
            response=sala.get("reglas")
            if not isinstance(response.get("reglas"),dict) or response.get("ok") is False:
                raise ValueError("reglas_sin_contrato")
            rules=response["reglas"]
        except Exception:
            rules={}
            checks.append(record("canario-reglas",False,now,"Lectura de configuración sin confirmar"))
        else:
            checks.append(record("canario-reglas",True,now,"Configuración leída; ninguna regla modificada"))
        test_rules={**rules,"audio_margen_s":0.25,"audio_cola_s":0.25}
        ev={"dice":"Esta es una prueba técnica de funcionamiento.","ve":"Figura sintética de prueba"}
        job={"pieza":"saludcanario","item":"1","evidencia":ev}
        try:
            voice=voz_kokoro.producir(job,test_rules,{},root)
            seconds=audio_correcto(voice)
            checks.append(record("motor-voz",True,now,"Kokoro real: WAV con señal y duración %.3fs"%seconds))
        except Exception:
            voice=None
            checks.append(record("motor-voz",False,now,"Síntesis o señal de audio sin confirmar"))
        try:
            image=Image.new("RGB",(320,480),(37,66,97))
            draw=ImageDraw.Draw(image)
            draw.rectangle((55,90,270,420),fill=(205,179,109))
            draw.rectangle((100,160,215,350),fill=(82,135,96))
            photo=root/"figura-sintetica.png";image.save(photo)
            scene,depth=escena_parallax.animar(photo,root/"escena.mp4",2)
            seconds=video_correcto(metadata(scene))
            checks.append(record("motor-escena",True,now,
                "Parallax real 1080×1920 H264 %.3fs; profundidad %s"%(seconds,depth)))
        except Exception:
            scene=None
            checks.append(record("motor-escena",False,now,"Animación o video sin confirmar"))
        if scene and voice:
            try:
                digest=hashlib.sha256(ev["dice"].encode()).hexdigest()[:8]
                queue=[{"id":"saludcanario:"+stage+":1:"+digest,"pieza":"saludcanario",
                        "item":"1","etapa":stage,"estado":"hecho",
                        "evidencia":{**ev,"ruta_local":str(path)}} for stage,path in
                        (("voz",voice),("escena",scene))]
                cut=montador.ensamblar({"pieza":"saludcanario","evidencia":{
                    "laminas":[{"item":"1","huella":digest}]}},test_rules,{},root,queue)
                seconds=video_correcto(metadata(cut),audio=True)
                checks.append(record("motor-corte",True,now,
                    "Montador real: H264/AAC con audio, duración %.3fs"%seconds))
            except Exception:
                checks.append(record("motor-corte",False,now,"Montaje del canario sin confirmar"))
        else:
            checks.append(record("motor-corte",False,now,"Falta voz o escena de la prueba"))
        try:
            parent=str(rules.get("drive_raiz") or "").strip()
            if not parent: raise ValueError("drive_sin_raiz")
            proof=probar_drive(root,parent)
            checks.append(record("drive-transferencia",True,now,
                "Archivo de prueba subido, releído byte exacto y retirado"))
        except Exception:
            checks.append(record("drive-transferencia",False,now,
                "Transferencia o limpieza de la prueba sin confirmar"))
    report={"schema":1,"generado_en":now,"code_sha":os.environ["GITHUB_SHA"],
            "run_id":os.environ["GITHUB_RUN_ID"],"zona_horaria":"America/Hermosillo",
            "alcance":"Canario sintético aislado; no certifica todos los motores ni aceptación editorial",
            "checks":checks,"escrituras_negocio":0,"correos_enviados":0,"decisiones":0}
    commit=publish(report)
    ok=all(c["estado"]=="ok" for c in checks)
    print(json.dumps({"canario_ok":ok,"checks":{c["id"]:c["estado"] for c in checks},
                      "datos_commit":commit,"escrituras_negocio":0}))
    return 0 if ok else 2

if __name__=="__main__":
    raise SystemExit(main())
