#!/usr/bin/env python3
"""Comprueba acceso de lectura y configuración sin publicar datos ni cambiar negocio."""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_cliente as sala

def main():
    sala.enmascarar_en_actions()
    report = {"solo_lectura": True, "publicador_app": {
        "id_configurado": bool(re.fullmatch(r"[0-9]+", os.environ.get("YOD_APP_ID", ""))),
        "llave_configurada": bool(os.environ.get("YOD_APP_KEY", "").strip()),
    }}
    try:
        data = sala.get("catalogo", fresco="1")
        catalog = data.get("catalogo")
        if not isinstance(catalog, dict):
            raise sala.SalaError("catalogo sin estructura válida")
        revisions = [r for c in catalog.values() for r in c.get("revisiones", [])]
        report["catalogo"] = {
            "seriales": len(catalog), "revisiones": len(revisions),
            "con_huella": sum(bool(r.get("huella")) for r in revisions),
            "campos_revision": sorted({k for r in revisions for k in r}),
        }
        day = sala.get("dia", fresco="1")
        if not isinstance(day.get("decisiones"), dict):
            raise sala.SalaError("dia sin decisiones válidas")
        report["dia"] = {
            "fecha": day.get("fecha"), "propuestas": len(day.get("propuestas") or []),
            "relevo_virtual": bool(day.get("relevo_virtual")),
            "ultima_revision": day.get("ultima_revision"),
        }
    except sala.SalaError:
        report["error"] = "lectura_gas_no_verificada"
        sala.avisar(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2
    sala.avisar(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
