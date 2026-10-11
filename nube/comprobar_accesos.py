#!/usr/bin/env python3
"""Lecturas de autenticación y metadata; no genera, publica ni modifica registros."""
import json
import os
import sys
import urllib.error
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
result = {"mode": "api_metadata_only", "businessWrites": 0, "generatedMedia": 0}
def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.status, json.loads(response.read().decode("utf-8") or "{}")
def error(exc):
    return {"ok": False, "code": type(exc).__name__, "status": getattr(exc, "code", None)}
try:
    import sala_drive
    token = sala_drive._token()
    status, data = get("https://www.googleapis.com/drive/v3/files?pageSize=1&fields=files(id)&supportsAllDrives=true&includeItemsFromAllDrives=true", {"Authorization": "Bearer " + token})
    result["drive"] = {"ok": status == 200, "status": status, "listed": len(data.get("files", []))}
except Exception as exc:
    result["drive"] = error(exc)
try:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("credential_missing")
    models, next_page = [], None
    for _ in range(10):
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"
        if next_page:
            from urllib.parse import quote
            url += "&pageToken=" + quote(next_page, safe="")
        status, data = get(url, {"x-goog-api-key": key})
        models.extend(data.get("models", []))
        next_page = data.get("nextPageToken")
        if not next_page:
            break
    wanted = ["models/gemini-2.5-flash-lite", "models/gemini-3.5-flash-image"]
    result["gemini"] = {"ok": status == 200, "status": status, "complete": not next_page,
                       "modelsListed": len(models), "requestedModels": {name: any(m.get("name") == name for m in models) for name in wanted},
                       "imageModels": [m.get("name") for m in models if "image" in m.get("name", "").lower()]}
except Exception as exc:
    result["gemini"] = error(exc)
try:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise ValueError("credential_missing")
    status, data = get("https://huggingface.co/api/whoami-v2", {"Authorization": "Bearer " + token})
    result["huggingface"] = {"ok": status == 200, "status": status, "role": (data.get("auth", {}).get("accessToken") or {}).get("role")}
except Exception as exc:
    result["huggingface"] = error(exc)
try:
    import modal
    model = modal.Cls.from_name("sala-ltx", "LTX")
    model.hydrate()
    result["modal"] = {"ok": True, "app": "sala-ltx", "class": "LTX", "metadataResolved": True, "gpuInvoked": False}
except Exception as exc:
    result["modal"] = error(exc)
print(json.dumps(result, ensure_ascii=False))
