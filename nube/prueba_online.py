#!/usr/bin/env python3
"""Prueba técnica sintética: no consulta ni escribe registros de Sala."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import sala_drive as drive
import sala_compositor as compositor
import sala_montador as montador
from motores import imagen_cpu, escena_parallax, voz_kokoro
import sala_guion as guion

ROOT = Path(__file__).resolve().parent
DEST = ROOT / ".producido" / "prueba-online"
DEST.mkdir(parents=True, exist_ok=True)


def metadata(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                             "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True)
    parsed = json.loads(result.stdout)
    return {"duracion_s": float(parsed["format"].get("duration") or 0),
            "streams": [{"tipo": s.get("codec_type"), "codec": s.get("codec_name"),
                         "ancho": s.get("width"), "alto": s.get("height"),
                         "sample_rate": s.get("sample_rate")} for s in parsed["streams"]]}


def main():
    began = time.monotonic()
    raw, _ = imagen_cpu.generar(
        "Photograph of an empty residential courtyard in Sonora, warm natural morning light, "
        "simple stone and desert plants, no people, no text, no letters, no signs, no logos.", {})
    photo = DEST / "imagen.png"
    photo.write_bytes(raw)
    lamina, ligera = compositor.componer(photo, "Prueba técnica de la Sala en línea",
                                         DEST / "lamina.png", firma="Prueba técnica")
    scene, depth = escena_parallax.animar(lamina, DEST / "escena.mp4", 4)
    narration = "Esta es una prueba técnica de voz y edición ejecutada en la nube."
    trabajo = {"pieza": "prueba-tecnica-online", "item": "1"}
    with patch.object(guion, "cargar", return_value={"prueba": True}), \
         patch.object(guion, "partes_de", return_value=[("narrador", narration)]), \
         patch.object(guion, "voz_de", return_value="em_alex"):
        voice = voz_kokoro.producir(trabajo, {}, {}, DEST)
    piece = trabajo["pieza"]
    huella = hashlib.sha256(lamina.read_bytes()).hexdigest()[:8]
    jobs = [{"id": f"{piece}:{stage}:1:{huella}", "pieza": piece, "etapa": stage,
             "item": "1", "estado": "hecho", "evidencia": {"ruta_local": str(path)}}
            for stage, path in (("escena", scene), ("voz", voice))]
    cut_job = {"pieza": piece, "etapa": "corte",
               "evidencia": {"laminas": [{"item": "1", "huella": huella}]}}
    with patch("motores._comun.lamina_de", return_value={"dice": narration}), \
         patch.object(guion, "cargar", return_value={"prueba": True}), \
         patch.object(guion, "partes_de", return_value=[("narrador", narration)]):
        cut = montador.ensamblar(cut_job, {}, {}, DEST, jobs)
    media = {p.name: metadata(p) for p in (scene, voice, cut)}
    cut_streams = media[cut.name]["streams"]
    assert any(s["tipo"] == "video" and s["ancho"] == 1080 and s["alto"] == 1920
               for s in cut_streams), "El corte no confirmó video vertical"
    assert any(s["tipo"] == "audio" for s in cut_streams), "El corte no confirmó audio"
    assert media[voice.name]["duracion_s"] > 1, "Síntesis sin voz"
    run = os.environ["GITHUB_RUN_ID"]
    folder = drive.asegurar_carpeta("1fYi2fCCy-2Wnas0pWn0NdplzkDE0SzGc",
                                  "SALA-prueba-online-" + run)
    files = []
    for path in (photo, lamina, ligera, scene, voice, cut):
        fid = drive.subir(path, folder)
        # Una subida no basta: los bytes recuperados deben coincidir.
        downloaded = DEST / ("recuperado-" + path.name)
        drive.bajar(fid, downloaded)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashlib.sha256(downloaded.read_bytes()).hexdigest() == digest
        files.append({"nombre": path.name, "id": fid, "sha256": digest,
                      "bytes": path.stat().st_size})
        downloaded.unlink()
    report = {"tipo": "prueba_tecnica_sintetica", "run_id": run,
              "cola_escrita": False, "decisiones_escritas": False,
              "motor_imagen": imagen_cpu.MODELO, "revision_modelo": imagen_cpu.REVISION,
              "motor_escena": "parallax", "profundidad": depth,
              "motor_voz": "kokoro", "motor_corte": "ffmpeg",
              "segundos": round(time.monotonic() - began, 1), "archivos": files,
              "media": media, "carpeta": folder}
    report_path = DEST / "informe.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    drive.subir(report_path, folder)
    print("PRUEBA_ONLINE " + json.dumps({
        "ok": True, "archivos_privados_verificados": len(files),
        "segundos": report["segundos"], "profundidad": depth,
        "corte": media[cut.name], "escrituras_negocio": 0}))


if __name__ == "__main__":
    main()
