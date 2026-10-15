#!/usr/bin/env python3
"""Manual technical canary; default is GET-only readiness inspection.

The only publishable bytes are the neutral PNG generated here. No production
manifest, snapshot, Sheet, Drive or business endpoint is read or modified.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from medios_publicos import MediaError, REPO, upload_new, verify_manifest_assets
from snapshots_online import GitHub, NoRedirect, OnlineError, Snapshots

SITE = "https://yodesarrollomx.github.io/sala-edicion/"
WIDTH = HEIGHT = 8
MAX_CODE = 4 * 1024 * 1024
MAX_CANARY = 64 * 1024


class SondaError(RuntimeError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canary_png():
    """Own deterministic 8×8 RGB checker, generated without external assets."""
    def chunk(kind, raw):
        return (struct.pack(">I", len(raw)) + kind + raw
                + struct.pack(">I", zlib.crc32(kind + raw) & 0xffffffff))
    pixels = b"".join(b"\0" + b"".join(bytes((48, 64, 80) if (x + y) % 2
                                               else (180, 192, 204))
                                      for x in range(WIDTH)) for y in range(HEIGHT))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels, level=9)) + chunk(b"IEND", b""))


def _dimensions(raw):
    if (type(raw) is not bytes or len(raw) < 24 or not raw.startswith(b"\x89PNG\r\n\x1a\n")
            or raw[12:16] != b"IHDR" or struct.unpack(">II", raw[16:24]) != (WIDTH, HEIGHT)):
        raise SondaError("La imagen técnica no conserva sus dimensiones")


def anonymous_get(url, limit):
    """Bounded GET with no credentials; signed CDN locations stay in memory."""
    try:
        original = urllib.parse.urlsplit(url)
        if (original.scheme != "https" or original.username or original.password
                or original.port not in (None, 443) or original.fragment):
            raise ValueError("url")
        pages = original.hostname == "yodesarrollomx.github.io" and original.path.startswith("/sala-edicion/")
        asset = (original.hostname == "github.com" and not original.query
                 and original.path.startswith("/" + REPO + "/releases/download/"))
        if not pages and not asset:
            raise ValueError("host")
    except (ValueError, TypeError):
        raise SondaError("Destino público no permitido") from None
    opener = urllib.request.build_opener(NoRedirect)
    current = url
    for _ in range(4):
        request = urllib.request.Request(current, headers={"Cache-Control": "no-cache"})
        try:
            with opener.open(request, timeout=60) as response:
                status = response.status
                mime = response.headers.get_content_type()
                raw = response.read(limit + 1)
            if status != 200 or len(raw) > limit:
                raise SondaError("Respuesta pública fuera del contrato de la sonda")
            return status, mime, raw
        except urllib.error.HTTPError as exc:
            if not asset or exc.code not in (301, 302, 303, 307, 308):
                raise SondaError("GET público de la sonda no confirmado") from None
            target = exc.headers.get("Location", "")
            try:
                parsed = urllib.parse.urlsplit(target)
                if (parsed.scheme != "https" or parsed.username or parsed.password
                        or parsed.port not in (None, 443) or parsed.fragment
                        or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                        or (parsed.hostname == "github.com" and (parsed.path != original.path or parsed.query))):
                    raise ValueError("redirect")
            except (ValueError, TypeError):
                raise SondaError("Redirección pública no permitida") from None
            current = target
        except (OSError, urllib.error.URLError, ValueError):
            raise SondaError("GET público de la sonda no confirmado") from None
    raise SondaError("Demasiadas redirecciones públicas")


def _get(get, url, limit, mimes):
    try:
        status, mime, raw = get(url, limit)
    except Exception:
        raise SondaError("Lectura pública de la sonda no confirmada") from None
    if (status != 200 or mime not in mimes or type(raw) is not bytes or len(raw) > limit):
        raise SondaError("HTTP, MIME o bytes públicos fuera del contrato")
    return raw


class _ReaderMarker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.marker, self.script = False, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "sala-medios-publicos" and attrs.get("content") == "1":
            self.marker = True
        if tag == "script":
            parsed = urllib.parse.urlsplit(attrs.get("src", ""))
            if (not parsed.scheme and not parsed.netloc and not parsed.fragment
                    and parsed.path == "medios-publicos.js"):
                self.script = True


def reader_ready(head, index_sha256, reader_sha256, get):
    if (not re.fullmatch(r"[0-9a-f]{40}", head)
            or not re.fullmatch(r"[0-9a-f]{64}", index_sha256)
            or not re.fullmatch(r"[0-9a-f]{64}", reader_sha256)):
        raise SondaError("Falta la identidad exacta del código aprobado")
    nonce = "?sonda=" + str(time.monotonic_ns())
    raw = _get(get, SITE + "version-online.json" + nonce, 32768, {"application/json"})
    try:
        receipt = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SondaError("Recibo Pages no es JSON válido") from None
    if (type(receipt) is not dict or type(receipt.get("schema")) is not int
            or receipt["schema"] != 1 or receipt.get("code_sha") != head):
        raise SondaError("Pages todavía no acredita el HEAD de esta sonda")
    index = _get(get, SITE + "index.html" + nonce, MAX_CODE, {"text/html"})
    script = _get(get, SITE + "medios-publicos.js" + nonce, MAX_CODE,
                  {"application/javascript", "text/javascript"})
    try:
        parser = _ReaderMarker()
        parser.feed(index.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise SondaError("Index del lector no es válido") from None
    if (not parser.marker or not parser.script or sha256(index) != index_sha256
            or sha256(script) != reader_sha256):
        raise SondaError("El lector servido no coincide con el código aprobado")


class ReadOnlyAPI:
    """Second pass rejects mutation intent before forwarding any request."""
    def __init__(self, api):
        self.api, self.repo, self.mutations = api, api.repo, 0

    def request(self, path, body=None, method=None, **kw):
        effective = method or ("GET" if body is None else "POST")
        if effective != "GET" or body is not None:
            self.mutations += 1
            raise SondaError("La reentrada intentó una mutación")
        return self.api.request(path, method=method, **kw)

    def upload(self, *args, **kw):
        self.mutations += 1
        raise SondaError("La reentrada intentó subir otro activo")


def run_canary(*, apply, head, run, attempt, index_sha256, reader_sha256, api_factory,
               publication_proof, get=anonymous_get):
    if type(apply) is not bool or not re.fullmatch(r"[1-9][0-9]*", run) or not re.fullmatch(r"[1-9][0-9]*", attempt):
        raise SondaError("Identidad de ejecución técnica inválida")
    reader_ready(head, index_sha256, reader_sha256, get)
    # The receipt itself is not authority: the shared snapshot guard confirms
    # its successful publicar.yml run, repository, exact HEAD and main branch.
    if not callable(publication_proof):
        raise SondaError("Falta acreditar la publicación del lector con Actions")
    publication_proof()
    png = canary_png()
    _dimensions(png)
    logical = "laminas/_sondas/" + sha256(png) + ".png"

    def fetch(url):
        raw = _get(get, url, MAX_CANARY, {"image/png"})
        _dimensions(raw)
        return raw

    api = api_factory()
    verify_manifest_assets({"schema": 1, "repo": REPO, "entries": {}}, ReadOnlyAPI(api), fetch)
    report = {"schema": 1, "scope": "technical-canary", "aplicar": apply,
              "state": "ready", "code_sha": head, "index_sha256": index_sha256,
              "reader_sha256": reader_sha256,
              "image": {"sha256": sha256(png), "bytes": len(png), "mime": "image/png",
                        "width": WIDTH, "height": HEIGHT}}
    if not apply:
        return report
    manifest = upload_new({}, {logical: png}, head, run, attempt, "arranque", api, fetch, journal={})
    second = ReadOnlyAPI(api_factory())
    other_source = "b" * 40 if head != "b" * 40 else "a" * 40
    try:
        repeated = upload_new({}, {logical: png}, other_source, str(int(run) + 1),
                              str(int(attempt) + 1), "arranque", second, fetch, journal={})
    except Exception:
        if second.mutations:
            raise SondaError("Reentrada sin journal intentó otra escritura") from None
        raise
    if second.mutations or repeated != manifest:
        raise SondaError("La reentrada no conservó el activo público exacto")
    report.update({"state": "verified", "entry": manifest["entries"][logical],
                   "reentry_mutations": second.mutations})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="publicar sólo el PNG técnico neutro")
    parser.add_argument("--salida", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    output = args.salida.resolve()
    if output == root or root in output.parents or args.salida.is_symlink():
        raise SystemExit("El informe debe quedar fuera del árbol de producción")
    try:
        def git(*parts):
            proc = subprocess.run(["git", *parts], cwd=root, capture_output=True, timeout=60)
            if proc.returncode:
                raise SondaError("No se pudo comprobar el código de la sonda")
            return proc.stdout
        head = git("rev-parse", "HEAD").decode("ascii").strip()
        if (os.environ.get("GITHUB_REPOSITORY") != REPO
                or os.environ.get("GITHUB_REF") != "refs/heads/main"
                or os.environ.get("GITHUB_SHA") != head):
            raise SondaError("La sonda requiere el checkout exacto de main")
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise SondaError("Falta el token efímero de la ejecución")
        report = run_canary(apply=args.aplicar, head=head,
                           run=os.environ.get("GITHUB_RUN_ID", ""),
                           attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                           index_sha256=sha256(git("show", head + ":index.html")),
                           reader_sha256=sha256(git("show", head + ":medios-publicos.js")),
                           api_factory=lambda: GitHub(REPO, token),
                           publication_proof=lambda: Snapshots(root, env=os.environ,
                               api=GitHub(REPO, token)).assert_media_reader_published())
        code = 0
    except (SondaError, MediaError, OnlineError) as exc:
        report = {"schema": 1, "scope": "technical-canary", "aplicar": args.aplicar,
                  "state": "failed", "error": str(exc)}
        code = 1
    except Exception:
        report = {"schema": 1, "scope": "technical-canary", "aplicar": args.aplicar,
                  "state": "failed", "error": "La sonda no confirmó sus comprobaciones"}
        code = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
