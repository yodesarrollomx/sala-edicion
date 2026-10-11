import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"nube"))
import cierre_online as c
import correo_estado as mail

NOW="2026-10-11T18:00:00+00:00"
LOG={"ok":True,"bitacora":[{"cuando":"2026-10-11 07:13","evento":mail.EVENTO,"detalle":"privado"}]}

class API:
    def request(self,path):
        return {"path":".github/workflows/"+path.split("/")[-1],"state":"active"}

class MailTests(unittest.TestCase):
    def test_record_is_not_receipt(self):
        data=mail.observar(LOG,NOW)
        self.assertEqual(data["estado"],"envio_registrado")
        self.assertFalse(data["recepcion_verificada"])
        self.assertEqual(data["ultimo_envio_registrado"],"2026-10-11T14:13:00+00:00")
        self.assertNotIn("privado",str(data))

    def test_old_or_missing_is_unknown(self):
        for log in ({"bitacora":[]},{"bitacora":[{"cuando":"2026-10-08 07:13","evento":mail.EVENTO}]}):
            self.assertEqual(mail.observar(log,NOW)["estado"],"sin_envio_reciente_observado")

    def test_rejected_malformed_and_future(self):
        for log in ({"ok":False,"bitacora":[]},{}, {"bitacora":[{"evento":mail.EVENTO,"cuando":"fecha"}]},
                    {"bitacora":[{"evento":mail.EVENTO,"cuando":"2026-10-12 07:13"}]}):
            with self.assertRaises(ValueError):
                mail.observar(log,NOW)

    def test_only_daily_event_counts(self):
        self.assertEqual(mail.observar({"bitacora":[{"evento":"Entrada enviada por correo",
                                                   "cuando":"2026-10-11 07:13"}]},NOW)["estado"],
                         "sin_envio_reciente_observado")

class CloseTests(unittest.TestCase):
    def getter(self,key):
        return {"reglas":{"reglas":{"nube_ejecuta_etapas":"voz,escena,corte,prospecto"}},
                "cola":{"cola":[{"estado":"hecho","nombre":"no publicar"}]},
                "bitacora":LOG}[key]

    def test_read_only_preserves_operations(self):
        calls=[]
        report=c.ejecutar(self.getter,lambda x:calls.append(x),lambda _:None,API(),now=NOW)
        self.assertEqual(calls,[])
        self.assertEqual(report["cola"],{"hecho":1})
        self.assertFalse(report["decisiones_cambiadas"])

    def test_backup_failure_prevents_mail(self):
        calls=[]
        def save(_):raise RuntimeError("Drive no confirmó")
        with self.assertRaises(RuntimeError):
            c.ejecutar(self.getter,lambda x:calls.append(x),save,API(),send=True,now=NOW)
        self.assertEqual(calls,[])

    def test_unknown_mail_attempt_is_saved_and_never_retried(self):
        saves=[];calls=[]
        def operation(name):
            calls.append(name)
            raise TimeoutError()
        with self.assertRaises(c.CierreError):
            c.ejecutar(self.getter,operation,lambda x:saves.append(copy.deepcopy(x)),API(),send=True,now=NOW)
        self.assertEqual(calls,["entrada"])
        self.assertEqual(saves[-1]["operaciones"][-1]["estado"],"resultado_desconocido_no_reintentar")

    def test_second_run_attempt_never_sends(self):
        with patch.dict(os.environ,{"GITHUB_RUN_ATTEMPT":"2"}):
            with patch.object(c,"una_vez") as operation:
                with self.assertRaises(c.CierreError):
                    c.ejecutar(self.getter,operation,lambda _:None,API(),send=True,now=NOW)
                operation.assert_not_called()

    def test_disabled_workflow_prevents_effect(self):
        class Disabled(API):
            def request(self,path):
                return {**super().request(path),"state":"disabled_manually"}
        calls=[]
        with self.assertRaises(c.CierreError):
            c.ejecutar(self.getter,lambda x:calls.append(x),lambda _:None,Disabled(),send=True,now=NOW)
        self.assertEqual(calls,[])

    def test_missing_stage_prevents_effect(self):
        def getter(key):
            return {"reglas":{"nube_ejecuta_etapas":"voz"}} if key=="reglas" else self.getter(key)
        with self.assertRaises(c.CierreError):
            c.ejecutar(getter,lambda _:None,lambda _:None,API(),send=True,now=NOW)

    def test_single_transport_no_fallback_for_ambiguous_mail(self):
        with patch.object(c.sala,"_clave",return_value="secret-sintetico"),\
             patch.object(c.sala,"_exec_url",return_value="https://example.invalid/exec"),\
             patch.object(c.sala,"_curl",side_effect=TimeoutError()) as transport:
            with self.assertRaises(c.CierreError):
                c.una_vez("entrada")
            self.assertEqual(transport.call_count,1)

    def test_rate_limit_is_not_sent(self):
        with patch.object(c.sala,"_clave",return_value="secret-sintetico"),\
             patch.object(c.sala,"_exec_url",return_value="https://example.invalid/exec"),\
             patch.object(c.sala,"_curl",return_value='{"ok":true,"espera":true}'):
            result=c.una_vez("entrada")
            self.assertEqual(result["estado"],"limitado")
            self.assertFalse(result["envio_confirmado"])

    def test_mail_ack_without_destination_rejected(self):
        with patch.object(c.sala,"_clave",return_value="secret-sintetico"),\
             patch.object(c.sala,"_exec_url",return_value="https://example.invalid/exec"),\
             patch.object(c.sala,"_curl",return_value='{"ok":true}'):
            with self.assertRaises(c.CierreError):
                c.una_vez("entrada")

    def test_unexpected_zone_rejected(self):
        with patch.object(c.sala,"_clave",return_value="secret-sintetico"),\
             patch.object(c.sala,"_exec_url",return_value="https://example.invalid/exec"),\
             patch.object(c.sala,"_curl",return_value='{"ok":true,"zona":"UTC","borrados":1}'):
            with self.assertRaises(c.CierreError):
                c.una_vez("reprogramar_correo")

if __name__=="__main__":
    unittest.main()
