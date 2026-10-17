"""Content-addressed public derivatives; callers decide which new files qualify.

This module never reads Drive, credentials or local files and never activates
offload. It accepts only public-image bytes supplied by the snapshot caller.
Published references require immutable releases and an anonymous download of
the exact bytes. An uncertain write is reconciled by identity, never retried.
"""
import copy
import hashlib
import io
import json
import re
import warnings

MEDIA_PATH = "datos/medios-publicos.json"
REPO = "yodesarrollomx/sala-edicion"
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_RELEASE_ASSETS = 1000
MAX_RELEASES = 10000
KIND = "sala-public-media"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_NUMBER = re.compile(r"[1-9][0-9]*\Z")
_TAG = re.compile(r"sala-media-([0-9a-f]{64})-(mesa|arranque)\Z")
_PATH = re.compile(r"laminas/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp)\Z")
_MIMES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
          "webp": "image/webp"}
_ENTRY_KEYS = {"sha256", "bytes", "mime", "release_id", "asset_id", "tag", "url"}


class MediaError(RuntimeError):
    """Safe diagnostic: no remote responses, credentials or signed URLs."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _batch_payload(descriptor):
    """Stable identity excludes runner provenance, which can be lost on retry."""
    return {key: descriptor[key] for key in ("schema", "repo", "process", "files")}


def _batch_hash(descriptor):
    return _digest(_canonical(_batch_payload(descriptor)))


def _keys(value, keys):
    return type(value) is dict and set(value) == set(keys)


def _positive(value):
    return type(value) is int and 0 < value <= 9007199254740991


def _suffix(path):
    if type(path) is not str or len(path) > 512 or not _PATH.fullmatch(path):
        raise MediaError("Ruta de medio público inválida")
    parts = path.split("/")
    if any(p in (".", "..") for p in parts):
        raise MediaError("Ruta de medio público inválida")
    suffix = parts[-1].rsplit(".", 1)[-1]
    if suffix not in _MIMES:
        raise MediaError("Formato de medio público no permitido")
    return suffix


def _url(tag, name):
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def _entry(path, item):
    suffix = _suffix(path)
    if (not _keys(item, _ENTRY_KEYS) or type(item["sha256"]) is not str
            or not _SHA256.fullmatch(item["sha256"])
            or type(item["bytes"]) is not int or not 1 <= item["bytes"] <= MAX_IMAGE_BYTES
            or item["mime"] != _MIMES[suffix]
            or not _positive(item["release_id"]) or not _positive(item["asset_id"])
            or type(item["tag"]) is not str or not _TAG.fullmatch(item["tag"])
            or item["url"] != _url(item["tag"], item["sha256"] + "." + suffix)):
        raise MediaError("Entrada de medio público inválida")


def _unique_json(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise MediaError("Manifiesto de medios con claves duplicadas")
        value[key] = item
    return value


def validate_manifest(rawbytes, repo):
    """Validate the entire public contract and return a detached dictionary."""
    if repo != REPO:
        raise MediaError("Repositorio de medios no permitido")
    if isinstance(rawbytes, bytes):
        if len(rawbytes) > MAX_MANIFEST_BYTES:
            raise MediaError("Manifiesto de medios supera el límite permitido")
        try:
            rawbytes = json.loads(rawbytes.decode("utf-8"), object_pairs_hook=_unique_json)
        except (ValueError, UnicodeError):
            raise MediaError("Manifiesto de medios no es JSON válido") from None
    if (not _keys(rawbytes, {"schema", "repo", "entries"})
            or type(rawbytes["schema"]) is not int or rawbytes["schema"] != 1
            or rawbytes["repo"] != repo or type(rawbytes["entries"]) is not dict):
        raise MediaError("Manifiesto de medios públicos inválido")
    refs, tags, assets = {}, {}, {}
    for path, item in rawbytes["entries"].items():
        _entry(path, item)
        # An ID cannot acquire another tag, URL, digest or file suffix.
        release = (item["release_id"], item["tag"])
        if item["release_id"] in refs and refs[item["release_id"]] != release:
            raise MediaError("Referencia de release contradictoria")
        if item["tag"] in tags and tags[item["tag"]] != item["release_id"]:
            raise MediaError("Referencia de tag contradictoria")
        refs[item["release_id"]] = release
        tags[item["tag"]] = item["release_id"]
        identity = (item["sha256"], item["bytes"], item["mime"], item["release_id"],
                    item["tag"], item["url"])
        if item["asset_id"] in assets and assets[item["asset_id"]] != identity:
            raise MediaError("Referencia de activo contradictoria")
        assets[item["asset_id"]] = identity
    # The snapshot caller writes canonical JSON plus its trailing newline.
    if len(_canonical(rawbytes)) + 1 > MAX_MANIFEST_BYTES:
        raise MediaError("Manifiesto de medios supera el límite permitido")
    return copy.deepcopy(rawbytes)


def _request(api, path, body=None, method=None, missing=False):
    try:
        return api.request(path, body, method=method)
    except Exception as exc:
        if missing and str(exc) == "GitHub HTTP 404":
            return None
        raise MediaError("GitHub no confirmó la operación de medios") from None


def _public_repo(api):
    if getattr(api, "repo", None) != REPO:
        raise MediaError("Cliente de medios fuera del repositorio permitido")
    info = _request(api, "/repos/" + REPO)
    if (type(info) is not dict or info.get("full_name") != REPO
            or info.get("private") is not False
            or info.get("visibility", "public") != "public"):
        raise MediaError("No se acreditó el repositorio público de medios")


def _assets(api, release_id):
    result = []
    for page in range(1, MAX_RELEASE_ASSETS // 100 + 2):
        items = _request(api, f"releases/{release_id}/assets?per_page=100&page={page}")
        if type(items) is not list or any(type(a) is not dict for a in items):
            raise MediaError("Inventario de activos inválido")
        result.extend(items)
        if len(result) > MAX_RELEASE_ASSETS:
            raise MediaError("Demasiados activos en el release de medios")
        if len(items) < 100:
            break
    ids, names = set(), set()
    for item in result:
        if (not _positive(item.get("id")) or type(item.get("name")) is not str
                or item["id"] in ids or item["name"] in names):
            raise MediaError("Inventario de activos contradictorio")
        ids.add(item["id"])
        names.add(item["name"])
    return result


def _image(data, suffix):
    if type(data) is not bytes or not 1 <= len(data) <= MAX_IMAGE_BYTES:
        raise MediaError("Bytes de imagen fuera del límite permitido")
    png = (len(data) >= 45 and data.startswith(b"\x89PNG\r\n\x1a\n")
           and data[8:16] == b"\x00\x00\x00\rIHDR"
           and data[-12:] == b"\x00\x00\x00\x00IEND\xaeB`\x82")
    jpeg = len(data) >= 5 and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    webp = (len(data) >= 20 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            and data[12:16] in (b"VP8 ", b"VP8L", b"VP8X")
            and int.from_bytes(data[4:8], "little") == len(data) - 8)
    if not {"png": png, "jpg": jpeg, "jpeg": jpeg, "webp": webp}[suffix]:
        raise MediaError("La firma de la imagen no coincide con su formato")


def _file_info(path, data):
    suffix = _suffix(path)
    _image(data, suffix)
    sha = _digest(data)
    return {"sha256": sha, "bytes": len(data), "mime": _MIMES[suffix],
            "name": sha + "." + suffix}


def _decode_image(data, suffix):
    # Only producers opt into decoding; read-only consumers of old manifests
    # need no Pillow installation. Never publish an opaque renamed binary.
    try:
        from PIL import Image
    except ImportError:
        raise MediaError("Validación de imágenes no disponible; lote detenido") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}[suffix]:
                    raise ValueError("format")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except Exception:
        raise MediaError("La imagen nueva no se pudo verificar y decodificar") from None


def _descriptor(value):
    if type(value) is not str:
        raise MediaError("Release de medios sin descriptor")
    try:
        info = json.loads(value, object_pairs_hook=_unique_json)
    except (ValueError, UnicodeError):
        raise MediaError("Descriptor de medios inválido") from None
    if (not _keys(info, {"schema", "kind", "repo", "source_sha", "run_id", "attempt",
                         "process", "files"})
            or type(info["schema"]) is not int or info["schema"] != 1
            or info["kind"] != KIND or info["repo"] != REPO
            or type(info["source_sha"]) is not str or not _SHA.fullmatch(info["source_sha"])
            or type(info["run_id"]) is not str or not _NUMBER.fullmatch(info["run_id"])
            or type(info["attempt"]) is not str or not _NUMBER.fullmatch(info["attempt"])
            or info["process"] not in ("mesa", "arranque")
            or type(info["files"]) is not dict or not info["files"]):
        raise MediaError("Descriptor de medios inválido")
    unique = {}
    for path, item in info["files"].items():
        suffix = _suffix(path)
        if (not _keys(item, {"sha256", "bytes", "mime", "name"})
                or type(item["sha256"]) is not str or not _SHA256.fullmatch(item["sha256"])
                or type(item["bytes"]) is not int or not 1 <= item["bytes"] <= MAX_IMAGE_BYTES
                or item["mime"] != _MIMES[suffix]
                or item["name"] != item["sha256"] + "." + suffix):
            raise MediaError("Archivo del descriptor de medios inválido")
        if item["name"] in unique and unique[item["name"]] != item:
            raise MediaError("Descriptor de activos contradictorio")
        unique[item["name"]] = item
    if len(unique) > MAX_RELEASE_ASSETS:
        raise MediaError("Demasiados activos nuevos de medios")
    return info


def _release(release, tag, descriptor=None, published=False):
    if (type(release) is not dict or not _positive(release.get("id"))
            or release.get("tag_name") != tag or release.get("prerelease") is not False
            or type(release.get("draft")) is not bool):
        raise MediaError("Release de medios con identidad incorrecta")
    info = _descriptor(release.get("body"))
    expected_tag = f"sala-media-{_batch_hash(info)}-{info['process']}"
    if (expected_tag != tag or (descriptor is not None
                               and _batch_payload(info) != _batch_payload(descriptor))):
        raise MediaError("El release pertenece a otro lote de medios")
    if published and (release["draft"] or release.get("immutable") is not True):
        raise MediaError("El release público de medios no es inmutable")
    return info


def _asset(item, expected, tag, asset_id=None, require_digest=False):
    # GitHub uses a temporary tag in draft download URLs. It is never emitted
    # in our manifest; the published asset must use the exact final tag URL.
    url = item.get("browser_download_url") if type(item) is dict else None
    draft_url = (require_digest and type(url) is str and re.fullmatch(
        re.escape(f"https://github.com/{REPO}/releases/download/")
        + r"untagged-[0-9a-f]+/" + re.escape(expected["name"]), url) is not None)
    if (type(item) is not dict or not _positive(item.get("id"))
            or (asset_id is not None and item["id"] != asset_id)
            or item.get("name") != expected["name"] or item.get("state") != "uploaded"
            or type(item.get("size")) is not int or item["size"] != expected["bytes"]
            or item.get("content_type") != expected["mime"]
            or (url != _url(tag, expected["name"]) and not draft_url)
            or (require_digest and item.get("digest") != "sha256:" + expected["sha256"])
            or ("digest" in item and item["digest"] is not None
                and item["digest"] != "sha256:" + expected["sha256"])):
        raise MediaError("Activo de medios sin integridad acreditada")


def _download(fetch, entry, path):
    try:
        data = fetch(entry["url"])
    except Exception:
        raise MediaError("Descarga anónima de medios no confirmada") from None
    _image(data, _suffix(path))
    if len(data) != entry["bytes"] or _digest(data) != entry["sha256"]:
        raise MediaError("La descarga anónima no coincide con el medio")


def verify_manifest_assets(manifest, api, fetch):
    """Verify API metadata and anonymously fetched bytes, one asset at a time.

    ``fetch`` receives only a stable, validated URL and returns bytes; it must
    send no credentials. A caller may cache these bytes to disk for hydration.
    No byte collection is retained here, and no total storage limit is imposed.
    """
    manifest = validate_manifest(manifest, REPO)
    _public_repo(api)
    grouped = {}
    for path, item in manifest["entries"].items():
        grouped.setdefault(item["release_id"], []).append((path, item))
    for rid, entries in grouped.items():
        tag = entries[0][1]["tag"]
        release = _request(api, "releases/" + str(rid))
        info = _release(release, tag, published=True)
        if release["id"] != rid:
            raise MediaError("ID de release de medios incorrecto")
        assets = {a["id"]: a for a in _assets(api, rid)}
        declared = {item["name"]: item for item in info["files"].values()}
        observed = {item["name"]: item for item in assets.values()}
        if set(declared) != set(observed):
            raise MediaError("Inventario publicado no coincide con su descriptor")
        for name, expected in declared.items():
            _asset(observed[name], expected, tag)
        seen = set()
        for path, entry in entries:
            expected = {k: entry[k] for k in ("sha256", "bytes", "mime")}
            expected["name"] = entry["sha256"] + "." + _suffix(path)
            if info["files"].get(path) != expected:
                raise MediaError("El descriptor no acredita el medio solicitado")
            _asset(assets.get(entry["asset_id"]), expected, tag, entry["asset_id"])
            if entry["asset_id"] not in seen:
                _download(fetch, entry, path)
                seen.add(entry["asset_id"])


def _find_release(api, tag):
    # The tag endpoint only promises published releases. List authenticated
    # drafts as well, so a lost create response cannot duplicate the batch.
    found = None
    for page in range(1, MAX_RELEASES // 100 + 2):
        items = _request(api, f"releases?per_page=100&page={page}")
        if type(items) is not list or any(type(r) is not dict for r in items):
            raise MediaError("Inventario de releases inválido")
        if page * 100 > MAX_RELEASES and items:
            raise MediaError("Inventario de releases supera el límite de revisión")
        for release in items:
            if release.get("tag_name") == tag:
                if found is not None:
                    raise MediaError("Hay releases duplicados para el lote de medios")
                found = release
        if len(items) < 100:
            return found
    raise MediaError("Inventario de releases incompleto")


class _Journal:
    """Caller-owned durable intent: an unconfirmed prior write is read-only."""
    def __init__(self, journal, descriptor, checkpoint):
        self.value = {} if journal is None else journal
        self.checkpoint = checkpoint
        batch = _batch_hash(descriptor)
        names = {"create", "publish"} | {"upload:" + item["name"]
                                        for item in descriptor["files"].values()}
        if type(self.value) is not dict:
            raise MediaError("Journal de medios inválido")
        if not self.value:
            self.value.update({"schema": 1, "batch_sha256": batch, "operations": {}})
        if (not _keys(self.value, {"schema", "batch_sha256", "operations"})
                or type(self.value["schema"]) is not int or self.value["schema"] != 1
                or self.value["batch_sha256"] != batch
                or type(self.value["operations"]) is not dict
                or set(self.value["operations"]) - names
                or any(not _keys(v, {"state"}) or v["state"] not in ("pending", "confirmed")
                       for v in self.value["operations"].values())):
            raise MediaError("Journal no corresponde al lote de medios")

    def observed(self, operation):
        return operation in self.value["operations"]

    def set(self, operation, state):
        if self.value["operations"].get(operation) == {"state": state}:
            return
        self.value["operations"][operation] = {"state": state}
        if self.checkpoint is not None:
            try:
                self.checkpoint(copy.deepcopy(self.value))
            except Exception:
                raise MediaError("No se pudo guardar el checkpoint de medios") from None


def upload_new(entriesExisting, filesdict, sourceSHA, run, attempt, process, api, fetch,
               *, journal=None, checkpoint=None):
    """Stage, upload, publish and verify one deterministic new-image batch.

    Existing references are preserved. Historical-byte eligibility belongs to
    the caller; an existing logical path can never be replaced here. The only
    mutations are a release with this exact public descriptor and its assets.
    A caller that persists ``journal`` via ``checkpoint(journal_copy)`` also
    prevents repeating an uncertain write after interruption or re-entry.
    """
    if type(entriesExisting) is not dict or type(filesdict) is not dict:
        raise MediaError("Lote de medios inválido")
    existing = (entriesExisting if set(entriesExisting) == {"schema", "repo", "entries"}
                else {"schema": 1, "repo": REPO, "entries": entriesExisting})
    existing = validate_manifest(existing, REPO)
    if (type(sourceSHA) is not str or not _SHA.fullmatch(sourceSHA)
            or type(run) is not str or not _NUMBER.fullmatch(run)
            or type(attempt) is not str or not _NUMBER.fullmatch(attempt)
            or process not in ("mesa", "arranque")):
        raise MediaError("Identidad del lote de medios inválida")
    new_files, payloads = {}, {}
    for path, data in filesdict.items():
        info = _file_info(path, data)
        _decode_image(data, _suffix(path))
        old = existing["entries"].get(path)
        if old is not None:
            if any(old[k] != info[k] for k in ("sha256", "bytes", "mime")):
                raise MediaError("No se puede reemplazar un medio público existente")
            continue
        new_files[path] = info
        payloads[info["name"]] = data
    if len(payloads) > MAX_RELEASE_ASSETS:
        raise MediaError("Demasiados activos nuevos de medios")
    verify_manifest_assets(existing, api, fetch)
    if not new_files:
        return existing
    descriptor = {"schema": 1, "kind": KIND, "repo": REPO, "source_sha": sourceSHA,
                  "run_id": run, "attempt": attempt, "process": process, "files": new_files}
    journal = _Journal(journal, descriptor, checkpoint)
    tag = f"sala-media-{_batch_hash(descriptor)}-{process}"
    release = _find_release(api, tag)
    if release is None:
        if journal.observed("create"):
            raise MediaError("Creación anterior del release no acreditada; no se repite")
        journal.set("create", "pending")
        try:
            release = api.request("releases", {"tag_name": tag, "target_commitish": sourceSHA,
                    "name": tag, "body": _canonical(descriptor).decode(),
                    "draft": True, "prerelease": False})
        except Exception:
            release = _find_release(api, tag)
            if release is None:
                raise MediaError("Creación del release de medios no confirmada") from None
    _release(release, tag, descriptor)
    journal.set("create", "confirmed")
    rid = release["id"]
    expected_by_name = {i["name"]: i for i in new_files.values()}
    assets = {a["name"]: a for a in _assets(api, rid)}
    if set(assets) - set(expected_by_name):
        raise MediaError("El release contiene activos ajenos al lote")
    if not release["draft"]:
        _release(release, tag, descriptor, published=True)
    for name, expected in expected_by_name.items():
        operation = "upload:" + name
        if name not in assets:
            if not release["draft"]:
                raise MediaError("Release público incompleto; no se modifica")
            if journal.observed(operation):
                raise MediaError("Subida anterior del medio no acreditada; no se repite")
            journal.set(operation, "pending")
            try:
                api.upload(release, payloads[name], name=name, content_type=expected["mime"])
            except Exception:
                # One re-read only. Missing means unknown, never another POST.
                reread = {a["name"]: a for a in _assets(api, rid)}
                if name not in reread:
                    raise MediaError("Subida del medio no confirmada") from None
            assets = {a["name"]: a for a in _assets(api, rid)}
            if set(assets) - set(expected_by_name):
                raise MediaError("El release contiene activos ajenos al lote")
        # Draft assets are not anonymously downloadable. Their server digest
        # must prove bytes before publishing, including interrupted uploads.
        _asset(assets.get(name), expected, tag, require_digest=release["draft"])
        journal.set(operation, "confirmed")
    result = copy.deepcopy(existing)
    for path, info in new_files.items():
        asset = assets[info["name"]]
        result["entries"][path] = {k: info[k] for k in ("sha256", "bytes", "mime")}
        result["entries"][path].update({"release_id": rid, "asset_id": asset["id"],
                                      "tag": tag, "url": _url(tag, info["name"])})
    # Check the exact final size (including real IDs) while the batch is still
    # private. An over-budget manifest never makes a draft public.
    result = validate_manifest(result, REPO)
    if release["draft"]:
        if journal.observed("publish"):
            raise MediaError("Publicación anterior del release no acreditada; no se repite")
        journal.set("publish", "pending")
        try:
            api.request("releases/" + str(rid), {"draft": False}, method="PATCH")
        except Exception:
            # Publication may have succeeded before HTTP 500. Read the exact
            # release once; never repeat the PATCH on an uncertain response.
            pass
    release = _request(api, "releases/" + str(rid))
    _release(release, tag, descriptor, published=True)
    if release["id"] != rid:
        raise MediaError("ID de release de medios incorrecto")
    journal.set("publish", "confirmed")
    assets = {a["name"]: a for a in _assets(api, rid)}
    if set(assets) != set(expected_by_name):
        raise MediaError("Inventario publicado no coincide con el lote")
    for path, info in new_files.items():
        asset = assets[info["name"]]
        _asset(asset, info, tag)
        if asset["id"] != result["entries"][path]["asset_id"]:
            raise MediaError("El activo cambió durante la publicación del lote")
    # A usable reference exists only after anonymous downloads match hashes.
    verify_manifest_assets(result, api, fetch)
    return result
