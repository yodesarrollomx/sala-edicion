#!/usr/bin/env python3
"""Datos públicos versionados en releases draft privados; código continúa por PR.

Identidad: GITHUB_TOKEN del propio workflow. Un mutex Git con fast-forward
serializa escritores sin cancelar procesos distintos en la cola de Actions.
Nunca contiene credenciales ni registros privados. Antes de montar se exige
el recibo exacto de Pages y el hash de cada archivo.

SALA_SNAPSHOT_INCREMENTAL=1 activa la emisión de parches sólo después de
desplegar este lector y drenar consumidores antiguos. Por defecto se emiten
overlays completos, también útiles como checkpoint antes de una reversión.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from revisiones_presentacion import assert_public_bytes

SCHEMA = 1
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PREFIX = "yod-online-"
KIND = "yod-online-public-data"
LOCK_REF = "heads/runtime/online-data-lease"
# El límite de cada ZIP no acredita el tamaño de Pages. El lector admite parches
# encadenados; el sitio final se mide por separado, sin borrar históricos.
MAX_ZIP = 450 * 1024 * 1024
MAX_PLAIN = 900 * 1024 * 1024
AVISO_ZIP = int(MAX_ZIP * 0.75)
MAX_FILE = 25 * 1024 * 1024
MAX_FILES = 10000
MAX_SITE = 900 * 1024 * 1024
MAX_CHAIN = 1024
MEDIA_PATH = "datos/medios-publicos.json"
SALA_PATHS = {
    "arranque": ("laminas/", "datos/tiras/", "datos/arranque.json", MEDIA_PATH),
    "mesa": ("laminas/", "datos/tiras/", "datos/mesa-estado.json", MEDIA_PATH),
    "relevo": ("datos/manifiesto.json",),
    "maquinas": ("datos/maquinas.json",),
    "chinches": ("datos/encargos.json", "datos/piezas.json", "datos/motores_puntaje.json"),
    "revision": ("datos/revision.json",),
    "plan": ("datos/plan-agregados.json",),
}
MARKETING_PATHS = {"metricas": ("metrics.json", "covers/")}


class OnlineError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def allowed(path, prefixes):
    parts = PurePosixPath(path).parts
    if (not isinstance(path, str) or not path or "\\" in path or "\x00" in path
            or path.startswith("/") or ".." in parts or "." in parts
            or str(PurePosixPath(path)) != path
            or any(p.startswith(".") for p in parts)):
        return False
    if Path(path).suffix.lower() not in {".json", ".jpg", ".jpeg", ".png", ".webp"}:
        return False
    return any(path.startswith(p) if p.endswith("/") else path == p for p in prefixes)


def validate_file(path, data):
    if len(data) > MAX_FILE:
        raise OnlineError("Archivo público demasiado grande")
    if path.endswith(".json"):
        try:
            json.loads(data)
            assert_public_bytes(data)
        except (ValueError, UnicodeError) as exc:
            raise OnlineError("JSON público inválido") from exc
    elif path.lower().endswith((".jpg", ".jpeg")) and not data.startswith(b"\xff\xd8\xff"):
        raise OnlineError("JPEG inválido")
    elif path.lower().endswith(".png") and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise OnlineError("PNG inválido")
    elif path.lower().endswith(".webp") and not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        raise OnlineError("WEBP inválido")


def encode_archive(repo, source_sha, files, deleted, prefixes, *, base_id=0, base_data=None):
    if not SHA.fullmatch(source_sha):
        raise OnlineError("SHA de código inválido")
    records = []
    for path, data in sorted(files.items()):
        if not allowed(path, prefixes):
            raise OnlineError("Archivo fuera del contrato público")
        validate_file(path, data)
        records.append({"path": path, "sha256": digest(data), "bytes": len(data)})
    if (len(records) > MAX_FILES or sum(r["bytes"] for r in records) > MAX_PLAIN
            or len(deleted) != len(set(deleted))
            or any(not allowed(p, prefixes) or p in files for p in deleted)):
        raise OnlineError("Manifiesto de snapshot inválido")
    manifest = {"schema": SCHEMA, "repo": repo, "source_sha": source_sha,
                "files": records, "deleted": sorted(deleted)}
    data_sha = digest(canonical({"files": records, "deleted": sorted(deleted)}))
    if base_id:
        if type(base_id) is not int or base_id < 1 or not DIGEST.fullmatch(str(base_data)):
            raise OnlineError("Base incremental inválida")
        manifest.update({"base_snapshot_id": base_id, "base_data_sha": base_data})
        data_sha = digest(canonical({"base_data_sha": base_data, "patch_sha": data_sha}))
    manifest["data_sha"] = data_sha
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Identidad estable entre reintentos (el timestamp ZIP no es un dato).
        for path, data in [("snapshot.json", canonical(manifest)),
                           *(("files/" + p, raw) for p, raw in sorted(files.items()))]:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    result = buf.getvalue()
    if len(result) > MAX_ZIP:
        raise OnlineError("Snapshot comprimido demasiado grande")
    if len(result) > AVISO_ZIP:
        print(f"::warning::Snapshot online en {len(result) // (1024 * 1024)} MiB de "
              f"{MAX_ZIP // (1024 * 1024)} MiB: compactar o sacar medios antes de llegar al límite.")
    return result, manifest


def decode_archive(data, repo, prefixes, expected_hash=None, expected_data=None):
    if len(data) > MAX_ZIP or (expected_hash and digest(data) != expected_hash):
        raise OnlineError("Hash o tamaño del snapshot incorrecto")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if (len(names) != len(set(names)) or len(names) > MAX_FILES + 1
                    or "snapshot.json" not in names
                    or sum(i.file_size for i in infos) > MAX_PLAIN + 1024 * 1024):
                raise OnlineError("ZIP duplicado, incompleto o demasiado grande")
            for i in infos:
                if (i.is_dir() or stat.S_ISLNK(i.external_attr >> 16)
                        or i.file_size > MAX_FILE or i.flag_bits & 1):
                    raise OnlineError("ZIP contiene un tipo o tamaño no admitido")
            manifest = json.loads(z.read("snapshot.json"))
            if (manifest.get("schema") != SCHEMA or manifest.get("repo") != repo
                    or not SHA.fullmatch(str(manifest.get("source_sha", "")))
                    or not isinstance(manifest.get("files"), list)
                    or not isinstance(manifest.get("deleted"), list)):
                raise OnlineError("Manifiesto fuera del contrato")
            files, declared = {}, {"snapshot.json"}
            for r in manifest["files"]:
                if (set(r) != {"path", "sha256", "bytes"} or not allowed(r["path"], prefixes)
                        or r["path"] in files or not DIGEST.fullmatch(str(r["sha256"]))
                        or type(r["bytes"]) is not int or not 0 <= r["bytes"] <= MAX_FILE):
                    raise OnlineError("Registro de archivo inválido")
                name = "files/" + r["path"]
                raw = z.read(name)
                validate_file(r["path"], raw)
                if len(raw) != r["bytes"] or digest(raw) != r["sha256"]:
                    raise OnlineError("El archivo no coincide con su manifiesto")
                files[r["path"]] = raw
                declared.add(name)
            deleted = manifest["deleted"]
            if (len(deleted) != len(set(deleted)) or any(
                    not allowed(p, prefixes) or p in files for p in deleted)
                    or set(names) != declared):
                raise OnlineError("ZIP con archivos no declarados")
            actual = digest(canonical({"files": manifest["files"], "deleted": deleted}))
            if "base_snapshot_id" in manifest or "base_data_sha" in manifest:
                if (type(manifest.get("base_snapshot_id")) is not int
                        or manifest["base_snapshot_id"] < 1
                        or not DIGEST.fullmatch(str(manifest.get("base_data_sha")))):
                    raise OnlineError("Base incremental inválida")
                actual = digest(canonical({"base_data_sha": manifest["base_data_sha"],
                                           "patch_sha": actual}))
            if manifest.get("data_sha") != actual or (expected_data and actual != expected_data):
                raise OnlineError("Identidad de los datos incorrecta")
            return manifest, files
    except OnlineError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise OnlineError("No se pudo validar el snapshot") from exc


def receipt_matches(receipt, *, code_sha, data_sha, snapshot_id, run_id, plan_sha256=None,
                    media_manifest_sha256=None):
    return not receipt_differences(receipt, code_sha=code_sha, data_sha=data_sha,
                                  snapshot_id=snapshot_id, run_id=run_id, plan_sha256=plan_sha256,
                                  media_manifest_sha256=media_manifest_sha256)


def receipt_differences(receipt, *, code_sha, data_sha, snapshot_id, run_id, plan_sha256=None,
                        media_manifest_sha256=None):
    """Sólo nombres fijos de campos; nunca valores ni cuerpos recibidos."""
    if not isinstance(receipt, dict):
        return ["tipo_recibo"]
    expected = {"schema": SCHEMA, "code_sha": code_sha, "data_sha": data_sha,
                "snapshot_id": snapshot_id, "run_id": run_id}
    if plan_sha256 is not None:
        expected["plan_sha256"] = plan_sha256
    if media_manifest_sha256 is not None:
        expected["media_manifest_sha256"] = media_manifest_sha256
    differences = [field for field, value in expected.items() if receipt.get(field) != value]
    if media_manifest_sha256 is None and "media_manifest_sha256" in receipt:
        differences.append("media_manifest_sha256")
    return differences


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, repo, token, sleep=time.sleep):
        self.repo, self.token, self.sleep = repo, token, sleep

    def request(self, path, body=None, method=None, raw=False):
        if not path.startswith("/"):
            path = "/repos/" + self.repo + "/" + path
        req = urllib.request.Request("https://api.github.com" + path,
              data=None if body is None else canonical(body),
              method=method or ("GET" if body is None else "POST"),
              headers={"Authorization": "Bearer " + self.token,
                       "Accept": "application/vnd.github+json",
                       "X-GitHub-Api-Version": "2022-11-28",
                       "Content-Type": "application/json"})
        # Sólo lecturas se reintentan aquí. Una escritura ambigua se reconcilia
        # en su operación por identidad; repetir POST a ciegas duplica versiones.
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    content = r.read()
                break
            except urllib.error.HTTPError as exc:
                if req.get_method() == "GET" and exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                # No cuerpo remoto ni URL firmada/token en logs.
                raise OnlineError("GitHub HTTP " + str(exc.code)) from None
            except (OSError, urllib.error.URLError):
                if req.get_method() == "GET" and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise OnlineError("GitHub no confirmó la operación") from None
        if raw:
            return content
        try:
            return json.loads(content) if content else None
        except ValueError:
            raise OnlineError("GitHub no devolvió JSON válido") from None

    def asset(self, asset_id):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}/releases/assets/{asset_id}",
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/octet-stream"})
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=90) as r:
                data = r.read(MAX_ZIP + 1)
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise OnlineError("No se pudo recuperar el snapshot privado") from None
            url = exc.headers.get("Location", "")
            parsed = urllib.parse.urlsplit(url)
            if (parsed.scheme != "https" or parsed.username or parsed.password
                    or not parsed.hostname or not parsed.hostname.endswith(".githubusercontent.com")):
                raise OnlineError("Destino de descarga no permitido")
            # No reenviar Authorization al destino firmado.
            try:
                with urllib.request.urlopen(url, timeout=90) as r:
                    data = r.read(MAX_ZIP + 1)
            except (OSError, urllib.error.URLError):
                raise OnlineError("Descarga del activo no confirmada") from None
        if len(data) > MAX_ZIP:
            raise OnlineError("Snapshot demasiado grande")
        return data

    def upload(self, release, data, *, name="snapshot.zip", content_type="application/zip"):
        if name != "snapshot.zip":
            match = re.fullmatch(r"[0-9a-f]{64}\.(png|jpg|jpeg|webp)", name)
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
            if not match or content_type != mime[match[1]]:
                raise OnlineError("Activo público fuera del contrato de imágenes")
        elif content_type != "application/zip":
            raise OnlineError("Tipo de snapshot inválido")
        url = release["upload_url"].split("{")[0]
        expected = f"https://uploads.github.com/repos/{self.repo}/releases/{release['id']}/assets"
        if url != expected:
            raise OnlineError("Destino de subida no permitido")
        req = urllib.request.Request(url + "?name=" + urllib.parse.quote(name), data=data, method="POST",
              headers={"Authorization": "Bearer " + self.token,
                       "Content-Type": content_type,
                       "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except (ValueError, OSError, urllib.error.URLError):
            raise OnlineError("Subida del snapshot no confirmada") from None


class Snapshots:
    def __init__(self, root=None, env=None, api=None, clock=time.monotonic, sleep=time.sleep):
        self.env = os.environ if env is None else env
        self.root = Path(root or Path(__file__).resolve().parent.parent).resolve()
        self.repo = self.env.get("GITHUB_REPOSITORY", "")
        self.run = self.env.get("GITHUB_RUN_ID", "")
        self.attempt = self.env.get("GITHUB_RUN_ATTEMPT", "")
        token = self.env.get("GH_TOKEN") or self.env.get("GITHUB_TOKEN")
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo)
                or not self.run.isdecimal() or not self.attempt.isdecimal() or not token):
            raise OnlineError("Se requiere la identidad del workflow de este repositorio")
        self.paths = MARKETING_PATHS if self.repo.endswith("/aurum-board") else SALA_PATHS
        self.prefixes = tuple(dict.fromkeys(p for ps in self.paths.values() for p in ps))
        self.api = api or GitHub(self.repo, token)
        self.clock, self.sleep = clock, sleep
        state_name = self.repo.replace("/", "-") + "-" + self.run + "-" + self.attempt
        self.state_dir = Path(self.env.get("RUNNER_TEMP") or tempfile.gettempdir()) / state_name
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "online.json"
        self._verified_media = None

    def git(self, *args, binary=False):
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=not binary, timeout=120)
        if proc.returncode:
            raise OnlineError("No se pudo comprobar el árbol de código")
        return proc.stdout if binary else proc.stdout.strip()

    def head(self):
        sha = self.git("rev-parse", "HEAD")
        if not SHA.fullmatch(sha):
            raise OnlineError("Código sin SHA válido")
        return sha

    def main(self):
        return self.api.request("git/ref/heads/main")["object"]["sha"]

    def state(self, required=True):
        if not self.state_file.exists():
            if required:
                raise OnlineError("Falta hidratar y validar el snapshot inicial")
            return {}
        return json.loads(self.state_file.read_text())

    def save(self, state):
        self.state_file.write_text(json.dumps(state, sort_keys=True) + "\n")

    def output(self, **values):
        target = self.env.get("GITHUB_OUTPUT")
        if target:
            with open(target, "a", encoding="utf-8") as f:
                for key, value in values.items():
                    if "\n" in str(value):
                        raise OnlineError("Salida multilinea no admitida")
                    f.write(f"{key}={value}\n")
        return values

    def _lock_info(self):
        try:
            sha = self.api.request("git/ref/" + LOCK_REF)["object"]["sha"]
        except OnlineError as exc:
            if str(exc) == "GitHub HTTP 404":
                return None, None
            raise
        commit = self.api.request("git/commits/" + sha)
        try:
            info = json.loads(commit["message"])
        except (ValueError, KeyError):
            raise OnlineError("Mutex de datos sin contrato") from None
        if (info.get("schema") != SCHEMA or info.get("state") not in ("held", "released")
                or not str(info.get("run_id", "")).isdecimal() or type(info.get("expires")) is not int):
            raise OnlineError("Mutex de datos inválido")
        return sha, info

    def acquire(self, process, timeout=1800):
        deadline = self.clock() + timeout
        tree = self.api.request("git/trees", {"tree": [{
            "path": "README.md", "mode": "100644", "type": "blob",
            "content": "Runtime mutex for validated public data; no business records.\n"}]})["sha"]
        while True:
            before, info = self._lock_info()
            busy = info and info["state"] == "held"
            if busy and info["expires"] <= time.time():
                busy = False
            if (busy and info.get("run_id") == self.run
                    and str(info.get("attempt")) == self.attempt
                    and info.get("process") == process):
                # Recuperar el mismo intento después de perder la respuesta del
                # CAS o su estado local. No inventar una segunda concesión.
                state = self.state(required=False)
                state.update({"lease": before, "process": process})
                self.save(state)
                return before
            if busy:
                owner = self.api.request("actions/runs/" + str(info["run_id"]))
                # Actions conserva run_id al reintentar. El intento anterior ya
                # terminó aunque la corrida consultada vuelva a estar activa.
                newer_attempt = (str(owner.get("run_attempt", "")).isdecimal()
                                 and str(info.get("attempt", "")).isdecimal()
                                 and int(owner["run_attempt"]) > int(info["attempt"]))
                busy = owner["status"] != "completed" and not newer_attempt
            if not busy:
                payload = {"schema": SCHEMA, "state": "held", "run_id": self.run,
                           "attempt": self.attempt, "process": process,
                           "expires": int(time.time()) + 7200}
                commit = self.api.request("git/commits", {
                    "message": canonical(payload).decode(), "tree": tree,
                    "parents": [] if before is None else [before]})["sha"]
                try:
                    if before is None:
                        self.api.request("git/refs", {"ref": "refs/" + LOCK_REF, "sha": commit})
                    else:
                        # Non-fast-forward rejects sibling commits: compare-and-swap.
                        self.api.request("git/refs/" + LOCK_REF, {"sha": commit, "force": False},
                                         method="PATCH")
                    state = self.state(required=False)
                    state["lease"] = commit
                    state["process"] = process
                    self.save(state)
                    return commit
                except OnlineError as exc:
                    # GitHub puede haber escrito el ref y devolver 500 después.
                    # La lectura exacta acredita el CAS; nunca usar force=True.
                    observed, _ = self._lock_info()
                    if observed == commit:
                        state = self.state(required=False)
                        state.update({"lease": commit, "process": process})
                        self.save(state)
                        return commit
                    if str(exc) not in ("GitHub HTTP 409", "GitHub HTTP 422"):
                        raise
            if self.clock() >= deadline:
                raise OnlineError("Mutex ocupado: datos conservados, publicación pendiente")
            self.sleep(10)

    def assert_lease(self, lease=None):
        expected = lease or self.state().get("lease")
        sha, info = self._lock_info()
        if (not expected or sha != expected or not info or info["state"] != "held"
                or info["expires"] <= time.time()):
            raise OnlineError("La publicación perdió el mutex; no se puede confirmar")
        return info

    def release(self):
        state = self.state(required=False)
        if not state.get("lease"):
            return
        sha, info = self._lock_info()
        if (info and info["state"] == "released" and info["run_id"] == self.run
                and str(info.get("attempt")) == self.attempt
                and state["lease"] in {
                    p.get("sha") if isinstance(p, dict) else p
                    for p in self.api.request("git/commits/" + sha).get("parents", [])}):
            state.pop("lease", None)
            self.save(state)
            return
        if sha != state["lease"] or info["run_id"] != self.run:
            raise OnlineError("No se libera un mutex de otro proceso")
        info["state"] = "released"
        commit = self.api.request("git/commits", {
            "message": canonical(info).decode(),
            "tree": self.api.request("git/commits/" + sha)["tree"]["sha"],
            "parents": [sha]})["sha"]
        try:
            self.api.request("git/refs/" + LOCK_REF, {"sha": commit, "force": False}, method="PATCH")
        except OnlineError:
            observed, _ = self._lock_info()
            if observed != commit:
                raise
        state.pop("lease", None)
        self.save(state)

    def releases(self):
        releases = []
        for page in range(1, 101):
            batch = self.api.request(f"releases?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise OnlineError("No se pudo leer el historial de snapshots")
            releases.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise OnlineError("Historial de snapshots incompleto; no elegir un padre a ciegas")
        return releases

    def latest(self):
        found = []
        for release in self.releases():
            if not release.get("draft"):
                continue
            try:
                body = json.loads(release["body"] or "")
            except ValueError:
                continue
            if not isinstance(body, dict) or body.get("kind") != KIND:
                continue
            if body.get("schema") == SCHEMA and body.get("repo") == self.repo and body.get("state") == "published":
                self.validate_release(release, body)
                found.append((release, body))
        return max(found, key=lambda r: r[0]["id"]) if found else (None, None)

    def validate_release(self, release, body):
        if (not release.get("draft") or body.get("kind") != KIND
                or body.get("schema") != SCHEMA or body.get("repo") != self.repo
                or body.get("state") not in ("prepared", "published")
                or not SHA.fullmatch(str(body.get("source_sha", "")))
                or not DIGEST.fullmatch(str(body.get("archive_sha256", "")))
                or not DIGEST.fullmatch(str(body.get("data_sha", "")))
                or type(body.get("parent_id")) is not int
                or type(body.get("asset_id")) is not int
                or not any(a["id"] == body["asset_id"] and a["name"] == "snapshot.zip"
                           for a in release.get("assets", []))):
            raise OnlineError("Versión privada inválida")

    def archive(self, release, body):
        self.validate_release(release, body)
        cache = self.state_dir / (body["archive_sha256"] + ".zip")
        raw = cache.read_bytes() if cache.is_file() else self.api.asset(body["asset_id"])
        result = decode_archive(raw, self.repo, self.prefixes,
                              body["archive_sha256"], body["data_sha"])
        if result[0]["source_sha"] != body["source_sha"]:
            raise OnlineError("El código del archivo no coincide con la versión")
        if not cache.exists():
            tmp = cache.with_suffix(".tmp")
            tmp.write_bytes(raw)
            tmp.replace(cache)
        return result

    def download(self, release, body):
        # Los ZIP antiguos son overlays completos. Los nuevos sólo llevan el
        # parche contra el padre; cada enlace acredita id y hash antes de aplicar.
        chain, seen = [], set()
        while True:
            if release["id"] in seen or len(chain) >= MAX_CHAIN:
                raise OnlineError("Cadena de snapshots cíclica o demasiado larga")
            seen.add(release["id"])
            manifest, _ = self.archive(release, body)
            chain.append((release, body))
            base = manifest.get("base_snapshot_id")
            if not base:
                break
            if base != body["parent_id"] or base >= release["id"]:
                raise OnlineError("Padre incremental fuera de orden")
            release = self.api.request("releases/" + str(base))
            body = json.loads(release["body"])
            if body.get("state") != "published" or body.get("data_sha") != manifest["base_data_sha"]:
                raise OnlineError("La base incremental no coincide con el padre publicado")
        files, deleted = {}, set()
        for current, metadata in reversed(chain):
            manifest, patch = self.archive(current, metadata)
            for path in manifest["deleted"]:
                files.pop(path, None)
                deleted.add(path)
            files.update(patch)
            deleted.difference_update(patch)
            if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_PLAIN:
                raise OnlineError("Datos acumulados fuera del presupuesto público")
        resolved = {**manifest, "files": [{"path": p, "sha256": digest(raw), "bytes": len(raw)}
                                          for p, raw in sorted(files.items())],
                    "deleted": sorted(deleted)}
        if MEDIA_PATH in files:
            media = self._parse_media(files[MEDIA_PATH])
            if set(media["entries"]) & (set(files) | deleted):
                raise OnlineError("Un medio externo no puede viajar o borrarse dentro del ZIP")
        return resolved, files

    def _reader_ready(self):
        class ReaderMarker(HTMLParser):
            ready = False
            script = False

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "meta" and attrs.get("name") == "sala-medios-publicos" and attrs.get("content") == "1":
                    self.ready = True
                if tag == "script" and urllib.parse.urlsplit(attrs.get("src", "")).path == "medios-publicos.js":
                    self.script = True
        parser = ReaderMarker()
        try:
            parser.feed(self.git("show", self.head() + ":index.html"))
            script = self.git("show", self.head() + ":medios-publicos.js", binary=True)
        except OnlineError:
            return False
        return parser.ready and parser.script and bool(script)

    def _parse_media(self, raw):
        from medios_publicos import MediaError, validate_manifest
        try:
            manifest = validate_manifest(raw, self.repo)
        except MediaError as exc:
            raise OnlineError(str(exc)) from None
        if not self._reader_ready():
            raise OnlineError("El código aprobado no declara el lector de medios públicos")
        tracked = set(self.git("ls-files", "-z").split("\0"))
        if tracked & set(manifest["entries"]):
            raise OnlineError("No se externalizan rutas históricas de Git")
        return manifest

    def assert_media_reader_published(self):
        """The emitter needs a completed, independently accredited reader deploy."""
        if not self._reader_ready():
            raise OnlineError("El código aprobado no declara el lector de medios públicos")
        source = self.head()
        try:
            site = self.api.request("pages")["html_url"].rstrip("/") + "/"
            parsed = urllib.parse.urlsplit(site)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
                raise ValueError("site")
            query = urllib.parse.urlencode({"lector": source, "check": str(time.time_ns())})
            request = urllib.request.Request(site + "version-online.json?" + query,
                                             headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(32769)
            if len(raw) > 32768:
                raise ValueError("size")
            receipt = json.loads(raw)
        except (KeyError, TypeError, ValueError, UnicodeError, OSError, urllib.error.URLError, OnlineError):
            raise OnlineError("No se acreditó el lector público antes de externalizar") from None
        if (not isinstance(receipt, dict) or type(receipt.get("schema")) is not int
                or receipt["schema"] != SCHEMA or receipt.get("code_sha") != source
                or type(receipt.get("run_id")) is not str
                or not re.fullmatch(r"[1-9][0-9]*", receipt["run_id"])):
            raise OnlineError("El recibo público no acredita el código del lector actual")
        try:
            run = self.api.request("actions/runs/" + receipt["run_id"])
        except OnlineError:
            raise OnlineError("No se acreditó la ejecución pública del lector") from None
        if (not isinstance(run, dict) or type(run.get("id")) is not int
                or str(run["id"]) != receipt["run_id"]
                or not isinstance(run.get("repository"), dict)
                or run["repository"].get("full_name") != self.repo
                or run.get("path") != ".github/workflows/publicar.yml"
                or run.get("head_branch") != "main" or run.get("head_sha") != source
                or run.get("event") not in ("push", "workflow_dispatch")
                or run.get("status") != "completed" or run.get("conclusion") != "success"):
            raise OnlineError("La ejecución de Pages no acredita un lector terminado y compatible")
        return receipt

    def media_manifest(self):
        path = self.root / MEDIA_PATH
        if path.is_symlink():
            raise OnlineError("Manifiesto de medios con symlink")
        return self._parse_media(path.read_bytes()) if path.is_file() else None

    def anonymous_media(self, url):
        """Sólo GET anónimo acotado; las URLs firmadas nunca se guardan ni se loguean."""
        def parsed_url(value):
            try:
                parsed = urllib.parse.urlsplit(value)
                if parsed.port not in (None, 443):
                    raise ValueError("port")
                return parsed
            except (TypeError, ValueError):
                raise OnlineError("URL pública de medio no autorizada") from None
        current, original = url, parsed_url(url)
        if (original.scheme != "https" or original.hostname != "github.com"
                or original.username or original.password or original.query or original.fragment
                or not original.path.startswith("/" + self.repo + "/releases/download/")):
            raise OnlineError("URL pública de medio no autorizada")
        opener = urllib.request.build_opener(NoRedirect)
        for _ in range(4):
            request = urllib.request.Request(current, headers={"Cache-Control": "no-cache"})
            try:
                with opener.open(request, timeout=90) as response:
                    raw = response.read(MAX_FILE + 1)
                if len(raw) > MAX_FILE:
                    raise OnlineError("Descarga pública demasiado grande")
                return raw
            except urllib.error.HTTPError as exc:
                if exc.code not in (301, 302, 303, 307, 308):
                    raise OnlineError("Descarga pública no confirmada") from None
                target = exc.headers.get("Location", "")
                parsed = parsed_url(target)
                if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment
                        or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                        or (parsed.hostname == "github.com" and (parsed.path != original.path or parsed.query))):
                    raise OnlineError("Redirección pública no autorizada") from None
                current = target
            except (OSError, urllib.error.URLError, ValueError):
                raise OnlineError("Descarga pública no confirmada") from None
        raise OnlineError("Demasiadas redirecciones públicas")

    def _assert_media_origin(self, files):
        """A dirty checkout cannot introduce an unacknowledged public map."""
        path = self.root / MEDIA_PATH
        if not path.exists() or MEDIA_PATH in files:
            return
        try:
            raw = self.git("show", self.head() + ":" + MEDIA_PATH, binary=True)
        except OnlineError:
            raise OnlineError("El manifiesto público no procede del snapshot ni de Git aprobado") from None
        if path.read_bytes() != raw:
            raise OnlineError("El manifiesto público no procede del snapshot ni de Git aprobado")

    def _media_cache(self, manifest):
        catalog = {entry["url"]: entry for entry in manifest["entries"].values()}
        directory = self.state_dir / "medios-publicos"
        directory.mkdir(exist_ok=True)

        def fetch(url):
            entry = catalog.get(url)
            if entry is None:
                raise OnlineError("Descarga no declarada en medios públicos")
            cache = directory / entry["sha256"]
            raw = cache.read_bytes() if cache.is_file() else self.anonymous_media(url)
            if len(raw) != entry["bytes"] or digest(raw) != entry["sha256"]:
                raise OnlineError("Los bytes públicos no coinciden con su manifiesto")
            if not cache.exists():
                temp = cache.with_suffix(".tmp")
                temp.write_bytes(raw)
                temp.replace(cache)
            return raw
        return fetch

    def hydrate_media(self):
        manifest = self.media_manifest()
        if not manifest:
            return None
        from medios_publicos import MediaError, verify_manifest_assets
        identity = digest((self.root / MEDIA_PATH).read_bytes())
        fetch = self._media_cache(manifest)
        if self._verified_media != identity:
            try:
                verify_manifest_assets(manifest, self.api, fetch)
            except MediaError as exc:
                raise OnlineError(str(exc)) from None
            self._verified_media = identity
        # Verificar TODO antes de materializar; el caché ya acredita cada objeto.
        for logical, entry in manifest["entries"].items():
            target = self.root / logical
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != self.root):
                raise OnlineError("Destino de medio público con symlink")
            if target.exists() and (not target.is_file() or digest(target.read_bytes()) != entry["sha256"]):
                raise OnlineError("No se sobrescribe una identidad pública existente")
        for logical, entry in manifest["entries"].items():
            target = self.root / logical
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + ".online-tmp")
                temp.write_bytes(fetch(entry["url"]))
                temp.replace(target)
        return manifest

    def _prepare_media(self, state, process, current):
        manifest = self.media_manifest()
        if manifest != state.get("media_baseline") and manifest != state.get("media_prepared"):
            raise OnlineError("No se edita el manifiesto público fuera de su publicador")
        entries = manifest["entries"] if manifest else {}
        if any(current.get(path) != entry["sha256"] for path, entry in entries.items()):
            raise OnlineError("No se modifica ni elimina una identidad pública externalizada")
        if self.env.get("SALA_MEDIOS_PUBLICOS") != "1" or process not in ("mesa", "arranque"):
            return manifest
        from medios_publicos import MediaError, upload_new
        tracked = set(self.git("ls-files", "-z").split("\0"))
        candidates = {path: (self.root / path).read_bytes() for path in current
                      if path.startswith("laminas/") and path not in state["baseline"]
                      and path not in tracked and path not in entries}
        if not candidates:
            return manifest
        if not self._reader_ready():
            raise OnlineError("Desplegar y verificar el lector antes de externalizar imágenes")
        self.assert_media_reader_published()
        # upload_new exige inmutabilidad y una descarga anónima antes de devolver referencias.
        journal = state.setdefault("media_journal", {})
        def checkpoint(value):
            state["media_journal"] = value
            self.save(state)
        try:
            updated = upload_new(entries, candidates, self.head(), self.run, self.attempt,
                                 process, self.api, self.anonymous_media,
                                 journal=journal, checkpoint=checkpoint)
        except MediaError as exc:
            raise OnlineError(str(exc)) from None
        state["media_prepared"] = updated
        self.save(state)
        target = self.root / MEDIA_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".online-tmp")
        temp.write_bytes(canonical(updated) + b"\n")
        temp.replace(target)
        return self.hydrate_media()

    def fingerprint(self):
        files = {}
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root).as_posix()
            if allowed(rel, self.prefixes):
                if path.is_symlink():
                    raise OnlineError("Symlink dentro de datos públicos")
                if path.is_file():
                    files[rel] = digest(path.read_bytes())
        return files

    def apply(self, manifest, files):
        # Todo el ZIP ya validado antes de la primera escritura.
        for path in list(files) + manifest["deleted"]:
            target = self.root / path
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != self.root):
                raise OnlineError("Destino de snapshot con symlink")
        for path in manifest["deleted"]:
            target = self.root / path
            if target.exists():
                target.unlink()
        for path, raw in files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".online-tmp")
            tmp.write_bytes(raw)
            tmp.replace(target)

    def bootstrap(self, process=None, lock=False):
        if process and process not in self.paths:
            raise OnlineError("Proceso sin contrato")
        if lock:
            self.acquire(process)
        state = self.state(required=False)
        release, body = self.latest()
        files = {}
        if release:
            manifest, files = self.download(release, body)
            self.apply(manifest, files)
        self._assert_media_origin(files)
        media = self.hydrate_media()
        state.update({"source_sha": self.head(), "parent_id": release["id"] if release else 0,
                      "baseline": self.fingerprint(), "data_sha": body["data_sha"] if body else digest(canonical({"files": [], "deleted": []}))})
        state["parent_data_sha"] = state["data_sha"]
        state["media_baseline"] = media
        state.pop("media_prepared", None)
        self.save(state)
        return self.output(snapshot_id=state["parent_id"], hidratado="si")

    def prepare(self, process):
        if process not in self.paths:
            raise OnlineError("Proceso sin contrato")
        state = self.state()
        self.assert_lease()
        source = self.head()
        if source != state["source_sha"] or self.main() != source:
            raise OnlineError("main avanzó; se requiere una nueva ejecución")
        current = self.fingerprint()
        changed = {p for p in set(current) | set(state["baseline"])
                   if current.get(p) != state["baseline"].get(p)}
        if any(not allowed(p, self.paths[process]) for p in changed):
            raise OnlineError("El productor cambió datos de otro proceso")
        if not changed:
            state["prepared_id"] = 0
            self.save(state)
            return self.output(hubo="no", merge_sha=source, snapshot_id=state["parent_id"])
        paths = set(self.git("diff", "--name-only", "HEAD").splitlines())
        if any(not allowed(p, self.prefixes) for p in paths):
            raise OnlineError("El productor alteró código; se requiere PR")
        media = self._prepare_media(state, process, current)
        if media:
            current = self.fingerprint()
            changed = {p for p in set(current) | set(state["baseline"])
                       if current.get(p) != state["baseline"].get(p)}
        incremental = self.env.get("SALA_SNAPSHOT_INCREMENTAL") == "1"
        if incremental:
            candidates = sorted(changed)
        else:
            # Desplegar primero el lector compatible y drenar jobs antiguos.
            # Sin activar el flag seguimos emitiendo overlays completos v1.
            untracked = self.git("ls-files", "--others", "--exclude-standard").splitlines()
            candidates = sorted(p for p in paths | set(untracked) if allowed(p, self.prefixes))
        external = set(media["entries"]) if media else set()
        files = {p: (self.root / p).read_bytes() for p in candidates
                 if p not in external and (self.root / p).is_file()}
        deleted = [p for p in candidates if not (self.root / p).exists()]
        self.site_files()  # Presupuesto FINAL antes de crear/subir otra versión.
        raw, manifest = encode_archive(self.repo, source, files, deleted, self.prefixes,
                                      base_id=state["parent_id"] if incremental else 0,
                                      base_data=state["parent_data_sha"])
        body = {"schema": SCHEMA, "repo": self.repo, "kind": KIND,
                "process": process, "source_sha": source, "parent_id": state["parent_id"],
                "archive_sha256": digest(raw), "data_sha": manifest["data_sha"],
                "lease": state["lease"], "run_id": self.run,
                "attempt": self.attempt}
        def existing():
            found = []
            for candidate in self.releases():
                try:
                    metadata = json.loads(candidate.get("body") or "")
                except ValueError:
                    continue
                if (candidate.get("draft") and isinstance(metadata, dict)
                        and all(metadata.get(k) == v for k, v in body.items())):
                    found.append(candidate)
            if len(found) > 1:
                raise OnlineError("Más de un snapshot coincide con esta operación")
            return found[0] if found else None
        release = existing()
        if not release:
            try:
                release = self.api.request("releases", {
                    "tag_name": PREFIX + self.run + "-" + self.attempt + "-" + process,
                    "target_commitish": source, "name": "Datos online " + process,
                    "draft": True, "body": canonical({**body, "state": "uploading"}).decode()})
            except OnlineError:
                release = existing()
                if not release:
                    raise
        assets = [a for a in release.get("assets", []) if a.get("name") == "snapshot.zip"]
        if len(assets) > 1:
            raise OnlineError("Activos duplicados en el snapshot")
        if assets:
            asset = assets[0]
        else:
            try:
                asset = self.api.upload(release, raw)
            except OnlineError:
                release = self.api.request("releases/" + str(release["id"]))
                assets = [a for a in release.get("assets", []) if a.get("name") == "snapshot.zip"]
                if len(assets) != 1:
                    raise
                asset = assets[0]
        if digest(self.api.asset(asset["id"])) != body["archive_sha256"]:
            raise OnlineError("El snapshot subido no coincide")
        body.update({"state": "prepared", "asset_id": asset["id"]})
        if json.loads(release["body"]).get("state") != "published":
            try:
                self.api.request("releases/" + str(release["id"]),
                                 {"body": canonical(body).decode(), "draft": True,
                                  "tag_name": PREFIX + body["run_id"] + "-" + self.attempt + "-" + process}, method="PATCH")
            except OnlineError:
                observed = self.api.request("releases/" + str(release["id"]))
                if json.loads(observed["body"]) != body:
                    raise
        state.update({"prepared_id": release["id"], "data_sha": body["data_sha"]})
        self.save(state)
        return self.output(hubo="si", merge_sha=source, snapshot_id=release["id"],
                           data_sha=body["data_sha"])

    def dispatch_publish(self, sha, timeout=1200):
        state = self.state()
        if not SHA.fullmatch(sha) or self.main() != sha:
            raise OnlineError("Código de publicación sin confirmar")
        self.assert_lease()
        rid = state.get("prepared_id") or state["parent_id"]
        publication = f"datos-{self.run}-{self.attempt}-{state.get('process', 'manual')}"
        deadline = self.clock() + timeout
        title = f"Sala · publicacion={publication} · sha={sha}"
        def matching_runs():
            runs = self.api.request("actions/workflows/publicar.yml/runs?event=workflow_dispatch&per_page=100")["workflow_runs"]
            found = [r for r in runs if r.get("display_title") == title
                     and r.get("head_sha") == sha and r.get("head_branch") == "main"]
            if len(found) > 1:
                raise OnlineError("Más de una publicación coincide; no montar")
            return found[0] if found else None
        run = matching_runs()
        if not run:
            try:
                self.api.request("actions/workflows/publicar.yml/dispatches", {
                    "ref": "main", "inputs": {"sha": sha, "publicacion_id": publication,
                                              "snapshot_id": str(rid), "lease": state["lease"]}})
            except OnlineError:
                # Una respuesta perdida no autoriza duplicar el dispatch. Su
                # identidad exacta se reconcilia en el mismo bucle de lectura:
                # Actions puede tardar en indexar una corrida ya aceptada.
                pass
        while self.clock() < deadline:
            run = matching_runs()
            if run and run["status"] == "completed":
                release = self.api.request("releases/" + str(rid)) if rid else None
                body = json.loads(release["body"]) if release else None
                if release:
                    self.validate_release(release, body)
                    if body["state"] != "published" or body["data_sha"] != state["data_sha"]:
                        raise OnlineError("Pages no confirmó el snapshot")
                if run["conclusion"] != "success" and not (body and body.get("published_code_sha") == sha
                        and str(body.get("published_run")) == str(run["id"])):
                    raise OnlineError("Pages falló; snapshot conservado sin montar")
                self.verify_receipt(sha, state["data_sha"], rid, str(run["id"]))
                if run["conclusion"] != "success":
                    print("::warning::Pages acredita la publicación exacta; falló un paso posterior del workflow.")
                state["published_receipt"] = {"schema": SCHEMA, "code_sha": sha,
                    "data_sha": state["data_sha"], "snapshot_id": rid, "run_id": str(run["id"])}
                media_hash = self.media_hash_for_receipt()
                if media_hash:
                    state["published_receipt"]["media_manifest_sha256"] = media_hash
                self.save(state)
                return self.output(publicado="si", snapshot_id=rid, pages_run=run["id"])
            self.sleep(10)
        raise OnlineError("Pages sin recibo a tiempo; snapshot conservado")

    def stage(self, sha, snapshot_id=0, lease=None):
        if not SHA.fullmatch(sha) or self.main() != sha or self.head() != sha:
            raise OnlineError("Sólo se publica código de main confirmado")
        if snapshot_id:
            if not lease:
                raise OnlineError("Falta mutex del productor")
            self.assert_lease(lease)
            release = self.api.request("releases/" + str(snapshot_id))
            body = json.loads(release["body"])
            self.validate_release(release, body)
            latest, _ = self.latest()
            if body["state"] == "prepared" and (body["source_sha"] != sha
                    or body.get("lease") != lease or body["parent_id"] != (latest["id"] if latest else 0)):
                raise OnlineError("Snapshot concurrente o código diferente")
        else:
            release, body = self.latest()
        files = {}
        if release:
            manifest, files = self.download(release, body)
            self.apply(manifest, files)
            data_sha, rid = body["data_sha"], release["id"]
        else:
            data_sha, rid = digest(canonical({"files": [], "deleted": []})), 0
        self._assert_media_origin(files)
        media = self.hydrate_media()
        receipt = {"schema": SCHEMA, "code_sha": sha, "data_sha": data_sha,
                   "snapshot_id": rid, "run_id": self.run}
        plan_file = self.root / "datos" / "plan-agregados.json"
        if plan_file.is_file():
            receipt["plan_sha256"] = digest(plan_file.read_bytes())
        if media:
            receipt["media_manifest_sha256"] = digest((self.root / MEDIA_PATH).read_bytes())
        (self.root / "version-online.json").write_bytes(canonical(receipt) + b"\n")
        state = {"source_sha": sha, "snapshot_id": rid, "data_sha": data_sha,
                 "lease": lease, "staged_receipt": receipt}
        self.save(state)
        return self.output(snapshot_id=rid, data_sha=data_sha)

    def site_files(self):
        media = self.hydrate_media()
        external = set(media["entries"]) if media else set()
        # Sólo archivos de Git aprobado y outputs allowlisted. Nunca logs ni credenciales.
        tracked = self.git("ls-files", "-z").split("\0")
        public = set(tracked) | set(self.fingerprint()) | {"version-online.json"}
        files, total = {}, 0
        for rel in sorted(public):
            if not rel or rel.startswith(".github/") or rel.startswith(".git"):
                continue
            if rel in external:
                continue
            path = self.root / rel
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != self.root):
                raise OnlineError("Bundle con symlink")
            if path.is_file():
                if rel.endswith('.json'):
                    try:
                        assert_public_bytes(path.read_bytes())
                    except ValueError as exc:
                        raise OnlineError("Bundle con revisión privada sin proyectar") from exc
                files[rel] = path
                total += path.stat().st_size
        if "version-online.json" not in files:
            total += 32768  # Reserva para el recibo aún no creado en preparar.
        if total > MAX_SITE:
            raise OnlineError(f"Sitio público de {total} bytes excede el presupuesto de {MAX_SITE}; "
                              "conservar históricos y migrar medios antes de publicar")
        if total > MAX_SITE * 0.9:
            print(f"::warning::Sitio público en {total} de {MAX_SITE} bytes; externalizar derivados nuevos.")
        return files

    def build_site(self, destination):
        import shutil
        dest = Path(destination).resolve()
        if dest == self.root or self.root in dest.parents:
            raise OnlineError("El bundle debe estar fuera del checkout")
        self.plan_hash_for_receipt()  # Detectar cambios posteriores a stage antes de publicar.
        self.media_hash_for_receipt()
        files = self.site_files()  # Fallar antes de tocar un bundle anterior.
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for rel, path in files.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        return self.output(bundle="si")

    def plan_hash_for_receipt(self):
        plan_file = self.root / "datos" / "plan-agregados.json"
        actual = digest(plan_file.read_bytes()) if plan_file.is_file() else None
        staged = self.state(required=False).get("staged_receipt")
        if isinstance(staged, dict) and staged.get("plan_sha256") != actual:
            raise OnlineError("El plan local cambió después de stage; campo=plan_sha256")
        return actual

    def media_hash_for_receipt(self):
        manifest = self.media_manifest()
        actual = digest((self.root / MEDIA_PATH).read_bytes()) if manifest else None
        staged = self.state(required=False).get("staged_receipt")
        if isinstance(staged, dict) and staged.get("media_manifest_sha256") != actual:
            raise OnlineError("El manifiesto local cambió después de stage; campo=media_manifest_sha256")
        return actual

    def verify_receipt(self, sha, data_sha, snapshot_id, run_id, timeout=300):
        expected_plan = self.plan_hash_for_receipt()
        expected_media = self.media_hash_for_receipt()
        site = self.api.request("pages")["html_url"].rstrip("/") + "/"
        parsed = urllib.parse.urlsplit(site)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise OnlineError("Sitio Pages sin HTTPS")
        deadline = self.clock() + timeout
        diagnostic = "sin_respuesta"
        previous = None
        while self.clock() < deadline:
            # Cada lectura tiene una clave distinta: no fijar una respuesta vieja
            # de un edge durante toda la espera de propagación del deployment.
            query = urllib.parse.urlencode({"run": run_id, "check": str(time.time_ns())})
            url = site + "version-online.json?" + query
            try:
                req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    receipt = json.loads(response.read(32768))
                differences = receipt_differences(receipt, code_sha=sha, data_sha=data_sha,
                                                 snapshot_id=snapshot_id, run_id=run_id,
                                                 plan_sha256=expected_plan,
                                                 media_manifest_sha256=expected_media)
                if not differences:
                    return receipt
                diagnostic = "campos=" + ",".join(differences)
            except urllib.error.HTTPError as exc:
                diagnostic = ("http=" + str(exc.code)
                              if type(exc.code) is int and 100 <= exc.code <= 599 else "http_error")
            except (ValueError, UnicodeError):
                diagnostic = "json_invalido"
            except (OSError, urllib.error.URLError):
                diagnostic = "transporte"
            if diagnostic != previous:
                print("::warning::ONLINE_RECEIPT " + diagnostic)
                previous = diagnostic
            self.sleep(5)
        raise OnlineError("El sitio no acredita la versión exacta; " + diagnostic)

    def confirm(self):
        state = self.state()
        sha, rid = state["source_sha"], state["snapshot_id"]
        receipt = self.verify_receipt(sha, state["data_sha"], rid, self.run)
        if self.main() != sha:
            raise OnlineError("main avanzó durante la publicación")
        if rid:
            release = self.api.request("releases/" + str(rid))
            body = json.loads(release["body"])
            self.validate_release(release, body)
            if body["state"] == "prepared":
                self.assert_lease(state.get("lease"))
                latest, _ = self.latest()
                if body["parent_id"] != (latest["id"] if latest else 0):
                    raise OnlineError("La versión padre cambió")
                body.update({"state": "published", "published_code_sha": sha,
                             "published_run": self.run, "confirmed_at": int(time.time())})
                try:
                    self.api.request("releases/" + str(rid),
                                     {"body": canonical(body).decode()}, method="PATCH")
                except OnlineError:
                    observed = self.api.request("releases/" + str(rid))
                    if json.loads(observed["body"]) != body:
                        raise
        state["published_receipt"] = state.get("staged_receipt", receipt)
        self.save(state)
        return self.output(publicado="si", snapshot_id=rid)

    def publish_raw(self):
        """Board: datos públicos separados del código de Pages, sin permiso admin."""
        import base64
        state = self.state()
        self.assert_lease()
        source = self.head()
        if self.main() != source or source != state["source_sha"]:
            raise OnlineError("El código cambió durante la medición")
        rid = state.get("prepared_id") or state["parent_id"]
        receipt = {"schema": SCHEMA, "code_sha": source, "data_sha": state["data_sha"],
                   "snapshot_id": rid, "run_id": self.run}
        if self.repo.endswith("/aurum-board"):
            metric_file = self.root / "metrics.json"
            if not metric_file.is_file():
                raise OnlineError("Métricas públicas ausentes")
            receipt["metrics_sha256"] = digest(metric_file.read_bytes())
        ref = "heads/datos-online"
        try:
            before = self.api.request("git/ref/" + ref)["object"]["sha"]
        except OnlineError as exc:
            if str(exc) != "GitHub HTTP 404":
                raise
            before = None
        base_tree = None
        existing = {}
        if before:
            base_tree = self.api.request("git/commits/" + before)["tree"]["sha"]
            entries = self.api.request("git/trees/" + base_tree + "?recursive=1")
            if entries.get("truncated"):
                raise OnlineError("Árbol de datos incompleto")
            for entry in entries["tree"]:
                if entry["type"] == "tree":
                    continue
                path = entry["path"]
                if (entry["mode"] != "100644" or entry["type"] != "blob"
                        or (path != "version-online.json" and not allowed(path, self.prefixes))):
                    raise OnlineError("La rama de datos contiene código o un archivo no permitido")
                existing[path] = entry["sha"]
        files = {p: (self.root / p).read_bytes() for p in self.fingerprint()}
        for path, data in files.items():
            validate_file(path, data)
        files["version-online.json"] = canonical(receipt) + b"\n"
        tree = []
        for path, data in sorted(files.items()):
            blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if existing.get(path) == blob_sha:
                continue
            blob = self.api.request("git/blobs", {
                "encoding": "base64", "content": base64.b64encode(data).decode()})["sha"]
            if blob != blob_sha:
                raise OnlineError("GitHub no confirmó los bytes públicos")
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob})
        for path in set(existing) - set(files):
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        payload = {"tree": tree}
        if base_tree:
            payload["base_tree"] = base_tree
        tree_sha = self.api.request("git/trees", payload)["sha"]
        commit = self.api.request("git/commits", {
            "message": "Datos públicos online " + self.run + " · " + state["data_sha"][:12],
            "tree": tree_sha, "parents": [before] if before else []})["sha"]
        self.assert_lease()
        if self.main() != source:
            raise OnlineError("main avanzó antes de publicar datos")
        if before:
            self.api.request("git/refs/" + ref, {"sha": commit, "force": False}, method="PATCH")
        else:
            self.api.request("git/refs", {"ref": "refs/" + ref, "sha": commit})
        url = f"https://raw.githubusercontent.com/{self.repo}/datos-online/version-online.json"
        deadline = self.clock() + 300
        while self.clock() < deadline:
            try:
                req = urllib.request.Request(url + "?run=" + self.run,
                                              headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    observed = json.loads(response.read(32768))
                if receipt_matches(observed, code_sha=source, data_sha=state["data_sha"],
                                   snapshot_id=rid, run_id=self.run):
                    break
            except (ValueError, OSError, urllib.error.URLError):
                pass
            self.sleep(5)
        else:
            raise OnlineError("La rama pública aún no acredita el recibo exacto")
        self.assert_lease()
        if self.api.request("git/ref/" + ref)["object"]["sha"] != commit:
            raise OnlineError("La publicación de datos cambió concurrentemente")
        if rid and state.get("prepared_id"):
            release = self.api.request("releases/" + str(rid))
            body = json.loads(release["body"])
            self.validate_release(release, body)
            body.update({"state": "published", "published_code_sha": source,
                         "published_run": self.run, "confirmed_at": int(time.time()),
                         "raw_commit": commit})
            self.api.request("releases/" + str(rid), {"body": canonical(body).decode()}, method="PATCH")
        state["published_receipt"] = receipt
        self.save(state)
        return self.output(publicado="si", data_commit=commit, snapshot_id=rid)

    def file_is_published(self, path):
        state = self.state()
        receipt = state.get("published_receipt")
        media_hash = self.media_hash_for_receipt()
        if not receipt or not receipt_matches(receipt, code_sha=self.head(),
                data_sha=state["data_sha"], snapshot_id=receipt["snapshot_id"],
                run_id=receipt["run_id"], media_manifest_sha256=media_hash):
            return False
        relative = Path(path).resolve().relative_to(self.root).as_posix()
        media = self.media_manifest()
        external = media and relative in media["entries"]
        if not receipt["snapshot_id"]:
            try:
                if external:
                    if digest(self.git("show", self.head() + ":" + MEDIA_PATH, binary=True)) != media_hash:
                        return False
                    self.hydrate_media()
                    return digest(Path(path).read_bytes()) == media["entries"][relative]["sha256"]
                return allowed(relative, self.prefixes) and digest(Path(path).read_bytes()) == digest(
                    self.git("show", self.head() + ":" + relative, binary=True))
            except (OnlineError, OSError):
                return False
        release = self.api.request("releases/" + str(receipt["snapshot_id"]))
        body = json.loads(release["body"])
        if body["state"] != "published" or body["data_sha"] != state["data_sha"]:
            return False
        manifest, files = self.download(release, body)
        local = self.root / relative
        if external:
            if MEDIA_PATH not in files or digest(files[MEDIA_PATH]) != media_hash:
                return False
            self.hydrate_media()
            return local.is_file() and digest(local.read_bytes()) == media["entries"][relative]["sha256"]
        # Un archivo base que nunca cambió también debe acreditar su hash Git.
        if relative in files:
            return local.is_file() and digest(local.read_bytes()) == digest(files[relative])
        if relative in manifest["deleted"] or not allowed(relative, self.prefixes):
            return False
        try:
            return digest(local.read_bytes()) == digest(self.git("show", self.head() + ":" + relative, binary=True))
        except (OnlineError, OSError):
            return False


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["bootstrap", "preparar", "publicar", "stage", "confirmar", "liberar", "bundle", "publicar-raw"])
    parser.add_argument("--proceso")
    parser.add_argument("--lock", action="store_true")
    parser.add_argument("--sha")
    parser.add_argument("--snapshot-id", type=int, default=0)
    parser.add_argument("--lease")
    parser.add_argument("--destino")
    args = parser.parse_args()
    s = Snapshots()
    if args.accion == "bootstrap":
        value = s.bootstrap(args.proceso, args.lock)
    elif args.accion == "preparar":
        value = s.prepare(args.proceso)
    elif args.accion == "publicar":
        value = s.dispatch_publish(args.sha)
    elif args.accion == "stage":
        value = s.stage(args.sha, args.snapshot_id, args.lease)
    elif args.accion == "confirmar":
        value = s.confirm()
    elif args.accion == "publicar-raw":
        value = s.publish_raw()
    elif args.accion == "bundle":
        value = s.build_site(args.destino)
    else:
        s.release()
        value = {"liberado": "si"}
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    try:
        cli()
    except OnlineError as exc:
        print("ERROR_ONLINE: " + str(exc))
        raise SystemExit(1)
