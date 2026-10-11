#!/usr/bin/env python3
"""Cierre técnico autorizado; correo original, una sola llamada con efectos."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import urllib.parse

import sala_cliente as sala
import sala_drive as drive
from plan_agregados import private_config
from snapshots_online import GitHub
from correo_estado import observar, workflows

class CierreError(RuntimeError):
    pass

def exigir(condition, code):
    if not condition:
        raise CierreError(code)

def guardar(report, parent, work):
    name="SALA-CIERRE-"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    raw=(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    path=Path(work)/name
    path.write_bytes(raw)
    fid=drive.subir(path,parent,name)
    exigir(drive.bajar(fid,Path(work)/"leido.json").read_bytes()==raw,"acuse_privado_no_confirmado")
    return fid

def una_vez(operation):
    # No usar get/post generales: reintentan. curl sigue sólo la redirección normal de GAS.
    try:
        if operation == "reprogramar_correo":
            url=sala._exec_url()+"?"+urllib.parse.urlencode({
                "recurso":operation,"clave":sala._clave()})
            body=None
        elif operation == "entrada":
            url=sala._exec_url()
            body=json.dumps({"accion":"entrada","clave":sala._clave()})
        else:
            raise CierreError("operacion_prohibida")
        data=sala._leer_json(sala._curl(url,body,espera=60),"cierre")
    except CierreError:
        raise
    except Exception:
        raise CierreError("operacion_resultado_desconocido_no_reintentar") from None
    exigir(isinstance(data,dict) and data.get("ok") is True,"acuse_no_confirmado")
    if operation=="reprogramar_correo":
        exigir(data.get("zona")=="America/Hermosillo","zona_correo_no_confirmada")
        exigir(isinstance(data.get("borrados"),int) and not isinstance(data["borrados"],bool)
               and data["borrados"]>=0,"disparador_sin_acuse")
        return {"estado":"reprogramado","zona":data["zona"],"anteriores":data["borrados"],
                "inventario_completo_verificado":False}
    if data.get("espera") is True:
        return {"estado":"limitado","tope":data.get("tope") is True,"envio_confirmado":False}
    exigir(isinstance(data.get("correo"),str) and data["correo"].count("@")==1,
           "entrada_sin_destino_confirmado")
    return {"estado":"solicitud_aceptada","destino_preexistente":True,
            "envio_confirmado":False,"recepcion_verificada":False}

def ejecutar(getter, operation, save, api, send=False, reset=False, now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    rules=getter("reglas")
    queue=getter("cola")
    exigir(isinstance(rules,dict) and rules.get("ok") is not False
           and isinstance(rules.get("reglas"),dict),"reglas_sin_contrato")
    exigir(isinstance(queue,dict) and queue.get("ok") is not False
           and isinstance(queue.get("cola"),list),"cola_sin_contrato")
    enabled=sorted(set(str(rules["reglas"].get("nube_ejecuta_etapas","")).split(",")))
    exigir({"voz","escena","corte","prospecto"}.issubset(enabled),"etapas_no_habilitadas")
    report={"schema":1,"at":now,"code_sha":os.environ.get("GITHUB_SHA"),
            "etapas_habilitadas":enabled,"cola":dict(Counter(str(x.get("estado")) for x in queue["cola"])),
            "rutinas":workflows(api),"correo":observar(getter("bitacora"),now),
            "operaciones":[],"reglas_cambiadas":False,"decisiones_cambiadas":False,
            "escrituras_negocio":0,"publicaciones_sociales":0}
    exigir(all(x["activo"] for x in report["rutinas"]),"rutina_no_activa")
    save(report)  # Guardar preflight antes de cualquier efecto; fallo = no llamar.
    for name,requested in (("reprogramar_correo",reset),("entrada",send)):
        if not requested:
            continue
        # Una segunda ejecución del mismo run tampoco debe repetir un efecto ambiguo.
        exigir(os.environ.get("GITHUB_RUN_ATTEMPT","1")=="1","reintento_con_efectos_prohibido")
        item={"operacion":name,"estado":"intentando"}
        report["operaciones"].append(item)
        save(report)
        try:
            result=operation(name)
            item.update(result)
        except Exception:
            item["estado"]="resultado_desconocido_no_reintentar"
            save(report)
            raise CierreError("efecto_sin_confirmar_revisar_acuse") from None
        save(report)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--enviar-entrada",action="store_true")
    parser.add_argument("--reprogramar-correo",action="store_true")
    args=parser.parse_args()
    sala.enmascarar_en_actions()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _,parent=private_config()
            api=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
            receipt=[None]
            def save(report):
                receipt[0]=guardar(report,parent,tmp)
            report=ejecutar(sala.get,una_vez,save,api,args.enviar_entrada,args.reprogramar_correo)
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"],"a") as out:
                    out.write("acuse="+str(receipt[0])+"\n")
            print("SALA_CIERRE "+json.dumps({
                "ok":True,"etapas":report["etapas_habilitadas"],"cola":report["cola"],
                "rutinas_activas":len(report["rutinas"]),"correo":report["correo"],
                "operaciones":report["operaciones"],"acuse_privado":"byte_verificado",
                "escrituras_negocio":0},ensure_ascii=False,sort_keys=True))
        return 0
    except Exception:
        print("SALA_CIERRE "+json.dumps({"ok":False,"error":"cierre_no_confirmado_revisar_acuse",
                                        "reintento_automatico":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
