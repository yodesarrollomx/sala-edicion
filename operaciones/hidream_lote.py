#!/usr/bin/env python3
"""Operación autorizada: rehacer sólo fotografías pendientes, con main intacto."""
import argparse, copy, datetime as dt, hashlib, inspect, io, json, os, re, sys, tempfile, time
from pathlib import Path
import requests
from PIL import Image
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"nube"))
import sala_cliente as sala
import sala_mesa as mesa
import sala_produccion as produccion
from motores import imagen
from motores._comun import MotorError
from motores.politica_imagen import POLITICA
from snapshots_online import Snapshots
SPACE="HiDream-ai/HiDream-I1-Dev"
MODEL="HiDream-I1-Dev"
MOTOR="hidream_demo"
BRANCH="codex/sala-hidream-lote-20261012"
TECH=Path(os.environ["RUNNER_TEMP"])/"hidream-operacion"
TECH.mkdir(exist_ok=True)
STOP={"detenido":False,"causa":"","generadas":0,"recuperadas":0}
CLIENT=None
ABRIR_ORIGINAL=mesa.abiertas
GENERAR_TOMAS_ORIGINAL=mesa.producir_tomas
MODELO_ORIGINAL=imagen.modelo_de
GET_ORIGINAL=sala.get

def emit(tag,data):
    print(tag+" "+json.dumps(data,ensure_ascii=False),flush=True)
def limpiar(value):
    s=sala.redactar(str(value))
    token=os.environ.get("HF_TOKEN","")
    if token:s=s.replace(token,"[secreto]")
    s=re.sub(r"hf_[A-Za-z0-9]{12,}","[secreto]",s)
    return s[:900]
def publicar_resumen(nombre,value):
    path="operaciones/hidream-lote-20261012/"+nombre+".json"
    base="https://api.github.com/repos/"+os.environ["GITHUB_REPOSITORY"]+"/contents/"+path
    headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"}
    old=requests.get(base,headers=headers,params={"ref":BRANCH},timeout=35)
    body={"branch":BRANCH,"message":"HiDream: "+nombre+" de la operación autorizada",
          "content":__import__("base64").b64encode((json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()).decode()}
    if old.status_code==200:body["sha"]=old.json()["sha"]
    elif old.status_code!=404:raise RuntimeError("No se pudo leer recibo técnico GitHub")
    response=requests.put(base,headers=headers,json=body,timeout=45)
    response.raise_for_status()

def pendientes():
    if produccion.peticiones_abiertas():
        raise RuntimeError("PASO 0: petición abierta; no se genera ni monta")
    mesa._contexto_produccion=None
    dia=mesa.contexto_produccion()
    mesa.hidratar_tiras_activas(dia)
    piezas=mesa.tiras_vigentes(mesa.tiras_por_pieza(),dia)
    publicadas=mesa.publicadas()
    result=[]
    for slug,(pid,t) in mesa.piezas_por_prioridad(piezas,dia):
        if str(t.get("pieza") or slug).lower() in publicadas:continue
        targets=[int(l["n"]) for l,marca,nota in ABRIR_ORIGINAL(pid,t,True)
                 if marca in ("no","reemplazar_modelo")]
        if targets:result.append({"slug":slug,"fuente":pid,"pieza":str(t.get("pieza") or slug),
                                   "laminas":targets,"cantidad":len(targets)})
    return result

def filtro_abiertas(tid,t,leer_sheet=True):
    return [(l,m,(note+" Rehacer únicamente la fotografía con HiDream-I1-Dev. Conservar exactamente el texto visible.").strip())
            for l,m,note in ABRIR_ORIGINAL(tid,t,leer_sheet)
            if m in ("no","reemplazar_modelo")]
def reglas_operacion(recurso,**kwargs):
    r=GET_ORIGINAL(recurso,**kwargs)
    if recurso=="reglas":
        r=copy.deepcopy(r)
        r.setdefault("reglas",{}).update(imagen_motores=MOTOR,mesa_tomas_por_lamina="1",mesa_tope_laminas="100")
    return r
def tomas_con_texto_vigente(slug,t,lam,nota,reglas,cola,carpeta,n_tomas,solo_recibo=False):
    visual=copy.deepcopy(lam)
    visual["reemplazo_modelo"]=POLITICA["revision"]
    return GENERAR_TOMAS_ORIGINAL(slug,t,visual,nota,reglas,cola,carpeta,1,solo_recibo=solo_recibo)

def generar_hidream(receta,reglas):
    global CLIENT
    from gradio_client import Client
    from contenido_reglas import exigir
    exigir(receta,reglas,"receta HiDream")
    prompt=receta.rstrip(". ")+imagen.SIN_LETRAS
    rid=str(reglas.get("_imagen_request_id") or hashlib.sha256(prompt.encode()).hexdigest())
    if not re.fullmatch(r"[0-9a-f]{64}",rid):raise MotorError("Identidad de generación inválida")
    folder=ROOT/"laminas"/"recibos-hidream"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(rid+".png");receipt_path=folder/(rid+".json")
    recipe=hashlib.sha256(prompt.encode()).hexdigest()
    if path.is_file() and receipt_path.is_file():
        receipt=json.loads(receipt_path.read_text())
        if receipt.get("modelo")!=MODEL or receipt.get("receta_sha256")!=recipe \
                or receipt.get("imagen_sha256")!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise MotorError("Recibo de HiDream incompatible; se conserva y no se duplica")
        STOP["recuperadas"]+=1
        reglas["_receta_proveedor_sha256"]=recipe;reglas["_imagen_recibo_id"]=rid
        return path.read_bytes(),"png",MOTOR,[]
    if STOP["detenido"] or reglas.get("_imagen_solo_recibo"):
        raise imagen.ReciboNoConfirmado("HiDream detenido; sin recibo para esta toma")
    try:
        if CLIENT is None:
            kw={"verbose":False,"download_files":str(TECH/"descargas")}
            sig=inspect.signature(Client)
            if "token" in sig.parameters:kw["token"]=os.environ.get("HF_TOKEN") or None
            elif "hf_token" in sig.parameters:kw["hf_token"]=os.environ.get("HF_TOKEN") or None
            CLIENT=Client(SPACE,**kw)
        seed=int(rid[:8],16)%(2**31)
        start=time.monotonic()
        job=CLIENT.submit(prompt,"3:4",seed,api_name="/generate_with_status")
        try:out=job.result(timeout=300)
        except Exception:
            try:job.cancel()
            except Exception:pass
            raise
        if not isinstance(out,(list,tuple)) or len(out)<4 or not out[0]:
            status=out[2] if isinstance(out,(list,tuple)) and len(out)>2 else "sin imagen"
            raise RuntimeError("HiDream no entregó foto: "+limpiar(status))
        info=out[3] or {}
        if info.get("model")!=MODEL:raise RuntimeError("HiDream declaró otro modelo; no se presenta como "+MODEL)
        f=out[0]
        if isinstance(f,dict):f=f.get("path") or f.get("url")
        if str(f).startswith("https://"):
            r=requests.get(f,timeout=45);r.raise_for_status();raw=r.content
        else:raw=Path(f).read_bytes()
        im=Image.open(io.BytesIO(raw));im.verify()
        im=Image.open(io.BytesIO(raw))
        if min(im.size)<512:raise RuntimeError("Imagen con resolución insuficiente")
        if len(raw)>25*1024*1024:raise RuntimeError("Imagen excede el contrato de publicación")
        buffer=io.BytesIO();im.convert("RGB").save(buffer,format="PNG");data=buffer.getvalue()
        receipt={"schema":1,"request_id":rid,"motor":MOTOR,"modelo":MODEL,"space":SPACE,
                 "receta_sha256":recipe,"imagen_sha256":hashlib.sha256(data).hexdigest(),
                 "resolucion":list(im.size),"seed":info.get("seed"),"segundos":round(time.monotonic()-start,1),
                 "run_id":os.environ["GITHUB_RUN_ID"],"generado_en":dt.datetime.now(dt.timezone.utc).isoformat()}
        path.write_bytes(data);receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
        STOP["generadas"]+=1
        reglas["_receta_proveedor_sha256"]=recipe;reglas["_imagen_recibo_id"]=rid
        emit("HIDREAM_FOTO_CONFIRMADA",receipt)
        publicar_resumen("generacion",{"modelo":MODEL,"generadas":STOP["generadas"],"ultima":receipt,"run_id":os.environ["GITHUB_RUN_ID"]})
        return data,"png",MOTOR,[]
    except Exception as e:
        STOP.update(detenido=True,causa=limpiar(e))
        if re.search(r"429|quota|rate.limit|resource.exhaust|cupo",str(e),re.I):
            raise imagen.CupoImagen("HiDream: "+STOP["causa"],intermitente=True) from None
        raise MotorError("HiDream detenido: "+STOP["causa"],intermitente=True) from None

def instalar_perfil():
    mesa.abiertas=filtro_abiertas
    mesa.producir_tomas=tomas_con_texto_vigente
    sala.get=reglas_operacion
    imagen.generar=generar_hidream
    imagen.modelo_de=lambda motor,reglas=None:MODEL if motor==MOTOR else MODELO_ORIGINAL(motor,reglas)

def llamar_mesa(*args):
    before=sys.argv[:]
    sys.argv=["sala_mesa.py",*args]
    try:return mesa.main()
    finally:sys.argv=before

def verificar_codigo_y_datos():
    import subprocess
    subprocess.run(["git","diff","--check"],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"nube/verificar.py"],cwd=ROOT,check=True)
    changed=subprocess.check_output(["git","diff","--name-only","HEAD"],cwd=ROOT,text=True).splitlines()
    if any(not p.startswith(("datos/","laminas/")) for p in changed):
        raise RuntimeError("Cambió código aprobado; no se publica")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("modo",choices=["inventario","producir"]);args=ap.parse_args()
    sala.enmascarar_en_actions()
    cloud=Snapshots(ROOT)
    if args.modo=="inventario":
        cloud.bootstrap("mesa",False)
        queue=pendientes()
        value={"fecha_hmo":sala.hoy_hermosillo(),"modelo":MODEL,"pendientes":sum(q["cantidad"] for q in queue),
               "piezas":queue,"run_id":os.environ["GITHUB_RUN_ID"],"codigo_main":cloud.head()}
        emit("HIDREAM_COLA_VIVA",value)
        (TECH/"inventario.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
        publicar_resumen("inventario",value)
        return
    instalar_perfil()
    mounted=[]
    try:
        cloud.bootstrap("mesa",True)
        queue=pendientes()
        total=sum(q["cantidad"] for q in queue)
        emit("HIDREAM_LOTE",{"pendientes":total,"piezas":queue,"modelo":MODEL,"una_toma_por_lamina":True})
        for round_number,item in enumerate(queue,1):
            if STOP["detenido"]:break
            before=STOP["generadas"]
            code=llamar_mesa("--producir","--pieza",item["slug"])
            plan=mesa._leer(mesa.PLAN,{}) or {}
            cartas=plan.get("cartas") or []
            if not cartas:
                emit("HIDREAM_PIEZA_SIN_CARTA",{"pieza":item["pieza"],"codigo":code})
                continue
            verificar_codigo_y_datos()
            cloud.attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT","1"))*1000+round_number
            cloud.prepare("mesa")
            cloud.dispatch_publish(cloud.head())
            if llamar_mesa("--montar")!=0:raise RuntimeError("Mesa no confirmó el montaje")
            ids=[c["tira_id"] for c in cartas]
            mounted.append({"pieza":item["pieza"],"laminas_nuevas":STOP["generadas"]-before,"tiras":ids})
            emit("HIDREAM_PIEZA_MONTADA",mounted[-1])
            progreso={"modelo":MODEL,"objetivo":total,"generadas":STOP["generadas"],"recuperadas":STOP["recuperadas"],
                      "montadas":mounted,"detenido":STOP["detenido"],"causa":STOP["causa"],
                      "run_id":os.environ["GITHUB_RUN_ID"],"fecha_hmo":sala.hoy_hermosillo()}
            (TECH/"progreso.json").write_text(json.dumps(progreso,ensure_ascii=False,indent=2)+"\n")
            publicar_resumen("progreso",progreso)
            cloud.release()
            if STOP["detenido"]:break
            cloud.bootstrap("mesa",True)
            mesa._snapshot_verifier=None
        remaining=pendientes()
        final={"modelo":MODEL,"objetivo_inicial":total,"generadas":STOP["generadas"],"recuperadas":STOP["recuperadas"],
               "montadas":mounted,"pendientes":sum(q["cantidad"] for q in remaining),"cola_restante":remaining,
               "detenido":STOP["detenido"],"causa":STOP["causa"],"run_id":os.environ["GITHUB_RUN_ID"],
               "decisiones_editoriales_escritas":0,"codigo_main":cloud.head()}
        (TECH/"cierre.json").write_text(json.dumps(final,ensure_ascii=False,indent=2)+"\n")
        publicar_resumen("cierre",final);emit("HIDREAM_CIERRE",final)
    finally:cloud.release()
if __name__=="__main__":main()
