"""HiDream-I1-Dev: Space oficial gratuito; disponibilidad sin cuota diaria garantizada.

Recibos en laminas/recibos-hidream sobreviven en el snapshot privado de la Sala.
No usa API de pago ni cambia de proveedor al alcanzar cuota.
"""
import datetime as dt
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import time

import sala_cliente as sala
from motores._comun import MotorError

SPACE = "HiDream-ai/HiDream-I1-Dev"
MODELO = "HiDream-I1-Dev"
RAIZ = Path(__file__).resolve().parents[2]
MAX_BYTES = 25 * 1024 * 1024
_FALLOS = 0
_DETENIDO = ""

def validar(datos):
    from PIL import Image
    if not isinstance(datos, bytes) or not 5000 < len(datos) <= MAX_BYTES:
        raise MotorError("HiDream: tamaño de imagen inválido", intermitente=True)
    try:
        im = Image.open(io.BytesIO(datos))
        size = im.size
        if min(size) < 512:
            raise ValueError("resolución")
        im.verify()
        im = Image.open(io.BytesIO(datos)).convert("RGB")
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue(), size
    except (OSError, ValueError):
        raise MotorError("HiDream: archivo no es una imagen válida", intermitente=True) from None

def _client(folder):
    from gradio_client import Client
    kw = {"verbose": False, "download_files": str(folder)}
    name = "token" if "token" in inspect.signature(Client).parameters else "hf_token"
    kw[name] = os.environ.get("HF_TOKEN", "").strip() or None
    return Client(SPACE, **kw)

def generar(receta, reglas):
    from motores.imagen import CupoImagen, ReciboNoConfirmado, ServicioImagen
    global _FALLOS, _DETENIDO
    rules = reglas if isinstance(reglas, dict) else {}
    recipe_sha = hashlib.sha256(receta.encode()).hexdigest()
    rid = str(rules.get("_imagen_request_id") or recipe_sha)
    if not re.fullmatch(r"[a-f0-9]{64}", rid):
        raise MotorError("HiDream: identidad de pedido inválida")
    folder = RAIZ / "laminas" / "recibos-hidream"
    photo, receipt = folder / (rid + ".png"), folder / (rid + ".json")
    if photo.exists() and receipt.exists():
        try:
            d = json.loads(receipt.read_text())
            data = photo.read_bytes()
            if (d.get("modelo") == MODELO and (d.get("receta_sha256") == recipe_sha or rules.get("_imagen_solo_recibo"))
                    and re.fullmatch(r"[a-f0-9]{64}", str(d.get("receta_sha256") or ""))
                    and (d.get("foto_sha256") or d.get("imagen_sha256")) == hashlib.sha256(data).hexdigest()):
                data, _ = validar(data)
                rules["_receta_proveedor_sha256"] = d["receta_sha256"]
                rules["_imagen_recibo_id"] = rid
                rules["_imagen_parametros"] = {"seed": d.get("seed"), "aspect_ratio": "3:4", "space": SPACE}
                return data, "png"
        except (ValueError, OSError, MotorError):
            pass
        # Un mismo ID con otra receta no se sobreescribe ni se regenera a ciegas.
        raise MotorError("HiDream: recibo existente no coincide; requiere conciliación")
    if rules.get("_imagen_solo_recibo"):
        raise ReciboNoConfirmado("HiDream: toma aún sin recibo confirmado", intermitente=True)
    if _DETENIDO:
        raise ServicioImagen("HiDream detenido: " + _DETENIDO, intermitente=True)
    folder.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="hidream-") as tmp:
        try:
            client = _client(Path(tmp))
        except Exception as e:
            _DETENIDO = "servicio gratuito no disponible"
            raise ServicioImagen("HiDream no está disponible: " + sala.redactar(str(e))[:180],
                             intermitente=True) from None
        seed = int(rid[:8], 16) % 1000000
        started = time.monotonic()
        for attempt in range(2):
            job = None
            try:
                job = client.submit(receta, "3:4", (seed + attempt) % 1000000,
                                    api_name="/generate_with_status")
                result = job.result(timeout=300)
                if not isinstance(result, (list, tuple)) or len(result) < 4:
                    raise ValueError("respuesta incompleta")
                path, used_seed, message, details = result[:4]
                if not path:
                    if "No image name in successful response" in str(message):
                        raise RuntimeError("No image name in successful response")
                    raise ValueError("no entregó imagen: " + str(message))
                if not isinstance(details, dict) or details.get("model") != MODELO:
                    raise ValueError("modelo no confirmado")
                if isinstance(path, dict):
                    path = path.get("path")
                p = Path(str(path)).resolve()
                if Path(tmp).resolve() not in p.parents or p.stat().st_size > MAX_BYTES:
                    raise ValueError("archivo fuera del directorio de descarga")
                data, size = validar(p.read_bytes())
                d = {"request_id": rid, "motor": "hidream_demo", "modelo": MODELO, "space": SPACE,
                     "receta_sha256": recipe_sha, "foto_sha256": hashlib.sha256(data).hexdigest(),
                     "resolucion": list(size), "seed": used_seed, "segundos": round(time.monotonic()-started, 2),
                     "run_id": os.environ.get("GITHUB_RUN_ID"), "generado_en": dt.datetime.now(dt.timezone.utc).isoformat()}
                tmp_photo = photo.with_suffix(".part")
                tmp_photo.write_bytes(data); tmp_photo.replace(photo)
                tmp_receipt = receipt.with_suffix(".part")
                tmp_receipt.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
                tmp_receipt.replace(receipt)
                rules["_receta_proveedor_sha256"] = recipe_sha
                rules["_imagen_recibo_id"] = rid
                rules["_imagen_parametros"] = {"seed": d.get("seed"), "aspect_ratio": "3:4", "space": SPACE}
                _FALLOS = 0
                return data, "png"
            except Exception as e:
                msg = sala.redactar(str(e))[:220]
                if "No image name in successful response" in msg and attempt == 0:
                    time.sleep(8)
                    continue
                if job is not None and isinstance(e, TimeoutError):
                    try:
                        job.cancel()
                    except Exception:
                        pass
                if re.search(r"\b429\b|quota|rate.?limit|daily free allocation|GPU.*exceeded", msg, re.I):
                    raise CupoImagen("HiDream: cupo gratuito no disponible; queda pendiente", intermitente=True) from None
                _FALLOS += 1
                if _FALLOS >= 2:
                    _DETENIDO = "dos respuestas consecutivas sin imagen confirmada"
                    raise ServicioImagen("HiDream: " + _DETENIDO, intermitente=True) from None
                raise MotorError("HiDream sin imagen confirmada: " + msg, intermitente=True) from None
    raise MotorError("HiDream: sin imagen confirmada", intermitente=True)
