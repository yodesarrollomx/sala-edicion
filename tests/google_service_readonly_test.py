import importlib.util
import json
import pathlib
import re
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "nube/google_service_readonly.py"
SPEC = importlib.util.spec_from_file_location("google_service_readonly", PATH)
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
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class ServiceReadonlyTest(unittest.TestCase):
    def test_publishable_sources_exclude_fixed_private_resource_identifiers(self):
        root = PATH.parents[1]
        paths = [PATH, pathlib.Path(__file__), root / ".github/workflows/google-service-readonly.yml"]
        fixed_google_id = re.compile(r"(?<![A-Za-z0-9_-])(?:1[A-Za-z0-9_-]{30,}|AKfycb[A-Za-z0-9_-]{25,})(?![A-Za-z0-9_-])")
        for path in paths:
            source = path.read_text()
            self.assertIsNone(fixed_google_id.search(source), path.name)
            self.assertNotRegex(source, r"-----BEGIN [A-Z ]+KEY-----\s*[A-Za-z0-9+/]{20}")
        source = PATH.read_text()
        self.assertNotRegex(source, r"(?m)^\s*(?:PROJECT_ID|SALA_SHEET|SCRIPT_ID|PROJECTS)\s*=")
        self.assertEqual(source.count("print("), 1)
        self.assertIn("print(json.dumps(report, sort_keys=True))", source)

    def test_disabled_service_and_permissions_are_reported_without_identifiers(self):
        session = Session([Response(200, {"projectId": "synthetic-project", "name": "projects/123456789"}),
                           Response(200, {"permissions": list(PROBE.PERMISSIONS)}),
                           Response(200, {"state": "DISABLED"})])
        report = PROBE.diagnose(session, "synthetic-token", "synthetic-project")
        self.assertEqual(report["appsScriptService"]["state"], "DISABLED")
        self.assertTrue(report["permissionTest"]["canEnableService"])
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST", "GET"])
        self.assertTrue(session.calls[1][1].endswith(":testIamPermissions"))
        self.assertEqual(session.calls[1][2]["json"], {"permissions": list(PROBE.PERMISSIONS)})
        for item in ("synthetic-project", "123456789", "synthetic-token"):
            self.assertNotIn(item, json.dumps(report))
        for method, url, options in session.calls:
            self.assertNotIn(":enable", url)
            self.assertFalse(options["allow_redirects"])
        self.assertEqual(report["configurationWrites"], 0)

    def test_denials_do_not_retry_or_leak_provider_prose(self):
        denied = Response(403, {"error": {"status": "PERMISSION_DENIED", "message": "SECRET project-private",
                                          "details": [{"reason": "SERVICE_DISABLED", "metadata": {"private": "SECRET"}}]}})
        session = Session([denied, denied])
        report = PROBE.diagnose(session, "synthetic-token", "synthetic-project")
        self.assertEqual(len(session.calls), 2)
        self.assertFalse(report["appsScriptService"]["attempted"])
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(report["permissionTest"]["reasons"], ["SERVICE_DISABLED"])

    def test_project_mismatch_does_not_read_another_project_service(self):
        session = Session([Response(200, {"projectId": "another-project", "name": "projects/123"}),
                           Response(200, {"permissions": []})])
        report = PROBE.diagnose(session, "synthetic-token", "synthetic-project")
        self.assertEqual(len(session.calls), 2)
        self.assertFalse(report["projectMetadata"]["credentialProjectMatched"])
        self.assertFalse(report["permissionTest"]["canEnableService"])

    def test_invalid_project_never_calls_network(self):
        session = Session([])
        with self.assertRaises(ValueError):
            PROBE.diagnose(session, "synthetic-token", "../another-project")
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
