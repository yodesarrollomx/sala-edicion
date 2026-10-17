"""Synthetic public-derivative lifecycle; no HTTP, local media or secrets."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
import medios_publicos as mp


def synthetic_image(fmt):
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (20, 40, 60)).save(stream, format=fmt)
    return stream.getvalue()


PNG = synthetic_image("PNG")
JPEG = synthetic_image("JPEG")
WEBP = synthetic_image("WEBP")
SOURCE = "a" * 40
PATH = "laminas/synthetic/L1.png"


class FakeGitHub:
    """Reusable fake for snapshot integration; every remote mutation is visible."""
    def __init__(self):
        self.repo = mp.REPO
        self.public = True
        self.immutable = True
        self.releases, self.bytes = {}, {}
        self.calls, self.fetches = [], []
        self.number = 0
        self.fail_create = self.fail_upload = self.fail_publish = None

    def _id(self):
        self.number += 1
        return self.number

    def request(self, path, body=None, method=None):
        self.calls.append((path, copy.deepcopy(body), method))
        if path == "/repos/" + self.repo:
            return {"full_name": self.repo, "private": not self.public,
                    "visibility": "public" if self.public else "private"}
        if path.startswith("releases?"):
            page = int(path.rsplit("=", 1)[1])
            return copy.deepcopy(list(self.releases.values())[(page - 1) * 100:page * 100])
        if path == "releases" and body:
            fail, self.fail_create = self.fail_create, None
            if fail != "unapplied":
                rid = self._id()
                self.releases[rid] = {**copy.deepcopy(body), "id": rid, "immutable": False,
                                      "upload_url": "synthetic", "assets": []}
            if fail:
                raise RuntimeError("remote secret and signed URL must not escape")
            return copy.deepcopy(self.releases[rid])
        if path.startswith("releases/"):
            parts = path.split("/")
            rid = int(parts[1])
            if rid not in self.releases:
                raise RuntimeError("GitHub HTTP 404")
            release = self.releases[rid]
            if len(parts) == 3 and parts[2].startswith("assets?"):
                page = int(path.rsplit("=", 1)[1])
                return copy.deepcopy(release["assets"][(page - 1) * 100:page * 100])
            if body is not None:
                if method != "PATCH" or body != {"draft": False}:
                    raise AssertionError("Unexpected release mutation")
                fail, self.fail_publish = self.fail_publish, None
                if fail != "unapplied":
                    release["draft"] = False
                    release["immutable"] = self.immutable
                if fail:
                    raise RuntimeError("remote secret must not escape")
            return copy.deepcopy(release)
        raise AssertionError("Unexpected API path: " + path)

    def upload(self, release, data, *, name, content_type):
        self.calls.append(("upload", {"name": name, "bytes": len(data)}, "POST"))
        target = self.releases[release["id"]]
        if not target["draft"] or target["immutable"]:
            raise AssertionError("Cannot mutate a public or immutable release")
        if any(a["name"] == name for a in target["assets"]):
            raise AssertionError("Duplicate asset POST")
        fail, self.fail_upload = self.fail_upload, None
        if fail != "unapplied":
            aid = self._id()
            url = f"https://github.com/{self.repo}/releases/download/{release['tag_name']}/{name}"
            asset = {"id": aid, "name": name, "size": len(data), "state": "uploaded",
                     "content_type": content_type, "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                     "browser_download_url": url}
            target["assets"].append(asset)
            self.bytes[url] = data
        if fail:
            raise RuntimeError("remote secret must not escape")
        return copy.deepcopy(asset)

    def fetch(self, url):
        self.fetches.append(url)
        # Draft bytes cannot be fetched anonymously, even if uploaded.
        for release in self.releases.values():
            if any(a["browser_download_url"] == url for a in release["assets"]):
                if release["draft"]:
                    raise RuntimeError("HTTP 404")
                return self.bytes[url]
        raise RuntimeError("HTTP 404")

    def writes(self, operation):
        return sum(path == operation and body is not None for path, body, _ in self.calls)


class CrashAfterApplied:
    """Fresh runner wrappers share only the actual remote API state."""
    def __init__(self, remote, operation=None):
        self.repo, self.remote, self.operation = remote.repo, remote, operation

    def request(self, path, body=None, method=None):
        result = self.remote.request(path, body, method)
        if body is not None:
            operation = "create" if path == "releases" else "publish"
            if self.operation == operation:
                raise KeyboardInterrupt("synthetic runner loss after accepted write")
        return result

    def upload(self, release, data, **kw):
        result = self.remote.upload(release, data, **kw)
        if self.operation == "upload":
            raise KeyboardInterrupt("synthetic runner loss after accepted upload")
        return result

    def fetch(self, url):
        return self.remote.fetch(url)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.manifest = mp.upload_new({}, {PATH: PNG}, SOURCE, "12", "1", "mesa",
                                      self.api, self.api.fetch)

    def test_public_contract_and_detached_json(self):
        result = mp.validate_manifest(json.dumps(self.manifest).encode(), mp.REPO)
        self.assertEqual(result, self.manifest)
        result["entries"].clear()
        self.assertEqual(len(self.manifest["entries"]), 1)
        entry = self.manifest["entries"][PATH]
        self.assertEqual(set(entry), mp._ENTRY_KEYS)
        self.assertRegex(entry["tag"], r"^sala-media-[0-9a-f]{64}-mesa$")
        self.assertEqual(entry["url"], f"https://github.com/{mp.REPO}/releases/download/{entry['tag']}/{entry['sha256']}.png")

    def test_private_fields_signed_urls_and_extra_keys_rejected(self):
        for key, value in (("drive_id", "private"), ("token", "private"),
                           ("url", self.manifest["entries"][PATH]["url"] + "?token=private"),
                           ("bytes", True), ("asset_id", False), ("release_id", 0),
                           ("asset_id", 2 ** 53), ("release_id", 2 ** 53),
                           ("mime", "image/svg+xml"), ("sha256", "A" * 64),
                           ("tag", "sala-media-12-1-mesa/../../private")):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.manifest)
                bad["entries"][PATH][key] = value
                with self.assertRaises(mp.MediaError):
                    mp.validate_manifest(bad, mp.REPO)
        for key, value in (("schema", True), ("repo", "private/repo"), ("private", True)):
            bad = copy.deepcopy(self.manifest)
            bad[key] = value
            with self.assertRaises(mp.MediaError):
                mp.validate_manifest(bad, mp.REPO)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(mp.MediaError):
            mp.validate_manifest(b'{"schema":1,"schema":1,"repo":"yodesarrollomx/sala-edicion","entries":{}}', mp.REPO)

    def test_raw_limit_is_checked_before_json_parse_and_final_size_includes_newline(self):
        with patch.object(mp.json, "loads", side_effect=AssertionError("must not parse")):
            with self.assertRaises(mp.MediaError):
                mp.validate_manifest(b" " * (mp.MAX_MANIFEST_BYTES + 1), mp.REPO)
        size = len(mp._canonical(self.manifest)) + 1
        with patch.object(mp, "MAX_MANIFEST_BYTES", size):
            self.assertEqual(mp.validate_manifest(self.manifest, mp.REPO), self.manifest)
        with patch.object(mp, "MAX_MANIFEST_BYTES", size - 1), self.assertRaises(mp.MediaError):
            mp.validate_manifest(self.manifest, mp.REPO)

    def test_exact_path_policy(self):
        for path in ("laminas/a.png", "laminas/slug_1/L1-a.jpeg", "laminas/a/b/L1.webp"):
            self.assertIn(mp._suffix(path), ("png", "jpeg", "webp"))
        for path in ("laminas/../a.png", "laminas/./a.png", "laminas/a//L1.png",
                     "laminas/a.b/L1.png", "laminas/a%2fb.png", "laminas/a\\b.png",
                     "/laminas/a.png", "laminas/a.png?q=1", "laminas/a.png#x", "laminas/a.PNG",
                     "datos/a.png", "laminas/a.mp4", "laminas/a.svg", "laminas/a b.png"):
            with self.subTest(path=path), self.assertRaises(mp.MediaError):
                mp._suffix(path)

    def test_inconsistent_asset_ids_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["entries"]["laminas/a.jpg"] = {**bad["entries"][PATH], "mime": "image/jpeg"}
        old = bad["entries"]["laminas/a.jpg"]
        old["url"] = old["url"].removesuffix("png") + "jpg"
        with self.assertRaises(mp.MediaError):
            mp.validate_manifest(bad, mp.REPO)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def upload(self, files=None, existing=None, **kw):
        return mp.upload_new(existing or {}, files or {PATH: PNG}, SOURCE, "12", "1", "mesa",
                             self.api, kw.get("fetch", self.api.fetch))

    def test_draft_upload_publication_anonymous_verification_order(self):
        manifest = self.upload()
        release = next(iter(self.api.releases.values()))
        self.assertFalse(release["draft"])
        self.assertTrue(release["immutable"])
        self.assertEqual(self.api.writes("releases"), 1)
        self.assertEqual(self.api.writes("upload"), 1)
        self.assertEqual(self.api.writes("releases/1"), 1)
        self.assertEqual(self.api.fetches, [manifest["entries"][PATH]["url"]])

    def test_same_batch_reentry_has_no_second_mutation(self):
        first = self.upload()
        self.assertEqual(first, self.upload())
        self.assertEqual(self.api.writes("releases"), 1)
        self.assertEqual(self.api.writes("upload"), 1)
        self.assertEqual(self.api.writes("releases/1"), 1)

    def test_existing_manifest_preserved_and_same_path_not_replaced(self):
        first = self.upload()
        before = copy.deepcopy(first)
        second = mp.upload_new(first["entries"], {"laminas/new/L1.jpg": JPEG}, SOURCE,
                               "13", "1", "arranque", self.api, self.api.fetch)
        self.assertEqual(first, before)
        self.assertEqual(second["entries"][PATH], first["entries"][PATH])
        self.assertEqual(len(second["entries"]), 2)
        self.assertEqual(self.upload(existing=first), first)
        with self.assertRaises(mp.MediaError):
            self.upload(files={PATH: PNG[:-12] + b"different" + PNG[-12:]}, existing=first)

    def test_all_three_formats_and_jpeg_suffix(self):
        manifest = self.upload(files={"laminas/a.png": PNG, "laminas/a.jpg": JPEG,
                                      "laminas/a.jpeg": JPEG, "laminas/a.webp": WEBP})
        self.assertEqual(len(manifest["entries"]), 4)
        self.assertEqual(self.api.writes("upload"), 4)

    def test_same_bytes_same_suffix_only_one_asset_and_fetch(self):
        manifest = self.upload(files={PATH: PNG, "laminas/other/L1.png": PNG})
        self.assertEqual(self.api.writes("upload"), 1)
        self.assertEqual(len(self.api.fetches), 1)
        self.assertEqual(manifest["entries"][PATH]["asset_id"],
                         manifest["entries"]["laminas/other/L1.png"]["asset_id"])

    def test_applied_500_reconciles_without_second_post(self):
        for operation in ("create", "upload", "publish"):
            with self.subTest(operation=operation):
                self.api = FakeGitHub()
                setattr(self.api, "fail_" + operation, "applied")
                manifest = self.upload()
                mp.verify_manifest_assets(manifest, self.api, self.api.fetch)
                self.assertEqual(self.api.writes("releases"), 1)
                self.assertEqual(self.api.writes("upload"), 1)
                self.assertEqual(self.api.writes("releases/1"), 1)

    def test_unknown_ambiguous_write_fails_closed_without_retry(self):
        for operation in ("create", "upload", "publish"):
            with self.subTest(operation=operation):
                self.api = FakeGitHub()
                setattr(self.api, "fail_" + operation, "unapplied")
                with self.assertRaises(mp.MediaError) as raised:
                    self.upload()
                self.assertNotIn("secret", str(raised.exception))
                self.assertLessEqual(self.api.writes("releases"), 1)
                self.assertLessEqual(self.api.writes("upload"), 1)
                self.assertLessEqual(self.api.writes("releases/1"), 1)

    def test_durable_journal_blocks_ambiguous_reentry_for_each_write(self):
        for operation in ("create", "upload", "publish"):
            with self.subTest(operation=operation):
                self.api = FakeGitHub()
                setattr(self.api, "fail_" + operation, "unapplied")
                journal, saved = {}, []
                args = ({}, {PATH: PNG}, SOURCE, "12", "1", "mesa", self.api, self.api.fetch)
                with self.assertRaises(mp.MediaError):
                    mp.upload_new(*args, journal=journal, checkpoint=saved.append)
                counts = [self.api.writes(key) for key in ("releases", "upload", "releases/1")]
                self.assertEqual(saved[-1], journal)
                self.assertIn({"state": "pending"}, journal["operations"].values())
                with self.assertRaises(mp.MediaError):
                    mp.upload_new(*args, journal=copy.deepcopy(saved[-1]), checkpoint=saved.append)
                self.assertEqual(counts, [self.api.writes(key) for key in ("releases", "upload", "releases/1")])

    def test_checkpoint_precedes_mutation_and_applied_errors_reconcile_journal(self):
        self.api.fail_create = self.api.fail_upload = self.api.fail_publish = "applied"
        journal, saved = {}, []

        def checkpoint(value):
            for operation, state in value["operations"].items():
                if state["state"] == "pending":
                    key = "upload" if operation.startswith("upload:") else {"create": "releases", "publish": "releases/1"}[operation]
                    self.assertEqual(self.api.writes(key), 0)
            saved.append(value)

        args = ({}, {PATH: PNG}, SOURCE, "12", "1", "mesa", self.api, self.api.fetch)
        first = mp.upload_new(*args, journal=journal, checkpoint=checkpoint)
        self.assertEqual(len(saved), 6)
        self.assertTrue(all(v == {"state": "confirmed"} for v in journal["operations"].values()))
        self.assertEqual(first, mp.upload_new(*args, journal=journal, checkpoint=checkpoint))
        self.assertEqual(self.api.writes("releases"), 1)
        self.assertEqual(self.api.writes("upload"), 1)

    def test_checkpoint_failure_stops_before_post_and_does_not_leak(self):
        journal = {}

        def fail(value):
            raise RuntimeError("private checkpoint response")

        with self.assertRaises(mp.MediaError) as raised:
            mp.upload_new({}, {PATH: PNG}, SOURCE, "12", "1", "mesa", self.api,
                          self.api.fetch, journal=journal, checkpoint=fail)
        self.assertNotIn("private", str(raised.exception))
        self.assertFalse(any(body is not None for _, body, _ in self.api.calls))
        self.assertEqual(journal["operations"], {"create": {"state": "pending"}})

    def test_journal_is_bound_to_exact_batch(self):
        journal = {}
        self.api.fail_create = "unapplied"
        with self.assertRaises(mp.MediaError):
            mp.upload_new({}, {PATH: PNG}, SOURCE, "12", "1", "mesa", self.api,
                          self.api.fetch, journal=journal)
        count = self.api.writes("releases")
        with self.assertRaises(mp.MediaError):
            mp.upload_new({}, {"laminas/different/L1.png": PNG}, SOURCE, "12", "1", "mesa", self.api,
                          self.api.fetch, journal=journal)
        self.assertEqual(self.api.writes("releases"), count)

    def test_draft_owned_by_other_descriptor_never_published(self):
        self.api.fail_upload = "unapplied"
        with self.assertRaises(mp.MediaError):
            self.upload()
        release = self.api.releases[1]
        info = json.loads(release["body"])
        info["kind"] = "unrelated-private-release"
        release["body"] = json.dumps(info)
        before = len(self.api.calls)
        with self.assertRaises(mp.MediaError):
            self.upload()
        self.assertFalse(any(body is not None for _, body, _ in self.api.calls[before:]))
        self.assertTrue(release["draft"])

    def test_new_runner_without_journal_recovers_each_applied_remote_write(self):
        for operation in ("create", "upload", "publish"):
            with self.subTest(operation=operation):
                remote = FakeGitHub()
                first_runner = CrashAfterApplied(remote, operation)
                with self.assertRaises(KeyboardInterrupt):
                    mp.upload_new({}, {PATH: PNG}, SOURCE, "12", "1", "mesa",
                                  first_runner, first_runner.fetch, journal={})
                before = {key: remote.writes(key) for key in ("releases", "upload", "releases/1")}
                second_runner = CrashAfterApplied(remote)
                manifest = mp.upload_new({}, {PATH: PNG}, "b" * 40, "13", "2", "mesa",
                                         second_runner, second_runner.fetch, journal={})
                self.assertEqual(len(remote.releases), 1)
                self.assertEqual(remote.writes("releases"), 1)
                self.assertEqual(remote.writes("upload"), 1)
                self.assertEqual(remote.writes("releases/1"), 1)
                for key, count in before.items():
                    if count:
                        self.assertEqual(remote.writes(key), count)
                descriptor = json.loads(remote.releases[1]["body"])
                self.assertEqual(descriptor["source_sha"], SOURCE)
                self.assertEqual((descriptor["run_id"], descriptor["attempt"]), ("12", "1"))
                self.assertEqual(manifest["entries"][PATH]["tag"], remote.releases[1]["tag_name"])

    def test_stable_batch_hash_ignores_provenance_but_binds_payload_and_process(self):
        first = self.upload()
        journal = {}
        second = mp.upload_new({}, {PATH: PNG}, "b" * 40, "13", "2", "mesa",
                               self.api, self.api.fetch, journal=journal)
        self.assertEqual(first, second)
        self.assertEqual(journal["batch_sha256"], first["entries"][PATH]["tag"].split("-")[2])
        next_manifest = mp.upload_new({}, {PATH: PNG}, SOURCE, "14", "1", "arranque",
                                     self.api, self.api.fetch)
        self.assertNotEqual(first["entries"][PATH]["tag"], next_manifest["entries"][PATH]["tag"])
        self.assertEqual(len(self.api.releases), 2)

    def test_private_repository_blocks_all_writes(self):
        self.api.public = False
        with self.assertRaises(mp.MediaError):
            self.upload()
        self.assertFalse(any(body is not None for _, body, _ in self.api.calls))

    def test_wrong_repo_client_blocks_all_calls(self):
        self.api.repo = "private/repo"
        with self.assertRaises(mp.MediaError):
            self.upload()
        self.assertEqual(self.api.calls, [])

    def test_immutable_setting_mandatory_before_return_or_download(self):
        self.api.immutable = False
        with self.assertRaises(mp.MediaError):
            self.upload()
        self.assertEqual(self.api.fetches, [])

    def test_resumed_draft_without_digest_never_becomes_public(self):
        self.api.fail_upload = "unapplied"
        with self.assertRaises(mp.MediaError):
            self.upload()
        release = self.api.releases[1]
        info = json.loads(release["body"])["files"][PATH]
        self.api.upload(release, PNG, name=info["name"], content_type=info["mime"])
        asset = release["assets"][0]
        del asset["digest"]
        altered = bytearray(PNG)
        altered[30] ^= 1
        self.api.bytes[asset["browser_download_url"]] = bytes(altered)
        with self.assertRaises(mp.MediaError):
            self.upload()
        self.assertTrue(release["draft"])
        self.assertEqual(self.api.writes("releases/1"), 0)
        self.assertEqual(self.api.fetches, [])

    def test_combined_manifest_limit_is_checked_before_publication(self):
        with patch.object(mp, "MAX_MANIFEST_BYTES", 100), self.assertRaises(mp.MediaError):
            self.upload()
        self.assertTrue(self.api.releases[1]["draft"])
        self.assertEqual(self.api.writes("releases/1"), 0)
        self.assertEqual(self.api.fetches, [])

    def test_wrong_anonymous_bytes_rejected(self):
        with self.assertRaises(mp.MediaError):
            self.upload(fetch=lambda url: PNG[:-12] + b"wrong" + PNG[-12:])

    def test_metadata_digest_size_state_mime_and_url_are_enforced(self):
        manifest = self.upload()
        release = self.api.releases[1]
        asset = copy.deepcopy(release["assets"][0])
        for key, value in (("digest", "sha256:" + "b" * 64), ("size", len(PNG) + 1),
                           ("state", "new"), ("content_type", "text/html"),
                           ("browser_download_url", "https://private.example/file"),
                           ("name", "private.png"), ("id", True)):
            with self.subTest(key=key):
                release["assets"] = [{**asset, key: value}]
                with self.assertRaises(mp.MediaError):
                    mp.verify_manifest_assets(manifest, self.api, self.api.fetch)
        release["assets"] = [{k: v for k, v in asset.items() if k != "digest"}]
        mp.verify_manifest_assets(manifest, self.api, self.api.fetch)

    def test_existing_mutable_or_draft_release_rejected(self):
        manifest = self.upload()
        release = self.api.releases[1]
        for field, value in (("immutable", False), ("draft", True), ("prerelease", True)):
            old = release[field]
            release[field] = value
            with self.assertRaises(mp.MediaError):
                mp.verify_manifest_assets(manifest, self.api, self.api.fetch)
            release[field] = old

    def test_wrong_magic_or_oversize_rejected_before_api(self):
        for path, data in ((PATH, JPEG), ("laminas/a.jpg", PNG), ("laminas/a.webp", b"RIFFbad"),
                           (PATH, b""), (PATH, bytearray(PNG))):
            with self.subTest(path=path), self.assertRaises(mp.MediaError):
                self.upload(files={path: data})
        with patch.object(mp, "MAX_IMAGE_BYTES", len(PNG) - 1), self.assertRaises(mp.MediaError):
            self.upload()
        self.assertEqual(self.api.calls, [])

    def test_renamed_binary_and_missing_decoder_fail_before_any_api(self):
        with self.assertRaises(mp.MediaError):
            self.upload(files={"laminas/a.jpg": b"\xff\xd8\xffarbitrary payload\xff\xd9"})
        with patch.dict(sys.modules, {"PIL": None}), self.assertRaises(mp.MediaError):
            self.upload()
        self.assertEqual(self.api.calls, [])

    def test_unique_asset_limit_checked_before_api(self):
        with patch.object(mp, "MAX_RELEASE_ASSETS", 1), self.assertRaises(mp.MediaError):
            self.upload(files={PATH: PNG, "laminas/a.jpg": JPEG})
        self.assertEqual(self.api.calls, [])

    def test_no_new_files_preserves_validated_existing_manifest(self):
        manifest = self.upload()
        self.assertEqual(mp.upload_new(manifest, {}, SOURCE, "13", "1", "mesa",
                                      self.api, self.api.fetch), manifest)
        self.assertEqual(self.api.writes("releases"), 1)


if __name__ == "__main__":
    unittest.main()

class DraftTemporaryURLTests(unittest.TestCase):
    def test_draft_temporary_url_recovers_existing_upload_without_resending(self):
        api = FakeGitHub()
        original_upload = api.upload
        def upload(release, data, **kw):
            result = original_upload(release, data, **kw)
            api.releases[release["id"]]["assets"][0]["browser_download_url"] = (
                f"https://github.com/{mp.REPO}/releases/download/untagged-484177f273a8b354c76f/"
                + result["name"])
            raise KeyboardInterrupt("runner interrupted after upload")
        api.upload = upload
        with self.assertRaises(KeyboardInterrupt):
            mp.upload_new({}, {PATH: PNG}, SOURCE, "12", "1", "mesa", api, api.fetch)
        original_request = api.request
        def request(path, body=None, method=None):
            result = original_request(path, body, method)
            if body == {"draft": False}:
                release = api.releases[int(path.split("/")[1])]
                for asset in release["assets"]:
                    asset["browser_download_url"] = mp._url(release["tag_name"], asset["name"])
                result = copy.deepcopy(release)
            return result
        api.request = request
        manifest = mp.upload_new({}, {PATH: PNG}, SOURCE, "13", "1", "mesa", api, api.fetch)
        self.assertEqual(api.writes("upload"), 1)
        self.assertNotIn("untagged", manifest["entries"][PATH]["url"])
        mp.verify_manifest_assets(manifest, api, api.fetch)

    def test_temporary_url_only_before_publication_with_exact_digest(self):
        expected = mp._file_info(PATH, PNG)
        item = {"id": 1, "name": expected["name"], "size": len(PNG),
                "state": "uploaded", "content_type": "image/png",
                "digest": "sha256:" + expected["sha256"],
                "browser_download_url": f"https://github.com/{mp.REPO}/releases/download/untagged-ab12/" + expected["name"]}
        mp._asset(item, expected, "sala-media-test", require_digest=True)
        with self.assertRaises(mp.MediaError):
            mp._asset(item, expected, "sala-media-test", require_digest=False)
        for url in (item["browser_download_url"] + "?token=bad",
                    item["browser_download_url"].replace(mp.REPO, "other/repo"),
                    item["browser_download_url"].replace("github.com", "evil.example"),
                    item["browser_download_url"].replace("untagged-ab12", "other-tag")):
            with self.subTest(url=url), self.assertRaises(mp.MediaError):
                mp._asset({**item, "browser_download_url": url}, expected, "sala-media-test", require_digest=True)
        for digest in (None, "sha256:" + "0" * 64):
            with self.subTest(digest=digest), self.assertRaises(mp.MediaError):
                mp._asset({**item, "digest": digest}, expected, "sala-media-test", require_digest=True)
