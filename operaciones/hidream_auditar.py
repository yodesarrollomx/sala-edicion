#!/usr/bin/env python3
"""Comprobar resultados públicos del lote; no generar, montar ni decidir."""
import base64,datetime as dt,hashlib,io,json,os,re,sys,time
from pathlib import Path
import requests
from PIL import Image,ImageOps,ImageDraw,ImageFont
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/"nube"))
import sala_cliente as sala
import sala_mesa as mesa
from snapshots_online import Snapshots
BRANCH="codex/sala-hidream-lote-20261012"
PREFIX="operaciones/hidream-lote-20261012/"
SITE="https://yodesarrollomx.github.io/sala-edicion/"
HEADERS={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"}
API="https://api.github.com/repos/"+os.environ["GITHUB_REPOSITORY"]
RUN="38336377009"
def api(path,**kw):
    r=requests.get(API+"/"+path,headers=HEADERS,timeout=45,**kw)
    r.raise_for_status();return r.json()
def get_file(name):
    try:
        r=api("contents/"+PREFIX+name,params={"ref":BRANCH})
        return json.loads(base64.b64decode(r["content"]))
    except requests.HTTPError as exc:
        if exc.response.status_code==404:return None
        raise
def public(path):
    r=requests.get(SITE+path,headers={"Cache-Control":"no-cache"},timeout=45)
    r.raise_for_status();return r.content
def save(name,data):
    path=PREFIX+name;url=API+"/contents/"+path
    old=requests.get(url,headers=HEADERS,params={"ref":BRANCH},timeout=45)
    body={"branch":BRANCH,"message":"HiDream: verificación de resultados publicados","content":base64.b64encode(data).decode()}
    if old.status_code==200:body["sha"]=old.json()["sha"]
    elif old.status_code!=404:old.raise_for_status()
    r=requests.put(url,headers=HEADERS,json=body,timeout=45);r.raise_for_status()
sala.enmascarar_en_actions()
deadline=time.monotonic()+5400
while time.monotonic()<deadline:
    final=get_file("cierre.json")
    if final and str(final.get("run_id"))==RUN:break
    state=api("actions/runs/"+RUN)
    if state["status"]=="completed":raise RuntimeError("El lote terminó sin cierre; conservar fotos y revisar el fallo")
    time.sleep(25)
else:raise RuntimeError("Lote sin cierre a tiempo")
inventory=get_file("inventario-inicial.json")
if not inventory or inventory.get("pendientes")!=21:raise RuntimeError("Inventario inicial de otra operación")
expected=get_file("textos-vigentes.json") or {}
targets={q["pieza"]:q for q in inventory["piezas"]}
cloud=Snapshots(ROOT);cloud.bootstrap("mesa",False)
mesa._contexto_produccion=None
day=mesa.contexto_produccion()
active={p["id"] for p in day["propuestas"]}
checks=[];previews=[]
for mounted in final["montadas"]:
    item=targets[mounted["pieza"]]
    for tid in mounted["tiras"]:
        if tid not in active:raise RuntimeError("Tira generada no está activa en la sala: "+tid)
        tira=json.loads(public("datos/tiras/"+tid+".json"))
        base=json.loads(public("datos/tiras/"+item["fuente"]+".json"))
        if tira.get("base")!=item["fuente"]:raise RuntimeError("Tira enlazada a otra fuente")
        newnums={l["n"] for l in tira["laminas"] if any(c.get("motor")=="hidream_demo" for c in l.get("candidatas") or [])}
        if not newnums or not newnums.issubset(set(item["laminas"])):raise RuntimeError("El lote tocó láminas ajenas")
        mesa.validar_nuevas_tomas(tira)
        old={l["n"]:l for l in base["laminas"]}
        checked=[]
        for lam in tira["laminas"]:
            number=lam["n"]
            if number not in newnums:continue
            options=[c for c in lam.get("candidatas") or [] if c.get("motor")=="hidream_demo"]
            if len(options)!=1:raise RuntimeError("No hay exactamente una foto HiDream en L"+str(number))
            c=options[0]
            if c.get("modelo")!="HiDream-I1-Dev":raise RuntimeError("Otro modelo declarado")
            key=item["slug"]+":"+str(number)
            expected_text=expected.get(key,{}).get("dice")
            previous_texts={str(old[number].get("dice") or "")}
            for field in ("candidatas","versiones"):
                previous_texts.update(str(v.get("dice") or "") for v in old[number].get(field) or [])
            if expected_text is not None:
                if c.get("dice")!=expected_text:raise RuntimeError("Se modificó el texto vigente de la sala")
            elif str(c.get("dice") or "") not in previous_texts:
                raise RuntimeError("El texto no pertenece a la fuente previa")
            rid=c.get("recibo_imagen") or ""
            if not re.fullmatch(r"[0-9a-f]{64}",rid):raise RuntimeError("Foto sin recibo verificable")
            receipt=json.loads(public("laminas/recibos-hidream/"+rid+".json"))
            raw=public("laminas/recibos-hidream/"+rid+".png")
            if receipt["modelo"]!=c["modelo"] or hashlib.sha256(raw).hexdigest()!=receipt["imagen_sha256"]:
                raise RuntimeError("Recibo o imagen original distinto")
            jpg=public(c["src"]);png=public(c["original"])
            if hashlib.md5(png).hexdigest()!=c["huella"]:raise RuntimeError("Lámina compuesta no coincide")
            Image.open(io.BytesIO(jpg)).verify();Image.open(io.BytesIO(png)).verify()
            check={"n":number,"modelo":c["modelo"],"jpg":SITE+c["src"],"png":SITE+c["original"],
                   "foto_sha256":receipt["imagen_sha256"],"segundos":receipt["segundos"],
                   "texto_preservado":True,"tira_activa":True,"recibo_confirmado":True}
            checked.append(check)
            previews.append((mounted["pieza"],number,jpg))
        checks.append({"pieza":mounted["pieza"],"tira":tid,"cantidad":len(checked),"laminas":checked})
total=sum(x["cantidad"] for x in checks)
if total!=final["generadas"]:raise RuntimeError("Cuenta de imágenes montadas no coincide con las generadas")
report={"modelo":"HiDream-I1-Dev","run_produccion":RUN,"verificado_en":dt.datetime.now(dt.timezone.utc).isoformat(),
        "generadas_y_montadas":total,"pendientes":final["pendientes"],"detenido":final["detenido"],
        "causa":final["causa"],"piezas":checks,"decisiones_editoriales_escritas":0,
        "segundos_fotos":[p["segundos"] for x in checks for p in x["laminas"]],
        "observacion_visual":"Las primeras cuatro candidatas incluyen texto añadido por el generador; están pendientes de revisión humana."}
save("verificacion.json",(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode())
if previews:
    columns=4;width=270;height=380
    grid=Image.new("RGB",(columns*width,((len(previews)+columns-1)//columns)*height),"#f3eee6")
    draw=ImageDraw.Draw(grid)
    try:font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",12)
    except OSError:font=ImageFont.load_default()
    for i,(title,num,jpg) in enumerate(previews):
        x=(i%columns)*width;y=(i//columns)*height
        pic=ImageOps.contain(Image.open(io.BytesIO(jpg)).convert("RGB"),(width-12,height-42))
        grid.paste(pic,(x+(width-pic.width)//2,y+6))
        label=title+" · L"+str(num)
        draw.text((x+7,y+height-30),label[:37],fill="#15120c",font=font)
    out=io.BytesIO();grid.save(out,"JPEG",quality=85,optimize=True)
    save("vista-lote.jpg",out.getvalue())
print("HIDREAM_AUDITORIA "+json.dumps(report,ensure_ascii=False),flush=True)
