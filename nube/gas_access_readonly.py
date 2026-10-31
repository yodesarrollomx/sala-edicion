#!/usr/bin/env python3
"""One-shot access diagnosis using Sala's existing service account, without delegation.

Only GET requests reach resource APIs. Source bytes, Google identities, resource
IDs and provider error messages never enter stdout or an artifact. No grants,
configuration changes, publication, function execution or business writes occur.
"""
import json
import os
import re

PROJECTS = {
    "sala": "1GCmrDxEdR7p8hcox6EQXWbaRaM8TBuuuty-r5L68kMaKGoy-ieIqS4Oo",
    "portero": "115k1wTxnEdPaPyAVqDo9-N2mAhS5d50eoQT9W83nxrXe99EfPhwpC_dw",
}
SALA_SHEET = "1PREF0MQ5-Au_wZjZIooVt4Y6vvTWyLCGlKxzAS64aJs"
SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/script.projects.readonly",
    "https://www.googleapis.com/auth/script.deployments.readonly",
)


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z_]{1,64}", value) else "UNSPECIFIED"


def read_once(session, url, token, params=None):
    """No retry. Return sanitized status and transient JSON, never provider prose."""
    try:
        response = session.get(url, headers={"Authorization": "Bearer " + token},
                               params=params, timeout=25, allow_redirects=False)
        data = response.json()
        if response.status_code != 200:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            details = error.get("details", []) if isinstance(error, dict) else []
            reasons = sorted({safe_code(item.get("reason")) for item in details if isinstance(item, dict) and item.get("reason")})
            return {"ok": False, "httpStatus": response.status_code,
                    "status": safe_code(error.get("status")) if isinstance(error, dict) else "UNSPECIFIED",
                    "reasons": reasons}, None
        return {"ok": True, "httpStatus": 200}, data
    except Exception:
        return {"ok": False, "status": "TRANSPORT_OR_JSON_ERROR"}, None


def diagnose(session, token):
    report = {"mode": "service_account_original_projects_readonly", "businessWrites": 0,
              "sourceExported": False, "credentialsExported": False, "impersonation": False,
              "resourceApiMethods": ["GET"], "retries": 0, "projects": {}}
    status, data = read_once(session, "https://www.googleapis.com/drive/v3/files/" + SALA_SHEET,
                             token, {"fields": "id,mimeType,capabilities(canEdit)", "supportsAllDrives": "true"})
    if status["ok"]:
        status["originalSheetMatched"] = isinstance(data, dict) and data.get("id") == SALA_SHEET and data.get("mimeType") == "application/vnd.google-apps.spreadsheet"
        status["canEdit"] = bool((data.get("capabilities") or {}).get("canEdit")) if isinstance(data, dict) else False
    report["salaContainer"] = status
    del data
    for label, script_id in PROJECTS.items():
        base = "https://script.googleapis.com/v1/projects/" + script_id
        entry = {}
        status, data = read_once(session, base, token, {"fields": "scriptId,parentId"})
        if status["ok"]:
            status["originalProjectMatched"] = isinstance(data, dict) and data.get("scriptId") == script_id
            if label == "sala":
                status["originalContainerMatched"] = isinstance(data, dict) and data.get("parentId") == SALA_SHEET
        entry["project"] = status
        del data
        # An explicit rejection closes the route for this project; no repeated
        # attempts against sibling methods with the same rejected identity.
        if not status["ok"]:
            entry["content"] = {"attempted": False, "reason": "PROJECT_READ_REJECTED"}
            entry["deployments"] = {"attempted": False, "reason": "PROJECT_READ_REJECTED"}
        else:
            status, data = read_once(session, base + "/content", token)
            if status["ok"]:
                status["sourceReadable"] = isinstance(data, dict) and isinstance(data.get("files"), list)
            entry["content"] = status
            del data
            status, data = read_once(session, base + "/deployments", token,
                                     {"pageSize": 1, "fields": "deployments(deploymentId),nextPageToken"})
            if status["ok"]:
                status["deploymentsReadable"] = isinstance(data, dict) and isinstance(data.get("deployments", []), list)
                status["hasDeployment"] = bool(data.get("deployments")) if isinstance(data, dict) else False
            entry["deployments"] = status
            del data
        report["projects"][label] = entry
    return report


def main():
    try:
        import requests
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(os.environ.get("GDRIVE_SA_JSON", ""))
        if info.get("type") != "service_account":
            raise ValueError("wrong_credential_type")
        credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        del info
        # No with_subject, user impersonation, credential copy or secret output.
        credentials.refresh(Request())
        report = diagnose(requests.Session(), credentials.token)
        report["authenticatedAsExistingServiceAccount"] = True
    except Exception:
        report = {"mode": "service_account_original_projects_readonly", "businessWrites": 0,
                  "sourceExported": False, "credentialsExported": False, "impersonation": False,
                  "authenticatedAsExistingServiceAccount": False, "status": "CREDENTIAL_INITIALIZATION_FAILED"}
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
