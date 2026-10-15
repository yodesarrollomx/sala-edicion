"""Supervisa correo por bitácora; no equivale a comprobar recepción."""
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Hermosillo")
EVENTO = "Correo de las 7:00 enviado"
CAMPOS = ("revision", "aprobadas", "cambios", "producidas", "publicadas", "sin_acuse",
          "en_cola", "corriendo", "fallos")

def contenido(detalle):
    """Sólo publica metadatos agregados del contrato nuevo, nunca el asunto o notas."""
    result = {"contenido_estado": "sin_telemetria", "resumen_ultimo_envio": None}
    if not isinstance(detalle, str) or not detalle.lstrip().startswith("{"):
        return result  # Bitácoras históricas traen únicamente el asunto.
    try:
        data = json.loads(detalle)
    except (ValueError, TypeError):
        raise ValueError("contenido_correo_invalido") from None
    if not isinstance(data, dict) or data.get("correo") != 2:
        return result
    if data.get("lectura") == "sin_confirmar":
        return {"contenido_estado": "lectura_sin_confirmar", "resumen_ultimo_envio": None}
    if data.get("lectura") != "confirmada":
        raise ValueError("contenido_correo_sin_contrato")
    if any(not isinstance(data.get(k), int) or isinstance(data[k], bool) or data[k] < 0 for k in CAMPOS):
        raise ValueError("conteo_correo_invalido")
    return {"contenido_estado": "confirmado", "resumen_ultimo_envio": {k: data[k] for k in CAMPOS}}

def observar(response, now):
    if (not isinstance(response,dict) or response.get("ok") is False
            or response.get("error") or not isinstance(response.get("bitacora"),list)):
        raise ValueError("bitacora_sin_contrato")
    clock=datetime.fromisoformat(now.replace("Z","+00:00"))
    if clock.tzinfo is None:
        raise ValueError("reloj_sin_zona")
    dates=[]
    for row in response["bitacora"]:
        if not isinstance(row,dict) or row.get("evento") != EVENTO:
            continue
        try:
            date=datetime.strptime(row["cuando"],"%Y-%m-%d %H:%M").replace(tzinfo=ZONA)
        except (ValueError,TypeError,KeyError):
            raise ValueError("fecha_correo_invalida") from None
        if date > clock + timedelta(minutes=5):
            raise ValueError("correo_en_futuro")
        dates.append((date, row))
    last_row=max(enumerate(dates), key=lambda item: (item[1][0], item[0]))[1] if dates else None
    last=last_row[0] if last_row else None
    recent=last is not None and clock-last <= timedelta(hours=36)
    return {"estado":"envio_registrado" if recent else "sin_envio_reciente_observado",
            "fuente":"Apps Script","zona_horaria":"America/Hermosillo",
            "ultimo_envio_registrado":last.astimezone(timezone.utc).isoformat() if last else None,
            "leido_en":now,"recepcion_verificada":False,
            "disparadores":"inventario_original_pendiente",
            **(contenido(last_row[1].get("detalle")) if last_row else
               {"contenido_estado":"sin_telemetria", "resumen_ultimo_envio":None})}

def workflows(api):
    allowed=("sala-cada-hora.yml","sala-diario.yml","sala-plan.yml","sala-revision.yml")
    result=[]
    for name in allowed:
        item=api.request("actions/workflows/"+name)
        if not isinstance(item,dict) or item.get("state") not in {
                "active","disabled_manually","disabled_inactivity","disabled_fork"}:
            raise ValueError("workflow_sin_estado")
        if str(item.get("path","")).split("/")[-1] != name:
            raise ValueError("workflow_diferente")
        result.append({"archivo":name,"estado":item["state"],"activo":item["state"]=="active"})
    return result
