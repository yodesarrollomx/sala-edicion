"""Respaldo generativo CPU; no consume Modal ni requiere una sesión de chat.

Modelo público segmind/tiny-sd, OpenRAIL-M, revisión upstream cad0bd7.
Los pesos se cargan con el unpickler restringido de PyTorch (weights_only),
sin trust_remote_code; nunca se desactiva ese control.
"""
import hashlib
import io
import os
from motores._comun import MotorError

MODELO = "segmind/tiny-sd"
REVISION = "cad0bd7"
_pipe = None


def instancia():
    global _pipe
    if _pipe is None:
        os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        try:
            import torch
            from diffusers import StableDiffusionPipeline
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            _pipe = StableDiffusionPipeline.from_pretrained(
                MODELO, revision=REVISION, torch_dtype=torch.float32,
                use_safetensors=False, token=False)
            _pipe.to("cpu")
            _pipe.enable_attention_slicing()
            _pipe.enable_vae_tiling()
            _pipe.set_progress_bar_config(disable=True)
        except Exception as exc:
            _pipe = None
            raise MotorError("CPU imagen: no se pudo cargar el modelo verificado",
                             intermitente=True) from exc
    return _pipe


def generar(receta, reglas):
    seed = int(hashlib.sha256(receta.encode("utf-8")).hexdigest()[:8], 16)
    try:
        pipe = instancia()
        import torch
        tokens = pipe.tokenizer(receta[:900], truncation=True,
                                max_length=pipe.tokenizer.model_max_length).input_ids
        prompt = pipe.tokenizer.decode(tokens, skip_special_tokens=True)
        image = pipe(
            prompt=prompt, negative_prompt="text, letters, words, logos, watermark",
            width=512, height=640, num_inference_steps=20, guidance_scale=7.5,
            generator=torch.Generator(device="cpu").manual_seed(seed)).images[0]
        if image.size != (512, 640):
            raise ValueError("Dimensiones inesperadas")
        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG")
        return output.getvalue(), "png"
    except MotorError:
        raise
    except Exception as exc:
        raise MotorError("CPU imagen: generación sin confirmar", intermitente=True) from exc
