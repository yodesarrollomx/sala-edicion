import copy
from contextlib import redirect_stdout
import io
import json
import tempfile
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

class DiagnosisTests(unittest.TestCase):
    def test_only_allowlisted_codes_and_http_status_are_public(self):
        error=c.drive.DriveError("Drive GET https://www.googleapis.com/drive/v3/files/PRIVATE-ID 403: PRIVATE-BODY TOKEN")
        out=c.error_seguro(error,{"fase":"configuracion_privada","efecto":"no_iniciado"})
        self.assertEqual(out["tipo"],"DriveError")
        self.assertEqual(out["codigo"],"drive_http_403")
        self.assertNotIn("PRIVATE",json.dumps(out))
        self.assertNotIn("TOKEN",json.dumps(out))
        self.assertEqual(c.error_seguro(c.OnlineError("GitHub HTTP 401"),{})["codigo"],"github_http_401")
        self.assertEqual(c.error_seguro(c.OnlineError("GitHub HTTP 401 PRIVATE"),{})["codigo"],"github_sin_confirmar")

    def test_arbitrary_exception_text_type_names_and_context_never_escape(self):
        class PrivateName(RuntimeError):
            def __str__(self):
                raise AssertionError("diagnóstico no debe llamar str")
        result=c.error_seguro(PrivateName("PRIVATE-URL TOKEN"),
            {"fase":"PRIVATE-PHASE","paso":"PRIVATE-STEP","efecto":"PRIVATE-EFFECT"})
        self.assertEqual(result,{"fase":"sin_fase","paso":None,"tipo":"Exception",
                                "codigo":"fallo_no_clasificado","efecto":"no_iniciado"})
        self.assertNotIn("PRIVATE",json.dumps(result))

    def test_authentication_error_is_classified_without_identity(self):
        result=c.error_seguro(c.drive.DriveError(
            "no se pudo obtener el token de la cuenta de servicio (cuenta private@example.invalid): PRIVATE"),{})
        self.assertEqual(result["codigo"],"drive_autenticacion_sin_confirmar")
        self.assertNotIn("private",json.dumps(result))

    def test_main_identifies_private_configuration_failure_without_effect(self):
        out=io.StringIO()
        with patch.object(sys,"argv",["cierre_online.py"]), \
             patch.object(c.sala,"enmascarar_en_actions"), \
             patch.object(c,"private_config",side_effect=c.PlanError("configuracion_privada_no_unica")), \
             patch.object(c,"una_vez") as operation, redirect_stdout(out):
            self.assertEqual(c.main(),2)
        operation.assert_not_called()
        data=json.loads(out.getvalue().split("SALA_CIERRE ",1)[1])
        self.assertFalse(data["ok"])
        self.assertEqual(data["diagnostico"]["fase"],"configuracion_privada")
        self.assertEqual(data["diagnostico"]["codigo"],"configuracion_privada_no_unica")
        self.assertFalse(data["reintento_automatico"])

    def test_network_failure_identifies_each_read_without_effect(self):
        normal=CloseTests().getter
        for resource,phase in (("reglas","leer_reglas"),("cola","leer_cola"),("bitacora","leer_bitacora")):
            diagnostic={"efecto":"no_iniciado"};calls=[]
            def getter(key):
                if key==resource:
                    raise c.sala.SalaError("PRIVATE-URL TOKEN")
                return normal(key)
            with self.subTest(resource=resource),self.assertRaises(c.sala.SalaError) as raised:
                c.ejecutar(getter,lambda x:calls.append(x),lambda _:None,API(),send=True,now=NOW,
                           diagnostico=diagnostic)
            result=c.error_seguro(raised.exception,diagnostic)
            self.assertEqual(result["fase"],phase)
            self.assertEqual(result["codigo"],"sala_sin_lectura_confirmada")
            self.assertNotIn("PRIVATE",json.dumps(result))
            self.assertEqual(calls,[])

    def test_workflow_failure_is_located_before_any_write(self):
        class Broken(API):
            def request(self,path):
                raise c.OnlineError("GitHub HTTP 403")
        diagnostic={"efecto":"no_iniciado"};calls=[]
        with self.assertRaises(c.OnlineError) as raised:
            c.ejecutar(CloseTests().getter,lambda x:calls.append(x),lambda x:calls.append("save"),
                       Broken(),now=NOW,diagnostico=diagnostic)
        result=c.error_seguro(raised.exception,diagnostic)
        self.assertEqual(result["fase"],"leer_workflows")
        self.assertEqual(result["codigo"],"github_http_403")
        self.assertEqual(calls,[])

    def test_preflight_drive_failure_keeps_phase_and_does_not_send(self):
        diagnostic={"efecto":"no_iniciado"};calls=[]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ,{"GITHUB_RUN_ID":"synthetic"}), \
             patch.object(c.drive,"subir",side_effect=c.drive.DriveError(
                "Drive POST https://www.googleapis.com/upload/drive/v3/files 403: PRIVATE")):
            def save(report):
                c.guardar(report,"PRIVATE-PARENT",tmp,diagnostic)
            with self.assertRaises(c.drive.DriveError) as raised:
                c.ejecutar(CloseTests().getter,lambda x:calls.append(x),save,API(),send=True,now=NOW,
                           diagnostico=diagnostic)
        result=c.error_seguro(raised.exception,diagnostic)
        self.assertEqual(result["fase"],"guardar_preflight")
        self.assertEqual(result["paso"],"subir_drive")
        self.assertEqual(result["codigo"],"drive_http_403")
        self.assertEqual(result["efecto"],"no_iniciado")
        self.assertEqual(calls,[])

    def test_byte_verification_failure_has_its_own_step(self):
        diagnostic={"fase":"guardar_preflight","efecto":"no_iniciado"}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ,{"GITHUB_RUN_ID":"synthetic"}), \
             patch.object(c.drive,"subir",return_value="PRIVATE-ID"), \
             patch.object(c.drive,"bajar",return_value=type("Read",(),{"read_bytes":lambda _:b"different"})()):
            with self.assertRaises(c.CierreError) as raised:
                c.guardar({},"PRIVATE-PARENT",tmp,diagnostic)
        result=c.error_seguro(raised.exception,diagnostic)
        self.assertEqual(result["paso"],"verificar_drive")
        self.assertEqual(result["codigo"],"acuse_privado_no_confirmado")

    def test_ambiguous_effect_is_saved_once_without_retry(self):
        diagnostic={"efecto":"no_iniciado"};calls=[];saves=[]
        def operation(name):
            calls.append(name)
            raise TimeoutError("PRIVATE-URL TOKEN")
        with self.assertRaises(c.CierreError) as raised:
            c.ejecutar(CloseTests().getter,operation,lambda x:saves.append(copy.deepcopy(x)),API(),
                       send=True,now=NOW,diagnostico=diagnostic)
        result=c.error_seguro(raised.exception,diagnostic)
        self.assertEqual(calls,["entrada"])
        self.assertEqual(result["fase"],"guardar_resultado_ambiguo")
        self.assertEqual(result["efecto"],"resultado_desconocido_no_reintentar")
        self.assertEqual(result["codigo"],"efecto_sin_confirmar_revisar_acuse")
        self.assertEqual(saves[-1]["operaciones"][-1]["estado"],"resultado_desconocido_no_reintentar")

    def test_drive_failure_after_ambiguous_effect_never_retries_effect(self):
        diagnostic={"efecto":"no_iniciado"};calls=[]
        def operation(name):
            calls.append(name)
            raise TimeoutError()
        def save(report):
            if report["operaciones"] and report["operaciones"][-1]["estado"]=="resultado_desconocido_no_reintentar":
                raise c.drive.DriveError("PRIVATE")
        with self.assertRaises(c.drive.DriveError) as raised:
            c.ejecutar(CloseTests().getter,operation,save,API(),send=True,now=NOW,diagnostico=diagnostic)
        result=c.error_seguro(raised.exception,diagnostic)
        self.assertEqual(result["fase"],"guardar_resultado_ambiguo")
        self.assertEqual(result["efecto"],"resultado_desconocido_no_reintentar")
        self.assertEqual(calls,["entrada"])

if __name__=="__main__":
    unittest.main()
