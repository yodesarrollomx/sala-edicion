"""Supervisa correo por bitácora; no equivale a comprobar recepción."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Hermosillo")
EVENTO = "Correo de las 7:00 enviado"

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
        dates.append(date)
    last=max(dates) if dates else None
    recent=last is not None and clock-last <= timedelta(hours=36)
    return {"estado":"envio_registrado" if recent else "sin_envio_reciente_observado",
            "fuente":"Apps Script","zona_horaria":"America/Hermosillo",
            "ultimo_envio_registrado":last.astimezone(timezone.utc).isoformat() if last else None,
            "leido_en":now,"recepcion_verificada":False,
            "disparadores":"inventario_original_pendiente"}

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
