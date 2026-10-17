"""Public-media integration: synthetic Git, releases and HTTP; never production."""
import copy
import io
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import snapshots_online_test as legacy
import medios_publicos_test as public
import snapshots_online as so
import medios_publicos as mp


class GitHub(legacy.FakeGitHub):
    def __init__(self, head):
        super().__init__(head)
        self.repo = mp.REPO
        self.media = public.FakeGitHub()
        self.media.number = 10000

    def request(self, path, body=None, method=None):
        if path == "/repos/" + self.repo:
            return self.media.request(path, body, method)
        if path.startswith("releases?"):
            page = int(path.rsplit("=", 1)[1])
            all_releases = [*self.releases.values(), *self.media.releases.values()]
            return copy.deepcopy(all_releases[(page - 1) * 100:page * 100])
        if path == "releases" and body and json.loads(body.get("body", "{}") or "{}").get("kind") == mp.KIND:
            return self.media.request(path, body, method)
        if path.startswith("releases/") and int(path.split("/")[1]) in self.media.releases:
            return self.media.request(path, body, method)
        return super().request(path, body, method)

    def upload(self, release, raw, **kwargs):
        if kwargs:
            return self.media.upload(release, raw, **kwargs)
        return super().upload(release, raw)


class MediaSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "datos").mkdir()
        (self.root / "datos/manifiesto.json").write_text("{}")
        (self.root / "index.html").write_text('<!doctype html><meta name="sala-medios-publicos" content="1"><script src="medios-publicos.js?v=1"></script>')
        (self.root / "medios-publicos.js").write_text("// synthetic approved reader\n")
        old = self.root / "laminas/history/L1.png"
        old.parent.mkdir(parents=True)
        old.write_bytes(public.PNG)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        self.api = GitHub(self.git("rev-parse", "HEAD"))
        self.env = {"GITHUB_REPOSITORY": mp.REPO, "GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "1",
                    "GH_TOKEN": "synthetic", "RUNNER_TEMP": str(Path(self.temp.name) / "state")}
        self.new_snapshot()
        self.s.bootstrap("mesa", lock=True)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def new_snapshot(self):
        self.s = so.Snapshots(self.root, self.env, api=self.api)
        self.s.anonymous_media = self.api.media.fetch
        self.s.assert_media_reader_published = lambda: None

    def new_images(self):
        folder = self.root / "laminas/new"
        folder.mkdir()
        (folder / "L1.png").write_bytes(public.PNG)
        (folder / "L1.jpg").write_bytes(public.JPEG)
        tira = self.root / "datos/tiras/new.json"
        tira.parent.mkdir()
        tira.write_text(json.dumps({"laminas": [{"src": "laminas/new/L1.jpg", "original": "laminas/new/L1.png"}]}))

    def prepare(self, enabled=True):
        if enabled:
            self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        return self.s.prepare("mesa")

    def publish(self, output):
        lease = self.s.state()["lease"]
        self.s.stage(self.s.head(), output["snapshot_id"], lease)
        with patch.object(self.s, "verify_receipt", return_value=self.s.state()["staged_receipt"]):
            self.s.confirm()

    def archive(self, output):
        release = self.api.releases[output["snapshot_id"]]
        body = json.loads(release["body"])
        return self.s.download(release, body)

    def test_json_receipts_stay_in_snapshot_and_only_images_are_externalized(self):
        folder = self.root / "laminas/recibos-hidream"
        folder.mkdir(parents=True)
        receipt = folder / "synthetic.json"
        raw = b'{"modelo":"synthetic","foto_sha256":"synthetic"}'
        receipt.write_bytes(raw)
        output = self.prepare()
        _, files = self.archive(output)
        self.assertEqual(files["laminas/recibos-hidream/synthetic.json"], raw)
        manifest = mp.validate_manifest(files[so.MEDIA_PATH], mp.REPO)
        self.assertEqual(set(manifest["entries"]), {"laminas/new/L1.png", "laminas/new/L1.jpg"})
        self.assertNotIn("laminas/recibos-hidream/synthetic.json", manifest["entries"])

    def test_default_off_keeps_legacy_full_bytes_and_has_no_media_api_effect(self):
        output = self.prepare(enabled=False)
        _, files = self.archive(output)
        self.assertEqual(files["laminas/new/L1.png"], public.PNG)
        self.assertNotIn(so.MEDIA_PATH, files)
        self.assertEqual(self.api.media.calls, [])

    def test_external_full_omits_only_new_images_but_preserves_workers_and_old_urls(self):
        output = self.prepare()
        _, files = self.archive(output)
        self.assertIn(so.MEDIA_PATH, files)
        self.assertNotIn("laminas/new/L1.png", files)
        self.assertNotIn("laminas/new/L1.jpg", files)
        manifest = mp.validate_manifest(files[so.MEDIA_PATH], mp.REPO)
        self.assertEqual(set(manifest["entries"]), {"laminas/new/L1.png", "laminas/new/L1.jpg"})
        self.assertNotIn("laminas/history/L1.png", manifest["entries"])
        self.publish(output)
        bundle = Path(self.temp.name) / "site"
        self.s.build_site(bundle)
        self.assertEqual((bundle / "laminas/history/L1.png").read_bytes(), public.PNG)
        self.assertFalse((bundle / "laminas/new/L1.png").exists())
        self.assertEqual((self.root / "laminas/new/L1.png").read_bytes(), public.PNG)
        receipt = json.loads((bundle / "version-online.json").read_bytes())
        self.assertEqual(receipt["media_manifest_sha256"], so.digest(files[so.MEDIA_PATH]))
        self.assertTrue(self.s.file_is_published(self.root / "laminas/new/L1.jpg"))
        self.assertTrue(self.s.file_is_published(self.root / "datos/tiras/new.json"))

    def test_new_reader_hydrates_full_then_flag_off_never_reembeds_external_bytes(self):
        output = self.prepare()
        self.publish(output)
        self.s.release()
        for rel in (so.MEDIA_PATH, "laminas/new/L1.png", "laminas/new/L1.jpg", "datos/tiras/new.json"):
            (self.root / rel).unlink()
        self.env.pop("SALA_MEDIOS_PUBLICOS")
        self.env["GITHUB_RUN_ID"] = "13"
        self.new_snapshot()
        self.s.bootstrap("relevo", lock=True)
        self.assertEqual((self.root / "laminas/new/L1.png").read_bytes(), public.PNG)
        (self.root / "datos/manifiesto.json").write_text('{"synthetic":1}')
        updated = self.s.prepare("relevo")
        _, files = self.archive(updated)
        self.assertIn(so.MEDIA_PATH, files)
        self.assertNotIn("laminas/new/L1.png", files)
        self.assertNotIn("laminas/new/L1.jpg", files)
        self.assertEqual(self.api.media.writes("releases"), 1)

    def test_reentry_does_not_repeat_media_writes_or_change_manifest(self):
        first = self.prepare()
        raw = (self.root / so.MEDIA_PATH).read_bytes()
        second = self.s.prepare("mesa")
        self.assertEqual(first, second)
        self.assertEqual(raw, (self.root / so.MEDIA_PATH).read_bytes())
        self.assertEqual(self.api.media.writes("releases"), 1)
        self.assertEqual(self.api.media.writes("upload"), 2)
        self.assertTrue(self.s.state()["media_journal"]["operations"])

    def test_manipulated_manifest_or_bytes_never_credit_publication(self):
        output = self.prepare()
        self.publish(output)
        target = self.root / "laminas/new/L1.png"
        target.write_bytes(b"not the declared public bytes")
        with self.assertRaises(so.OnlineError):
            self.s.file_is_published(target)
        target.write_bytes(public.PNG)
        path = self.root / so.MEDIA_PATH
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(so.OnlineError, "media_manifest_sha256"):
            self.s.file_is_published(target)

    def test_old_reader_fails_closed_and_immutable_release_is_required(self):
        output = self.prepare()
        release = self.api.releases[output["snapshot_id"]]
        body = json.loads(release["body"])
        old_prefixes = tuple(p for p in self.s.prefixes if p != so.MEDIA_PATH)
        with self.assertRaises(so.OnlineError):
            so.decode_archive(self.api.assets[body["asset_id"]], mp.REPO, old_prefixes)
        media_release = next(iter(self.api.media.releases.values()))
        media_release["immutable"] = False
        self.s._verified_media = None
        with self.assertRaises(so.OnlineError):
            self.s.stage(self.s.head(), output["snapshot_id"], self.s.state()["lease"])
        self.assertNotIn("published_receipt", self.s.state())

    def test_historical_paths_are_never_uploaded(self):
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        (self.root / "laminas/history/L1.png").write_bytes(public.PNG + b"changed")
        output = self.s.prepare("mesa")
        _, files = self.archive(output)
        self.assertIn("laminas/history/L1.png", files)
        self.assertNotIn(so.MEDIA_PATH, files)
        self.assertEqual(self.api.media.calls, [])

    def test_marker_without_approved_reader_never_creates_public_assets(self):
        self.s.release()
        self.git("rm", "medios-publicos.js")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "no reader")
        self.api.main = self.git("rev-parse", "HEAD")
        self.env["GITHUB_RUN_ID"] = "13"
        self.new_snapshot()
        self.s.bootstrap("mesa", lock=True)
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        with self.assertRaisesRegex(so.OnlineError, "lector"):
            self.s.prepare("mesa")
        self.assertEqual(self.api.media.calls, [])

    def large_new_image(self):
        from PIL import Image
        raw = io.BytesIO()
        Image.frombytes("RGB", (512, 512), random.Random(7).randbytes(512 * 512 * 3)).save(raw, "PNG")
        path = "laminas/new/large.png"
        (self.root / path).write_bytes(raw.getvalue())
        return path, raw.getvalue()

    def test_external_bytes_stop_bundle_and_snapshot_growth_under_existing_budgets(self):
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        logical, raw = self.large_new_image()
        with patch.object(so, "MAX_SITE", 65536), patch.object(so, "MAX_ZIP", 65536):
            with self.assertRaisesRegex(so.OnlineError, "presupuesto"):
                self.s.site_files()
            with self.assertRaises(so.OnlineError):
                so.encode_archive(mp.REPO, self.s.head(), {logical: raw}, [], self.s.prefixes)
            output = self.s.prepare("mesa")
            _, files = self.archive(output)
            self.assertNotIn(logical, files)
            self.assertLess(sum(path.stat().st_size for path in self.s.site_files().values()), 65536)
            self.assertEqual((self.root / logical).read_bytes(), raw)

    def test_unacknowledged_dirty_manifest_is_not_a_bootstrap_baseline(self):
        self.prepare()
        self.s.release()
        self.env["GITHUB_RUN_ID"] = "13"
        self.new_snapshot()
        with self.assertRaisesRegex(so.OnlineError, "no procede"):
            self.s.bootstrap("mesa", lock=True)

    def test_receipt_requires_exact_manifest_pin(self):
        output = self.prepare()
        self.s.stage(self.s.head(), output["snapshot_id"], self.s.state()["lease"])
        expected = self.s.state()["staged_receipt"]
        wrong = {**expected, "media_manifest_sha256": "0" * 64}
        elapsed = [0]
        def advance(seconds):
            elapsed[0] += seconds
        with patch.object(self.api, "request", return_value={"html_url": "https://example.invalid/sala/"}), \
                patch.object(so.urllib.request, "urlopen", return_value=io.BytesIO(so.canonical(wrong))), \
                patch.object(self.s, "clock", side_effect=lambda: elapsed[0]), \
                patch.object(self.s, "sleep", side_effect=advance):
            with self.assertRaisesRegex(so.OnlineError, "campos=media_manifest_sha256"):
                self.s.verify_receipt(self.s.head(), expected["data_sha"], output["snapshot_id"], self.s.run, timeout=1)

    def test_legacy_receipt_cannot_claim_an_unavailable_manifest(self):
        expected = {"code_sha": self.s.head(), "data_sha": "a" * 64,
                    "snapshot_id": 0, "run_id": self.s.run}
        receipt = {"schema": 1, **expected, "media_manifest_sha256": "b" * 64}
        self.assertEqual(so.receipt_differences(receipt, **expected), ["media_manifest_sha256"])

    def reader_proof(self):
        self.s.assert_media_reader_published = so.Snapshots.assert_media_reader_published.__get__(self.s)
        receipt = {"schema": 1, "code_sha": self.s.head(), "run_id": "41"}
        run = {"id": 41, "repository": {"full_name": mp.REPO}, "head_sha": self.s.head(),
               "head_branch": "main", "path": ".github/workflows/publicar.yml",
               "event": "push", "status": "completed", "conclusion": "success"}
        original = self.api.request
        def request(path, body=None, method=None):
            if path == "pages":
                return {"html_url": "https://example.invalid/sala/"}
            if path == "actions/runs/41":
                return copy.deepcopy(run)
            return original(path, body, method)
        return receipt, run, request

    def test_emitter_requires_completed_reader_deploy_proved_independently(self):
        receipt, run, request = self.reader_proof()
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        requests = []
        def opened(req, **kwargs):
            requests.append(req)
            return io.BytesIO(so.canonical(receipt))
        with patch.object(self.api, "request", side_effect=request), \
                patch.object(so.urllib.request, "urlopen", side_effect=opened):
            output = self.s.prepare("mesa")
        self.assertGreater(output["snapshot_id"], 0)
        self.assertEqual(len(requests), 1)
        self.assertIn("check=", requests[0].full_url)
        self.assertIsNone(requests[0].get_header("Authorization"))

    def test_incompatible_or_unfinished_reader_proof_has_zero_remote_effects(self):
        receipt, run, request = self.reader_proof()
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        variants = [(receipt, "code_sha", "a" * 40), (receipt, "run_id", "invalid"),
                    (receipt, "schema", True), (run, "head_sha", "a" * 40),
                    (run, "repository", {"full_name": "other/repo"}),
                    (run, "path", ".github/workflows/other.yml"),
                    (run, "head_branch", "feature"), (run, "event", "pull_request"),
                    (run, "status", "in_progress"), (run, "conclusion", "failure")]
        for target, key, value in variants:
            previous = copy.deepcopy(target[key])
            target[key] = value
            with self.subTest(field=key), patch.object(self.api, "request", side_effect=request), \
                    patch.object(so.urllib.request, "urlopen", side_effect=lambda *a, **kw: io.BytesIO(so.canonical(receipt))), \
                    self.assertRaises(so.OnlineError):
                self.s.prepare("mesa")
            target[key] = previous
            self.assertEqual(self.api.media.calls, [])
        for response in (b"PRIVATE", b"x" * 32769, OSError("PRIVATE")):
            def opened(*args, **kwargs):
                if isinstance(response, Exception):
                    raise response
                return io.BytesIO(response)
            with self.subTest(response_type=type(response).__name__), \
                    patch.object(self.api, "request", side_effect=request), \
                    patch.object(so.urllib.request, "urlopen", side_effect=opened), \
                    self.assertRaises(so.OnlineError) as caught:
                self.s.prepare("mesa")
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertEqual(self.api.media.calls, [])

    def test_real_image_decoder_rejects_renamed_private_payload_before_remote_effects(self):
        self.env["SALA_MEDIOS_PUBLICOS"] = "1"
        self.new_images()
        (self.root / "laminas/new/L1.png").write_bytes(b"\x89PNG\r\n\x1a\nPRIVATE")
        with self.assertRaises(so.OnlineError):
            self.s.prepare("mesa")
        self.assertEqual(self.api.media.writes("releases"), 0)
        self.assertFalse((self.root / so.MEDIA_PATH).exists())


class AnonymousDownload(unittest.TestCase):
    def test_redirect_is_anonymous_bounded_and_rejects_other_hosts(self):
        snapshot = object.__new__(so.Snapshots)
        snapshot.repo = mp.REPO
        stable = f"https://github.com/{mp.REPO}/releases/download/sala-media-" + "b" * 64 + "-mesa/" + "a" * 64 + ".png"
        requests = []
        def opened(request, **kwargs):
            requests.append(request)
            if len(requests) == 1:
                raise urllib.error.HTTPError(stable, 302, "PRIVATE", {
                    "Location": "https://release-assets.githubusercontent.com/object?signature=PRIVATE"}, None)
            return io.BytesIO(public.PNG)
        opener = type("Opener", (), {"open": staticmethod(opened)})()
        with patch.object(so.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(snapshot.anonymous_media(stable), public.PNG)
        self.assertTrue(all(request.get_header("Authorization") is None for request in requests))
        for destination in ("http://release-assets.githubusercontent.com/object", "https://untrusted.invalid/object",
                            "https://user:pass@release-assets.githubusercontent.com/object",
                            "https://release-assets.githubusercontent.com:PRIVATE/object"):
            def rejected(request, **kwargs):
                raise urllib.error.HTTPError(stable, 302, "PRIVATE", {"Location": destination}, None)
            opener = type("Opener", (), {"open": staticmethod(rejected)})()
            with self.subTest(destination=destination), \
                    patch.object(so.urllib.request, "build_opener", return_value=opener), \
                    self.assertRaises(so.OnlineError):
                snapshot.anonymous_media(stable)

    def test_limits_and_malformed_initial_url_fail_without_remote_details(self):
        snapshot = object.__new__(so.Snapshots)
        snapshot.repo = mp.REPO
        stable = f"https://github.com/{mp.REPO}/releases/download/sala-media-" + "b" * 64 + "-mesa/" + "a" * 64 + ".png"
        with self.assertRaisesRegex(so.OnlineError, "URL pública"):
            snapshot.anonymous_media(stable.replace("github.com/", "github.com:PRIVATE/"))
        opener = type("Opener", (), {"open": staticmethod(lambda *a, **kw: io.BytesIO(b"12345"))})()
        with patch.object(so.urllib.request, "build_opener", return_value=opener), \
                patch.object(so, "MAX_FILE", 4), self.assertRaisesRegex(so.OnlineError, "demasiado grande"):
            snapshot.anonymous_media(stable)
        def redirect(request, **kwargs):
            raise urllib.error.HTTPError(stable, 302, "PRIVATE", {"Location": stable}, None)
        opener = type("Opener", (), {"open": staticmethod(redirect)})()
        with patch.object(so.urllib.request, "build_opener", return_value=opener), \
                self.assertRaisesRegex(so.OnlineError, "Demasiadas redirecciones"):
            snapshot.anonymous_media(stable)


if __name__ == "__main__":
    unittest.main()
