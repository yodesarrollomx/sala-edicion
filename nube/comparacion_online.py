#!/usr/bin/env python3
"""Comparación aislada: insumos versionados originales, motores reales y Drive privado."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
from unittest.mock import patch
import urllib.request
import urllib.error

import sala_cliente as sala
import sala_drive as drive
import sala_guion as guion
import sala_montador as montador
from motores import escena_parallax, voz_kokoro
from medios_reconexion import private_instructions, recovered_bytes

SOURCE_SHA="f0668c56d536e5b97d7ddbc2d53b66f93195ce85"
BASELINE_PATH="video/apodo/REEL_apodo-corte-2026-09-15.mp4"
BASELINE_SHA256="e22c9af6b9db5febb2bccc88513b9a70b7cbb6b4c576cc56d7a8afe390a3bc29"
ROOT=Path(__file__).resolve().parent.parent

class ComparacionError(RuntimeError):
    pass

def require(value, code):
    if not value:
        raise ComparacionError(code)

def download(path, target):
    part=PurePosixPath(path)
    require(not part.is_absolute() and ".." not in part.parts and
            all(c.isalnum() or c in "._-/" for c in path),"fuente_invalida")
    url="https://raw.githubusercontent.com/yodesarrollomx/sala-edicion/"+SOURCE_SHA+"/"+path
    with urllib.request.urlopen(url,timeout=120) as response:
        raw=response.read(30*1024*1024+1)
        require(response.status==200 and 0<len(raw)<=30*1024*1024,"fuente_sin_confirmar")
    Path(target).parent.mkdir(parents=True,exist_ok=True)
    Path(target).write_bytes(raw)
    return raw

def original_image(scene, target, baseline):
    try:
        raw=download(scene["lamina_src"],target)
        return raw, {"tipo":"repositorio_original","source_sha":SOURCE_SHA,
                     "misma_ruta_versionada":True}
    except urllib.error.HTTPError as error:
        require(error.code==404 and scene["n"]==6,"imagen_original_no_confirmada")
    try:
        catalog=sala.get("catalogo",fresco="1")
        require(isinstance(catalog.get("catalogo"),dict),"catalogo_sin_contrato")
        refs={}
        for serial,item in catalog["catalogo"].items():
            for revision in item.get("revisiones",[]):
                routes=str(revision.get("rutas") or revision.get("ruta") or "").split("|")
                if scene["lamina_src"] in routes and revision.get("original"):
                    refs[str(revision["original"])]={"serial":serial,"revision":revision.get("r"),
                                                    "huella":revision.get("huella")}
        if len(refs)==1:
            candidate=next(iter(refs))
            drive.bajar(candidate,target)
            raw=Path(target).read_bytes()
            meta=drive._peticion("GET",drive.API+"/files/"+candidate,
                params={"fields":"id,size,md5Checksum,trashed"}).json()
            require(meta.get("trashed") is False and int(meta.get("size",0))==len(raw)
                    and meta.get("md5Checksum")==hashlib.md5(raw).hexdigest(),"original_drive_diferente")
            return raw, {"tipo":"original_catalogado_drive","drive_id":candidate,
                         "identidad_catalogo":refs[candidate],"misma_ruta_versionada":False,
                         "igualdad_con_insumo_del_corte_no_acreditada":True}
    except Exception:
        pass
    # Una referencia del video original permite terminar la comparación PARCIAL;
    # no se considera la foto de fuente ni se reemplaza el original en el negocio.
    subprocess.run(["ffmpeg","-v","error","-y","-sseof","-1.5","-i",str(baseline),
                    "-frames:v","1",str(target)],check=True,timeout=30)
    raw=Path(target).read_bytes()
    require(len(raw)>0,"referencia_del_corte_no_confirmada")
    return raw, {"tipo":"frame_del_corte_original","offset_fin_s":1.5,
                 "baseline_sha256":BASELINE_SHA256,"misma_ruta_versionada":False,
                 "igualdad_con_insumo_del_corte_no_acreditada":True}


def metadata(path):
    result=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format",
                           "-of","json",str(path)],capture_output=True,check=True,text=True,timeout=30)
    data=json.loads(result.stdout)
    return {"duracion_s":float(data["format"]["duration"]),
            "streams":[{"tipo":x.get("codec_type"),"codec":x.get("codec_name"),
                        "ancho":x.get("width"),"alto":x.get("height"),
                        "sample_rate":x.get("sample_rate")} for x in data["streams"]]}

def store_file(path, folder):
    path=Path(path)
    raw=path.read_bytes()
    fid=drive.subir(path,folder,path.name)
    require(drive.bajar(fid,path.parent/("readback-"+path.name)).read_bytes()==raw,
            "archivo_privado_no_confirmado")
    (path.parent/("readback-"+path.name)).unlink()
    return {"nombre":path.name,"drive_id":fid,"bytes":len(raw),
            "sha256":hashlib.sha256(raw).hexdigest(),"md5":hashlib.md5(raw).hexdigest()}

def summary(original, cloud):
    def stream(meta,kind):
        return next((x for x in meta["streams"] if x["tipo"]==kind),None)
    old,new=stream(original,"video"),stream(cloud,"video")
    require(old is not None and new is not None and stream(cloud,"audio") is not None,
            "corte_sin_audio_video")
    return {"original":original,"nube":cloud,
            "mismo_formato_video":old["codec"]==new["codec"],
            "misma_resolucion":(old["ancho"],old["alto"])==(new["ancho"],new["alto"]),
            "diferencia_duracion_s":round(cloud["duracion_s"]-original["duracion_s"],4),
            "igualdad_visual_verificada":False,"aceptacion_editorial":False}

def main():
    began=time.monotonic()
    sala.enmascarar_en_actions()
    # Sin post(), decisiones, nuevas filas ni sustitución de originales.
    try:
        rules_response=sala.get("reglas")
        require(isinstance(rules_response,dict) and rules_response.get("ok") is not False
                and isinstance(rules_response.get("reglas"),dict),"reglas_sin_contrato")
        rules=rules_response["reglas"]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates,parent,_=private_instructions(root)
            folder=drive.asegurar_carpeta(parent,"SALA-comparacion-"+os.environ["GITHUB_RUN_ID"])
            baseline=root/"original-claude-mac.mp4"
            raw=download(BASELINE_PATH,baseline)
            require(hashlib.sha256(raw).hexdigest()==BASELINE_SHA256,"original_corte_diferente")
            script_dir=root/"guiones"
            script_raw=download("datos/guiones/APODO-VIDEO.json",script_dir/"APODO-VIDEO.json")
            script=json.loads(script_raw)
            scenes=script.get("escenas")
            require(isinstance(scenes,list) and len(scenes)==6,"guion_original_incompleto")
            jobs=[];laminas=[];inputs=[];files=[];depth=[]
            with patch.object(guion,"GUIONES",script_dir):
                for scene in scenes:
                    n=str(scene["n"])
                    require(n in {"1","2","3","4","5","6"},"lamina_original_invalida")
                    photo=root/("entrada-L"+n+".png")
                    original,source_proof=original_image(scene,photo,baseline)
                    digest=hashlib.sha256(original).hexdigest()
                    text=" ".join(x["dice"] for x in scene["partes"])
                    evidence={"src":str(photo),"dice":text,"ve":scene.get("intencion","")}
                    job={"pieza":"apodo","item":n,"evidencia":evidence}
                    voice=voz_kokoro.producir(job,rules,{},root)
                    movie,proof=escena_parallax.animar(photo,root/("nube-L"+n+"-escena.mp4"),4)
                    depth.append(proof)
                    for stage,path in (("escena",movie),("voz",voice)):
                        jobs.append({"id":"apodo:"+stage+":"+n+":"+digest[:8],
                            "pieza":"apodo","item":n,"etapa":stage,"estado":"hecho",
                            "evidencia":{**evidence,"ruta_local":str(path)}})
                        files.append(store_file(path,folder))
                    inputs.append({"lamina":n,"source_path":scene["lamina_src"],"sha256":digest,
                                   "partes":scene["partes"],"procedencia":source_proof})
                    laminas.append({"item":n,"huella":digest[:8]})
                cut=montador.ensamblar({"pieza":"apodo","evidencia":{"laminas":laminas}},
                                      rules,{},root,jobs)
            files.append(store_file(baseline,folder))
            files.append(store_file(cut,folder))
            files.append(store_file(script_dir/"APODO-VIDEO.json",folder))
            original_meta=metadata(baseline)
            cloud_meta=metadata(cut)
            comparative=summary(original_meta,cloud_meta)
            require(any(x.get("ancho")==1080 and x.get("alto")==1920 and x.get("codec")=="h264"
                        for x in cloud_meta["streams"]),"corte_nube_sin_formato")
            recovered=[]
            voice1=next(x for x in files if x["nombre"]=="apodo-L1-voz.wav")
            for candidate in candidates:
                exact=recovered_bytes(candidate,root)
                recovered.append({"original_drive_id":candidate["new_drive_id"],
                    "sha256":hashlib.sha256(exact).hexdigest(),
                    "bytes_identicos_a_voz_nube_l1":hashlib.sha256(exact).hexdigest()==voice1["sha256"],
                    "metadata":metadata(root/(candidate["sha256"]+".wav")),
                    "guion_de_esa_revision_no_registrado":True})
            report={"schema":1,"at":datetime.now(timezone.utc).isoformat(),
                "run_id":os.environ["GITHUB_RUN_ID"],"code_sha":os.environ["GITHUB_SHA"],
                "tipo":"comparacion_aislada_original_con_nube","source_sha":SOURCE_SHA,
                "baseline_sha256":BASELINE_SHA256,"guion_sha256":hashlib.sha256(script_raw).hexdigest(),
                "insumos_originales":inputs,
                "laminas_versionadas_en_mismo_commit":sum(x["procedencia"]["misma_ruta_versionada"] for x in inputs),
                "limite_original":"Corte archivado y guion del mismo commit; cinco láminas originales disponibles. La sexta se documenta por catálogo o frame del corte, sin equivalencia de insumo presumida. No se conserva recibo del montador Mac con hashes de todos los insumos; comparación completa no acreditada.",
                "motores":{"escena":"parallax_2_5d","voz":"kokoro","corte":"ffmpeg"},
                "profundidad":depth,"comparacion":comparative,
                "voces_originales_recuperadas":recovered,"archivos":files,"carpeta":folder,
                "reglas_comparacion":{k:rules.get(k) for k in ("voz_narrador","voz_vecino","audio_margen_s","audio_cola_s","audio_xfade_s")},
                "decisiones_escritas":False,"cola_escrita":False,"publicaciones_sociales":0,
                "duracion_ejecucion_s":round(time.monotonic()-began,1)}
            path=root/"comparacion.json"
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
            receipt=store_file(path,folder)
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"],"a") as out:
                    out.write("acuse="+receipt["drive_id"]+"\n")
                    out.write("carpeta="+folder+"\n")
            print("SALA_COMPARACION "+json.dumps({"ok":True,"laminas":len(inputs),
                "archivos_privados_verificados":len(files)+1,"comparacion":comparative,
                "laminas_originales_versionadas":report["laminas_versionadas_en_mismo_commit"],
                "voces_l1_identicas":sum(x["bytes_identicos_a_voz_nube_l1"] for x in recovered),
                "escrituras_negocio":0,"segundos":report["duracion_ejecucion_s"]},sort_keys=True))
        return 0
    except Exception:
        print("SALA_COMPARACION "+json.dumps({"ok":False,"error":"comparacion_no_confirmada",
                                             "escrituras_negocio":0}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
