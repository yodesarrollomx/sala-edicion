import sys,json,re,urllib.request
sys.path.insert(0,"nube")
from snapshots_online import GitHub
from sala_recibos import unpack
import os
api=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
count=0
for page in range(1,101):
 rows=api.request("releases?per_page=100&page="+str(page))
 for row in rows:
  if not row.get("draft") or not row.get("tag_name","").startswith("sala-ejecucion-"):continue
  assets={a["name"]:a for a in row.get("assets",[])}
  if "plan.zip" not in assets or "resultado.zip" in assets:continue
  plan,_=unpack(api.asset(assets["plan.zip"]["id"]))
  src=plan.get("entradas",{})
  print("PENDIENTE",json.dumps({"rid":row["tag_name"].removeprefix("sala-ejecucion-"),"pieza":src.get("pieza"),"fuente":src.get("fuente"),"n":src.get("n"),"variante":src.get("variante"),"run_plan":plan.get("run_id"),"assets":sorted(assets),"motores":plan.get("configuracion",{}).get("imagen_motores")}))
  count+=1
 if len(rows)<100:break
print("PENDIENTES",count)
u="https://huggingface.co/spaces/HiDream-ai/HiDream-I1-Dev/raw/main/app.py"
s=urllib.request.urlopen(u,timeout=30).read().decode()
lines=s.splitlines()
for i,l in enumerate(lines):
 if "status" in l and ("3" in l or "failed" in l):
  print("PROVEEDOR",i+1,"\n".join(lines[max(0,i-3):i+5]))
