"""Mantenimiento acotado: dobles de API, sin red, tokens ni cancelaciones reales."""
import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "nube"))
import mantenimiento_queued as m

NOW = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)
TARGET = "actions/runs/" + str(m.RUN)
JOBS = {"total_count": 0, "jobs": []}


def run(**changes):
    return {"id": m.RUN, "head_sha": m.HEAD, "run_attempt": 1,
            "repository": {"full_name": m.REPO}, "head_branch": "main",
            "event": "schedule", "path": ".github/workflows/sala-cada-hora.yml",
            "status": "queued", "conclusion": None,
            "created_at": "2026-10-07T16:57:37Z", **changes}


class API:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, path, **kwargs):
        self.calls.append((kwargs.get("method", "GET"), path))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class MaintenanceTests(unittest.TestCase):
    def apply(self, api, timeout=12):
        clock = Clock()
        result = m.maintain(api, apply=True, now=NOW, clock=clock,
                            sleep=clock.sleep, timeout=timeout)
        return result, clock

    def test_fixed_identity_rejects_altered_and_malformed_targets(self):
        for changes in ({"id": m.RUN + 1}, {"head_sha": "a" * 40},
                        {"run_attempt": 2}, {"run_attempt": True},
                        {"repository": {"full_name": "other/repo"}},
                        {"repository": None}, {"head_branch": "other"},
                        {"event": "workflow_dispatch"}, {"path": "other.yml"}):
            with self.subTest(changes=changes):
                api = API([run(**changes), JOBS])
                with self.assertRaises(m.OnlineError):
                    self.apply(api)
                self.assertFalse(any(method == "POST" for method, _ in api.calls))
        for invalid in (None, [], "not a run"):
            with self.subTest(invalid=invalid), self.assertRaises(m.OnlineError):
                m.identity(invalid)

    def test_age_queued_attempt_and_absence_of_jobs_must_be_proven(self):
        m.eligible(run(created_at=(NOW - m.MIN_AGE).isoformat()), JOBS, NOW)
        missing_conclusion = run()
        del missing_conclusion["conclusion"]
        variants = [(run(status="in_progress"), JOBS),
                    (run(status="completed", conclusion="cancelled"), JOBS),
                    (run(conclusion="success"), JOBS), (missing_conclusion, JOBS),
                    (run(created_at=(NOW - m.MIN_AGE + timedelta(seconds=1)).isoformat()), JOBS),
                    (run(created_at="2026-10-07T16:57:37"), JOBS),
                    (run(created_at=[]), JOBS), (run(created_at="bad"), JOBS),
                    (run(), {"total_count": 1, "jobs": []}),
                    (run(), {"total_count": 0, "jobs": [{"id": 1}]}),
                    (run(), {"total_count": False, "jobs": []}),
                    (run(), {"jobs": []}), (run(), None)]
        for observed, jobs in variants:
            with self.subTest(observed=observed, jobs=jobs):
                api = API([observed, jobs])
                with self.assertRaises(m.OnlineError):
                    self.apply(api)
                self.assertFalse(any(method == "POST" for method, _ in api.calls))

    def test_dry_run_only_reads_fixed_run_and_all_jobs(self):
        api = API([run(), JOBS])
        result = m.maintain(api, now=NOW)
        self.assertEqual(api.calls, [("GET", TARGET),
                                    ("GET", TARGET + "/jobs?filter=all&per_page=100")])
        self.assertEqual(result, {"run_id": m.RUN, "modo": "simular",
                                  "elegible": True, "cancelado": False})

    def test_immediate_recheck_race_prevents_post(self):
        for changed_run, changed_jobs in ((run(status="in_progress"), JOBS),
                                          (run(), {"total_count": 1, "jobs": [{"id": 1}]}),
                                          (run(run_attempt=2), JOBS)):
            with self.subTest(changed_run=changed_run, changed_jobs=changed_jobs):
                api = API([run(), JOBS, changed_run, changed_jobs])
                with self.assertRaises(m.OnlineError):
                    self.apply(api)
                self.assertEqual(len(api.calls), 4)
                self.assertTrue(all(method == "GET" for method, _ in api.calls))

    def test_500_and_rejected_post_reconcile_via_get_without_post_retry(self):
        for status in (500, 409, 403):
            calls = []
            responses = [run(), JOBS, run(), JOBS, status, run(),
                         run(status="completed", conclusion="cancelled")]

            def open_response(req, **kwargs):
                calls.append((req.get_method(), req.full_url))
                response = responses.pop(0)
                if isinstance(response, int):
                    raise urllib.error.HTTPError(req.full_url, response,
                                                 "remote detail must remain private", {}, None)
                return io.BytesIO(json.dumps(response).encode())

            with self.subTest(status=status), patch("snapshots_online.urllib.request.urlopen",
                                                   side_effect=open_response):
                result, _ = self.apply(m.GitHub(m.REPO, "synthetic-not-a-token"))
            self.assertTrue(result["cancelado"])
            self.assertTrue(result["terminal"])
            self.assertEqual(result["respuesta_ambigua"], status == 500)
            self.assertEqual(result["post_http_status"], status)
            self.assertEqual([url for method, url in calls if method == "POST"],
                             ["https://api.github.com/repos/" + m.REPO + "/" + TARGET + "/force-cancel"])
            self.assertEqual([method for method, _ in calls[-2:]], ["GET", "GET"])

    def test_read_failures_and_timeout_never_accredit_cancellation(self):
        api = API([run(), JOBS, run(), JOBS, None, m.OnlineError("read unavailable"),
                   run(status="completed", conclusion="cancelled")])
        result, _ = self.apply(api)
        self.assertTrue(result["cancelado"])
        self.assertEqual(result["errores_lectura"], 1)
        for final in (run(), m.OnlineError("read unavailable")):
            with self.subTest(final=final):
                api = API([run(), JOBS, run(), JOBS, None, final, final, final])
                result, clock = self.apply(api)
                self.assertFalse(result["cancelado"])
                self.assertFalse(result["terminal"])
                self.assertEqual(clock(), 12)
                self.assertEqual(sum(method == "POST" for method, _ in api.calls), 1)
        for invalid_timeout in (0, -1, float("inf"), float("nan"), True):
            api = API([])
            with self.subTest(timeout=invalid_timeout), self.assertRaises(m.OnlineError):
                self.apply(api, timeout=invalid_timeout)
            self.assertEqual(api.calls, [])

    def test_main_requires_manual_main_ephemeral_token_and_first_attempt(self):
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": m.REPO,
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
               "GITHUB_RUN_ID": str(m.RUN + 1), "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_TOKEN": "synthetic-not-a-token"}
        for changes in ({"GITHUB_ACTIONS": ""}, {"GITHUB_REPOSITORY": "other/repo"},
                        {"GITHUB_EVENT_NAME": "push"}, {"GITHUB_REF": "refs/heads/feature"},
                        {"GITHUB_RUN_ID": str(m.RUN)}, {"GITHUB_RUN_ID": ""},
                        {"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_TOKEN": ""}):
            with self.subTest(changes=changes), patch.dict(os.environ, {**env, **changes}, clear=True), \
                    patch.object(sys, "argv", ["mantenimiento"]), patch.object(m, "GitHub") as github:
                with self.assertRaises(m.OnlineError):
                    m.main()
                github.assert_not_called()
        for args, report, exit_code in (([], {"modo": "simular", "cancelado": False}, 0),
                                       (["--aplicar"], {"terminal": True, "cancelado": False}, 1),
                                       (["--aplicar"], {"terminal": True, "cancelado": True}, 0)):
            output = io.StringIO()
            with self.subTest(args=args, report=report), patch.dict(os.environ, env, clear=True), \
                    patch.object(sys, "argv", ["mantenimiento", *args]), \
                    patch.object(m, "GitHub") as github, \
                    patch.object(m, "maintain", return_value=report) as maintain, redirect_stdout(output):
                self.assertEqual(m.main(), exit_code)
                github.assert_called_once_with(m.REPO, env["GITHUB_TOKEN"])
                self.assertEqual(maintain.call_args.kwargs, {"apply": bool(args)})
            self.assertNotIn(env["GITHUB_TOKEN"], output.getvalue())

    def test_workflow_manual_default_no_personal_secrets_or_production_groups(self):
        workflow = (ROOT / ".github/workflows/sala-mantenimiento-queued.yml").read_text()
        triggers = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"^  ([a-z_]+):", triggers, re.M), ["workflow_dispatch"])
        self.assertEqual(re.findall(r"^      ([a-z_]+):", triggers, re.M), ["aplicar"])
        self.assertRegex(triggers, r"type: boolean\s+required: false\s+default: false")
        permissions = workflow.split("\npermissions:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertEqual(set(re.findall(r"^  (\w+): (\w+)$", permissions, re.M)),
                         {("contents", "read"), ("actions", "write")})
        self.assertIn("group: sala-mantenimiento-queued\n  cancel-in-progress: false", workflow)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("uses: ./", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("filter: blob:none", workflow)
        self.assertIn('python3 nube/mantenimiento_queued.py "${args[@]}"', workflow)


if __name__ == "__main__":
    unittest.main()
