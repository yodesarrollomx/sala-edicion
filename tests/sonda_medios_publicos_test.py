"""Technical canary tests: fake GitHub and bounded anonymous HTTP only."""
import email.message
import io
import json
from pathlib import Path
import re
import struct
import sys
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import medios_publicos as mp
from medios_publicos_test import FakeGitHub
import sonda_medios_publicos as sonda


HEAD = "a" * 40
INDEX = b'<meta name="sala-medios-publicos" content="1"><script src="medios-publicos.js?v=1"></script>'
SCRIPT = b"window.SalaMediosPublicos = {};"


class PublicHTTP:
    def __init__(self, api):
        self.api, self.calls = api, []
        self.receipt = {"schema": 1, "code_sha": HEAD, "run_id": "unrelated-run"}
        self.index, self.script = INDEX, SCRIPT
        self.asset_mime, self.alter = "image/png", False

    def __call__(self, url, limit):
        self.calls.append((url, limit))
        path = urllib.parse.urlsplit(url).path
        if path.endswith("/version-online.json"):
            return 200, "application/json", json.dumps(self.receipt).encode()
        if path.endswith("/index.html"):
            return 200, "text/html", self.index
        if path.endswith("/medios-publicos.js"):
            return 200, "application/javascript", self.script
        raw = self.api.fetch(url)
        return 200, self.asset_mime, raw[:-1] + b"x" if self.alter else raw


class SondaTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.http = PublicHTTP(self.api)
        self.factories = 0
        self.proof_calls = 0
        self.proof_ok = True

    def proof(self):
        self.proof_calls += 1
        self.assertEqual(len(self.http.calls), 3)
        self.assertFalse(any(body is not None for _, body, _ in self.api.calls))
        if not self.proof_ok:
            raise sonda.SondaError("Actions no acreditó la publicación")

    def factory(self):
        self.factories += 1
        # A fresh proxy owns no state; the fake remote remains shared.
        class Proxy:
            repo = mp.REPO
            def request(inner, *args, **kw):
                return self.api.request(*args, **kw)
            def upload(inner, *args, **kw):
                return self.api.upload(*args, **kw)
        return Proxy()

    def run_canary(self, apply=False, factory=None):
        return sonda.run_canary(apply=apply, head=HEAD, run="12", attempt="1",
                                index_sha256=sonda.sha256(INDEX),
                                reader_sha256=sonda.sha256(SCRIPT),
                                api_factory=factory or self.factory, publication_proof=self.proof,
                                get=self.http)

    def test_default_inspection_is_get_only_and_png_is_own_known_dimensions(self):
        report = self.run_canary()
        self.assertEqual(report["state"], "ready")
        self.assertFalse(report["aplicar"])
        self.assertEqual(self.factories, 1)
        self.assertEqual(self.proof_calls, 1)
        self.assertEqual(len(self.http.calls), 3)
        self.assertEqual(self.http.calls[0][1], 32768)
        self.assertFalse(any(body is not None for _, body, _ in self.api.calls))
        self.assertEqual(self.api.releases, {})
        png = sonda.canary_png()
        self.assertEqual(png, sonda.canary_png())
        self.assertEqual(struct.unpack(">II", png[16:24]), (8, 8))
        self.assertEqual(report["image"]["sha256"], sonda.sha256(png))

    def test_stale_receipt_missing_reader_or_wrong_served_code_blocks_before_api(self):
        variants = [("receipt", {"schema": 1, "code_sha": "b" * 40}),
                    ("index", b'<script src="medios-publicos.js"></script>'),
                    ("index", b'<meta name="sala-medios-publicos" content="1">'),
                    ("script", SCRIPT + b"changed")]
        for attr, value in variants:
            with self.subTest(attr=attr):
                self.http = PublicHTTP(self.api)
                setattr(self.http, attr, value)
                with self.assertRaises(sonda.SondaError):
                    self.run_canary(apply=True)
        self.assertEqual(self.api.calls, [])
        self.http = PublicHTTP(self.api)
        self.proof_ok = False
        with self.assertRaises(sonda.SondaError):
            self.run_canary(apply=True)
        self.assertEqual(self.api.calls, [])

    def test_apply_verifies_immutable_bytes_and_empty_journal_reentry_has_zero_writes(self):
        report = self.run_canary(apply=True)
        self.assertEqual(report["state"], "verified")
        self.assertEqual(report["reentry_mutations"], 0)
        self.assertEqual(self.factories, 2)
        self.assertTrue(self.api.releases[1]["immutable"])
        self.assertEqual(self.api.writes("releases"), 1)
        self.assertEqual(self.api.writes("upload"), 1)
        self.assertEqual(self.api.writes("releases/1"), 1)
        descriptor = json.loads(self.api.releases[1]["body"])
        path = next(iter(descriptor["files"]))
        self.assertEqual(path, "laminas/_sondas/" + report["image"]["sha256"] + ".png")
        self.assertNotIn("?", report["entry"]["url"])
        self.assertEqual(report["entry"]["mime"], "image/png")
        self.assertNotIn("entries", report)  # Artifact is not a production manifest.

    def test_private_repository_mutable_release_bad_mime_or_bad_bytes_fail_closed(self):
        for fault in ("private", "mutable", "mime", "bytes"):
            with self.subTest(fault=fault):
                self.api = FakeGitHub()
                self.http = PublicHTTP(self.api)
                if fault == "private":
                    self.api.public = False
                elif fault == "mutable":
                    self.api.immutable = False
                elif fault == "mime":
                    self.http.asset_mime = "text/html"
                else:
                    self.http.alter = True
                with self.assertRaises((sonda.SondaError, mp.MediaError)):
                    self.run_canary(apply=True)
                if fault == "private":
                    self.assertEqual(self.api.writes("releases"), 0)

    def test_reentry_mutation_intent_is_blocked_before_reaching_real_api(self):
        count = 0

        def factory():
            nonlocal count
            count += 1
            proxy = self.factory()
            if count == 2:
                original = proxy.request
                def hide_release(path, *args, **kw):
                    return [] if path.startswith("releases?") else original(path, *args, **kw)
                proxy.request = hide_release
            return proxy

        with self.assertRaisesRegex(sonda.SondaError, "Reentrada sin journal"):
            self.run_canary(apply=True, factory=factory)
        self.assertEqual(self.api.writes("releases"), 1)
        self.assertEqual(self.api.writes("upload"), 1)
        self.assertEqual(self.api.writes("releases/1"), 1)

    def test_http_asset_redirect_is_anonymous_bounded_and_does_not_return_signed_url(self):
        headers = email.message.Message()
        headers["Location"] = "https://release-assets.githubusercontent.com/fake?signature=must-not-persist"
        redirect = urllib.error.HTTPError("unused", 302, "Found", headers, None)

        class Response(io.BytesIO):
            status = 200
            headers = email.message.Message()
        response = Response(sonda.canary_png())
        response.headers["Content-Type"] = "image/png"
        requests = []

        class Opener:
            def open(inner, request, timeout):
                requests.append(request)
                if len(requests) == 1:
                    raise redirect
                return response

        with patch.object(sonda.urllib.request, "build_opener", return_value=Opener()):
            result = sonda.anonymous_get(f"https://github.com/{mp.REPO}/releases/download/tag/asset.png", 1024)
        self.assertEqual(result, (200, "image/png", sonda.canary_png()))
        for request in requests:
            self.assertIsNone(request.get_header("Authorization"))
            self.assertIsNone(request.get_header("Cookie"))
        self.assertNotIn("signature", str(result))

    def test_http_rejects_foreign_redirect_and_oversized_or_non_200_bytes(self):
        headers = email.message.Message()
        headers["Location"] = "https://private.example/signed?secret=never-log"
        redirect = urllib.error.HTTPError("unused", 302, "Found", headers, None)
        with patch.object(sonda.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = redirect
            with self.assertRaises(sonda.SondaError) as raised:
                sonda.anonymous_get(f"https://github.com/{mp.REPO}/releases/download/tag/asset.png", 1024)
        self.assertNotIn("secret", str(raised.exception))
        for status, length in ((200, 11), (500, 1)):
            class Response(io.BytesIO):
                headers = email.message.Message()
            response = Response(b"x" * length)
            response.status = status
            response.headers["Content-Type"] = "image/png"
            with patch.object(sonda.urllib.request, "build_opener") as build:
                build.return_value.open.return_value = response
                with self.assertRaises(sonda.SondaError):
                    sonda.anonymous_get(sonda.SITE + "index.html", 10)

    def test_workflow_is_manual_default_false_and_write_permission_only_on_apply(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/sonda-medios-publicos.yml"
        source = path.read_text()
        events = source.split("on:\n", 1)[1].split("permissions:", 1)[0]
        self.assertEqual(re.findall(r"^  ([a-z_]+):", events, re.M), ["workflow_dispatch"])
        self.assertRegex(events, r"type: boolean\s+required: false\s+default: false")
        self.assertIn("\npermissions: {}\n", source)
        jobs = source.split("\njobs:\n", 1)[1]
        self.assertEqual(re.findall(r"^  ([a-z_]+):", jobs, re.M), ["inspeccionar", "aplicar"])
        inspect, apply = jobs.split("  aplicar:\n", 1)
        self.assertRegex(inspect, r"permissions:\s+contents: read\s+actions: read\s+steps:")
        self.assertRegex(apply, r"permissions:\s+contents: write\s+actions: read\s+steps:")
        self.assertIn("inputs.aplicar == true", apply)
        self.assertNotIn("--aplicar", inspect)
        self.assertIn("--aplicar", apply)
        for job in (inspect, apply):
            self.assertIn("refs/heads/main", job)
            self.assertNotIn("secrets.", job)
            self.assertEqual(job.count("persist-credentials: false"), 1)
            self.assertIn("ref: ${{ github.sha }}", job)


if __name__ == "__main__":
    unittest.main()
