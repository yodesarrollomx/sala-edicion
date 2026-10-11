#!/usr/bin/env python3
"""Sonda de cierre: lecturas, sin reglas/triggers/correos ni negocio escritos."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sala_cliente as sala
from snapshots_online import GitHub

def main():
    sala.enmascarar_en_actions()
    report = {"revisado_en": datetime.now(timezone.utc).isoformat(),
              "escrituras_negocio": 0, "correos_enviados": 0, "errores": []}
    for resource in ("reglas", "cola", "dia", "bitacora"):
        try:
            d = sala.get(resource, **({"fresco": "1"} if resource == "dia" else {}))
            if not isinstance(d, dict) or d.get("ok") is False or d.get("error"):
                raise ValueError("contrato")
            if resource == "reglas":
                r=d.get("reglas")
                if not isinstance(r,dict): raise ValueError("reglas")
                names=("nube_ejecuta_etapas","productor_ejecuta_etapas","nube_tope_minutos",
                       "nube_tope_trabajos","escena_modal","escena_parallax","escena_respaldo_camara",
                       "voz_motor","voz_respaldo","silencio_desde","silencio_hasta",
                       "cerebro_pago_tope_dia","imagen_motores","cerebro_motores")
                report[resource] = {k:r[k] for k in names if k in r}
                report["drive_raiz_configurada"] = bool(r.get("drive_raiz"))
                report["motores"] = [{"etapa":x.get("etapa"),"motor":x.get("motor"),
                    "encendido":x.get("encendido"),"tope_dia":x.get("tope_dia")} for x in d.get("motores",[])]
            elif resource == "cola":
                rows=d.get("cola")
                if not isinstance(rows,list): raise ValueError("cola")
                report[resource] = {"total":len(rows),"por_estado":dict(Counter(str(x.get("estado")) for x in rows)),
                    "por_etapa_estado":dict(Counter(str(x.get("etapa"))+":"+str(x.get("estado")) for x in rows))}
            elif resource == "dia":
                report[resource] = {"fecha":d.get("fecha"),"version":d.get("version"),"rol":d.get("rol"),
                    "propuestas":len(d.get("propuestas") or []),"peticiones":len(d.get("peticiones") or []),
                    "claves_respuesta":sorted(d)}
            else:
                report["correo_eventos"] = [{"cuando":x.get("cuando"),"evento":x.get("evento")}
                    for x in d.get("bitacora",[]) if "correo" in str(x.get("evento","")).lower()]
        except Exception:
            report["errores"].append(resource+"_sin_confirmar")
    api=GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    workflows=[]
    for name in ("sala-cada-hora.yml","sala-diario.yml","sala-plan.yml","sala-revision.yml",
                 "sala-prueba-online.yml","sala-ejecutor.yml"):
        try:
            w=api.request("actions/workflows/"+name)
            runs=api.request("actions/workflows/"+name+"/runs?branch=main&per_page=8")
            workflows.append({"archivo":name,"state":w.get("state"),"id":w.get("id"),
                "ejecuciones":[{"id":x.get("id"),"event":x.get("event"),"status":x.get("status"),
                    "conclusion":x.get("conclusion"),"created_at":x.get("created_at"),"sha":x.get("head_sha")}
                    for x in runs.get("workflow_runs",[])]})
        except Exception:
            report["errores"].append(name+"_sin_confirmar")
    report["workflows"]=workflows
    sala.avisar("CIERRE_SONDA "+json.dumps(report,ensure_ascii=False,sort_keys=True))
    return 0 if not report["errores"] else 2

if __name__=="__main__":
    raise SystemExit(main())
