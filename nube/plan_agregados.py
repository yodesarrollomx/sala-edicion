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
READ_TRANSPORT = None
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
        try:
            error = response.json().get("error", {})
            reasons = {item.get("reason") for item in error.get("details", []) if isinstance(item, dict)}
            reasons.update(item.get("reason") for item in error.get("errors", []) if isinstance(item, dict))
        except (ValueError, AttributeError, TypeError):
            reasons = set()
        if reasons & {"SERVICE_DISABLED", "accessNotConfigured"}:
            raise PlanError("sheets_api_no_habilitada")
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


def gviz_get(source, query):
    """Protocolo de consulta Google Charts autenticado; sólo GET y columnas permitidas."""
    url = "https://docs.google.com/spreadsheets/d/" + source["spreadsheet_id"] + "/gviz/tq"
    try:
        response = requests.get(url, params={"gid": source["sheet_id"], "headers": 1,
            "tqx": "out:json", "tq": query},
            headers={"Authorization": "Bearer " + drive._token()}, timeout=30,
            allow_redirects=False)
    except requests.RequestException:
        raise PlanError("gviz_red_sin_lectura") from None
    if response.status_code != 200 or len(response.content) > MAX_BYTES:
        raise PlanError("gviz_sin_respuesta_valida")
    try:
        text = response.content.decode("utf-8-sig")
        match = re.fullmatch(r"\\s*(?:/\\*O_o\\*/\\s*)?google\\.visualization\\.Query\\.setResponse\\((.*)\\);\\s*", text, re.S)
        if not match:
            raise ValueError()
        payload = json.loads(match.group(1))
        if payload.get("status") != "ok" or not isinstance(payload.get("table"), dict):
            raise ValueError()
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise PlanError("gviz_contrato_no_confirmado") from None
    return payload["table"]

def gviz_value(cell, column_type):
    if cell is None:
        return ""
    if not isinstance(cell, dict) or "v" not in cell:
        raise PlanError("gviz_celda_incompleta")
    value = cell["v"]
    if value is None:
        return ""
    if column_type in {"date", "datetime"}:
        match = re.fullmatch(r"Date\\((\\d{4}),(\\d{1,2}),(\\d{1,2})(?:,(\\d{1,2}),(\\d{1,2}),(\\d{1,2}))?\\)", str(value))
        if not match:
            raise PlanError("gviz_fecha_sin_contrato")
        try:
            nums = [int(x) if x is not None else 0 for x in match.groups()]
            nums[1] += 1
            return datetime(*nums).isoformat()
        except ValueError:
            raise PlanError("gviz_fecha_invalida") from None
    if isinstance(value, (str, int, float, bool)):
        return value
    raise PlanError("gviz_valor_no_escalar")

def read_gviz(source):
    global READ_TRANSPORT
    # limit0 devuelve sólo encabezados: no descargar datos de las columnas privadas.
    table = gviz_get(source, "select * limit 0")
    cols = table.get("cols")
    if (not isinstance(cols, list) or not 1 <= len(cols) <= 256
            or not isinstance(table.get("rows"), list) or table["rows"]):
        raise PlanError("gviz_metadatos_no_confirmados")
    headers = [col.get("label", "") if isinstance(col, dict) else "" for col in cols]
    positions = header_positions(headers)
    requested = [(field, cols[index]) for field, indices in positions.items() for index in indices]
    ids = [col.get("id", "") for _, col in requested]
    if (len(ids) != len(set(ids))
            or any(not isinstance(x, str) or not re.fullmatch(r"[A-Z]{1,3}", x) for x in ids)):
        raise PlanError("gviz_columnas_no_confirmadas")
    body = gviz_get(source, "select " + ",".join(ids) + " limit " + str(MAX_ROWS + 1))
    data_cols, rows = body.get("cols"), body.get("rows")
    if (not isinstance(data_cols, list) or [col.get("id") for col in data_cols] != ids
            or [col.get("label") for col in data_cols] != [col.get("label") for _, col in requested]
            or not isinstance(rows, list) or len(rows) > MAX_ROWS):
        raise PlanError("gviz_rangos_o_limites_no_confirmados")
    output = []
    for row in rows:
        cells = row.get("c") if isinstance(row, dict) else None
        if not isinstance(cells, list) or len(cells) != len(requested):
            raise PlanError("gviz_fila_incompleta")
        result = {}
        for (field, col), cell in zip(requested, cells):
            value = gviz_value(cell, col.get("type"))
            if field in result and value not in ("", None):
                if result[field] not in ("", None) and session_key(result[field]) != session_key(value):
                    raise PlanError("columnas_duplicadas_contradictorias")
                result[field] = value
            else:
                result.setdefault(field, value)
        output.append(result)
    READ_TRANSPORT = "gviz_autenticado"
    return output


def read_source(source):
    global READ_TRANSPORT
    sid = source["spreadsheet_id"]
    try:
        metadata = sheet_get(sid, {"fields": "properties(timeZone),sheets(properties)"})
    except PlanError as exc:
        if str(exc) == "sheets_api_no_habilitada":
            return read_gviz(source)
        raise
    READ_TRANSPORT = "sheets_rest"
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
        report.update(estado="confirmado", conteos=output["conteos"], transporte=READ_TRANSPORT)
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
    print(json.dumps({"plan": report["estado"], "transporte": report.get("transporte"), "error": report.get("error"),
                      "conteos": report.get("conteos")}, ensure_ascii=False))
    return 0 if report["estado"] == "confirmado" else 2

if __name__ == "__main__":
    raise SystemExit(main())
