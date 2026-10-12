"""Veto y reemisión de fuentes de imagen por instrucción de Dirección.
Conserva los votos y archivos; sólo cambia la elegibilidad de la fuente activa.
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
FUENTES=set(POLITICA.get("fuentes_retiradas") or [])

def ruta(src):
    return str(src or "").removeprefix("https://yodesarrollomx.github.io/sala-edicion/").split("?")[0].split("#")[0].lstrip("/")

def fuente_retirada(src):
    return ruta(src) in FUENTES

def vetada(c):
    return isinstance(c,dict) and (
        any(str(c.get(k) or "").strip().lower() in VETADOS for k in ("motor","modelo"))
        or fuente_retirada(c.get("src")) or fuente_retirada(c.get("original")))

def requiere_reemplazo(l):
    if not isinstance(l,dict):return False
    if fuente_retirada(l.get("src")):return True
    if l.get("reemplazo_modelo")==POLITICA["revision"] and not l.get("src"):return True
    if l.get("estado")=="aprobada":return False
    return any(fuente_retirada(c.get("src")) or fuente_retirada(c.get("original"))
               for c in l.get("candidatas") or [])

def depurar_tira(t):
    out=copy.deepcopy(t)
    retiradas=set()
    for l in out.get("laminas") or []:
        if requiere_reemplazo(l):
            selected=next((c for c in l.get("candidatas") or []
                           if l.get("src") and l["src"] in (c.get("src"),c.get("original"))),{})
            if not l.get("revision_retirada"):
                l["revision_retirada"]={"politica":POLITICA["revision"],"src":l.get("src"),
                                       "estado":l.get("estado"),"seleccion":copy.deepcopy(l.get("seleccion")),
                                       "candidatas":copy.deepcopy(l.get("candidatas") or [])}
            l["dice"]=str(selected.get("dice") or l.get("dice") or "")
            l.update(candidatas=[],src="",estado="pendiente",reemplazo_modelo=POLITICA["revision"])
            retiradas.add(l["n"])
            continue
        if l.get("estado")=="aprobada":continue
        cs=l.get("candidatas") or []
        allowed=[c for c in cs if not vetada(c)]
        if len(allowed)==len(cs):continue
        retiradas.add(l["n"])
        l["candidatas"]=allowed
        l["src"]=next((c.get("src") or c.get("original") for c in allowed),"")
        if not allowed:l["estado"]="pendiente"
    return out,retiradas

def para_revision(t):
    return not any(vetada(c) for l in t.get("laminas") or []
                   if l.get("n") in (t.get("decidir") or [])
                   for c in l.get("candidatas") or [])
