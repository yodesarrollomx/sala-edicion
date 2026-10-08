"""Pruebas sintéticas: ninguna llamada git/gh real ni endpoint de producción."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publicar_git", ROOT / "nube/publicar_git.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BASE, HEAD, MERGE = "a" * 40, "b" * 40, "c" * 40
BRANCH = "bot/sala-relevo-123-1"


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.status = " M datos/manifiesto.json\0?? relevo.log\0"
        self.staged = "datos/manifiesto.json\0architecture-impact.json\0"
        self.committed = False
        self.merged = False
        self.merge_confirmed = True
        self.head_changed = False
        self.guard = "success"
        self.verification = "success"
        self.publication = "success"
        self.wrong_guard_head = False
        self.ambiguous = False
        self.old_guard = False
        self.checks = [{"name": "Arquitectura YOD", "bucket": "pass"},
                       {"name": "verificar", "bucket": "pass"}]
        self.empty_checks_reads = 0
        self.dispatched = {}
        self.existing_pr = False
        self.fail_prefix = None
        self.clock = 0

    def now(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds

    def __call__(self, argv, *, cwd, input=None):
        self.calls.append((argv, input))
        result = ""
        if self.fail_prefix and argv[:len(self.fail_prefix)] == self.fail_prefix:
            return subprocess.CompletedProcess(argv, 1, "", "sensitive diagnostics must not escape")
        if argv[:3] == ["git", "status", "--porcelain=v1"]:
            result = self.status
        elif argv[:3] == ["git", "rev-parse", "HEAD"]:
            result = HEAD if self.committed else BASE
        elif argv[:4] == ["git", "diff", "--cached", "--name-only"]:
            result = self.staged
        elif argv[:2] == ["git", "-c"] and "commit" in argv:
            self.committed = True
        elif argv[:3] == ["gh", "pr", "checks"]:
            if self.empty_checks_reads:
                self.empty_checks_reads -= 1
                result = ""
            else:
                result = json.dumps(self.checks)
        elif argv[:3] == ["gh", "pr", "merge"]:
            self.merged = True
        elif argv[:2] == ["gh", "api"]:
            endpoint, method = argv[4], argv[3]
            if endpoint.endswith("/pulls?state=open&per_page=100") and method == "GET":
                result = json.dumps([{"number": 8, "title": "Sala relevo: archivos generados",
                                      "base": {"ref": "main"}, "state": "open"}]
                                    if self.existing_pr else [])
            elif endpoint.endswith("/pulls") and method == "POST":
                result = json.dumps({"number": 9})
            elif endpoint.endswith("/pulls/9"):
                result = json.dumps({
                    "state": "closed" if self.merged else "open", "draft": False,
                    "head": {"sha": BASE if self.head_changed else HEAD},
                    "base": {"ref": "main"},
                    "merged": self.merged and self.merge_confirmed,
                    "merge_commit_sha": MERGE if self.merged and self.merge_confirmed else None,
                })
            elif "/dispatches" in endpoint:
                workflow = endpoint.split("/workflows/")[1].split("/")[0]
                self.dispatched[workflow] = json.loads(input)
            elif "/runs?" in endpoint:
                workflow = endpoint.split("/workflows/")[1].split("/")[0]
                dispatch = self.dispatched.get(workflow)
                runs = []
                if workflow == "arquitectura.yml" and self.old_guard:
                    runs.append(self.make_run(workflow, 1, {"ref": BRANCH}))
                if dispatch:
                    runs.append(self.make_run(workflow, 10, dispatch))
                    if self.ambiguous:
                        runs.append(self.make_run(workflow, 11, dispatch))
                result = json.dumps({"workflow_runs": runs})
            else:
                raise AssertionError(f"Unexpected API route: {endpoint}")
        return subprocess.CompletedProcess(argv, 0, result, "")

    def make_run(self, workflow, number, dispatch):
        is_guard = workflow == "arquitectura.yml"
        is_verifier = workflow == "verificar.yml"
        status = self.guard if is_guard else (self.verification if is_verifier else self.publication)
        fields = dispatch.get("inputs", {})
        return {
            "id": number, "event": "workflow_dispatch", "head_branch": dispatch["ref"],
            "head_sha": (BASE if self.wrong_guard_head else HEAD) if is_guard else
                        (HEAD if is_verifier else BASE),
            "status": "queued" if status == "queued" else "completed",
            "conclusion": None if status == "queued" else status,
            "display_title": "" if is_guard or is_verifier else
            f"Sala publicar · {fields['sha']} · {fields['publicacion_id']}",
        }


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        (self.cwd / "datos").mkdir()
        (self.cwd / "datos/manifiesto.json").write_text('{"items": []}')
        (self.cwd / "architecture-impact.json").write_text('{"model_revision":"2026-09-30.1"}')
        self.fake = FakeGitHub()
        self.env = {"GITHUB_REPOSITORY": "example/sala", "GITHUB_RUN_ID": "123",
                    "GITHUB_RUN_ATTEMPT": "1", "GH_TOKEN": "synthetic",
                    "GITHUB_OUTPUT": str(self.cwd / "output")}
        self.publisher = module.Publisher(self.cwd, env=self.env, runner=self.fake,
                                          clock=self.fake.now, sleep=self.fake.sleep,
                                          timeout=30, interval=10)

    def commands(self):
        return [c[0] for c in self.fake.calls]

    def assert_no_merge(self):
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] for c in self.commands()))

    def test_integrates_exact_checked_head_without_push_main_or_bypass(self):
        result = self.publisher.integrate("relevo")
        self.assertEqual(result, {"hubo": "si", "merge_sha": MERGE, "pr": 9})
        pushes = [c for c in self.commands() if c[:2] == ["git", "push"]]
        self.assertEqual(pushes, [["git", "push", "--set-upstream", "origin", BRANCH]])
        merge = next(c for c in self.commands() if c[:3] == ["gh", "pr", "merge"])
        self.assertEqual(merge[-3:], ["--squash", "--match-head-commit", HEAD])
        for command in self.commands():
            self.assertNotIn("--admin", command)
            self.assertNotIn("--auto", command)
            self.assertNotIn("--force", command)
        impact = json.loads((self.cwd / "architecture-impact.json").read_text())
        self.assertEqual(impact["proposal_id"], "CHG-SALA-PUBLICACION-001")
        self.assertEqual(impact["model_revision"], "2026-09-30.1")
        self.assertNotIn("publicar.yml", self.fake.dispatched)

    def test_no_changes_does_not_mutate_git_or_github(self):
        self.fake.status = "?? relevo.log\0"
        self.assertEqual(self.publisher.integrate("relevo"), {"hubo": "no"})
        self.assertEqual(len(self.commands()), 1)

    def test_mesa_without_changes_returns_sha_to_verify_before_mount(self):
        self.fake.status = "?? mesa.log\0"
        self.assertEqual(self.publisher.integrate("mesa"), {"hubo": "no", "merge_sha": BASE})
        self.assertEqual(len(self.commands()), 3)
        self.assertEqual(self.commands()[-1], ["git", "rev-parse", "HEAD"])
        workflow = (ROOT / ".github/workflows/sala-mesa.yml").read_text()
        self.assertIn("steps.guardar.outputs.hubo == 'no' && env.MODO == 'montar'", workflow)

    def test_unexpected_changed_code_fails_before_any_mutation(self):
        self.fake.status += " M gas/Code.gs\0"
        with self.assertRaisesRegex(module.PublicationError, "fuera de las rutas"):
            self.publisher.integrate("relevo")
        self.assertEqual(len(self.commands()), 1)

    def test_staged_outside_allowed_routes_fails_before_commit(self):
        self.fake.staged += "index.html\0"
        with self.assertRaisesRegex(module.PublicationError, "archivos ajenos"):
            self.publisher.integrate("relevo")
        self.assertFalse(self.fake.committed)

    def test_invalid_generated_json_is_rejected(self):
        (self.cwd / "datos/manifiesto.json").write_text("invalid")
        with self.assertRaisesRegex(module.PublicationError, "JSON generado"):
            self.publisher.integrate("relevo")
        self.assertFalse(self.fake.committed)

    def test_generated_symlink_is_rejected(self):
        (self.cwd / "datos/manifiesto.json").unlink()
        (self.cwd / "datos/manifiesto.json").symlink_to(self.cwd / "architecture-impact.json")
        with self.assertRaisesRegex(module.PublicationError, "simbólicos"):
            self.publisher.integrate("relevo")

    def test_existing_bot_pr_does_not_generate_duplicate(self):
        self.fake.existing_pr = True
        result = self.publisher.integrate("relevo")
        self.assertEqual(result, {"hubo": "pendiente", "pr": 8})
        self.assertFalse(any(c[:2] == ["git", "checkout"] for c in self.commands()))
        self.assert_no_merge()

    def test_no_change_in_other_process_still_one_git_read(self):
        self.fake.status = ""
        self.assertEqual(self.publisher.integrate("relevo"), {"hubo": "no"})
        self.assertEqual(len(self.commands()), 1)

    def test_failed_guard_leaves_pr_without_merge(self):
        self.fake.guard = "failure"
        with self.assertRaisesRegex(module.PublicationError, "PR #9.*No montar"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()
        self.assertFalse((self.cwd / "output").exists())

    def test_guard_wrong_head_times_out_instead_of_accepting_green(self):
        self.fake.wrong_guard_head = True
        with self.assertRaisesRegex(module.PublicationError, "agotó"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_ambiguous_new_guard_runs_are_rejected(self):
        self.fake.ambiguous = True
        with self.assertRaisesRegex(module.PublicationError, "Más de una"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_old_guard_does_not_count_as_new_dispatch(self):
        self.fake.old_guard = True
        self.fake.guard = "queued"
        with self.assertRaisesRegex(module.PublicationError, "agotó"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_missing_required_architecture_check_is_blocked(self):
        self.fake.checks = [{"name": "unrelated", "bucket": "pass"}]
        result = self.publisher.integrate("relevo")
        self.assertEqual(result, {"hubo": "pendiente", "pr": 9})
        self.assert_no_merge()

    def test_bot_pr_dispatches_verification_on_exact_commit(self):
        self.publisher.integrate("relevo")
        self.assertEqual(self.fake.dispatched["verificar.yml"], {
            "ref": BRANCH, "inputs": {}})
        self.assertEqual(self.fake.dispatched["arquitectura.yml"], {
            "ref": BRANCH, "inputs": {"base_sha": BASE, "head_sha": HEAD}})
        self.assertTrue(self.fake.merged)

    def test_failed_explicit_verification_never_merges(self):
        self.fake.verification = "failure"
        with self.assertRaisesRegex(module.PublicationError, "sin éxito"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_missing_verification_check_never_merges(self):
        self.fake.checks = [{"name": "Arquitectura YOD", "bucket": "pass"}]
        result = self.publisher.integrate("relevo")
        self.assertEqual(result, {"hubo": "pendiente", "pr": 9})
        self.assert_no_merge()

    def test_empty_checks_while_github_registers_dispatch_are_retried(self):
        self.fake.empty_checks_reads = 2
        self.publisher.integrate("relevo")
        self.assertEqual(self.fake.empty_checks_reads, 0)
        self.assertTrue(self.fake.merged)

    def test_failed_required_check_is_blocked(self):
        self.fake.checks.append({"name": "functional", "bucket": "fail"})
        with self.assertRaisesRegex(module.PublicationError, "no pasó"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_pending_required_check_times_out(self):
        self.fake.checks[0]["bucket"] = "pending"
        with self.assertRaisesRegex(module.PublicationError, "agotó"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_head_changed_after_checks_is_blocked(self):
        self.fake.head_changed = True
        with self.assertRaisesRegex(module.PublicationError, "PR cambió"):
            self.publisher.integrate("relevo")
        self.assert_no_merge()

    def test_merge_rejection_is_not_retried_or_bypassed(self):
        self.fake.fail_prefix = ["gh", "pr", "merge"]
        with self.assertRaisesRegex(module.PublicationError, "PR #9") as error:
            self.publisher.integrate("relevo")
        self.assertNotIn("sensitive", str(error.exception))
        merges = [c for c in self.commands() if c[:3] == ["gh", "pr", "merge"]]
        self.assertEqual(len(merges), 1)
        self.assertFalse((self.cwd / "output").exists())

    def test_queued_merge_is_not_reported_as_integrated(self):
        self.fake.merge_confirmed = False
        with self.assertRaisesRegex(module.PublicationError, "no confirmó"):
            self.publisher.integrate("relevo")

    def test_publish_dispatches_branch_with_exact_sha_and_correlation(self):
        result = self.publisher.publish(MERGE, "relevo")
        self.assertEqual(result, {"publicado_sha": MERGE, "publicacion_run": 10})
        self.assertEqual(self.fake.dispatched["publicar.yml"], {
            "ref": "main", "inputs": {"sha": MERGE, "publicacion_id": "relevo-123-1"}})
        self.assertFalse(any(c[0] == "git" for c in self.commands()))

    def test_failed_publication_never_reports_success(self):
        self.fake.publication = "failure"
        with self.assertRaisesRegex(module.PublicationError, "sin éxito"):
            self.publisher.publish(MERGE, "relevo")
        self.assertFalse((self.cwd / "output").exists())

    def test_invalid_publication_sha_never_dispatches(self):
        with self.assertRaises(module.PublicationError):
            self.publisher.publish("main", "relevo")
        self.assertEqual(self.commands(), [])

    def test_all_generated_route_contracts_and_traversal(self):
        expected = {"arranque": "laminas/nueva.png", "mesa": "datos/tiras/nueva.json",
                    "relevo": "datos/manifiesto.json", "maquinas": "datos/maquinas.json",
                    "chinches": "datos/encargos.json"}
        for process, path in expected.items():
            self.assertTrue(module.Publisher.allowed_path(path, process))
            self.assertFalse(module.Publisher.allowed_path("datos/tiras/../../gas/Code.gs", process))
            self.assertFalse(module.Publisher.allowed_path("architecture-impact.json", process))

    def test_workflows_keep_verification_before_pr_and_publication_before_mount(self):
        for process in module.PATHS:
            text = (ROOT / f".github/workflows/sala-{process}.yml").read_text()
            self.assertLess(text.index("python3 nube/verificar.py"),
                            text.index(f"integrar --proceso {process}"))
            self.assertIn(f"publicar --proceso {process}", text)
            self.assertNotIn("git push", text)
            self.assertIn("pull-requests: write", text)
            if process in ("arranque", "mesa"):
                self.assertLess(text.index(f"publicar --proceso {process}"),
                                text.index(f"sala_{process}.py --montar"))
        publication = (ROOT / ".github/workflows/publicar.yml").read_text()
        self.assertIn('git merge-base --is-ancestor "$PUBLICAR_SHA"', publication)
        self.assertIn('[ "$actual" = "$PUBLICAR_SHA" ]', publication)
        self.assertIn("group: pages", publication)


if __name__ == "__main__":
    unittest.main()
