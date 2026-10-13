import contextlib, hashlib, io, json, os, pathlib, re, subprocess, sys, urllib.request
root=pathlib.Path.cwd()/"_codigo-temporal"
sys.path.insert(0,str(root/"nube"))
import sala_cliente as sala
sala.enmascarar_en_actions()
expected=os.environ["SOURCE_SHA"]
site="https://yodesarrollomx.github.io/sala-edicion/"
def get(path):
    with urllib.request.urlopen(site+path+"?verificar="+expected,timeout=60) as r:return r.read()
sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
assert sha==expected
verified=[]
for name in ["index.html","tablero-sala.js","tablero-sala.css","politica-imagen.json"]:
    served=get(name);local=(root/name).read_bytes()
    assert served==local,name+" no coincide"
    verified.append(name)
version=json.loads(get("version-online.json"))
from snapshots_online import Snapshots
snap=Snapshots(root);snap.bootstrap()
rules=(sala.get("reglas") or {}).get("reglas") or {}
assert rules.get("imagen_motores")=="hidream_demo"
import sala_mesa as mesa
capture=io.StringIO()
with contextlib.redirect_stdout(capture):
    old=sys.argv;sys.argv=["sala_mesa.py","--simular"]
    try:code=mesa.main()
    finally:sys.argv=old
assert code==0
# Sólo reporte agregado; jamás notas, claves ni exportaciones de Sheets.
summary=re.search(r"resumen: (\d+) carta",capture.getvalue())
raw=(sala.get("dia") or {})
proposals=raw.get("propuestas") or []
active=0;hidream=0;slides=0
for p in proposals:
    path=root/"datos/tiras"/(str(p.get("id"))+".json")
    if not path.exists():continue
    t=json.loads(path.read_text());active+=1
    for l in t.get("laminas") or []:
        slides+=1
        hidream+=sum(c.get("modelo")=="HiDream-I1-Dev" for c in l.get("candidatas") or [])
report={"ok":True,"code_sha":sha,"archivos_publicados_verificados":verified,
        "modelo_configurado":"HiDream-I1-Dev","motor_configurado":rules["imagen_motores"],
        "simulacion_mesa":code,"cartas_que_prepararia":int(summary[1]) if summary else None,
        "tiras_activas_inspeccionadas":active,"laminas_inspeccionadas":slides,
        "candidatas_hidream":hidream,"decisiones_escritas":0,
        "recibo_pages_confirmado":bool(version),"disponibilidad_gratuita":"sin cuota diaria garantizada"}
out=pathlib.Path("operaciones/tablero-20261013");out.mkdir(parents=True,exist_ok=True)
(out/"publicacion.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report))
