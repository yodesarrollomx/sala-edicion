import sys,os,json,pathlib,hashlib,time,tempfile
sys.path.insert(0,"nube")
from sala_recibos import Recibos
from gradio_client import Client
from PIL import Image
rid="6bf4f31211495b36176a36d652fc3dc84f7598e43029aba22cfa3694425049ff"
plan=Recibos(rid).get("plan.zip")[0]
assert plan["entradas"]["pieza"]=="dato-servilleta-3"
assert plan["entradas"]["n"]==2 and plan["entradas"]["variante"]==1
out=pathlib.Path("evidencia-hidream-o1");out.mkdir(exist_ok=True)
started=time.monotonic()
with tempfile.TemporaryDirectory() as td:
 c=Client("HiDream-ai/HiDream-O1-Image-Dev",verbose=False,download_files=td)
 job=c.submit(plan["prompt_imagen"],"3:4",False,124,api_name="/_generate_wrapped")
 try: result=job.result(timeout=360)
 except Exception as e:
  print(json.dumps({"ok":False,"tipo":type(e).__name__,"detalle":str(e)[:250]}))
  raise SystemExit(1)
 p=result[0] if isinstance(result,(list,tuple)) else result
 if isinstance(p,dict):p=p.get("path")
 if not p:
  print(json.dumps({"ok":False,"causa":"sin_imagen","respuesta":str(result)[:250]}))
  raise SystemExit(1)
 p=pathlib.Path(p).resolve()
 assert pathlib.Path(td).resolve() in p.parents
 data=p.read_bytes();assert 5000<len(data)<25*1024*1024
 (out/"original.png").write_bytes(data)
 im=Image.open(p);im.verify()
 im=Image.open(p).convert("RGB");assert min(im.size)>=512
 im.thumbnail((1024,1365));im.save(out/"prueba.jpg",quality=90)
 report={"ok":True,"space":"HiDream-ai/HiDream-O1-Image-Dev","lamina":2,"pieza":"dato-servilleta-3","segundos":round(time.monotonic()-started,2),"imagen_sha256":hashlib.sha256(data).hexdigest(),"preview_sha256":hashlib.sha256((out/"prueba.jpg").read_bytes()).hexdigest(),"prompt_sha256":hashlib.sha256(plan["prompt_imagen"].encode()).hexdigest(),"run_id":os.environ["GITHUB_RUN_ID"],"alcance":"prueba de reemplazo con receta real; no montada en Sala ni aprobada editorialmente"}
 (out/"resultado.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(report))
