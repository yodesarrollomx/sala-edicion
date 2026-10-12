#!/usr/bin/env python3
"""Lectura de producción independiente de las tarjetas visibles al editor.

Reutiliza exclusivamente lecturas del GAS existente. No escribe decisiones ni
reconstruye propuestas retiradas desde un archivo local.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import re
import sala_cliente as sala

ROOT = Path(__file__).resolve().parent.parent
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PID = re.compile(r"^[A-Za-z0-9_.-]+$")


def leer_tira(pid):
    if not PID.fullmatch(str(pid or "")):
        raise sala.SalaError("identidad de propuesta inválida")
    try:
        value = json.loads((ROOT / "datos" / "tiras" / (pid + ".json")).read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def validar_dia(value, fecha=None):
    if (not isinstance(value, dict) or value.get("ok") is False or value.get("error")
            or not isinstance(value.get("propuestas"), list)
            or not isinstance(value.get("decisiones"), dict)
            or not isinstance(value["decisiones"].get("propuestas"), dict)
            or not DATE.fullmatch(str(value.get("fecha", "")))
            or (fecha and value["fecha"] != fecha)):
        raise sala.SalaError("lectura del día sin contrato de producción")
    for prop in value["propuestas"]:
        if not isinstance(prop, dict) or not PID.fullmatch(str(prop.get("id", ""))):
            raise sala.SalaError("fuente de propuesta inválida")
    return value


def fechas_fuente(pid, tira, dia):
    candidates = []
    if isinstance(tira, dict):
        candidates.append(str(tira.get("fecha") or ""))
    candidates += re.findall(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", pid)
    # El historial sólo localiza una lectura; nunca acredita vigencia ni marcas.
    try:
        old = json.loads((ROOT / "datos" / "manifiesto.json").read_text())
    except (OSError, ValueError):
        old = {}
    candidates += [f for f, h in (old.get("historial") or {}).items()
                   if any(p.get("id") == pid for p in (h or {}).get("propuestas", []))]
    if not any(DATE.fullmatch(f) for f in candidates):
        candidates += sorted([f for f in dia.get("dias", []) if DATE.fullmatch(str(f))],
                             reverse=True)
    return list(dict.fromkeys(f for f in candidates
                if DATE.fullmatch(f) and f <= dia["fecha"]))[:16]


def cargar(getter=None, tira_reader=None):
    getter = getter or sala.get
    tira_reader = tira_reader or leer_tira
    day = validar_dia(getter("dia", fresco="1"))
    out = copy.deepcopy(day)
    props = {p["id"]: copy.deepcopy(p) for p in day["propuestas"]
             if not str(p.get("origen") or "").lower().startswith("retirada")}
    decisions = day["decisiones"]["propuestas"]
    wanted = [pid for pid, d in decisions.items()
              if isinstance(d, dict) and any(m in ("si", "no") for m in d.get("laminas", []))
              and pid not in props]
    cache = {day["fecha"]: day}
    inactive = 0
    for pid in wanted:
        tira = tira_reader(pid)
        found = None
        for date in fechas_fuente(pid, tira, day):
            if date not in cache:
                cache[date] = validar_dia(getter("dia", f=date, fresco="1"), date)
            same = [p for p in cache[date]["propuestas"] if p["id"] == pid
                    and not str(p.get("origen") or "").lower().startswith("retirada")]
            if len(same) > 1:
                raise sala.SalaError("fuente de propuesta duplicada")
            if same:
                found = copy.deepcopy(same[0])
                break
        if found:
            props[pid] = found
        else:
            # Puede ser una versión retirada. No se inventa su tarjeta desde la tira.
            inactive += 1
    out["propuestas"] = list(props.values())
    out["_produccion"] = {
        "visibles": len(day["propuestas"]), "recuperadas": len(props) - len(day["propuestas"]),
        "fuentes_no_vigentes": inactive,
        "si": sum(m == "si" for d in decisions.values() if isinstance(d, dict)
                  for m in d.get("laminas", [])),
        "no": sum(m == "no" for d in decisions.values() if isinstance(d, dict)
                  for m in d.get("laminas", [])),
    }
    return out


def resolver_tira(tira, decision, prop=None):
    """Aplica sólo lo que la fusión del Sheet acredita, sin modificar el original."""
    from motores._comun import toma_elegida
    result = copy.deepcopy(tira)
    mapa = result.get("mapa") or {
        str(i + 1): n for i, n in enumerate(result.get("decidir") or [])}
    marks = (decision or {}).get("laminas") or []
    notes = (decision or {}).get("notas") or (decision or {}).get("notas_laminas") or []
    firms = (decision or {}).get("firmas") or []
    by_n = {str(l.get("n")): l for l in result.get("laminas") or []}
    for i, mark in enumerate(marks):
        n = str(mapa.get(str(i + 1), i + 1))
        lam = by_n.get(n)
        if lam is None:
            if mark in ("si", "no"):
                raise sala.SalaError("decisión sin lámina en su tira")
            continue
        note = str(notes[i] or "") if i < len(notes) else ""
        note = note or str((decision or {}).get("nota") or "")
        if mark == "no":
            lam.update(estado="rechazada", marca_previa="no", nota_previa=note)
        elif mark == "si":
            candidates = lam.get("candidatas") or []
            selected = toma_elegida(note)
            if candidates:
                if not 0 < selected <= len(candidates):
                    raise sala.SalaError("aprobación sin toma elegida válida")
                chosen = candidates[selected - 1]
                src = str(chosen.get("original") or chosen.get("src") or "")
                if not src:
                    raise sala.SalaError("toma elegida sin imagen")
                lam["src"] = src
                lam["dice"] = str(chosen.get("dice") or lam.get("dice") or "")
                if chosen.get("ve"):
                    lam["ve"] = str(chosen["ve"])
                lam["seleccion"] = {"toma": selected, "src": src,
                                    "huella": str(chosen.get("huella") or "")}
            elif selected:
                raise sala.SalaError("toma elegida ausente de su versión")
            lam.update(estado="aprobada", marca_previa="si")
        elif i < len(firms) and firms[i]:
            # La fusión representa un BORRAR explícito como marca nula firmada.
            lam.update(estado="pendiente", marca_previa="")
    return result


def guion_faltante(tira):
    """Láminas del guion que aún no tienen propuesta visual; nunca aprobaciones."""
    guion = tira.get("guion") or []
    if not isinstance(guion, list):
        raise sala.SalaError("guion sin lista de láminas")
    numbers = [str(l.get("n", "")) for l in guion if isinstance(l, dict)]
    if (len(numbers) != len(guion) or len(set(numbers)) != len(numbers)
            or any(not n.isdigit() or int(n) < 1 for n in numbers)):
        raise sala.SalaError("guion con identidad de láminas inválida")
    present = {str(l.get("n")) for l in tira.get("laminas", [])}
    return [copy.deepcopy(l) for l in guion if str(l["n"]) not in present]


def es_video(tira):
    """Formato explícito; para piezas históricas sin formato conserva el contrato."""
    return str(tira.get("formato") or "").strip().lower() not in {
        "carrusel", "lamina", "lámina", "imagen"}


def peticiones_abiertas(path=None):
    path = path or ROOT / "datos" / "manifiesto.json"
    try:
        m = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        raise sala.SalaError("peticiones sin lectura válida")
    return any(isinstance(p, dict) and p.get("estado") != "cumplida"
               for p in m.get("peticiones", []))
