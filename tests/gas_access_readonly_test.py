import importlib.util
import json
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "nube/gas_access_readonly.py"
SPEC = importlib.util.spec_from_file_location("gas_access_readonly", PATH)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload
    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class ReadonlyProbeTest(unittest.TestCase):
    def test_rejection_closes_each_project_and_redacts_provider_message(self):
        rejected = Response(403, {"error": {"status": "PERMISSION_DENIED", "message": "private text token ABC",
                                               "details": [{"reason": "SERVICE_DISABLED", "metadata": {"secret": "ABC"}}]}})
        session = Session([rejected, rejected, rejected])
        report = PROBE.diagnose(session, "synthetic-token")
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(report["projects"]["sala"]["content"]["attempted"], False)
        serialized = json.dumps(report)
        for private in ["ABC", "private text", "synthetic-token", PROBE.SALA_SHEET, *PROBE.PROJECTS.values()]:
            self.assertNotIn(private, serialized)
        self.assertEqual(report["projects"]["sala"]["project"]["reasons"], ["SERVICE_DISABLED"])
        self.assertEqual(report["businessWrites"], 0)

    def test_success_discards_source_and_identity_and_uses_get_once(self):
        replies = [Response(200, {"id": PROBE.SALA_SHEET, "mimeType": "application/vnd.google-apps.spreadsheet", "capabilities": {"canEdit": True}})]
        for name, value in PROBE.PROJECTS.items():
            replies += [Response(200, {"scriptId": value, "parentId": PROBE.SALA_SHEET}),
                        Response(200, {"files": [{"name": "PRIVATE", "source": "sensitive-source"}]}),
                        Response(200, {"deployments": [{"deploymentId": "sensitive-deployment"}]})]
        session = Session(replies)
        report = PROBE.diagnose(session, "synthetic-token")
        self.assertEqual(len(session.calls), 7)
        self.assertTrue(report["projects"]["sala"]["project"]["originalContainerMatched"])
        self.assertTrue(report["projects"]["portero"]["content"]["sourceReadable"])
        for private in ["PRIVATE", "sensitive-source", "sensitive-deployment", "synthetic-token", PROBE.SALA_SHEET]:
            self.assertNotIn(private, json.dumps(report))
        for url, options in session.calls:
            self.assertFalse(options["allow_redirects"])
            self.assertEqual(options["timeout"], 25)
            self.assertTrue(url.startswith("https://www.googleapis.com/drive/v3/files/") or url.startswith("https://script.googleapis.com/v1/projects/"))

    def test_transport_exception_never_prints_exception_body(self):
        class Broken:
            def get(self, *args, **kwargs):
                raise RuntimeError("sensitive bearer secret")
        status, data = PROBE.read_once(Broken(), "https://example.invalid", "synthetic")
        self.assertIsNone(data)
        self.assertEqual(status, {"ok": False, "status": "TRANSPORT_OR_JSON_ERROR"})


if __name__ == "__main__":
    unittest.main()
