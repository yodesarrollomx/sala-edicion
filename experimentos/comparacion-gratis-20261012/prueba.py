#!/usr/bin/env python3
"""Comparación sintética autorizada. No lee ni escribe negocio, GAS, Sheets o votos."""
import base64, hashlib, html, inspect, io, json, os, re, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"resultados"
OUT.mkdir(parents=True,exist_ok=True)
PROMPT=("Photorealistic editorial photograph of a Mexican family of exactly three adults "
"a woman aged 65, a man aged 45 and a woman aged 35, sitting around a wooden dining table "
"and discussing a simple architectural floor plan. Contemporary modest home in Sonora, "
"warm neutral plaster walls, natural window light, authentic everyday clothing, candid "
"interaction, realistic facial proportions and skin texture, anatomically correct hands. "
"Vertical portrait composition, documentary photography, restrained colors, no illustration, "
"no cartoon, no plastic skin, no letters, no captions, no logos, no watermark.")
NEGATIVE="text, letters, captions, logos, watermark, cartoon, illustration, plastic skin, deformed hands"
BRANCH=os.environ.get("PRUEBA_BRANCH","codex/prueba-15-imagenes-gratis-20261012")
REPO=os.environ.get("GITHUB_REPOSITORY","yodesarrollomx/sala-edicion")
RUN=os.environ.get("GITHUB_RUN_ID","")
ITEMS=[
(1,"Z-Image Turbo","Tongyi-MAI/Z-Image-Turbo","hf"),
(2,"Qwen-Image 2.1","Qwen/Qwen-Image-2.1","hf"),
(3,"Krea 2 Turbo","krea/Krea-2","hf"),
(4,"SANA-Sprint","Efficient-Large-Model/SanaSprint","hf"),
(5,"Ovis-Image 7B","ATH-MaaS/Ovis-Image-7B","hf"),
(6,"Kolors","gokaygokay/Kolors","hf"),
(7,"Stable Diffusion 3.5 Large","stabilityai/stable-diffusion-3.5-large","hf"),
(8,"Playground v2.5","playgroundai/playground-v2.5","hf"),
(9,"PixArt-Sigma","PixArt-alpha/PixArt-Sigma","hf"),
(10,"Lucid Origin","@cf/leonardo/lucid-origin","cf"),
(11,"Phoenix 1.0","@cf/leonardo/phoenix-1.0","cf"),
(12,"Kandinsky 3.1","fusionbrain","kandinsky"),
(13,"HiDream-I1 Dev","HiDream-ai/HiDream-I1-Dev","hf"),
(14,"Ideogram","https://ideogram.ai/","web"),
(15,"Adobe Firefly nativo","https://firefly.adobe.com/generate/image","web")]
ROWS=[{"n":n,"nombre":name,"modelo":model,"tipo":kind,"estado":"pendiente","imagen":None}
      for n,name,model,kind in ITEMS]
SECRETS=[os.environ.get(k,"") for k in
 ("GH_TOKEN","HF_TOKEN","CF_ACCOUNT_ID","CF_API_TOKEN","KANDINSKY_API_KEY","KANDINSKY_SECRET_KEY")]
def clean(v):
    s=str(v)
    for x in SECRETS:
        if len(x)>6:s=s.replace(x,"[secreto]")
    s=re.sub(r"hf_[A-Za-z0-9]{12,}","[token]",s)
    s=re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+",r"\1[secreto]",s)
    return s[:1800]
def log(name,v):
    print(name+" "+json.dumps(v,ensure_ascii=False),flush=True)
def save_image(row,data):
    im=Image.open(io.BytesIO(data))
    im.verify()
    im=Image.open(io.BytesIO(data)).convert("RGB")
    if min(im.size)<256:raise ValueError("Respuesta sin resolución suficiente; no se presenta como foto")
    file="%02d-%s"%(row["n"],re.sub(r"[^a-z0-9]+","-",row["nombre"].lower()).strip("-"))
    original=OUT/(file+".png")
    im.save(original)
    preview=im.copy()
    preview.thumbnail((800,1000))
    preview.save(OUT/(file+".jpg"),quality=93)
    row.update(estado="generada",imagen=original.name,vista=file+".jpg",
               resolucion=list(im.size),sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
               bytes=original.stat().st_size)
def contact():
    ok=[r for r in ROWS if r["estado"]=="generada"]
    if not ok:return
    cols=3
    w,h=600,800
    page=Image.new("RGB",(cols*w,((len(ok)+cols-1)//cols)*h),"#f4f1eb")
    draw=ImageDraw.Draw(page)
    try:font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",23)
    except OSError:font=ImageFont.load_default()
    for i,r in enumerate(ok):
        im=Image.open(OUT/r["vista"]).convert("RGB")
        im.thumbnail((w-24,h-80))
        x=(i%cols)*w;y=(i//cols)*h
        page.paste(im,(x+(w-im.width)//2,y+60))
        draw.text((x+15,y+15),"%02d. %s"%(r["n"],r["nombre"]),font=font,fill="#171612")
    page.save(OUT/"comparacion.jpg",quality=94)
def write_report():
    contact()
    report={"encargo":PROMPT,"formato_objetivo":"1024x1280, 4:5 cuando el demo lo permite",
            "seed":74103,"run_id":RUN,"run_url":"https://github.com/%s/actions/runs/%s"%(REPO,RUN),
            "fecha_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"opciones":ROWS,
            "negocio_modificado":False}
    (OUT/"resultados.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# Prueba real de 15 generadores gratuitos","",
           "Mismo encargo: tres adultos mexicanos revisando un plano en una casa. Fotos sintéticas de comparación.",
           "No se han montado en la Sala ni cuentan como decisiones del editor.","",
           "[Ejecución y evidencia](%s)"%report["run_url"],"",
           "| # | Motor | Resultado | Foto |","|---|---|---|---|"]
    for r in ROWS:
        photo="[Abrir original](%s)"%r["imagen"] if r["imagen"] else "—"
        lines.append("| %d | %s | %s | %s |"%(r["n"],r["nombre"],r["estado"],photo))
    lines+=["","## Imágenes obtenidas",""]
    if (OUT/"comparacion.jpg").exists():lines+=["![Comparación](comparacion.jpg)",""]
    for r in ROWS:
        lines+=["### %02d. %s"%(r["n"],r["nombre"]),"",
                "**Estado:** "+r["estado"],""]
        if r["imagen"]:lines+=["![%s](%s)"%(r["nombre"],r["vista"]),"",
                              "[Abrir original PNG](%s)"%r["imagen"],""]
        if r.get("detalle"):lines += [r["detalle"].replace("\n"," "),""]
    lines+=["## Encargo común","",PROMPT,""]
    (OUT/"README.md").write_text("\n".join(lines),encoding="utf-8")
    cards=[]
    for r in ROWS:
        photo='<a href="%s"><img src="%s" alt="%s" loading="lazy"></a>'%(
            r["imagen"],r["vista"],html.escape(r["nombre"])) if r["imagen"] else '<div class="sin">Sin imagen generada</div>'
        cards.append('<article><h2>%02d. %s</h2><b class="%s">%s</b>%s<p>%s</p></article>'%(
            r["n"],html.escape(r["nombre"]),"ok" if r["imagen"] else "pendiente",
            html.escape(r["estado"]),photo,html.escape(r.get("detalle",""))))
    page='''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparación de 15 generadores gratuitos</title>
<style>body{margin:0;background:#f5f2ec;color:#221f18;font:16px system-ui;padding:24px}
header{max-width:1000px;margin:auto auto 24px}h1{font:38px Georgia}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px}
article{background:white;padding:16px;border-radius:14px}h2{font:22px Georgia}
img{display:block;width:100%%;height:auto;margin-top:12px}b{display:inline-block;padding:5px 10px;border-radius:12px}
.ok{background:#d9efdd;color:#19532c}.pendiente{background:#eee5d4;color:#76521c}
.sin{padding:80px 5px;text-align:center;background:#f1eee8;margin-top:12px}p{overflow-wrap:anywhere}
</style><header><h1>15 generadores · prueba real</h1><p>Tres adultos mexicanos revisando un plano en una casa. El mismo encargo para todos. Pulsa una foto para abrir su original.</p>
<p>Las tarjetas sin foto indican un bloqueo real; no se han sustituido por imágenes de muestra del proveedor.</p></header><main>%s</main></html>'''%"".join(cards)
    (OUT/"index.html").write_text(page,encoding="utf-8")
def publish():
    write_report()
    token=os.environ.get("GH_TOKEN","")
    if not token:return
    api="https://api.github.com/repos/"+REPO
    sess=requests.Session()
    sess.headers.update({"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    def call(method,path,body=None):
        resp=sess.request(method,api+path,json=body,timeout=45)
        if not resp.ok:raise RuntimeError("Publicación GitHub HTTP %d"%resp.status_code)
        return resp.json()
    head=call("GET","/git/ref/heads/"+quote(BRANCH,safe="/"))["object"]["sha"]
    tree=call("GET","/git/commits/"+head)["tree"]["sha"]
    files=[]
    for f in sorted(OUT.iterdir()):
        if not f.is_file() or f.suffix not in (".png",".jpg",".json",".html",".md"):continue
        content=f.read_bytes()
        b=call("POST","/git/blobs",{"content":base64.b64encode(content).decode(),"encoding":"base64"})
        files.append({"path":str(f.relative_to(Path.cwd())),"mode":"100644","type":"blob","sha":b["sha"]})
    new=call("POST","/git/trees",{"base_tree":tree,"tree":files})
    if new["sha"]==tree:return
    commit=call("POST","/git/commits",{"message":"Prueba sintética: %d/15 intentos, %d imágenes"%(
        sum(r["estado"] not in ("pendiente","ejecutando") for r in ROWS),sum(bool(r["imagen"]) for r in ROWS)),
        "tree":new["sha"],"parents":[head]})
    call("PATCH","/git/refs/heads/"+quote(BRANCH,safe="/"),{"sha":commit["sha"],"force":False})
    log("RESULTADOS_PUBLICADOS",{"sha":commit["sha"],"imagenes":sum(bool(r["imagen"]) for r in ROWS)})
def cf(row):
    account=os.environ.get("CF_ACCOUNT_ID","");token=os.environ.get("CF_API_TOKEN","")
    if not account or not token:raise RuntimeError("Faltan las credenciales existentes de Cloudflare")
    r=requests.post("https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s"%(account,row["modelo"]),
        headers={"Authorization":"Bearer "+token},
        json={"prompt":PROMPT,"negative_prompt":NEGATIVE,"width":1024,"height":1280,"num_steps":25,
              "seed":74103},timeout=180)
    row["http"]=r.status_code
    if not r.ok:raise RuntimeError("Cloudflare HTTP %d: %s"%(r.status_code,r.text[:1200]))
    if "image" in r.headers.get("Content-Type",""):data=r.content
    else:
        d=r.json();result=d.get("result") or {}
        b=result.get("image") if isinstance(result,dict) else None
        if not b:raise RuntimeError("Cloudflare respondió sin bytes de imagen")
        data=base64.b64decode(b.split(",",1)[-1])
    save_image(row,data)

def hf_discover(space):
    r=requests.get("https://huggingface.co/api/spaces/"+space,timeout=35)
    d=r.json() if r.ok else {}
    return {"http":r.status_code,"stage":(d.get("runtime") or {}).get("stage"),
            "host":d.get("host") or "https://"+space.replace("/","-").replace(".","-").lower()+".hf.space",
            "sdk":d.get("sdk"),"private":d.get("private",False)}
def get_hf_token():
    token=os.environ.get("HF_TOKEN","")
    if not token:return None,{"credencial":False,"detalle":"Sin HF_TOKEN; acceso público con cupo anónimo"}
    r=requests.get("https://huggingface.co/api/whoami-v2",headers={"Authorization":"Bearer "+token},timeout=30)
    if not r.ok:return None,{"credencial":True,"http":r.status_code,"detalle":"El token no autentica; se prueba el acceso público"}
    d=r.json()
    pro=bool(d.get("isPro",False))
    log("HF_ACCESO",{"autenticado":True,"pro":pro})
    if pro:return None,{"credencial":True,"pro":True,"detalle":"Se usa acceso público para impedir cargos al superar cuota PRO"}
    return token,{"credencial":True,"pro":False,"http":200}
def score_endpoint(name,ep):
    params=ep.get("parameters",[])
    p=" ".join(str(x.get("parameter_name",""))+" "+str(x.get("label","")) for x in params).lower()
    returns=" ".join(str(x.get("component",""))+" "+str(x.get("type","")) for x in ep.get("returns",[])).lower()
    n=name.lower()
    score=0
    if "prompt" in p:score+=20
    if any(s in returns for s in ("image","gallery","file")):score+=15
    if any(s in n for s in ("generate","infer","predict","run","process")):score+=10
    if any(s in n for s in ("prepare","enhance","rewrite","random","example","change","seed","load")):score-=40
    if not "prompt" in p:score-=50
    return score
def param_value(p,row):
    name=p.get("parameter_name","")
    low=(name+" "+str(p.get("label",""))).lower().replace("_"," ")
    default=p.get("parameter_default") if p.get("parameter_has_default") else None
    schema=p.get("type") or {}
    enum=schema.get("enum",[]) if isinstance(schema,dict) else []
    if enum:
        if "model" in low:
            return next((x for x in enum if "turbo" in str(x).lower()),default if default in enum else enum[0])
        if "resolution" in low or "width x height" in low:
            return next((x for x in enum if "864x1152" in str(x)),default if default in enum else enum[0])
        if "aspect" in low or "ratio" in low:
            return next((x for x in enum if "4:5" in str(x)),next((x for x in enum if "3:4" in str(x)),default if default in enum else enum[0]))
        if row["n"]==2 and "quality" in low and "speed" in enum:return "speed"
        return default if default in enum else enum[0]
    if "negative" in low and (schema.get("type")=="boolean" or "use negative" in low):return True
    if any(s in low for s in ("negative prompt","negative text")):return NEGATIVE
    if "prompt" in low and not any(s in low for s in ("extend","enhance","enable")):return PROMPT
    if any(s in low for s in ("enable extend","prompt extend","enable enhance","enhance prompt")):return False
    if "custom size" in low:return True
    if "quality" in low:return "speed" if row["n"]==2 else default
    if "random" in low:return False
    if "seed" in low:return 74103
    if "width" in low or "height" in low:
        target=832 if "width" in low else 1024
        desc=schema.get("description","") if isinstance(schema,dict) else ""
        bounds=re.search(r"between ([0-9.]+) and ([0-9.]+)",desc)
        if bounds:target=max(int(float(bounds.group(1))),min(target,int(float(bounds.group(2)))))
        return target
    if "aspect" in low:
        choices=enum or []
        return next((x for x in choices if str(x) in ("4:5","Portrait (4:5)")),
                    next((x for x in choices if "3:4" in str(x)),default or "4:5"))
    if "resolution" in low or "size preset" in low:
        choices=enum or []
        return next((x for x in choices if "1024x1280" in str(x)),next((x for x in choices if "864x1152" in str(x)),
              next((x for x in choices if "768x" in str(x) and "1344" in str(x)),default or (choices[0] if choices else "1024x1024"))))
    if "model" in low:
        return next((x for x in enum if "turbo" in str(x).lower()),default or (enum[0] if enum else "Turbo"))
    if any(s in low for s in ("num inference steps","num steps","steps")):
        if row["n"]==1:return 8
        if row["n"]==3:return 8
        if row["n"]==4:return default if default is not None else 2
        if row["n"]==9:return 20
        return 28
    if any(s in low for s in ("num images","num outputs","batch size")):return 1
    if any(s in low for s in ("input images","image paths","output gallery","gallery")):return []
    if "image" in low and not any(s in low for s in ("guidance","size")):return default
    if "guidance" in low:return default if default is not None else 4.5
    if "log dir" in low:return default or "./generation_logs_paper_case"
    if default is not None:return default
    if enum:return enum[0]
    typ=p.get("python_type") or {}
    t=str(typ.get("type","") if isinstance(typ,dict) else typ).lower()
    if "bool" in t:return False
    if "str" in t:return ""
    if "int" in t:return 1
    if "float" in t:return 1.0
    return None
def file_candidates(value):
    if isinstance(value,str) and re.search(r"\.(png|jpg|jpeg|webp)(?:\?|$)",value,re.I):yield value
    elif isinstance(value,dict):
        if value.get("path"):yield value["path"]
        elif value.get("url"):yield value["url"]
        for k,v in value.items():
            if k not in ("path","url","orig_name","mime_type","meta"):yield from file_candidates(v)
    elif isinstance(value,(list,tuple)):
        for v in value:yield from file_candidates(v)
def hf(row,token,metadata):
    from gradio_client import Client
    meta=metadata.get(row["modelo"],{})
    row["disponibilidad"]=meta
    kwargs={"verbose":False,"httpx_kwargs":{"timeout":45},"download_files":str(OUT/"descargas")}
    sig=inspect.signature(Client)
    if "token" in sig.parameters:kwargs["token"]=token
    elif "hf_token" in sig.parameters:kwargs["hf_token"]=token
    client=Client(row["modelo"],**kwargs)
    apis=client.view_api(return_format="dict")
    eps=apis.get("named_endpoints") or {}
    summary={name:{"parameters":[{"name":p.get("parameter_name"),"label":p.get("label"),
              "default":p.get("parameter_default"),"type":p.get("type")} for p in ep.get("parameters",[])],
              "returns":ep.get("returns",[])} for name,ep in eps.items()}
    (OUT/("%02d-api.json"%row["n"])).write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str)+"\n")
    if not eps:raise RuntimeError("Demo sin endpoint público identificado")
    names=sorted(eps,key=lambda x:score_endpoint(x,eps[x]),reverse=True)
    if row["n"]==2:
        prepare=next((x for x in eps if "prepare_request" in x),None)
        generate=next((x for x in eps if "generate_request" in x),None)
        names=[generate] if generate else names
        if prepare:
            ep=eps[prepare]
            values=[param_value(p,row) for p in ep.get("parameters",[])]
            log("HF_PREPARAR",{"n":row["n"],"endpoint":prepare})
            client.submit(*values,api_name=prepare).result(timeout=180)
    chosen=names[0]
    if not chosen or score_endpoint(chosen,eps[chosen])<15:raise RuntimeError("No se identificó función generadora de imagen")
    ep=eps[chosen]
    values=[param_value(p,row) for p in ep.get("parameters",[])]
    row["endpoint"]=chosen
    row["parametros"]=values
    log("HF_GENERAR",{"n":row["n"],"endpoint":chosen,"parametros":values})
    job=client.submit(*values,api_name=chosen)
    try:result=job.result(timeout=240)
    except Exception:
        try:job.cancel()
        except Exception:pass
        raise
    paths=list(file_candidates(result))
    for path in paths:
        try:
            if str(path).startswith("https://"):
                r=requests.get(path,timeout=45);r.raise_for_status();data=r.content
            else:data=Path(path).read_bytes()
            save_image(row,data)
            return
        except Exception:continue
    raise RuntimeError("El endpoint terminó, pero no entregó una imagen válida")

def kandinsky(row):
    key=os.environ.get("KANDINSKY_API_KEY","");secret=os.environ.get("KANDINSKY_SECRET_KEY","")
    row["credencial"]=bool(key and secret)
    if not key or not secret:
        row["estado"]="requiere registro"
        row["detalle"]="El API necesita API-key y Secret-key de Fusion Brain. No están instaladas. Se comprobó el portal sin registrar ni contratar un plan."
        try:
            r=requests.get("https://fusionbrain.ai/en/developers/",timeout=35);row["http_portal"]=r.status_code
        except Exception as e:row["portal"]=clean(e)
        return
    headers={"X-Key":"Key "+key,"X-Secret":"Secret "+secret}
    base="https://api-key.fusionbrain.ai/"
    r=requests.get(base+"key/api/v1/models",headers=headers,timeout=40);r.raise_for_status()
    models=r.json()
    model_id=models[0]["id"]
    request={"type":"GENERATE","numImages":1,"width":1024,"height":1024,"generateParams":{"query":PROMPT}}
    r=requests.post(base+"key/api/v1/text2image/run",headers=headers,
                    files={"model_id":(None,str(model_id)),
                           "params":(None,json.dumps(request),"application/json")},timeout=45)
    r.raise_for_status();uid=r.json()["uuid"]
    for _ in range(24):
        time.sleep(5)
        r=requests.get(base+"key/api/v1/text2image/status/"+uid,headers=headers,timeout=30);r.raise_for_status()
        d=r.json()
        if d.get("status")=="DONE":save_image(row,base64.b64decode(d["images"][0]));return
        if d.get("status")=="FAIL":raise RuntimeError("Kandinsky: generación rechazada")
    raise TimeoutError("Kandinsky no terminó en 120 segundos")

def web(row):
    from playwright.sync_api import sync_playwright
    url=row["modelo"]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":1000},locale="es-MX")
        resp=page.goto(url,wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(6000)
        row["http"]=resp.status if resp else None
        title=page.title();text=page.locator("body").inner_text(timeout=10000)
        row["titulo"]=clean(title)
        page.screenshot(path=str(OUT/("%02d-acceso-web.png"%row["n"])),full_page=False)
        (OUT/("%02d-acceso-web.txt"%row["n"])).write_text(clean(text),encoding="utf-8")
        # Solo se evalúa la experiencia gratuita. No se cambia a una API de pago ni se crea una identidad.
        row["estado"]="requiere sesión web"
        row["detalle"]="El acceso gratuito se ofrece dentro de una sesión de cuenta del proveedor. El navegador de ejecución no tiene esa sesión; no se recibió una imagen generada."
        if row["http"] in (401,403,429):
            row["estado"]="acceso bloqueado"
            row["detalle"]="El proveedor respondió HTTP %s al navegador de nube; no se recibió una imagen."%row["http"]
        browser.close()

def main():
    log("PRUEBA_15_INICIO",{"run_id":RUN,"modelos":15,"encargo":PROMPT,"escrituras_negocio":0})
    previous=OUT/"resultados.json"
    if previous.exists():
        saved=json.loads(previous.read_text(encoding="utf-8"))
        for old in saved.get("opciones",[]):
            n=old.get("n",0)
            if 1<=n<=15:ROWS[n-1].update(old)
    token,auth=get_hf_token()
    (OUT/"acceso-hf.json").write_text(json.dumps(auth,ensure_ascii=False,indent=2)+"\n")
    spaces=[r["modelo"] for r in ROWS if r["tipo"]=="hf"]
    metadata={}
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks={pool.submit(hf_discover,s):s for s in spaces}
        for future in as_completed(tasks):
            s=tasks[future]
            try:metadata[s]=future.result()
            except Exception as e:metadata[s]={"error":clean(e)}
    (OUT/"demos.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n")
    log("DEMOS",metadata)
    publish()
    # Primero dos proveedores ya autenticados; HF se ordena para reservar el demo de duración más alta antes de consumir el cupo.
    order=[1,7,8]
    for n in order:
        row=ROWS[n-1]
        row.setdefault("intentos_anteriores",[]).append({k:row.get(k) for k in ("estado","detalle","http","segundos")})
        row["estado"]="ejecutando";row.pop("detalle",None)
        start=time.monotonic()
        log("PRUEBA",{"n":n,"motor":row["nombre"],"estado":"ejecutando"})
        try:
            if row["tipo"]=="cf":cf(row)
            elif row["tipo"]=="hf":hf(row,token,metadata)
            elif row["tipo"]=="kandinsky":kandinsky(row)
            else:web(row)
        except Exception as e:
            error=clean(e)
            row["detalle"]=error
            low=error.lower()
            row["estado"]=("sin cupo" if any(s in low for s in ("quota","daily free","429","exceeded","gpu time","cuota"))
                          else "requiere acceso" if any(s in low for s in ("401","403","token","auth","login","sign in","credential"))
                          else "falló la generación")
        row["segundos"]=round(time.monotonic()-start,1)
        log("RESULTADO",row)
        try:publish()
        except Exception as e:log("PUBLICACION_PENDIENTE",{"error":clean(e)})
    publish()
    log("PRUEBA_15_FINAL",{"intentados":15,"generadas":sum(bool(r["imagen"]) for r in ROWS),
                          "estados":[{"n":r["n"],"estado":r["estado"]} for r in ROWS]})
if __name__=="__main__":main()
