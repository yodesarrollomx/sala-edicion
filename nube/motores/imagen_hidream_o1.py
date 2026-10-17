"""HiDream O1 oficial: selección explícita gratuita, recibos y sin fallback implícito."""
import datetime as dt
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import tempfile

import sala_cliente as sala
from motores._comun import MotorError
from motores.imagen_hidream import validar

SPACE = "HiDream-ai/HiDream-O1-Image-Dev"
MODELO = "HiDream-O1-Image-Dev"
RAIZ = Path(__file__).resolve().parents[2]
MAX_BYTES = 25 * 1024 * 1024

def _client(folder):
    from gradio_client import Client
    kw = {"verbose": False, "download_files": str(folder)}
    name = "token" if "token" in inspect.signature(Client).parameters else "hf_token"
    kw[name] = os.environ.get("HF_TOKEN", "").strip() or None
    return Client(SPACE, **kw)

def generar(receta, reglas):
    from motores.imagen import CupoImagen, ReciboNoConfirmado, ServicioImagen, RechazoImagen
    rules = reglas if isinstance(reglas, dict) else {}
    recipe_sha = hashlib.sha256(receta.encode()).hexdigest()
    rid = str(rules.get("_imagen_request_id") or recipe_sha)
    if not re.fullmatch(r"[a-f0-9]{64}", rid):
        raise MotorError("HiDream O1: identidad inválida")
    # Mismo almacén ya transportado por snapshots; nueva política da identidad nueva.
    folder = RAIZ / "laminas" / "recibos-hidream"
    photo, receipt = folder / (rid + ".png"), folder / (rid + ".json")
    if photo.exists() or receipt.exists():
        try:
            d = json.loads(receipt.read_text())
            data = photo.read_bytes()
            if not (d.get("modelo") == MODELO and d.get("space") == SPACE
                    and re.fullmatch(r"[a-f0-9]{64}", str(d.get("receta_sha256") or ""))
                    and (d["receta_sha256"] == recipe_sha or rules.get("_imagen_solo_recibo"))
                    and d.get("foto_sha256") == hashlib.sha256(data).hexdigest()):
                raise ValueError("recibo distinto")
            data, _ = validar(data)
            _metadata(rules, d, rid)
            return data, "png"
        except (ValueError, OSError, MotorError):
            raise MotorError("HiDream O1: recibo incompatible; requiere conciliación") from None
    if rules.get("_imagen_solo_recibo"):
        raise ReciboNoConfirmado("HiDream O1: envío pendiente de conciliación", intermitente=True)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hidream-o1-") as tmp:
        try:
            client = _client(Path(tmp))
        except Exception:
            raise RechazoImagen("no_enviado") from None
        seed = int(rid[:8], 16) % 1000000
        job = None
        try:
            job = client.submit(receta, "3:4", False, seed, api_name="/_generate_wrapped")
            result = job.result(timeout=360)
            path = result[0] if isinstance(result, (list, tuple)) and result else None
            if isinstance(path, dict):
                path = path.get("path")
            if not path:
                raise ServicioImagen("HiDream O1 no confirmó imagen; conservar envío para conciliación", intermitente=True)
            p = Path(str(path)).resolve()
            if Path(tmp).resolve() not in p.parents or p.stat().st_size > MAX_BYTES:
                raise ValueError("archivo no permitido")
            data, size = validar(p.read_bytes())
        except ServicioImagen:
            raise
        except Exception as e:
            if job is not None and isinstance(e, TimeoutError):
                try:
                    job.cancel()
                except Exception:
                    pass
            # No tratar un timeout ni un mensaje arbitrario como negativa confirmada.
            raise ServicioImagen("HiDream O1: resultado no confirmado (" + type(e).__name__ + ")",
                                 intermitente=True) from None
        d = {"request_id": rid, "motor": "hidream_o1", "modelo": MODELO, "space": SPACE,
             "receta_sha256": recipe_sha, "foto_sha256": hashlib.sha256(data).hexdigest(),
             "resolucion": list(size), "seed": seed, "aspect_ratio": "3:4", "prompt_refine": False,
             "run_id": os.environ.get("GITHUB_RUN_ID"),
             "generado_en": dt.datetime.now(dt.timezone.utc).isoformat()}
        tmp_photo = photo.with_suffix(".part")
        tmp_photo.write_bytes(data); tmp_photo.replace(photo)
        tmp_receipt = receipt.with_suffix(".part")
        tmp_receipt.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        tmp_receipt.replace(receipt)
        _metadata(rules, d, rid)
        return data, "png"

def _metadata(rules, receipt, rid):
    rules["_receta_proveedor_sha256"] = receipt["receta_sha256"]
    rules["_imagen_recibo_id"] = rid
    rules["_imagen_parametros"] = {"seed": receipt.get("seed"), "aspect_ratio": "3:4",
                                  "prompt_refine": False, "space": SPACE}
