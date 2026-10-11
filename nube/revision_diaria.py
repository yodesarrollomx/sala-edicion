#!/usr/bin/env python3
"""Revisión agregada; ningún registro de negocio ni credencial se publica."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import sala_cliente as sala
from snapshots_online import Snapshots, OnlineError
from correo_estado import observar as observar_correo, workflows as observar_workflows

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "datos" / "revision.json"
ROUTINES = [
    ("plan", "Atribución de Plan", "Cada hora", 24, "25 * * * *"),
    ("productor", "Productor", "Cada 20 minutos", 72, "10,30,50 * * * *"),
    ("ejecutor", "Voz, escena y corte", "Cada dos horas y al recibir trabajo", 12, "20 */2 * * *"),
    ("mesa", "Mesa de edición", "Cada hora y a las 05:40", 25, "35 * * * *; 40 12 * * *"),
    ("arranque", "Ideas elegidas", "Cada hora; semillero a las 05:50", 25, "5 * * * *; 50 12 * * *"),
    ("chinches", "Encargos", "Cada hora", 24, "45 * * * *"),
    ("maquinas", "Salud de las rutinas", "Cada dos horas", 12, "15 */2 * * *"),
    ("relevo", "Respaldo del tablero", "06:00, 09:00, 12:00, 15:00 y 18:00", 5, "0 13,16,19,22,1 * * *"),
]


def aggregate_queue(response):
    if (not isinstance(response, dict) or response.get("ok") is False
            or response.get("error") or not isinstance(response.get("cola"), list)):
        raise ValueError("Lectura de cola sin contrato")
    counts = Counter()
    for row in response["cola"]:
        if not isinstance(row, dict) or not isinstance(row.get("estado"), str):
            raise ValueError("Cola incompleta")
        state = row["estado"]
        counts[state if state in {"pendiente", "corriendo", "hecho", "fallo", "obsoleto"} else "otro"] += 1
    return {"total": len(response["cola"]), **{key: counts[key] for key in
             ("pendiente", "corriendo", "hecho", "fallo", "obsoleto", "otro")}}


def observe_runs(api):
    wanted = {r[0] for r in ROUTINES}
    result = {}
    # Hasta 400 latidos públicos: cubre el relevo aunque haya muchos productores.
    for page in range(1, 5):
        response = api.request(f"actions/runs?per_page=100&page={page}")
        if not isinstance(response.get("workflow_runs"), list):
            raise OnlineError("Actions sin contrato")
        for run in response["workflow_runs"]:
            if run.get("head_branch") != "main" or run.get("event") not in ("schedule", "workflow_dispatch", "push"):
                continue
            filename = str(run.get("path", "")).split("/")[-1]
            if filename not in {*(f"sala-{r[0]}.yml" for r in ROUTINES),
                                 "sala-cada-hora.yml", "sala-diario.yml", "sala-cierre-online.yml", "sala-vigilante.yml"}:
                continue
            jobs = api.request("actions/runs/" + str(run["id"]) + "/jobs?per_page=100").get("jobs")
            if not isinstance(jobs, list):
                raise OnlineError("Jobs sin contrato")
            for job in jobs:
                if job.get("conclusion") == "skipped":
                    continue
                name = str(job.get("name", "")).split(" / ")[-1]
                process = "chinches" if name in ("puente", "chinches") else name
                if process in wanted and process not in result:
                    result[process] = {"run_id": str(run["id"]), "status": job.get("status"),
                        "conclusion": job.get("conclusion"), "comenzo": job.get("started_at"),
                        "termino": job.get("completed_at")}
            if wanted.issubset(result):
                return result
        if len(response["workflow_runs"]) < 100:
            break
    return result


def collect(previous, getter, api, now):
    output = {"schema": 1, "revisado_en": now, "zona_horaria": "America/Hermosillo",
              "cola": previous.get("cola"), "cola_leida_en": previous.get("cola_leida_en"),
              "cola_estado": "sin_confirmar", "reglas_estado": "sin_confirmar",
              "etapas": previous.get("etapas", []), "errores": [],
              "rutinas_estado": "sin_confirmar", "rutinas": previous.get("rutinas", [])}
    try:
        output["cola"] = aggregate_queue(getter("cola"))
        output["cola_leida_en"] = now
        output["cola_estado"] = "confirmada"
    except (sala.SalaError, ValueError):
        output["errores"].append("cola_sin_lectura_confirmada")
    try:
        rules = getter("reglas")
        if (not isinstance(rules, dict) or rules.get("ok") is False or rules.get("error")
                or not isinstance(rules.get("reglas"), dict)):
            raise ValueError("Reglas sin contrato")
        output["etapas"] = sorted(set(str(rules["reglas"].get("nube_ejecuta_etapas", "")).split(","))
                                  & {"voz", "escena", "corte", "prospecto"})
        output["reglas_estado"] = "confirmada"
    except (sala.SalaError, ValueError):
        output["errores"].append("reglas_sin_lectura_confirmada")
    try:
        observed = observe_runs(api)
        output["rutinas"] = [{"id": ident, "nombre": name, "frecuencia": frequency,
            "horarios_diarios_declarados": times, "cron_utc": cron,
            "ultima": observed.get(ident)} for ident, name, frequency, times, cron in ROUTINES]
        output["rutinas_estado"] = "confirmada"
    except OnlineError:
        output["errores"].append("rutinas_sin_lectura_confirmada")
    try:
        output["correo"] = observar_correo(getter("bitacora"), now)
    except (sala.SalaError, ValueError):
        output["correo"] = {**previous.get("correo", {}), "estado": "lectura_sin_confirmar",
                            "fuente": "Apps Script", "recepcion_verificada": False}
        output["errores"].append("correo_sin_lectura_confirmada")
    try:
        output["disparadores_nube"] = observar_workflows(api)
        if not all(x["activo"] for x in output["disparadores_nube"]):
            output["errores"].append("rutina_nube_desactivada")
    except (OnlineError, ValueError, AttributeError):
        output["disparadores_nube"] = previous.get("disparadores_nube", [])
        output["errores"].append("disparadores_nube_sin_lectura_confirmada")
    return output


def main():
    sala.enmascarar_en_actions()
    previous = {}
    if DEST.exists():
        try:
            previous = json.loads(DEST.read_text())
        except (ValueError, OSError):
            pass
    now = datetime.now(timezone.utc).isoformat()
    s = Snapshots(ROOT)
    output = collect(previous, sala.get, s.api, now)
    DEST.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"revision": "preparada", "cola_estado": output["cola_estado"],
                      "rutinas_estado": output["rutinas_estado"], "errores": output["errores"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
