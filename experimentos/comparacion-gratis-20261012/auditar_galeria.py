#!/usr/bin/env python3
import hashlib, importlib.util, io, json, os, time, zipfile
from pathlib import Path
import requests
from PIL import Image
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"resultados"
OUT.mkdir(exist_ok=True)
HOST="https://yod-prueba-15-imagenes-gratis.onrender.com"
r=requests.get(HOST+"/resultados.json",timeout=40)
r.raise_for_status()
report=r.json()
rows=report["opciones"]
assert sorted(x["n"] for x in rows)==list(range(1,16))
home=requests.get(HOST+"/",timeout=40);home.raise_for_status()
assert home.text.count("<article>")==15
checks=[]
for row in rows:
    if not row.get("imagen"):continue
    image=requests.get(HOST+"/"+row["imagen"],timeout=40);image.raise_for_status()
    digest=hashlib.sha256(image.content).hexdigest()
    assert digest==row["sha256"],"La foto servida no coincide con la registrada"
    im=Image.open(io.BytesIO(image.content));im.verify()
    checks.append({"n":row["n"],"motor":row["nombre"],"http":image.status_code,
                   "sha256":digest,"resolucion":row["resolucion"],
                   "original":HOST+"/"+row["imagen"],
                   "generacion_run_id":"38329443469"})
    (OUT/row["imagen"]).write_bytes(image.content)
    preview=requests.get(HOST+"/"+row["vista"],timeout=40);preview.raise_for_status()
    (OUT/row["vista"]).write_bytes(preview.content)
model_metadata=[]
try:
    ar=requests.get("https://api.github.com/repos/yodesarrollomx/sala-edicion/actions/artifacts/11781488622/zip",
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
                 "Accept":"application/vnd.github+json"},timeout=50)
    ar.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(ar.content)) as z:
        for name in z.namelist():
            if "descargas/" not in name or not name.lower().endswith((".png",".jpg",".jpeg")):continue
            img=Image.open(io.BytesIO(z.read(name)))
            m={k:v for k,v in img.info.items() if k in ("model","seed","generated_by","generated_at")}
            if m:model_metadata.append(m)
except Exception as e:
    model_metadata.append({"estado":"No se pudo leer metadato del original del proveedor","tipo_error":type(e).__name__})
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":390,"height":844})
    page.goto(HOST,wait_until="networkidle",timeout=60000)
    assert page.locator("article").count()==15
    assert page.locator("article img").count()==len(checks)
    page.screenshot(path=str(OUT/"galeria-movil.png"),full_page=True)
    browser.close()
audit={"utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"galeria_http":home.status_code,
       "tarjetas":15,"imagenes_verificadas":checks,"modelo_metadatos_proveedor":model_metadata,
       "reintento_utc":"2026-10-13T04:08:00Z","reintento_hmo":"2026-10-12 21:08",
       "reintento_run_id":"38330387449","writes_business":0,"production_changed":False}
(OUT/"auditoria-galeria.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
print("GALERIA_VERIFICADA "+json.dumps(audit,ensure_ascii=False),flush=True)
spec=importlib.util.spec_from_file_location("prueba",ROOT/"prueba.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
for row in rows:
    if row.get("imagen"):
        row["generacion_run_id"]="38329443469"
        row["generacion_recibo"]="https://github.com/yodesarrollomx/sala-edicion/actions/runs/38329443469"
    if row["tipo"]=="hf" and not row.get("imagen"):
        row["reintento_programado_utc"]="2026-10-13T04:08:00Z"
        row["reintento_programado_hmo"]="2026-10-12 21:08"
mod.ROWS[:]=rows
mod.RUN=report["run_id"]
mod.publish()
