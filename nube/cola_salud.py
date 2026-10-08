#!/usr/bin/env python3
"""Conciliación segura de trabajos abandonados en la COLA de Sala.

Conserva evidencia e identificadores. Nunca vuelve a producir automáticamente un
trabajo cuyo proceso ya murió: antes debe acreditarse la versión y autorización
editorial. El productor podrá seguir creando trabajos NUEVOS normalmente.
"""
import datetime as dt
import json
import re
import calendar

HMO = dt.timezone(dt.timedelta(hours=-7))
ABANDONO_MIN = 180

def fecha_utc(valor):
    """Acepta las tres formas que devuelve Sheets: ISO, fecha/hora local y JS Date."""
    s = str(valor or "").strip()
    if not s:
        return None
    try:
        m = re.match(
            r"^[A-Za-z]{3} ([A-Za-z]{3}) (\d{1,2}) (\d{4}) "
            r"(\d{1,2}):(\d{2}):(\d{2}) GMT([+-])(\d{2})(\d{2})", s
        )
        if m:
            mes, dia, ano, hh, mm, ss, signo, zh, zm = m.groups()
            tz = dt.timezone((1 if signo == "+" else -1)
                             * dt.timedelta(hours=int(zh), minutes=int(zm)))
            f = dt.datetime(int(ano), list(calendar.month_abbr).index(mes.title()),
                            int(dia), int(hh), int(mm), int(ss), tzinfo=tz)
        else:
            iso = s.replace("Z", "+00:00")
            try:
                f = dt.datetime.fromisoformat(iso)
            except ValueError:
                m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})[ T]"
                             r"(\d{1,2}):(\d{1,2}):(\d{1,2})$", s)
                if not m:
                    return None
                f = dt.datetime(*map(int, m.groups()))
            if f.tzinfo is None:
                f = f.replace(tzinfo=HMO)
        return f.astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        return None

def propuestas_rescate(cola, habilitadas, ahora_utc=None, minutos=ABANDONO_MIN):
    """Devuelve (cambios, ilegibles); no toca red ni hojas.

    Incluso si una etapa está habilitada, NO reencola un trabajo viejo sin
    comprobar su versión. Cambiar corriendo -> fallo no borra datos ni decisiones.
    """
    ahora = ahora_utc or dt.datetime.now(dt.timezone.utc)
    if ahora.tzinfo is None:
        raise ValueError("ahora_utc debe incluir zona horaria")
    cambios, ilegibles = [], []
    for t in cola:
        if str(t.get("estado") or "").strip() != "corriendo":
            continue
        identificador = str(t.get("id") or "").strip()
        fecha = fecha_utc(t.get("actualizado"))
        if not identificador or fecha is None:
            ilegibles.append(identificador or "(sin id)")
            continue
        edad = (ahora - fecha).total_seconds() / 60
        if edad <= minutos:
            continue
        ev = t.get("evidencia") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except (ValueError, TypeError):
                ev = {"evidencia_original": ev[:500]}
        if not isinstance(ev, dict):
            ev = {"evidencia_original": str(ev)[:500]}
        motivo = ("Trabajo interrumpido; se requiere validar que la versión actual "
                  "y las decisiones permiten repetirlo. No se reejecutó.")
        evidencia = dict(ev, estado_anterior="corriendo",
                         actualizado_anterior=str(t.get("actualizado") or ""),
                         recuperacion=motivo, requiere_revision=True)
        cambios.append({"id": identificador, "estado": "fallo", "evidencia": evidencia,
                        "bloqueado_por": motivo, "minutos_abandonado": round(edad)})
    return cambios, ilegibles
