"""Proyección pública mínima de las tiras vigentes; nunca escribe decisiones."""
import re

def proyectar(piezas, dia, resolver):
    props = {p["id"]: p for p in dia.get("propuestas", [])}
    decisions = (dia.get("decisiones") or {}).get("propuestas") or {}
    result = []
    for _, (pid, tira) in sorted(piezas.items()):
        if pid not in props:
            continue
        if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", pid):
            raise ValueError("Identidad pública inválida")
        resolved = resolver(tira, decisions.get(pid) or {}, props[pid])
        frames = []
        for lam in resolved.get("laminas") or []:
            n = lam.get("n")
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise ValueError("Número de lámina inválido")
            state = lam.get("estado")
            if state not in ("aprobada", "rechazada", "pendiente"):
                state = "pendiente"
            frame = {"n": n, "estado": state}
            take = (lam.get("seleccion") or {}).get("toma")
            if take is not None:
                if not isinstance(take, int) or isinstance(take, bool) or take < 1:
                    raise ValueError("Toma inválida")
                frame["toma"] = take
            frames.append(frame)
        if frames:
            result.append({"id": pid, "laminas": frames})
    return result
