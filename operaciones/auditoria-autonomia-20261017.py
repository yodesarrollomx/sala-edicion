import concurrent.futures as cf, json, urllib.request as u, urllib.parse as p, datetime, hashlib
BASE="https://yodesarrollomx.github.io/sala-edicion/"
def get(path):
 req=u.Request(BASE+path+(" &" if "?" in path else "?").strip()+"auditoria=20261017",headers={"User-Agent":"Sala-auditoria-lectura"})
 with u.urlopen(req,timeout=40) as r:return r.read()
out={"fecha":datetime.datetime.now(datetime.timezone.utc).isoformat(),"negocio_modificado":False,"publico":{}}
for path in ["version-online.json","index.html","tablero-sala.js","tablero-sala.css","datos/revision.json","datos/mesa-estado.json","datos/manifiesto.json"]:
 try:
  b=get(path);entry={"ok":True,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
  if path=="version-online.json":
   d=json.loads(b);entry["recibo"]={k:v for k,v in d.items() if isinstance(v,(int,float,bool)) or k in ("code_sha","data_sha","snapshot_id","run_id","publicacion_id","plan_sha")}
  if path=="datos/revision.json":
   d=json.loads(b);entry["estado"]={k:d.get(k) for k in ("revisado_en","cola","cola_estado","reglas_estado","etapas","errores","rutinas_estado","rutinas","correo")}
  if path=="datos/mesa-estado.json":
   d=json.loads(b);entry["estado"]={k:d.get(k) for k in ("estado","revisado_en","generadas","reutilizadas","fallidas","causa","modelo_imagen","cartas")}
  if path=="datos/manifiesto.json":manifest=json.loads(b)
  out["publico"][path]=entry
 except Exception as e:out["publico"][path]={"ok":False,"error":type(e).__name__}
def paths(obj):
 if isinstance(obj,dict):
  for v in obj.values():yield from paths(v)
 elif isinstance(obj,list):
  for v in obj:yield from paths(v)
 elif isinstance(obj,str):yield obj
tiras=sorted({s for s in paths(globals().get("manifest",{})) if s.startswith("datos/tiras/") and s.endswith(".json") and ".." not in s})
try:
 index=json.loads(get("datos/tiras/index.json"))
 if isinstance(index,list):
  tiras=sorted(set(tiras)|{"datos/tiras/"+s+".json" for s in index if isinstance(s,str) and "/" not in s and ".." not in s})
except Exception:out["indice_tiras_error"]=True
out["tiras_detectadas"]=len(tiras)
photos=set();errors=0
for t in tiras:
 try:
  d=json.loads(get(t))
  for s in paths(d):
   s=s.removeprefix(BASE)
   if s.startswith(("laminas/","muestras/","video/")) and s.lower().endswith((".jpg",".png",".webp",".mp4",".wav",".mp3")) and ".." not in s:photos.add(s)
 except Exception:errors+=1
def head(path):
 try:
  req=u.Request(BASE+p.quote(path,safe="/"),method="HEAD",headers={"User-Agent":"Sala-auditoria"})
  with u.urlopen(req,timeout=30) as r:return r.status==200
 except Exception:return False
with cf.ThreadPoolExecutor(max_workers=6) as pool:checks=list(pool.map(head,sorted(photos)[:250]))
out["medios"]={"detectados":len(photos),"comprobados":len(checks),"respondieron":sum(checks),"fallaron":len(checks)-sum(checks),"tiras_fallidas":errors}
for label,url in [("render","https://yod-cloud-room.onrender.com/healthz"),("hidream","https://huggingface.co/api/spaces/HiDream-ai/HiDream-I1-Dev")]:
 try:
  with u.urlopen(url,timeout=40) as r:
   d=json.loads(r.read());out[label]={"http":r.status,"runtime":d.get("runtime"),"status":d.get("status"),"ok":d.get("ok")}
 except Exception as e:out[label]={"error":type(e).__name__}
open("auditoria.json","w").write(json.dumps(out,ensure_ascii=False,indent=2))
print("AUDITORIA_RESULTADO "+json.dumps(out,ensure_ascii=False))
