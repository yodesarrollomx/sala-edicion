"""LTX-Video en Modal: animación de IA REAL por centavos (28-sep-2026).

Basado en el ejemplo oficial modal-labs/modal-examples · 06_gpu_and_ml/image-to-video.
Modal cobra por segundo de GPU y regala crédito cada mes (5 USD sin tarjeta, 30 USD con
tarjeta registrada, según su propia documentación). Un clip de ~5 s en una L40S son ~1-2 min
de GPU → unos centavos: el crédito gratis alcanza para cientos de escenas al mes.

Se despliega UNA vez (y en cada cambio) desde GitHub Actions: `modal deploy nube/modal_ltx.py`
con los secretos MODAL_TOKEN_ID / MODAL_TOKEN_SECRET. La Sala lo llama desde
`motores/escena_modal.py` con `modal.Cls.from_name('sala-ltx', 'LTX')`.

Devuelve los bytes del MP4 directo (sin Volume de salida): menos piezas que puedan fallar.
El contenedor se apaga a los 2 min sin uso → no se paga tiempo muerto.
"""

import io
import random

import modal

app = modal.App('sala-ltx')

imagen = (
    modal.Image.debian_slim(python_version='3.12')
    .apt_install('python3-opencv', 'ffmpeg')
    .uv_pip_install(
        'accelerate==1.4.0', 'diffusers==0.32.2', 'huggingface-hub==0.36.0',
        'imageio==2.37.0', 'imageio-ffmpeg==0.6.0', 'opencv-python==4.11.0.86',
        'pillow==11.1.0', 'sentencepiece==0.2.0', 'torch==2.6.0', 'torchvision==0.21.0',
        'transformers==4.49.0',
    )
    .env({'HF_XET_HIGH_PERFORMANCE': '1', 'HF_HUB_CACHE': '/models'})
)

MODELO = 'Lightricks/LTX-Video'
REVISION = 'a6d59ee37c13c58261aa79027d3e41cd41960925'   # la del ejemplo oficial
# 28-sep: L40S pide tarjeta registrada; A10G (24 GB) alcanza para LTX 2B en bf16 con el crédito gratis
pesos = modal.Volume.from_name('sala-ltx-pesos', create_if_missing=True)

with imagen.imports():
    import diffusers
    import torch
    from PIL import Image


@app.cls(image=imagen, gpu='A10G', timeout=15 * 60, scaledown_window=2 * 60,
         volumes={'/models': pesos})
class LTX:
    @modal.enter()
    def cargar(self):
        self.pipe = diffusers.LTXImageToVideoPipeline.from_pretrained(
            MODELO, revision=REVISION, torch_dtype=torch.bfloat16).to('cuda')

    @modal.method()
    def animar(self, imagen_bytes: bytes, prompt: str, segundos: float = 5.0,
               ancho: int = 512, alto: int = 640, pasos: int = 30, semilla: int = 0) -> bytes:
        import tempfile
        fps = 24
        # LTX pide 8·k+1 cuadros y lados múltiplos de 32
        cuadros = int(round(segundos * fps / 8)) * 8 + 1
        ancho, alto = ancho // 32 * 32, alto // 32 * 32
        torch.manual_seed(semilla or random.randint(0, 2 ** 31))
        img = Image.open(io.BytesIO(imagen_bytes)).convert('RGB').resize((ancho, alto))
        frames = self.pipe(
            image=img, prompt=prompt,
            negative_prompt=('worst quality, inconsistent motion, blurry, jittery, distorted, '
                             'text, letters, watermark, morphing faces'),
            width=ancho, height=alto, num_frames=cuadros, num_inference_steps=pasos,
        ).frames[0]
        with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
            diffusers.utils.export_to_video(frames, f.name, fps=fps)
            datos = open(f.name, 'rb').read()
        torch.cuda.empty_cache()
        return datos
