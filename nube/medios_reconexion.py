#!/usr/bin/env python3
"""Reconecta sólo evidencia de voces originales recuperadas. Nunca decide ni crea trabajos."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import sala_cliente as sala
import sala_drive as drive
from plan_agregados import private_config

MAX_BYTES = 32 * 1024 * 1024
EXPECTED_COUNT = 2
ID = re.compile(r"^[A-Za-z0-9_-]{10,128}$")
JOB = re.compile(r"^[a-z0-9_-]+:voz:[0-9]+:[a-f0-9]{8}$")

class ReconexionError(RuntimeError):
    pass

def require(condition, code):
    if not condition:
        raise ReconexionError(code)

def validate_report(report):
    require(isinstance(report, dict), "informe_invalido")
    require(report.get("queue_writes") == 0 and report.get("decisions_changed") is False
            and report.get("social_publications") == 0, "informe_fuera_de_alcance")
    copies = report.get("copies")
    require(isinstance(copies, list) and len(copies) == EXPECTED_COUNT, "objetivos_ambiguos")
    retained = report.get("retained_revisions")
    require(isinstance(retained, list), "revisiones_sin_prueba")
    jobs, new_ids = set(), set()
    for c in copies:
        require(isinstance(c, dict), "objetivo_invalido")
        require(JOB.fullmatch(str(c.get("job_id", ""))) is not None, "objetivo_no_es_voz")
        for key in ("source_drive_id", "source_revision_id", "new_drive_id"):
            require(ID.fullmatch(str(c.get(key, ""))) is not None, "referencia_invalida")
        require(c["source_drive_id"] != c["new_drive_id"], "copia_no_independiente")
        require(re.fullmatch(r"[a-f0-9]{32}", str(c.get("md5", ""))) is not None
                and re.fullmatch(r"[a-f0-9]{64}", str(c.get("sha256", ""))) is not None,
                "hash_invalido")
        require(type(c.get("bytes")) is int and 44 <= c["bytes"] <= MAX_BYTES, "tamano_invalido")
        require(c.get("storage_verified") is True and c.get("queue_reconnected") is False,
                "informe_no_acredita_copia")
        require(c["job_id"] not in jobs and c["new_drive_id"] not in new_ids, "objetivo_duplicado")
        jobs.add(c["job_id"]); new_ids.add(c["new_drive_id"])
        require(any(isinstance(r, dict) and r.get("file_id") == c["source_drive_id"]
                    and r.get("revision_id") == c["source_revision_id"]
                    and r.get("md5") == c["md5"] and r.get("keep_forever") is True
                    for r in retained), "revision_original_no_acreditada")
    return copies

def evidence(row):
    value = row.get("evidencia")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise ReconexionError("evidencia_invalida") from None
    require(isinstance(value, dict), "evidencia_invalida")
    return copy.deepcopy(value)

def signature(row):
    value = copy.deepcopy(row)
    value["evidencia"] = evidence(row)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

def unique_row(rows, job):
    require(isinstance(rows, list), "cola_invalida")
    found = [r for r in rows if isinstance(r, dict) and r.get("id") == job]
    require(len(found) == 1, "fila_no_unica")
    return copy.deepcopy(found[0])

def verify_audio(c, data):
    require(isinstance(data, bytes) and len(data) == c["bytes"], "archivo_tamano_diferente")
    require(hashlib.md5(data).hexdigest() == c["md5"]
            and hashlib.sha256(data).hexdigest() == c["sha256"], "archivo_hash_diferente")
    require(data[:4] == b"RIFF" and data[8:12] == b"WAVE", "archivo_no_es_wav")

def prepare(row, c, data):
    verify_audio(c, data)
    require(row.get("id") == c["job_id"] and row.get("etapa") == "voz", "fila_no_corresponde")
    require(row.get("estado") == "hecho", "trabajo_no_terminado")
    ev = evidence(row)
    require(ev.get("md5") == c["md5"], "evidencia_original_hash_diferente")
    if ev.get("sha256"):
        require(ev["sha256"] == c["sha256"], "evidencia_original_sha_diferente")
    current = ev.get("drive_id")
    require(current in (c["source_drive_id"], c["new_drive_id"]), "referencia_original_diferente")
    noop = current == c["new_drive_id"]
    if not noop:
        ev["drive_id"] = c["new_drive_id"]
        ev["recuperacion_drive"] = {
            "source_drive_id": c["source_drive_id"],
            "source_revision_id": c["source_revision_id"],
            "md5": c["md5"], "sha256": c["sha256"], "bytes": c["bytes"],
            "original_verificado": True
        }
    return {"id": c["job_id"], "before": copy.deepcopy(row), "evidence": ev, "noop": noop}

def apply(plan, read, write):
    before = plan["before"]
    fresh = read(plan["id"])
    require(signature(fresh) == signature(before), "fila_cambio_antes_de_escribir")
    if plan["noop"]:
        return fresh
    response = write(op="estado", filas=[{"id": plan["id"], "evidencia": plan["evidence"]}])
    require(isinstance(response, dict) and response.get("ok") is True
            and type(response.get("actualizadas")) is int and response["actualizadas"] == 1
            and response.get("creadas") == 0 and response.get("ignoradas") == [],
            "escritura_sin_acuse")
    after = read(plan["id"])
    require(evidence(after) == plan["evidence"], "evidencia_no_confirmada")
    stable = lambda row: {k: v for k, v in row.items() if k not in ("evidencia", "actualizado")}
    require(stable(after) == stable(before), "fila_cambio_despues_de_escribir")
    return after

def queue():
    response = sala.get("cola", etapa="voz")
    require(isinstance(response, dict) and response.get("ok") is True
            and not response.get("error") and isinstance(response.get("cola"), list),
            "cola_sin_lectura")
    return response["cola"]

def private_instructions(work):
    _, parent = private_config()
    query = "'" + parent + "' in parents and trashed = false and mimeType = 'application/json' and name contains 'SALA-ARCHIVOS-RECUPERADOS-'"
    response = drive._peticion("GET", drive.API + "/files",
        params={"q": query, "fields": "files(id,name,size),nextPageToken", "pageSize": 100}).json()
    files = response.get("files")
    require(isinstance(files, list) and len(files) == 1 and not response.get("nextPageToken"),
            "informe_privado_no_unico")
    file = files[0]
    require(re.fullmatch(r"SALA-ARCHIVOS-RECUPERADOS-[0-9]+-[0-9]+\.json",
                        str(file.get("name", ""))) is not None, "informe_privado_nombre_invalido")
    require(0 < int(file.get("size", 0)) <= 65536, "informe_privado_tamano_invalido")
    path = drive.bajar(file["id"], Path(work) / "informe.json")
    require(path.stat().st_size <= 65536, "informe_privado_tamano_invalido")
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ReconexionError("informe_privado_invalido") from None
    return validate_report(report), parent, file["id"]

def recovered_bytes(c, work):
    meta = drive._peticion("GET", drive.API + "/files/" + c["new_drive_id"],
        params={"fields": "id,size,md5Checksum,trashed,mimeType"}).json()
    require(meta.get("id") == c["new_drive_id"] and meta.get("trashed") is False,
            "archivo_privado_no_disponible")
    require(int(meta.get("size", 0)) == c["bytes"] and meta.get("md5Checksum") == c["md5"],
            "archivo_privado_meta_diferente")
    path = drive.bajar(c["new_drive_id"], Path(work) / (str(c["sha256"]) + ".wav"))
    data = path.read_bytes()
    verify_audio(c, data)
    return data

def save_private(receipt, parent, work):
    run = os.environ.get("GITHUB_RUN_ID", "manual")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    require(re.fullmatch(r"[A-Za-z0-9_-]+", run) is not None
            and re.fullmatch(r"[0-9]+", attempt) is not None, "identidad_run_invalida")
    name = "SALA-RECONEXION-MEDIOS-" + run + "-" + attempt + ".json"
    path = Path(work) / name
    raw = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    fid = drive.subir(path, parent, name)
    actual = drive.bajar(fid, Path(work) / "acuse-leido.json").read_bytes()
    require(actual == raw, "acuse_privado_no_confirmado")

def main():
    sala.enmascarar_en_actions()
    receipt = {"schema": 1, "at": datetime.now(timezone.utc).isoformat(),
               "queue_writes_confirmed": 0, "queue_writes_attempted": 0, "decisions_changed": False, "social_publications": 0,
               "targets": [], "code_sha": os.environ.get("GITHUB_SHA")}
    parent = None
    err = None
    with tempfile.TemporaryDirectory(prefix="sala-reconexion-") as work:
        try:
            copies, parent, source = private_instructions(work)
            receipt["source_report_id"] = source
            rows = queue()
            plans = []
            receipt["candidates"] = []
            for c in copies:
                row = unique_row(rows, c["job_id"])
                receipt["candidates"].append({"copy": c, "before": row})
                plans.append(prepare(row, c, recovered_bytes(c, work)))
            receipt["targets"] = [{"plan": p, "readback_verified": False} for p in plans]
            save_private(receipt, parent, work)  # guardar el antes antes de cualquier escritura
            def write_queue(**kw):
                receipt["queue_writes_attempted"] += 1
                return sala.post("cola", **kw)
            for item in receipt["targets"]:
                p = item["plan"]
                # El endpoint heredado no tiene CAS; lectura inmediata y acuse posterior.
                after = apply(p, lambda job: unique_row(queue(), job),
                              write_queue)
                item["after"] = after
                item["readback_verified"] = True
                if not p["noop"]:
                    receipt["queue_writes_confirmed"] += 1
                save_private(receipt, parent, work)
        except ReconexionError as exc:
            err = str(exc)
        except (drive.DriveError, sala.SalaError):
            err = "fuente_privada_inaccesible"
        except Exception:
            err = "reconexion_sin_acuse"
        finally:
            receipt["error"] = err
            if parent is not None:
                try:
                    save_private(receipt, parent, work)
                except Exception:
                    err = err or "acuse_privado_no_confirmado"
    verified = sum(x["readback_verified"] for x in receipt["targets"])
    print(json.dumps({"reconexion": "confirmada" if err is None and verified == EXPECTED_COUNT else "pendiente",
                      "verificados": verified, "actualizados_confirmados": receipt["queue_writes_confirmed"],
                      "intentos_escritura": receipt["queue_writes_attempted"],
                      "sin_cambios": sum(x["readback_verified"] and x["plan"]["noop"]
                                        for x in receipt["targets"]),
                      "error": err}, sort_keys=True))
    return 0 if err is None and verified == EXPECTED_COUNT else 2

if __name__ == "__main__":
    raise SystemExit(main())
