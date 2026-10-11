#!/usr/bin/env python3
"""Lectura acotada de Plan: publica agregados, nunca filas ni identificadores privados."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import quote

import requests
import sala_cliente as sala
import sala_drive as drive

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "datos" / "plan-agregados.json"
CONFIG_NAME = "SALA · conexiones-online-v1"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets/"
MAX_ROWS = 50000
MAX_BYTES = 8 * 1024 * 1024
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
FIELDS = ("Primer contacto", "Folio", "Tipo", "Estado", "Sesión agendada",
          "UTM campaign", "UTM content")

class PlanError(RuntimeError):
    pass

def normalized(value):
    text = str(value or "").strip()
    if "√" in text:
        try:
            text = text.encode("mac_roman").decode("utf-8")
        except (UnicodeError, LookupError):
            pass
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(c))

def column_name(index):
    out = ""
    number = index + 1
    while number:
        number, rem = divmod(number - 1, 26)
        out = chr(65 + rem) + out
    return out

def header_positions(headers):
    positions = {}
    for field in FIELDS:
        matches = [i for i, value in enumerate(headers)
                   if normalized(value) == normalized(field)]
        if not matches:
            raise PlanError("encabezado_incompleto")
        if len(matches) > 1 and field != "Sesión agendada":
            raise PlanError("encabezado_ambiguo")
        positions[field] = matches
    return positions

def valid_session(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value) and 30000 <= value < 100000
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
                "%d/%m/%Y %H:%M:%S"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            pass
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def session_key(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (datetime(1899, 12, 30) + timedelta(days=value)).isoformat(timespec="seconds")
    return str(value or "").strip()

def aggregate(rows, read_at):
    seen, groups = {}, {}
    counts = Counter()
    for row in rows:
        folio = str(row.get("Folio") or "").strip()
        if not folio and not any(value not in ("", None) for value in row.values()):
            continue
        if not re.fullmatch(r"POT-[A-Za-z0-9_-]{1,96}", folio):
            raise PlanError("folio_invalido")
        record = tuple((key, str(row.get(key) or "").strip()) for key in FIELDS)
        if folio in seen:
            if seen[folio] != record:
                raise PlanError("folio_duplicado_contradictorio")
            counts["duplicados_identicos"] += 1
            continue
        seen[folio] = record
        if normalized(row.get("Estado")) == "prueba" or normalized(row.get("Tipo")) == "prueba":
            counts["pruebas_excluidas"] += 1
            continue
        if row.get("Tipo") not in {"lead_potencial", "lead_interes"}:
            raise PlanError("tipo_de_lead_no_acreditado")
        counts["leads_historicos"] += 1
        state = normalized(row.get("Estado"))
        session = row.get("Sesión agendada")
        if session not in ("", None) and not valid_session(session):
            raise PlanError("sesion_sin_fecha_confirmada")
        confirmed = state == "sesion agendada" and valid_session(session)
        if state == "sesion agendada" and not confirmed:
            raise PlanError("estado_sin_confirmacion_de_sesion")
        if confirmed:
            counts["citas_historicas_confirmadas"] += 1
        campaign = str(row.get("UTM campaign") or "").strip()
        content = str(row.get("UTM content") or "").strip()
        if not campaign:
            counts["sin_campana"] += 1
            continue
        if not TAG.fullmatch(campaign) or (content and not TAG.fullmatch(content)):
            raise PlanError("utm_fuera_del_contrato_sin_pii")
        key = (campaign, content)
        group = groups.setdefault(key, {"utm_campaign": campaign, "utm_content": content,
                                       "leads": 0, "citas": 0})
        group["leads"] += 1
        group["citas"] += int(confirmed)
        counts["leads_con_campana"] += 1
    return {"schema": 1, "fuente": "plan_potencial_sheet", "ok": True,
            "leido_en": read_at, "zona_horaria": "America/Hermosillo",
            "periodo": "historico", "completo": True,
            "conteos": {key: counts[key] for key in ("leads_historicos",
                "citas_historicas_confirmadas", "leads_con_campana", "sin_campana",
                "pruebas_excluidas", "duplicados_identicos")},
            "campanas": [groups[key] for key in sorted(groups)]}

def sheet_get(suffix, params=None):
    try:
        response = requests.get(SHEETS + suffix, params=params,
            headers={"Authorization": "Bearer " + drive._token()}, timeout=30,
            allow_redirects=False)
    except requests.RequestException:
        raise PlanError("sheets_red_sin_lectura") from None
    if response.status_code != 200:
        raise PlanError("sheets_http_" + str(response.status_code))
    if len(response.content) > MAX_BYTES:
        raise PlanError("sheets_respuesta_demasiado_grande")
    try:
        payload = response.json()
    except ValueError:
        raise PlanError("sheets_json_invalido") from None
    if not isinstance(payload, dict) or payload.get("error"):
        raise PlanError("sheets_contrato_invalido")
    return payload

def private_config():
    q = "name = '" + CONFIG_NAME.replace("'", "\\'") + "' and trashed = false and mimeType = 'application/vnd.google-apps.document'"
    result = drive._peticion("GET", drive.API + "/files",
        params={"q": q, "fields": "files(id,parents)", "pageSize": 100}).json()
    files = result.get("files", [])
    if len(files) != 1 or len(files[0].get("parents", [])) != 1 or result.get("nextPageToken"):
        raise PlanError("configuracion_privada_no_unica")
    file = files[0]
    response = drive._peticion("GET", drive.API + "/files/" + file["id"] + "/export",
                               params={"mimeType": "text/plain"})
    if len(response.content) > 65536:
        raise PlanError("configuracion_demasiado_grande")
    try:
        config = json.loads(response.content.decode("utf-8-sig"))
        source = config["sources"]["plan_utm"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise PlanError("configuracion_privada_invalida") from None
    if (config.get("schema") != 1 or not isinstance(source, dict)
            or not re.fullmatch(r"[A-Za-z0-9_-]{10,128}", str(source.get("spreadsheet_id", "")))
            or source.get("sheet_title") != "LEADS - POTENCIAL"
            or not isinstance(source.get("sheet_id"), int) or isinstance(source["sheet_id"], bool)):
        raise PlanError("fuente_privada_fuera_de_contrato")
    return source, file["parents"][0]

def read_source(source):
    sid = source["spreadsheet_id"]
    metadata = sheet_get(sid, {"fields": "properties(timeZone),sheets(properties)"})
    matching = [item["properties"] for item in metadata.get("sheets", [])
                if isinstance(item, dict) and isinstance(item.get("properties"), dict)
                and item["properties"].get("sheetId") == source["sheet_id"]
                and item["properties"].get("title") == source["sheet_title"]]
    if len(matching) != 1:
        raise PlanError("hoja_canonica_no_confirmada")
    props = matching[0].get("gridProperties", {})
    rows, columns = props.get("rowCount"), props.get("columnCount")
    if (not isinstance(rows, int) or not 1 <= rows <= MAX_ROWS
            or not isinstance(columns, int) or not 1 <= columns <= 256):
        raise PlanError("limites_de_hoja_sin_confirmar")
    if metadata.get("properties", {}).get("timeZone") not in {"America/Phoenix", "America/Hermosillo"}:
        raise PlanError("zona_horaria_de_fuente_no_acreditada")
    tab = "'" + source["sheet_title"].replace("'", "''") + "'"
    header = sheet_get(sid + "/values/" + quote(tab + "!A1:" + column_name(columns - 1) + "1", safe=""),
                       {"valueRenderOption": "UNFORMATTED_VALUE"})
    headers = header.get("values")
    if not isinstance(headers, list) or len(headers) != 1 or not isinstance(headers[0], list):
        raise PlanError("encabezados_no_confirmados")
    positions = header_positions(headers[0])
    if rows == 1:
        return []
    columns_to_read = [(field, index) for field, indices in positions.items() for index in indices]
    ranges = [tab + "!" + column_name(index) + "2:" + column_name(index) + str(rows)
              for _, index in columns_to_read]
    response = sheet_get(sid + "/values:batchGet", {"ranges": ranges,
        "valueRenderOption": "UNFORMATTED_VALUE", "majorDimension": "COLUMNS"})
    value_ranges = response.get("valueRanges")
    if not isinstance(value_ranges, list) or len(value_ranges) != len(ranges):
        raise PlanError("columnas_incompletas")
    results = {}
    for (field, _), expected, value_range in zip(columns_to_read, ranges, value_ranges):
        if not isinstance(value_range, dict) or value_range.get("majorDimension") != "COLUMNS":
            raise PlanError("columna_sin_contrato")
        if value_range.get("range") != expected:
            raise PlanError("rango_no_coincide")
        values = value_range.get("values", [])
        if not isinstance(values, list) or len(values) > 1 or (values and not isinstance(values[0], list)):
            raise PlanError("columna_invalida")
        data = values[0] if values else []
        if len(data) > rows - 1:
            raise PlanError("fila_fuera_de_limite")
        results.setdefault(field, []).append(data)
    result, height = [], max((len(column) for cols in results.values() for column in cols), default=0)
    for i in range(height):
        row = {}
        for field, cols in results.items():
            supplied = [col[i] for col in cols if i < len(col) and col[i] not in ("", None)]
            if len(supplied) > 1 and len({session_key(value) for value in supplied}) != 1:
                raise PlanError("columnas_duplicadas_contradictorias")
            row[field] = supplied[0] if supplied else ""
        result.append(row)
    return result

def main():
    sala.enmascarar_en_actions()
    now = datetime.now(timezone.utc).isoformat()
    folder, report = None, {"schema": 1, "leido_en": now,
                            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                            "estado": "sin_lectura_confirmada"}
    try:
        source, folder = private_config()
        report["service_account_email"] = drive._credenciales().service_account_email
        output = aggregate(read_source(source), now)
        DEST.parent.mkdir(parents=True, exist_ok=True)
        temp = DEST.with_suffix(".tmp")
        temp.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")
        temp.replace(DEST)
        report.update(estado="confirmado", conteos=output["conteos"])
    except (PlanError, drive.DriveError):
        report["error"] = "lectura_plan_no_acreditada"
        if folder:
            # Sólo código estable, nunca mensajes remotos, URLs o filas.
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, PlanError):
                report["error"] = str(exc)
    try:
        if folder:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "plan-online-diagnostico.json"
                path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
                file_id = drive.subir(path, folder)
                recovered = Path(td) / "recuperado.json"
                drive.bajar(file_id, recovered)
                if recovered.read_bytes() != path.read_bytes():
                    raise drive.DriveError("diagnostico_no_confirmado")
    except drive.DriveError:
        report["estado"] = "diagnostico_privado_no_confirmado"
    print(json.dumps({"plan": report["estado"], "error": report.get("error"),
                      "conteos": report.get("conteos")}, ensure_ascii=False))
    return 0 if report["estado"] == "confirmado" else 2

if __name__ == "__main__":
    raise SystemExit(main())
