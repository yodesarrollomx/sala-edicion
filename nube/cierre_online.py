#!/usr/bin/env python3
"""Cierre técnico autorizado; correo original, una sola llamada con efectos."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import tempfile
import urllib.parse

import sala_cliente as sala
import sala_drive as drive
from plan_agregados import PlanError, private_config
from snapshots_online import GitHub, OnlineError
from correo_estado import observar, workflows

class CierreError(RuntimeError):
    pass

# Todo valor público del diagnóstico pertenece a estas listas. Ningún mensaje de
# excepción, cuerpo remoto, URL, identificador o credencial se copia a los logs.
FASES = frozenset({"iniciar", "enmascarar", "temporal", "configuracion_privada", "cliente_github",
    "leer_reglas", "leer_cola", "validar_reglas_cola", "verificar_etapas", "leer_workflows",
    "leer_bitacora", "validar_rutinas", "guardar_preflight", "verificar_no_reintento",
    "guardar_intento", "ejecutar_entrada", "ejecutar_reprogramar_correo",
    "guardar_resultado_ambiguo", "guardar_resultado", "exportar_acuse", "resumir"})
PASOS = frozenset({"escribir_local", "subir_drive", "verificar_drive"})
EFECTOS = frozenset({"no_iniciado", "intentando", "resultado_observado",
                     "resultado_desconocido_no_reintentar"})
CODIGOS = frozenset({"acuse_privado_no_confirmado", "operacion_prohibida",
    "operacion_resultado_desconocido_no_reintentar", "acuse_no_confirmado", "zona_correo_no_confirmada",
    "disparador_sin_acuse", "entrada_sin_destino_confirmado", "reglas_sin_contrato", "cola_sin_contrato",
    "etapas_no_habilitadas", "rutina_no_activa", "reintento_con_efectos_prohibido",
    "efecto_sin_confirmar_revisar_acuse", "configuracion_privada_no_unica", "configuracion_demasiado_grande",
    "configuracion_privada_invalida", "fuente_privada_fuera_de_contrato", "bitacora_sin_contrato",
    "reloj_sin_zona", "fecha_correo_invalida", "correo_en_futuro", "contenido_correo_invalido",
    "contenido_correo_sin_contrato", "conteo_correo_invalido", "workflow_sin_estado", "workflow_diferente"})
HTTP_PUBLICOS = frozenset({"400", "401", "403", "404", "409", "429", "500", "502", "503", "504"})


def marcar(diagnostico, fase):
    if diagnostico is not None:
        diagnostico["fase"] = fase
        diagnostico.pop("paso", None)


def error_seguro(error, diagnostico):
    """Clasifica localmente; sólo devuelve etiquetas constantes y códigos permitidos."""
    tipo, codigo = "Exception", "fallo_no_clasificado"
    for cls, label, fallback in ((CierreError, "CierreError", "cierre_sin_confirmar"),
            (PlanError, "PlanError", "configuracion_sin_confirmar"),
            (drive.DriveError, "DriveError", "drive_sin_confirmar"),
            (sala.SalaError, "SalaError", "sala_sin_lectura_confirmada"),
            (OnlineError, "OnlineError", "github_sin_confirmar"),
            (TimeoutError, "TimeoutError", "tiempo_agotado"),
            (KeyError, "KeyError", "entorno_o_contrato_incompleto"),
            (ValueError, "ValueError", "dato_sin_contrato"),
            (OSError, "OSError", "operacion_local_o_red_sin_confirmar")):
        if isinstance(error, cls):
            tipo, codigo = label, fallback
            break
    if drive.requests is not None and isinstance(error, drive.requests.RequestException):
        tipo, codigo = "RequestException", "red_sin_confirmar"
    # Leer args evita llamar __str__ y no imprime su contenido. Sólo el código
    # exacto permitido se hace público; el resto se descarta.
    raw = error.args[0] if error.args else None
    if isinstance(raw, str):
        if raw in CODIGOS:
            codigo = raw
        elif isinstance(error, OnlineError) and raw in {"GitHub HTTP " + x for x in HTTP_PUBLICOS}:
            codigo = "github_http_" + raw.rsplit(" ", 1)[-1]
        elif isinstance(error, drive.DriveError):
            match = re.match(r"^Drive (?:GET|POST|PUT|PATCH|DELETE) https://www\.googleapis\.com/[^\s]+ (\d{3}):", raw)
            if match and match.group(1) in HTTP_PUBLICOS:
                codigo = "drive_http_" + match.group(1)
            elif raw.startswith("no se pudo obtener el token de la cuenta de servicio"):
                codigo = "drive_autenticacion_sin_confirmar"
            elif raw.startswith("falta GDRIVE_SA_JSON"):
                codigo = "drive_credencial_ausente"
    d = diagnostico or {}
    return {"fase": d.get("fase") if d.get("fase") in FASES else "sin_fase",
            "paso": d.get("paso") if d.get("paso") in PASOS else None,
            "tipo": tipo, "codigo": codigo,
            "efecto": d.get("efecto") if d.get("efecto") in EFECTOS else "no_iniciado"}

def exigir(condition, code):
    if not condition:
        raise CierreError(code)

def guardar(report, parent, work, diagnostico=None):
    name="SALA-CIERRE-"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    raw=(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    path=Path(work)/name
    if diagnostico is not None: diagnostico["paso"]="escribir_local"
    path.write_bytes(raw)
    if diagnostico is not None: diagnostico["paso"]="subir_drive"
    fid=drive.subir(path,parent,name)
    if diagnostico is not None: diagnostico["paso"]="verificar_drive"
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

def ejecutar(getter, operation, save, api, send=False, reset=False, now=None, diagnostico=None):
    now=now or datetime.now(timezone.utc).isoformat()
    marcar(diagnostico,"leer_reglas")
    rules=getter("reglas")
    marcar(diagnostico,"leer_cola")
    queue=getter("cola")
    marcar(diagnostico,"validar_reglas_cola")
    exigir(isinstance(rules,dict) and rules.get("ok") is not False
           and isinstance(rules.get("reglas"),dict),"reglas_sin_contrato")
    exigir(isinstance(queue,dict) and queue.get("ok") is not False
           and isinstance(queue.get("cola"),list),"cola_sin_contrato")
    marcar(diagnostico,"verificar_etapas")
    enabled=sorted(set(str(rules["reglas"].get("nube_ejecuta_etapas","")).split(",")))
    exigir({"voz","escena","corte","prospecto"}.issubset(enabled),"etapas_no_habilitadas")
    marcar(diagnostico,"leer_workflows")
    routines=workflows(api)
    marcar(diagnostico,"leer_bitacora")
    correo=observar(getter("bitacora"),now)
    report={"schema":1,"at":now,"code_sha":os.environ.get("GITHUB_SHA"),
            "etapas_habilitadas":enabled,"cola":dict(Counter(str(x.get("estado")) for x in queue["cola"])),
            "rutinas":routines,"correo":correo,
            "operaciones":[],"reglas_cambiadas":False,"decisiones_cambiadas":False,
            "escrituras_negocio":0,"publicaciones_sociales":0}
    marcar(diagnostico,"validar_rutinas")
    exigir(all(x["activo"] for x in report["rutinas"]),"rutina_no_activa")
    marcar(diagnostico,"guardar_preflight")
    save(report)  # Guardar preflight antes de cualquier efecto; fallo = no llamar.
    for name,requested in (("reprogramar_correo",reset),("entrada",send)):
        if not requested:
            continue
        # Una segunda ejecución del mismo run tampoco debe repetir un efecto ambiguo.
        marcar(diagnostico,"verificar_no_reintento")
        exigir(os.environ.get("GITHUB_RUN_ATTEMPT","1")=="1","reintento_con_efectos_prohibido")
        item={"operacion":name,"estado":"intentando"}
        report["operaciones"].append(item)
        marcar(diagnostico,"guardar_intento")
        save(report)
        marcar(diagnostico,"ejecutar_"+name)
        if diagnostico is not None: diagnostico["efecto"]="intentando"
        try:
            result=operation(name)
            item.update(result)
            if diagnostico is not None: diagnostico["efecto"]="resultado_observado"
        except Exception:
            item["estado"]="resultado_desconocido_no_reintentar"
            if diagnostico is not None: diagnostico["efecto"]="resultado_desconocido_no_reintentar"
            marcar(diagnostico,"guardar_resultado_ambiguo")
            save(report)
            raise CierreError("efecto_sin_confirmar_revisar_acuse") from None
        marcar(diagnostico,"guardar_resultado")
        save(report)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--enviar-entrada",action="store_true")
    parser.add_argument("--reprogramar-correo",action="store_true")
    args=parser.parse_args()
    diagnostico={"fase":"iniciar","efecto":"no_iniciado"}
    try:
        marcar(diagnostico,"enmascarar")
        sala.enmascarar_en_actions()
        marcar(diagnostico,"temporal")
        with tempfile.TemporaryDirectory() as tmp:
            marcar(diagnostico,"configuracion_privada")
            _,parent=private_config()
            marcar(diagnostico,"cliente_github")
            api=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
            receipt=[None]
            def save(report):
                receipt[0]=guardar(report,parent,tmp,diagnostico)
            report=ejecutar(sala.get,una_vez,save,api,args.enviar_entrada,args.reprogramar_correo,
                            diagnostico=diagnostico)
            marcar(diagnostico,"exportar_acuse")
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"],"a") as out:
                    out.write("acuse="+str(receipt[0])+"\n")
            marcar(diagnostico,"resumir")
            print("SALA_CIERRE "+json.dumps({
                "ok":True,"etapas":report["etapas_habilitadas"],"cola":report["cola"],
                "rutinas_activas":len(report["rutinas"]),"correo":report["correo"],
                "operaciones":report["operaciones"],"acuse_privado":"byte_verificado",
                "escrituras_negocio":0},ensure_ascii=False,sort_keys=True))
        return 0
    except Exception as error:
        print("SALA_CIERRE "+json.dumps({"ok":False,"error":"cierre_no_confirmado_revisar_acuse",
                                        "diagnostico":error_seguro(error,diagnostico),
                                        "reintento_automatico":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
