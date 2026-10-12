"""Veto de modelos de imagen de Dirección, compartido con la revisión.
No modifica votos ni selecciones ya aprobadas.
"""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
POLITICA=json.loads((ROOT/"politica-imagen.json").read_text(encoding="utf-8"))
if POLITICA.get("schema")!=1 or not isinstance(POLITICA.get("retirados"),list):
    raise ValueError("Política de imagen sin contrato")
VETADOS={str(v).strip().lower() for r in POLITICA["retirados"]
         for v in [r.get("motor"),r.get("modelo"),*(r.get("aliases") or [])] if v}

def vetada(c):
    return isinstance(c,dict) and any(str(c.get(k) or "").strip().lower() in VETADOS
                                    for k in ("motor","modelo"))

def depurar_tira(t):
    out=copy.deepcopy(t)
    retiradas=set()
    for l in out.get("laminas") or []:
        if l.get("estado")=="aprobada":
            continue
        cs=l.get("candidatas") or []
        allowed=[c for c in cs if not vetada(c)]
        if len(allowed)==len(cs):
            continue
        retiradas.add(l["n"])
        l["candidatas"]=allowed
        l["src"]=next((c.get("src") or c.get("original") for c in allowed),"")
        if not allowed:
            l["estado"]="pendiente"
    return out,retiradas

def para_revision(t):
    return not any(vetada(c) for l in t.get("laminas") or []
                   if l.get("n") in (t.get("decidir") or [])
                   for c in l.get("candidatas") or [])
