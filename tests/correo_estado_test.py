"""Contrato de correo con datos sintéticos; ninguna conexión ni envío real."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nube"))
import correo_estado as mail

NOW = "2026-10-14T18:00:00Z"


def log(detail):
    return {"ok": True, "bitacora": [{"cuando": "2026-10-14 07:13", "evento": mail.EVENTO, "detalle": detail}]}


class CorreoEstadoTests(unittest.TestCase):
    def telemetry(self):
        return {"correo": 2, "fecha": "2026-10-14", "lectura": "confirmada",
                **{key: i for i, key in enumerate(mail.CAMPOS)},
                "privado": "no debe viajar al reporte"}

    def test_new_telemetry_preserves_counts_without_copying_private_fields(self):
        result = mail.observar(log(json.dumps(self.telemetry())), NOW)
        self.assertEqual(result["estado"], "envio_registrado")
        self.assertEqual(result["contenido_estado"], "confirmado")
        self.assertEqual(result["resumen_ultimo_envio"], {key: i for i, key in enumerate(mail.CAMPOS)})
        self.assertNotIn("privado", str(result))
        self.assertFalse(result["recepcion_verificada"])

    def test_diagnostic_message_does_not_fabricate_zero_counts(self):
        result = mail.observar(log('{"correo":2,"lectura":"sin_confirmar"}'), NOW)
        self.assertEqual(result["contenido_estado"], "lectura_sin_confirmar")
        self.assertIsNone(result["resumen_ultimo_envio"])
        self.assertEqual(result["estado"], "envio_registrado")

    def test_legacy_subject_is_not_evidence_of_counts(self):
        result = mail.observar(log("Sala de Edición · hoy no hay pendientes"), NOW)
        self.assertEqual(result["contenido_estado"], "sin_telemetria")
        self.assertIsNone(result["resumen_ultimo_envio"])

    def test_unknown_json_is_not_a_new_contract(self):
        self.assertEqual(mail.contenido('{"otro":3}')["contenido_estado"], "sin_telemetria")

    def test_malformed_negative_boolean_or_missing_counts_are_rejected(self):
        cases = ["{", json.dumps({"correo": 2, "lectura": "confirmada"})]
        for value in (-1, True, "1", None):
            cases.append(json.dumps({**self.telemetry(), "revision": value}))
        for detail in cases:
            with self.subTest(detail=detail), self.assertRaises(ValueError):
                mail.observar(log(detail), NOW)

    def test_latest_log_wins_even_when_two_emails_share_the_same_minute(self):
        response = log(json.dumps(self.telemetry()))
        response["bitacora"].append({**response["bitacora"][0], "detalle": '{"correo":2,"lectura":"sin_confirmar"}'})
        self.assertEqual(mail.observar(response, NOW)["contenido_estado"], "lectura_sin_confirmar")

    def test_backend_synthetic_suite_runs_in_existing_python_ci(self):
        run = subprocess.run(["node", "--test", str(ROOT / "tests/correo-estado.test.cjs")],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
