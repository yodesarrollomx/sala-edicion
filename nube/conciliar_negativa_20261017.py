"""Conciliación única: sólo la negativa explícita de L2/toma1 del run inspeccionado."""
import sys,os,json,subprocess,hashlib,re
sys.path.insert(0,"nube")
from sala_recibos import Recibos,digest,canonical
RID="6bf4f31211495b36176a36d652fc3dc84f7598e43029aba22cfa3694425049ff"
RUN="39069605297"
JOB="117504286674"
owner=RUN+"-1"
s=Recibos(RID)
plan_pair=s.get("plan.zip")
assert plan_pair is not None
plan=plan_pair[0];src=plan["entradas"]
assert plan["run_id"]==RUN and str(plan["run_attempt"])=="1"
assert src["pieza"]=="dato-servilleta-3" and src["n"]==2 and src["variante"]==1
assert src["fuente"]=="dato-servilleta-3-arranque-2026-09-27-1eca95"
assert hashlib.sha256(json.dumps(src,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==RID
assert plan["configuracion"]["imagen_motores"]=="hidream_demo"
sha=digest(canonical(plan))
assert s.get("envio-"+owner+".zip")[0]=={"plan_sha256":sha,"estado":"enviado"}
assert s.get("resultado.zip") is None
assets={a["name"] for a in s.find()["assets"]}
assert {x for x in assets if x.startswith("envio-")}=={"envio-"+owner+".zip"}
log=subprocess.run(["gh","run","view",RUN,"--repo",os.environ["GITHUB_REPOSITORY"],"--job",JOB,"--log"],check=True,capture_output=True,text=True).stdout
start="▶ La servilleta contra el estudio · tira "+src["fuente"]+" · 4 lámina(s) abiertas"
assert log.count(start)==1
section=log.split(start)[1].split("L3 · pendiente")[0]
assert "L2 · pendiente" in section
proof="toma 1: ningún motor de imagen pudo: HiDream sin imagen confirmada: no entregó imagen: Error: Task failed with status 3: Unknown error"
assert section.count(proof)==1
# No se infiere nada para toma2: su log no conserva el estado terminal exacto.
record={"estado":"rechazo_sin_imagen","motivo":"tarea_fallida","plan_sha256":sha}
s.put("rechazo-"+owner+".zip",record)
assert s.get("rechazo-"+owner+".zip")[0]==record
assert not s.pending(sha)
print(json.dumps({"conciliado":True,"fuente":src["fuente"],"lamina":2,"toma":1,"run_evidencia":RUN,"job_evidencia":JOB,"plan_sha256":sha,"log_sha256":hashlib.sha256(log.encode()).hexdigest(),"decisiones_modificadas":0,"toma2":"sin conciliacion automatica; evidencia insuficiente"}))
