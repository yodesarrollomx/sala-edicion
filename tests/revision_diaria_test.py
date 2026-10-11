import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nube"))
import revision_diaria as r
from snapshots_online import OnlineError


class ReviewTests(unittest.TestCase):
    def test_empty_real_is_zero(self):
        self.assertEqual(r.aggregate_queue({"ok": True, "cola": []})["total"], 0)

    def test_rejected_missing_and_invalid_are_errors(self):
        for payload in ({"ok": False, "cola": []}, {"error": "liga"}, {},
                        {"cola": [{"pieza": "privada"}]}):
            with self.assertRaises(ValueError):
                r.aggregate_queue(payload)

    def test_counts_exclude_private_rows(self):
        result = r.aggregate_queue({"cola": [
            {"estado": "hecho", "nombre": "Privado", "correo": "privado@example.invalid"},
            {"estado": "fallo", "evidencia": "no debe copiarse"}]})
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["hecho"], 1)
        self.assertNotIn("Privado", str(result))
        self.assertNotIn("example", str(result))

    def test_failure_keeps_last_confirmed_counts_and_timestamp(self):
        previous = {"cola": {"total": 31}, "cola_leida_en": "antes"}
        def getter(resource):
            return {"ok": False}
        with patch.object(r, "observe_runs", side_effect=OnlineError("sin lectura")):
            out = r.collect(previous, getter, None, "ahora")
        self.assertEqual(out["cola"], {"total": 31})
        self.assertEqual(out["cola_leida_en"], "antes")
        self.assertEqual(out["cola_estado"], "sin_confirmar")
        self.assertNotEqual(out["errores"], [])

    def test_no_previous_failure_is_unknown(self):
        with patch.object(r, "observe_runs", return_value={}):
            out = r.collect({}, lambda _: {}, None, "ahora")
        self.assertIsNone(out["cola"])
        self.assertIsNone(out["cola_leida_en"])

    def test_confirmed_rules_whitelist_stages_only(self):
        def getter(resource):
            return ({"cola": []} if resource == "cola" else
                    {"reglas": {"nube_ejecuta_etapas": "voz,corte,privado",
                                "drive_raiz": "privado", "clave": "no se copia"}})
        with patch.object(r, "observe_runs", return_value={}):
            out = r.collect({}, getter, None, "ahora")
        self.assertEqual(out["etapas"], ["corte", "voz"])
        self.assertNotIn("no se copia", str(out))
        self.assertEqual(out["cola_estado"], "confirmada")

    def test_real_nested_production_is_observed_on_main_push(self):
        class API:
            def request(self,path):
                if path.startswith("actions/runs?"):
                    return {"workflow_runs":[{"id":12,"head_branch":"main","event":"push",
                                              "path":".github/workflows/sala-cierre-online.yml"}]}
                return {"jobs":[
                    {"name":"ciclo / productor","status":"completed","conclusion":"success",
                     "started_at":"inicio","completed_at":"fin"},
                    {"name":"ejecutar / ejecutor","status":"in_progress","conclusion":None},
                    {"name":"comparar","status":"completed","conclusion":"success"}]}
        result=r.observe_runs(API())
        self.assertEqual(set(result),{"productor","ejecutor"})
        self.assertEqual(result["productor"]["run_id"],"12")
        self.assertEqual(result["productor"]["termino"],"fin")

    def test_guardian_dispatch_nested_jobs_are_observed(self):
        class API:
            def request(self, path):
                if path.startswith("actions/runs?"):
                    return {"workflow_runs": [{"id": 23, "head_branch": "main",
                            "event": "workflow_dispatch", "path": ".github/workflows/sala-vigilante.yml"}]}
                return {"jobs": [{"name": "chinches / puente", "status": "completed",
                        "conclusion": "success", "started_at": "inicio", "completed_at": "fin"},
                        {"name": "mesa / mesa", "status": "completed", "conclusion": "skipped"}]}
        result = r.observe_runs(API())
        self.assertEqual(set(result), {"chinches"})
        self.assertEqual(result["chinches"]["run_id"], "23")

    def test_other_branch_and_skipped_job_do_not_accredit_execution(self):
        class API:
            def request(self,path):
                if path.startswith("actions/runs?"):
                    return {"workflow_runs":[
                        {"id":1,"head_branch":"prueba","event":"push","path":".github/workflows/sala-plan.yml"},
                        {"id":2,"head_branch":"main","event":"push","path":".github/workflows/sala-plan.yml"}]}
                if path.startswith("actions/runs/1/"):
                    raise AssertionError("rama de prueba no debe leerse como operación")
                return {"jobs":[{"name":"plan","status":"completed","conclusion":"skipped"}]}
        self.assertEqual(r.observe_runs(API()),{})


if __name__ == "__main__":
    unittest.main()
