"""Contratos de almacenamiento y publicación: dobles, sin red ni datos reales."""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ("nube" if (ROOT / "nube").is_dir() else "scripts")))
import snapshots_online as so


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.repo = "yodesarrollomx/sala-edicion"
        self.prefixes = ("datos/tiras/", "laminas/")
        self.path = "datos/tiras/prueba.json"
        self.data, self.manifest = so.encode_archive(
            self.repo, "a" * 40, {self.path: b'{"prueba":true}'}, [], self.prefixes)

    def test_roundtrip_and_hash(self):
        manifest, files = so.decode_archive(self.data, self.repo, self.prefixes,
                                            so.digest(self.data), self.manifest["data_sha"])
        self.assertEqual(files[self.path], b'{"prueba":true}')
        self.assertEqual(manifest["data_sha"], self.manifest["data_sha"])

    def test_wrong_archive_hash(self):
        with self.assertRaises(so.OnlineError):
            so.decode_archive(self.data, self.repo, self.prefixes, "0" * 64)

    def test_archive_bytes_are_reproducible_for_recovery(self):
        repeated, _ = so.encode_archive(self.repo, "a" * 40,
                                       {self.path: b'{"prueba":true}'}, [], self.prefixes)
        self.assertEqual(self.data, repeated)
        with zipfile.ZipFile(io.BytesIO(repeated)) as archive:
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist()))

    def test_delta_identity_binds_base_and_patch(self):
        raw, manifest = so.encode_archive(self.repo, "a" * 40, {self.path: b"{}"}, [],
                                          self.prefixes, base_id=10, base_data="b" * 64)
        decoded, _ = so.decode_archive(raw, self.repo, self.prefixes,
                                       expected_data=manifest["data_sha"])
        self.assertEqual(decoded["base_snapshot_id"], 10)
        changed, _ = so.encode_archive(self.repo, "a" * 40, {self.path: b"{}"}, [],
                                       self.prefixes, base_id=10, base_data="c" * 64)
        with self.assertRaises(so.OnlineError):
            so.decode_archive(changed, self.repo, self.prefixes, expected_data=manifest["data_sha"])

    def test_wrong_repo(self):
        with self.assertRaises(so.OnlineError):
            so.decode_archive(self.data, "otro/repositorio", self.prefixes)

    def test_wrong_data_hash(self):
        with self.assertRaises(so.OnlineError):
            so.decode_archive(self.data, self.repo, self.prefixes, expected_data="0" * 64)

    def test_paths_and_secret_files_rejected(self):
        for path in ("../datos/tiras/x.json", "datos/tiras/../x.json",
                     "datos/tiras//x.json", "/datos/tiras/x.json", ".env",
                     "nube/secreto.json", "datos/tiras/.secreto.json", "laminas/ejecutar.py"):
            with self.subTest(path=path):
                self.assertFalse(so.allowed(path, self.prefixes))
                with self.assertRaises(so.OnlineError):
                    so.encode_archive(self.repo, "a" * 40, {path: b"{}"}, [], self.prefixes)

    def test_invalid_json(self):
        with self.assertRaises(so.OnlineError):
            so.encode_archive(self.repo, "a" * 40, {self.path: b"no es JSON"}, [], self.prefixes)

    def altered_zip(self, mutation):
        src, out = zipfile.ZipFile(io.BytesIO(self.data)), io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for info in src.infolist():
                name, data = info.filename, src.read(info.filename)
                if name == "snapshot.json":
                    m = json.loads(data)
                    mutation(m)
                    data = so.canonical(m)
                z.writestr(name, data)
        return out.getvalue()

    def test_file_checksum_tampering(self):
        altered = self.altered_zip(lambda m: m["files"][0].update(sha256="0" * 64))
        with self.assertRaises(so.OnlineError):
            so.decode_archive(altered, self.repo, self.prefixes)

    def test_undeclared_and_duplicate_entry(self):
        for path in ("files/nube/secret.json", "snapshot.json"):
            out = io.BytesIO(self.data)
            with zipfile.ZipFile(out, "a") as z:
                z.writestr(path, b"{}")
            with self.assertRaises(so.OnlineError):
                so.decode_archive(out.getvalue(), self.repo, self.prefixes)

    def test_symlink(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("snapshot.json", so.canonical(self.manifest))
            info = zipfile.ZipInfo("files/" + self.path)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, b"secret")
        with self.assertRaises(so.OnlineError):
            so.decode_archive(out.getvalue(), self.repo, self.prefixes)

    def test_declared_size_and_limits(self):
        altered = self.altered_zip(lambda m: m["files"][0].update(bytes=999))
        with self.assertRaises(so.OnlineError):
            so.decode_archive(altered, self.repo, self.prefixes)
        with patch.object(so, "MAX_ZIP", 10):
            with self.assertRaises(so.OnlineError):
                so.decode_archive(self.data, self.repo, self.prefixes)

    def test_room_and_early_warning(self):
        # La mesa se atoró con un snapshot acumulado de 208.4 MB contra 200 MiB.
        self.assertGreaterEqual(so.MAX_ZIP, 400 * 1024 * 1024)
        self.assertLess(so.AVISO_ZIP, so.MAX_ZIP)
        out = io.StringIO()
        with patch.object(so, "AVISO_ZIP", 1), patch("sys.stdout", out):
            so.encode_archive(self.repo, "a" * 40, {self.path: b'{"x": 1}'}, [], self.prefixes)
        self.assertIn("::warning::Snapshot online", out.getvalue())
        quiet = io.StringIO()
        with patch("sys.stdout", quiet):
            so.encode_archive(self.repo, "a" * 40, {self.path: b'{"x": 1}'}, [], self.prefixes)
        self.assertEqual(quiet.getvalue(), "")

    def test_deletion_contract(self):
        raw, _ = so.encode_archive(self.repo, "a" * 40, {}, [self.path], self.prefixes)
        m, files = so.decode_archive(raw, self.repo, self.prefixes)
        self.assertEqual(m["deleted"], [self.path])
        self.assertEqual(files, {})
        with self.assertRaises(so.OnlineError):
            so.encode_archive(self.repo, "a" * 40, {}, ["nube/private.json"], self.prefixes)

    def test_receipt_is_exact(self):
        expected = {"code_sha": "a" * 40, "data_sha": "b" * 64, "snapshot_id": 12, "run_id": "34"}
        receipt = {"schema": 1, **expected}
        self.assertTrue(so.receipt_matches(receipt, **expected))
        for key, value in expected.items():
            self.assertFalse(so.receipt_matches({**receipt, key: str(value) + "x"}, **expected))

    def test_receipt_differences_never_return_untrusted_values_or_keys(self):
        expected = {"code_sha": "a" * 40, "data_sha": "b" * 64,
                    "snapshot_id": 12, "run_id": "34", "plan_sha256": "c" * 64}
        receipt = {"schema": 1, **expected}
        self.assertEqual(so.receipt_differences(receipt, **expected), [])
        for field in ("schema", *expected):
            changed = {**receipt, field: "PRIVATE_REMOTE_VALUE", "PRIVATE_REMOTE_KEY": "PRIVATE"}
            self.assertEqual(so.receipt_differences(changed, **expected), [field])
        self.assertEqual(so.receipt_differences(["PRIVATE"], **expected), ["tipo_recibo"])


class FakeGitHub:
    def __init__(self, main):
        self.main = main
        self.lock = None
        self.commits, self.releases, self.assets = {}, {}, {}
        self.number = 0

    def request(self, path, body=None, method=None):
        if path == "git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path == "git/ref/" + so.LOCK_REF:
            if not self.lock:
                raise so.OnlineError("GitHub HTTP 404")
            return {"object": {"sha": self.lock}}
        if path == "git/trees":
            return {"sha": "d" * 40}
        if path == "git/commits":
            self.number += 1
            sha = f"{self.number:040x}"
            self.commits[sha] = {**copy.deepcopy(body), "tree": {"sha": body["tree"]}}
            return {"sha": sha}
        if path.startswith("git/commits/"):
            return copy.deepcopy(self.commits[path.rsplit("/", 1)[-1]])
        if path == "git/refs":
            if self.lock:
                raise so.OnlineError("GitHub HTTP 422")
            self.lock = body["sha"]
            return {}
        if path == "git/refs/" + so.LOCK_REF:
            if self.lock not in self.commits[body["sha"]]["parents"]:
                raise so.OnlineError("GitHub HTTP 422")
            self.lock = body["sha"]
            return {}
        if path.startswith("actions/runs/"):
            return {"status": "in_progress"}
        if path.startswith("releases?"):
            return copy.deepcopy(list(self.releases.values()))
        if path == "releases":
            self.number += 1
            rid = self.number
            self.releases[rid] = {**copy.deepcopy(body), "id": rid, "assets": [],
                                   "upload_url": "unused"}
            return copy.deepcopy(self.releases[rid])
        if path.startswith("releases/"):
            rid = int(path.split("/")[1])
            if body:
                self.releases[rid].update(copy.deepcopy(body))
            return copy.deepcopy(self.releases[rid])
        raise AssertionError("API no esperada: " + path)

    def upload(self, release, data):
        self.number += 1
        aid = self.number
        self.assets[aid] = data
        asset = {"id": aid, "name": "snapshot.zip"}
        self.releases[release["id"]]["assets"].append(asset)
        return asset

    def asset(self, aid):
        return self.assets[aid]


class TransportTests(unittest.TestCase):
    def test_only_get_retries_transient_failures(self):
        error = so.urllib.error.HTTPError("https://api.github.com/test", 500, "internal", {}, None)
        waits = []
        api = so.GitHub("prueba/repo", "doble", sleep=waits.append)
        with patch.object(so.urllib.request, "urlopen", side_effect=[error, error, io.BytesIO(b'{"ok":true}')]) as request:
            self.assertEqual(api.request("pages"), {"ok": True})
        self.assertEqual(request.call_count, 3)
        self.assertEqual(waits, [1, 2])
        with patch.object(so.urllib.request, "urlopen", side_effect=error) as request:
            with self.assertRaises(so.OnlineError):
                api.request("releases", {"draft": True})
        self.assertEqual(request.call_count, 1)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.path = self.root / "datos/manifiesto.json"
        self.path.parent.mkdir()
        self.path.write_text('{"version":1}')
        (self.root / "index.html").write_text("<!doctype html><title>Prueba</title>")
        self.run_git("init", "-q")
        self.run_git("add", ".")
        self.run_git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        head = self.run_git("rev-parse", "HEAD")
        self.api = FakeGitHub(head)
        self.env = {"GITHUB_REPOSITORY": "yodesarrollomx/sala-edicion", "GITHUB_RUN_ID": "12",
                    "GITHUB_RUN_ATTEMPT": "1", "GH_TOKEN": "doble",
                    "RUNNER_TEMP": str(Path(self.tmp.name) / "state")}
        self.s = so.Snapshots(self.root, self.env, api=self.api)
        self.s.bootstrap("relevo", lock=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True,
                              capture_output=True, check=True).stdout.strip()

    def prepare(self):
        self.path.write_text('{"version":2}')
        out = self.s.prepare("relevo")
        return out, self.api.releases[out["snapshot_id"]]

    def next_run(self, process="relevo"):
        self.s.release()
        self.run_git("reset", "--hard", "HEAD")
        self.env["GITHUB_RUN_ID"] = str(int(self.env["GITHUB_RUN_ID"]) + 1)
        self.s = so.Snapshots(self.root, self.env, api=self.api)
        self.s.bootstrap(process, lock=True)

    def mark_published(self, rid):
        body = json.loads(self.api.releases[rid]["body"])
        body["state"] = "published"
        self.api.releases[rid]["body"] = json.dumps(body)

    def test_snapshot_reentry_reuses_release_and_asset(self):
        first, _ = self.prepare()
        second = self.s.prepare("relevo")
        self.assertEqual(first, second)
        self.assertEqual(len(self.api.releases), 1)
        self.assertEqual(len(self.api.assets), 1)

    def test_delta_keeps_parent_media_without_uploading_it_again(self):
        self.env["SALA_SNAPSHOT_INCREMENTAL"] = "1"
        parent, _ = self.prepare()
        self.mark_published(parent["snapshot_id"])
        self.next_run("mesa")
        tira = self.root / "datos/tiras/prueba.json"
        tira.parent.mkdir()
        tira.write_text('{"version":3}')
        child = self.s.prepare("mesa")
        release = self.api.releases[child["snapshot_id"]]
        body = json.loads(release["body"])
        manifest, patch_files = so.decode_archive(self.api.assets[body["asset_id"]],
                                                self.s.repo, self.s.prefixes)
        self.assertEqual(set(patch_files), {"datos/tiras/prueba.json"})
        self.assertEqual(manifest["base_snapshot_id"], parent["snapshot_id"])
        resolved, files = self.s.download(release, body)
        self.assertEqual(files["datos/manifiesto.json"], b'{"version":2}')
        self.assertEqual(files["datos/tiras/prueba.json"], b'{"version":3}')
        self.assertEqual(resolved["data_sha"], child["data_sha"])

    def test_incremental_flag_is_off_by_default_and_full_checkpoint_reads_delta(self):
        parent, _ = self.prepare()
        body = json.loads(self.api.releases[parent["snapshot_id"]]["body"])
        manifest, _ = self.s.archive(self.api.releases[parent["snapshot_id"]], body)
        self.assertNotIn("base_snapshot_id", manifest)
        self.mark_published(parent["snapshot_id"])
        self.env["SALA_SNAPSHOT_INCREMENTAL"] = "1"
        self.next_run("mesa")
        tira = self.root / "datos/tiras/prueba.json"
        tira.parent.mkdir()
        tira.write_text('{"version":3}')
        child = self.s.prepare("mesa")
        self.mark_published(child["snapshot_id"])
        self.env.pop("SALA_SNAPSHOT_INCREMENTAL")
        self.next_run()
        self.path.write_text('{"version":4}')
        full = self.s.prepare("relevo")
        release = self.api.releases[full["snapshot_id"]]
        manifest, files = self.s.archive(release, json.loads(release["body"]))
        self.assertNotIn("base_snapshot_id", manifest)
        self.assertEqual(set(files), {"datos/manifiesto.json", "datos/tiras/prueba.json"})

    def test_snapshot_published_state_is_not_downgraded_on_reentry(self):
        out, _ = self.prepare()
        self.mark_published(out["snapshot_id"])
        self.s.prepare("relevo")
        self.assertEqual(json.loads(self.api.releases[out["snapshot_id"]]["body"])["state"], "published")

    def test_chain_bound_fails_without_applying_partial_files(self):
        self.env["SALA_SNAPSHOT_INCREMENTAL"] = "1"
        parent, _ = self.prepare()
        self.mark_published(parent["snapshot_id"])
        self.next_run()
        self.path.write_text('{"version":3}')
        child = self.s.prepare("relevo")
        release = self.api.releases[child["snapshot_id"]]
        with patch.object(so, "MAX_CHAIN", 1), self.assertRaises(so.OnlineError):
            self.s.download(release, json.loads(release["body"]))
        self.assertEqual(self.path.read_text(), '{"version":3}')

    def test_replay_preserves_deletion_then_restoration(self):
        self.env["SALA_SNAPSHOT_INCREMENTAL"] = "1"
        first, _ = self.prepare()
        self.mark_published(first["snapshot_id"])
        self.next_run()
        self.path.unlink()
        deleted = self.s.prepare("relevo")
        self.mark_published(deleted["snapshot_id"])
        self.next_run()
        self.assertFalse(self.path.exists())
        self.path.write_text('{"version":4}')
        restored = self.s.prepare("relevo")
        release = self.api.releases[restored["snapshot_id"]]
        manifest, files = self.s.download(release, json.loads(release["body"]))
        self.assertEqual(files["datos/manifiesto.json"], b'{"version":4}')
        self.assertNotIn("datos/manifiesto.json", manifest["deleted"])

    def test_delta_rejects_wrong_parent_hash_and_order(self):
        self.env["SALA_SNAPSHOT_INCREMENTAL"] = "1"
        parent, _ = self.prepare()
        self.mark_published(parent["snapshot_id"])
        self.next_run()
        self.path.write_text('{"version":3}')
        child = self.s.prepare("relevo")
        rid = child["snapshot_id"]
        for base_id, base_data in ((parent["snapshot_id"], "0" * 64),
                                    (rid, child["data_sha"])):
            raw, manifest = so.encode_archive(self.s.repo, self.s.head(),
                {"datos/manifiesto.json": b'{"version":3}'}, [], self.s.prefixes,
                base_id=base_id, base_data=base_data)
            body = json.loads(self.api.releases[rid]["body"])
            body.update({"archive_sha256": so.digest(raw), "data_sha": manifest["data_sha"],
                         "parent_id": base_id})
            self.api.assets[body["asset_id"]] = raw
            self.api.releases[rid]["body"] = json.dumps(body)
            with self.assertRaises(so.OnlineError):
                self.s.download(self.api.releases[rid], body)

    def test_site_budget_blocks_before_upload_and_preserves_bundle(self):
        bundle = Path(self.tmp.name) / "existing-site"
        bundle.mkdir()
        (bundle / "keep.txt").write_text("conservar")
        self.path.write_text('{"version":2}')
        with patch.object(so, "MAX_SITE", 1):
            with self.assertRaises(so.OnlineError):
                self.s.prepare("relevo")
            with self.assertRaises(so.OnlineError):
                self.s.build_site(bundle)
        self.assertEqual(self.api.releases, {})
        self.assertEqual((bundle / "keep.txt").read_text(), "conservar")

    def test_same_attempt_recovers_existing_lease(self):
        lease = self.s.state()["lease"]
        self.s.state_file.unlink()
        self.assertEqual(self.s.acquire("relevo"), lease)

    def test_new_run_attempt_can_replace_previous_attempt_lease(self):
        old_lease = self.s.state()["lease"]
        env = {**self.env, "GITHUB_RUN_ATTEMPT": "2"}
        new = so.Snapshots(self.root, env, api=self.api)
        request = self.api.request
        def observed(path, *args, **kwargs):
            if path.startswith("actions/runs/"):
                return {"status": "in_progress", "run_attempt": 2}
            return request(path, *args, **kwargs)
        with patch.object(self.api, "request", side_effect=observed):
            new.bootstrap("relevo", lock=True)
        self.assertNotEqual(new.state()["lease"], old_lease)
        with self.assertRaises(so.OnlineError):
            self.s.assert_lease()

    def test_lost_write_response_is_reconciled_without_duplicate(self):
        self.path.write_text('{"version":2}')
        request, upload = self.api.request, self.api.upload
        lost = {"releases", "upload", "patch"}
        def ambiguous(path, body=None, method=None):
            result = request(path, body, method)
            kind = "releases" if path == "releases" else "patch" if method == "PATCH" and path.startswith("releases/") else ""
            if kind in lost:
                lost.remove(kind)
                raise so.OnlineError("GitHub HTTP 500")
            return result
        def ambiguous_upload(release, raw):
            result = upload(release, raw)
            if "upload" in lost:
                lost.remove("upload")
                raise so.OnlineError("Subida del snapshot no confirmada")
            return result
        with patch.object(self.api, "request", side_effect=ambiguous), patch.object(self.api, "upload", side_effect=ambiguous_upload):
            result = self.s.prepare("relevo")
        self.assertEqual(len(self.api.releases), 1)
        self.assertEqual(len(self.api.assets), 1)
        self.assertEqual(json.loads(self.api.releases[result["snapshot_id"]]["body"])["state"], "prepared")

    def test_lost_lock_cas_response_is_reconciled(self):
        self.s.release()
        request = self.api.request
        def ambiguous(path, body=None, method=None):
            result = request(path, body, method)
            if path == "git/refs/" + so.LOCK_REF and method == "PATCH":
                raise so.OnlineError("GitHub HTTP 500")
            return result
        with patch.object(self.api, "request", side_effect=ambiguous):
            lease = self.s.acquire("relevo")
            self.assertEqual(lease, self.api.lock)
            self.s.release()
        self.assertNotIn("lease", self.s.state())

    def test_published_dispatch_is_recovered_without_sending_again(self):
        out, _ = self.prepare()
        body = json.loads(self.api.releases[out["snapshot_id"]]["body"])
        body.update({"state": "published", "published_code_sha": self.s.head(), "published_run": "99"})
        self.api.releases[out["snapshot_id"]]["body"] = json.dumps(body)
        run = {"id": 99, "display_title": f"Sala · publicacion=datos-12-1-relevo · sha={self.s.head()}",
               "head_sha": self.s.head(), "head_branch": "main", "status": "completed", "conclusion": "success"}
        request = self.api.request
        def observed(path, body=None, method=None):
            if "/runs?" in path:
                return {"workflow_runs": [run]}
            if path.endswith("/dispatches"):
                raise AssertionError("No volver a disparar una publicación identificada")
            return request(path, body, method)
        with patch.object(self.api, "request", side_effect=observed), patch.object(self.s, "verify_receipt") as verify:
            result = self.s.dispatch_publish(self.s.head())
            self.assertEqual(result["pages_run"], 99)
            verify.assert_called_once_with(self.s.head(), out["data_sha"], out["snapshot_id"], "99")
            run["conclusion"] = "failure"
            self.assertEqual(self.s.dispatch_publish(self.s.head())["publicado"], "si")
            run["id"] = 100
            with self.assertRaises(so.OnlineError):
                self.s.dispatch_publish(self.s.head())

    def test_duplicate_dispatches_never_report_publication(self):
        self.prepare()
        run = {"id": 99, "display_title": f"Sala · publicacion=datos-12-1-relevo · sha={self.s.head()}",
               "head_sha": self.s.head(), "head_branch": "main", "status": "completed", "conclusion": "success"}
        request = self.api.request
        def observed(path, body=None, method=None):
            if "/runs?" in path:
                return {"workflow_runs": [run, {**run, "id": 100}]}
            return request(path, body, method)
        with patch.object(self.api, "request", side_effect=observed), self.assertRaises(so.OnlineError):
            self.s.dispatch_publish(self.s.head())

    def test_lost_dispatch_response_waits_for_delayed_index_without_second_post(self):
        out, _ = self.prepare()
        lease = self.s.state()["lease"]
        run = {"id": 99, "display_title": f"Sala · publicacion=datos-12-1-relevo · sha={self.s.head()}",
               "head_sha": self.s.head(), "head_branch": "main", "status": "completed", "conclusion": "success"}
        request = self.api.request
        dispatches, pending_reads, elapsed = [], [], [0]
        def observed(path, body=None, method=None):
            if path.endswith("/dispatches"):
                dispatches.append(body)
                raise so.OnlineError("GitHub HTTP 500")
            if "/runs?" in path:
                if not dispatches:
                    return {"workflow_runs": []}
                pending_reads.append(path)
                self.assertEqual(self.api.lock, lease)
                if len(pending_reads) <= 2:
                    return {"workflow_runs": []}
                self.mark_published(out["snapshot_id"])
                return {"workflow_runs": [run]}
            return request(path, body, method)
        def advance(seconds):
            elapsed[0] += seconds
        with patch.object(self.api, "request", side_effect=observed), \
                patch.object(self.s, "clock", side_effect=lambda: elapsed[0]), \
                patch.object(self.s, "sleep", side_effect=advance), \
                patch.object(self.s, "verify_receipt") as verify:
            result = self.s.dispatch_publish(self.s.head(), timeout=60)
        self.assertEqual(result["pages_run"], 99)
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(len(pending_reads), 3)
        self.assertEqual(elapsed[0], 20)
        self.assertEqual(self.s.state()["lease"], lease)
        verify.assert_called_once_with(self.s.head(), out["data_sha"], out["snapshot_id"], "99")

    def test_no_change_is_not_a_new_snapshot(self):
        result = self.s.prepare("relevo")
        self.assertEqual(result["hubo"], "no")
        self.assertEqual(self.api.releases, {})

    def test_prepare_is_private_and_not_published(self):
        out, release = self.prepare()
        self.assertTrue(release["draft"])
        self.assertEqual(json.loads(release["body"])["state"], "prepared")
        self.assertFalse(self.s.file_is_published(self.path))
        self.assertEqual(self.s.latest(), (None, None))

    def test_other_process_output_rejected(self):
        (self.root / "datos/maquinas.json").write_text("{}")
        with self.assertRaises(so.OnlineError):
            self.s.prepare("relevo")

    def test_code_change_needs_pr(self):
        self.path.write_text('{"version":2}')
        (self.root / "index.html").write_text("alterado")
        with self.assertRaises(so.OnlineError):
            self.s.prepare("relevo")

    def test_main_move_rejected(self):
        self.path.write_text('{"version":2}')
        self.api.main = "b" * 40
        with self.assertRaises(so.OnlineError):
            self.s.prepare("relevo")

    def test_lease_fences_old_writer(self):
        self.path.write_text('{"version":2}')
        self.api.lock = "e" * 40
        self.api.commits[self.api.lock] = {"message": json.dumps({
            "schema": 1, "state": "held", "run_id": "13", "expires": int(time.time()) + 100})}
        with self.assertRaises(so.OnlineError):
            self.s.prepare("relevo")
        with self.assertRaises(so.OnlineError):
            self.s.release()

    def test_stage_rejects_wrong_code_or_parent(self):
        out, release = self.prepare()
        with self.assertRaises(so.OnlineError):
            self.s.stage("b" * 40, out["snapshot_id"], self.s.state()["lease"])
        body = json.loads(release["body"])
        body["parent_id"] = 999
        self.api.releases[release["id"]]["body"] = json.dumps(body)
        with self.assertRaises(so.OnlineError):
            self.s.stage(self.s.head(), out["snapshot_id"], self.s.state()["lease"])
        self.assertFalse((self.root / "version-online.json").exists())

    def test_stage_and_receipt_confirm_exact_file(self):
        out, release = self.prepare()
        self.s.stage(self.s.head(), out["snapshot_id"], self.s.state()["lease"])
        with patch.object(self.s, "verify_receipt", return_value={"ok": True}):
            self.s.confirm()
        self.assertEqual(json.loads(self.api.releases[release["id"]]["body"])["state"], "published")
        self.assertTrue(self.s.file_is_published(self.path))
        self.path.write_text('{"version":3}')
        self.assertFalse(self.s.file_is_published(self.path))

    def test_staging_alone_never_counts_as_a_published_receipt(self):
        self.s.stage(self.s.head())
        self.assertFalse(self.s.file_is_published(self.path))
        with patch.object(self.s, "verify_receipt", return_value={"ok": True}):
            self.s.confirm()
        self.assertTrue(self.s.file_is_published(self.path))

    def test_plan_drift_after_stage_blocks_bundle_and_confirmation_before_network(self):
        plan = self.root / "datos/plan-agregados.json"
        plan.write_bytes(b'{"synthetic":1}\n')
        self.s.stage(self.s.head())
        plan.write_bytes(b'{"synthetic":2}\n')
        bundle = Path(self.tmp.name) / "site"
        with patch.object(self.api, "request") as request:
            with self.assertRaisesRegex(so.OnlineError, "campo=plan_sha256"):
                self.s.build_site(bundle)
            with self.assertRaisesRegex(so.OnlineError, "campo=plan_sha256"):
                self.s.confirm()
        request.assert_not_called()
        self.assertFalse(bundle.exists())
        self.assertNotIn("published_receipt", self.s.state())

    def test_bundle_preserves_staged_plan_hash_exactly(self):
        plan = self.root / "datos/plan-agregados.json"
        plan.write_bytes(b'{"synthetic":1}\n')
        self.s.stage(self.s.head())
        staged = self.s.state()["staged_receipt"]
        bundle = Path(self.tmp.name) / "site"
        self.s.build_site(bundle)
        self.assertEqual(so.digest((bundle / "datos/plan-agregados.json").read_bytes()),
                         staged["plan_sha256"])
        self.assertEqual(json.loads((bundle / "version-online.json").read_bytes()), staged)

    def test_stale_receipt_retries_with_fresh_url_and_safe_field_diagnostic(self):
        plan = self.root / "datos/plan-agregados.json"
        plan.write_bytes(b'{"synthetic":1}\n')
        self.s.stage(self.s.head())
        expected = self.s.state()["staged_receipt"]
        stale = {**expected, "plan_sha256": "PRIVATE_REMOTE_VALUE"}
        urls, elapsed, output = [], [0], io.StringIO()
        replies = [stale, expected]
        def opened(req, **kwargs):
            urls.append(req.full_url)
            return io.BytesIO(so.canonical(replies.pop(0)))
        def advance(seconds):
            elapsed[0] += seconds
        with patch.object(self.api, "request", return_value={"html_url": "https://example.invalid/sala/"}), \
                patch.object(so.urllib.request, "urlopen", side_effect=opened), \
                patch.object(so.time, "time_ns", side_effect=[1, 2]), \
                patch.object(self.s, "clock", side_effect=lambda: elapsed[0]), \
                patch.object(self.s, "sleep", side_effect=advance), patch("sys.stdout", output):
            receipt = self.s.verify_receipt(self.s.head(), expected["data_sha"], 0, self.s.run, timeout=10)
        self.assertEqual(receipt, expected)
        self.assertNotEqual(urls[0], urls[1])
        self.assertTrue(all("run=12" in url for url in urls))
        self.assertIn("campos=plan_sha256", output.getvalue())
        self.assertNotIn("PRIVATE_REMOTE_VALUE", output.getvalue())

    def test_receipt_timeout_reports_http_json_or_transport_without_remote_details(self):
        self.s.stage(self.s.head())
        expected = self.s.state()["staged_receipt"]
        variants = [(so.urllib.error.HTTPError("https://private.invalid/secret", 503,
                                              "PRIVATE_REMOTE_VALUE", {}, None), "http=503"),
                    (OSError("PRIVATE_REMOTE_VALUE"), "transporte"),
                    (b"PRIVATE_REMOTE_VALUE", "json_invalido")]
        for reply, diagnostic in variants:
            elapsed, output = [0], io.StringIO()
            def opened(req, **kwargs):
                if isinstance(reply, Exception):
                    raise reply
                return io.BytesIO(reply)
            def advance(seconds):
                elapsed[0] += seconds
            with self.subTest(diagnostic=diagnostic), \
                    patch.object(self.api, "request", return_value={"html_url": "https://example.invalid/sala/"}), \
                    patch.object(so.urllib.request, "urlopen", side_effect=opened), \
                    patch.object(self.s, "clock", side_effect=lambda: elapsed[0]), \
                    patch.object(self.s, "sleep", side_effect=advance), patch("sys.stdout", output):
                with self.assertRaises(so.OnlineError) as caught:
                    self.s.verify_receipt(self.s.head(), expected["data_sha"], 0, self.s.run, timeout=1)
            self.assertIn(diagnostic, str(caught.exception))
            combined = output.getvalue() + str(caught.exception)
            self.assertNotIn("PRIVATE_REMOTE_VALUE", combined)
            self.assertNotIn("private.invalid", combined)

    def test_confirm_failure_never_marks_published(self):
        out, release = self.prepare()
        self.s.stage(self.s.head(), out["snapshot_id"], self.s.state()["lease"])
        with patch.object(self.s, "verify_receipt", side_effect=so.OnlineError("sin recibo")):
            with self.assertRaises(so.OnlineError):
                self.s.confirm()
        self.assertEqual(json.loads(self.api.releases[release["id"]]["body"])["state"], "prepared")

    def test_bundle_excludes_private_runtime_outputs(self):
        (self.root / "mesa.log").write_text("contenido privado")
        (self.root / "secreto.json").write_text("credencial")
        self.s.stage(self.s.head())
        bundle = Path(self.tmp.name) / "site"
        self.s.build_site(bundle)
        self.assertTrue((bundle / "index.html").exists())
        self.assertTrue((bundle / "version-online.json").exists())
        self.assertFalse((bundle / "mesa.log").exists())
        self.assertFalse((bundle / "secreto.json").exists())

    def test_untagged_draft_is_identified_by_kind_and_hash(self):
        out, release = self.prepare()
        self.api.releases[release["id"]]["tag_name"] = "untagged-github-generated"
        observed = self.api.request("releases/" + str(release["id"]))
        self.s.validate_release(observed, json.loads(observed["body"]))

    def test_unrelated_draft_does_not_become_a_snapshot(self):
        self.api.releases[999] = {"id": 999, "draft": True, "tag_name": "untagged-human",
                                  "body": "Notas privadas de otra publicación"}
        self.assertEqual(self.s.latest(), (None, None))

    def test_expired_lease_can_recover_without_old_run(self):
        before = self.s.state()["lease"]
        info = json.loads(self.api.commits[before]["message"])
        info["expires"] = 0
        self.api.commits[before]["message"] = json.dumps(info)
        original = self.api.request
        def guarded(path, *args, **kwargs):
            if path.startswith("actions/runs/"):
                raise AssertionError("No consultar un run desaparecido para un mutex caducado")
            return original(path, *args, **kwargs)
        with patch.object(self.api, "request", side_effect=guarded):
            self.s.acquire("relevo")
        self.assertNotEqual(self.s.state()["lease"], before)

    def test_release_preserves_history(self):
        before = self.s.state()["lease"]
        self.s.release()
        self.assertEqual(json.loads(self.api.commits[self.api.lock]["message"])["state"], "released")
        self.assertIn(before, self.api.commits[self.api.lock]["parents"])


if __name__ == "__main__":
    unittest.main()
