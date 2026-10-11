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


if __name__ == "__main__":
    unittest.main()
