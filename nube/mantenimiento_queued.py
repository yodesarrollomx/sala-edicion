#!/usr/bin/env python3
"""Intento manual acotado sobre una sola corrida huérfana; nunca borra historial.

API oficial: https://docs.github.com/en/rest/actions/workflow-runs#force-cancel-a-workflow-run
202 sólo acredita aceptación; se exige leer completed/cancelled. La API no
ofrece un CAS para cancelar: se releen las compuertas justo antes del único POST.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import time

from snapshots_online import GitHub, OnlineError

REPO = "yodesarrollomx/sala-edicion"
RUN = 37655539140
HEAD = "b6a28ea3885801818a6d5928d9776b1fb7f79028"
MIN_AGE = timedelta(days=7)


def identity(run):
    if (not isinstance(run, dict) or type(run.get("id")) is not int
            or run.get("id") != RUN or run.get("head_sha") != HEAD
            or type(run.get("run_attempt")) is not int or run.get("run_attempt") != 1
            or not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != REPO
            or run.get("head_branch") != "main" or run.get("event") != "schedule"
            or run.get("path") != ".github/workflows/sala-cada-hora.yml"):
        raise OnlineError("La corrida no coincide con la allowlist de mantenimiento")


def eligible(run, jobs, now):
    identity(run)
    if (run.get("status") != "queued" or "conclusion" not in run
            or run.get("conclusion") is not None):
        raise OnlineError("Sólo se permite la corrida aún queued y sin conclusión")
    try:
        stamp = run.get("created_at")
        if not isinstance(stamp, str):
            raise ValueError("Fecha ausente")
        created = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        old = created.tzinfo is not None and now - created >= MIN_AGE
    except (KeyError, TypeError, ValueError):
        old = False
    if not old:
        raise OnlineError("La antigüedad mínima de siete días no está comprobada")
    if (not isinstance(jobs, dict) or type(jobs.get("total_count")) is not int
            or jobs.get("total_count") != 0 or jobs.get("jobs") != []):
        raise OnlineError("La corrida tiene jobs o su ausencia no está comprobada")


def maintain(api, *, apply=False, now=None, clock=time.monotonic, sleep=time.sleep, timeout=60):
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise OnlineError("El plazo de conciliación debe ser positivo y finito")
    now = now or datetime.now(timezone.utc)
    endpoint = "actions/runs/" + str(RUN)

    def inspect():
        run = api.request(endpoint)
        jobs = api.request(endpoint + "/jobs?filter=all&per_page=100")
        eligible(run, jobs, now)

    inspect()
    if not apply:
        return {"run_id": RUN, "modo": "simular", "elegible": True, "cancelado": False}
    # Reduce la ventana de carrera; ni estos GET ni force-cancel son un CAS.
    inspect()
    ambiguous = False
    post_http = None
    try:
        api.request(endpoint + "/force-cancel", method="POST")
    except OnlineError as exc:
        # El cliente ya elimina cuerpos remotos; sólo se conservan códigos conocidos.
        codes = {"GitHub HTTP " + str(code): code
                 for code in (401, 403, 404, 409, 422, 429, 500, 502, 503, 504)}
        post_http = codes.get(str(exc))
        ambiguous = post_http not in (401, 403, 404, 409, 422, 429)
        # Un solo POST incluso si la respuesta se pierde o rechaza la petición.
    deadline = clock() + timeout
    read_errors = 0
    while clock() < deadline:
        try:
            observed = api.request(endpoint)
        except OnlineError:
            # Sólo se repite lectura. Un error de lectura no acredita cancelación.
            read_errors += 1
            sleep(min(5, max(0, deadline - clock())))
            continue
        identity(observed)
        if observed.get("status") == "completed":
            cancelled = observed.get("conclusion") == "cancelled"
            return {"run_id": RUN, "modo": "aplicar", "cancelado": cancelled,
                    "terminal": True, "respuesta_ambigua": ambiguous,
                    "post_http_status": post_http, "errores_lectura": read_errors}
        sleep(min(5, max(0, deadline - clock())))
    return {"run_id": RUN, "modo": "aplicar", "cancelado": False,
            "terminal": False, "respuesta_ambigua": ambiguous,
            "post_http_status": post_http, "errores_lectura": read_errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()
    own_run = os.environ.get("GITHUB_RUN_ID", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or not own_run.isascii() or not own_run.isdecimal() or int(own_run) <= 0
            or int(own_run) == RUN
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise OnlineError("Mantenimiento permitido sólo en workflow manual de main del repositorio")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise OnlineError("Falta el token efímero del workflow")
    result = maintain(GitHub(REPO, token), apply=args.aplicar)
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as target:
            target.write("Mantenimiento de corrida conocida: " + json.dumps(result, sort_keys=True) + "\n")
    return 0 if not args.aplicar or result.get("cancelado") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OnlineError as exc:
        print("MANTENIMIENTO_QUEUED: " + str(exc))
        raise SystemExit(1)
