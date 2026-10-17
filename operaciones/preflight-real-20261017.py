import sys,json,os
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path("nube").resolve()))
import sala_cliente as sala
import sala_produccion as produccion
import sala_mesa as mesa
from contenido_reglas import revisar
sala.enmascarar_en_actions()
report={"at":datetime.now(timezone.utc).isoformat(),"run_id":os.environ["GITHUB_RUN_ID"],"code_sha":os.environ["GITHUB_SHA"],"escrituras_negocio":0}
try:
    hist=produccion.validar_historica(sala.get("produccion",fresco="1"))
    report["contrato_historico"]={"ok":True,"propuestas":len(hist.get("propuestas",[]))}
except Exception as e:
    report["contrato_historico"]={"ok":False,"tipo":type(e).__name__,"codigo":getattr(e,"codigo",None)}
rules=(sala.get("reglas") or {}).get("reglas") or {}
dia=produccion.cargar(historica=False)
mesa.hidratar_tiras_activas(dia)
piezas=mesa.tiras_vigentes(mesa.tiras_por_pieza(),dia)
props={p["id"]:p for p in dia["propuestas"]}
decs=(dia.get("decisiones") or {}).get("propuestas") or {}
out=[]
for slug,(pid,t) in sorted(piezas.items()):
    resolved=produccion.resolver_tira(t,decs.get(pid) or {},props[pid])
    frames=resolved.get("laminas") or []
    invalid=revisar(resolved,rules)
    out.append({"pieza":slug,"tira":pid,"laminas":len(frames),"laminas_guion":len(resolved.get("guion") or []),
                "aprobadas":sum(l.get("estado")=="aprobada" for l in frames),
                "faltantes":len(produccion.guion_faltante(resolved)),
                "video":produccion.es_video(resolved),"vetos_contenido":len(invalid),
                "rutas_veto":[x.split(":")[0] for x in invalid]})
cola=(sala.get("cola") or {}).get("cola") or []
counts={}
for x in cola:counts[x.get("estado","sin_estado")]=counts.get(x.get("estado","sin_estado"),0)+1
report.update(piezas=out,cola=counts,peticiones_abiertas=produccion.peticiones_abiertas(),
    ejecuta_etapas=rules.get("nube_ejecuta_etapas"),modelo_imagen=rules.get("imagen_motores"))
Path("evidencia-preflight").mkdir(exist_ok=True)
Path("evidencia-preflight/preflight.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("PREPARACION_REAL "+json.dumps(report,ensure_ascii=False))
