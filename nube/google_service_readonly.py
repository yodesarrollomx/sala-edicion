#!/usr/bin/env python3
"""Inspect Apps Script API configuration on the existing credential project.

No project identifier is stored in source or receipts. Identity and project are
derived only from the same service-account credential already installed in Sala.
The only POST is Google's non-mutating testIamPermissions operation. No services
are enabled here, no IAM policy is changed, and no credentials are exported.
"""
import json
import os
import re

SCOPE = "https://www.googleapis.com/auth/cloud-platform.read-only"
PERMISSIONS = ("serviceusage.services.get", "serviceusage.services.enable")


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z_]{1,64}", value) else "UNSPECIFIED"


def request_once(session, method, url, token, **kwargs):
    try:
        response = session.request(method, url, headers={"Authorization": "Bearer " + token},
                                   timeout=25, allow_redirects=False, **kwargs)
        data = response.json()
        if response.status_code != 200:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            details = error.get("details", []) if isinstance(error, dict) else []
            reasons = sorted({safe_code(item.get("reason")) for item in details if isinstance(item, dict) and item.get("reason")})
            return {"ok": False, "httpStatus": response.status_code,
                    "status": safe_code(error.get("status")) if isinstance(error, dict) else "UNSPECIFIED",
                    "reasons": reasons}, data
        return {"ok": True, "httpStatus": 200}, data
    except Exception:
        return {"ok": False, "status": "TRANSPORT_OR_JSON_ERROR"}, None


def disabled_credential_consumer(data):
    """Resolve only the authenticated consumer identified by Google's CRM error.

    No quota project or impersonation is used, so this consumer belongs to the
    same credential. Reject other services, malformed names and ambiguity.
    """
    error = data.get("error", {}) if isinstance(data, dict) else {}
    details = error.get("details", []) if isinstance(error, dict) else []
    consumers = set()
    for detail in details:
        if not isinstance(detail, dict) or detail.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo":
            continue
        if detail.get("reason") != "SERVICE_DISABLED" or detail.get("domain") != "googleapis.com":
            continue
        metadata = detail.get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get("service") != "cloudresourcemanager.googleapis.com":
            continue
        consumer = metadata.get("consumer")
        match = re.fullmatch(r"projects/([0-9]+)", consumer) if isinstance(consumer, str) else None
        if match:
            consumers.add(match.group(1))
    return next(iter(consumers)) if len(consumers) == 1 else None


def diagnose(session, token, project_id):
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project_id):
        raise ValueError("invalid_credential_project")
    report = {"mode": "existing_credential_project_service_readonly", "businessWrites": 0,
              "configurationWrites": 0, "iamWrites": 0, "credentialsExported": False,
              "resourceIdentifiersExported": False, "impersonation": False, "retries": 0}
    project_url = "https://cloudresourcemanager.googleapis.com/v3/projects/" + project_id
    status, data = request_once(session, "GET", project_url, token,
                                params={"fields": "name,projectId"})
    project_number = None
    if status["ok"]:
        matches = isinstance(data, dict) and data.get("projectId") == project_id
        name = data.get("name", "") if isinstance(data, dict) else ""
        match = re.fullmatch(r"projects/([0-9]+)", name) if isinstance(name, str) else None
        status["credentialProjectMatched"] = matches and bool(match)
        if status["credentialProjectMatched"]:
            project_number = match.group(1)
    elif "SERVICE_DISABLED" in status.get("reasons", []):
        project_number = disabled_credential_consumer(data)
        status["consumerResolvedFromServiceDisabled"] = project_number is not None
    report["projectMetadata"] = status
    del data
    status, data = request_once(session, "POST", project_url + ":testIamPermissions", token,
                                json={"permissions": list(PERMISSIONS)})
    if status["ok"]:
        permissions = data.get("permissions", []) if isinstance(data, dict) else []
        status["canReadServiceState"] = PERMISSIONS[0] in permissions
        status["canEnableService"] = PERMISSIONS[1] in permissions
    report["permissionTest"] = status
    del data
    if project_number is None:
        report["appsScriptService"] = {"attempted": False, "reason": "PROJECT_NUMBER_NOT_VERIFIED"}
    else:
        url = "https://serviceusage.googleapis.com/v1/projects/" + project_number + "/services/script.googleapis.com"
        status, data = request_once(session, "GET", url, token, params={"fields": "state"})
        if status["ok"]:
            state = data.get("state") if isinstance(data, dict) else None
            status["state"] = state if state in ("ENABLED", "DISABLED") else "UNKNOWN"
        report["appsScriptService"] = status
        del data
    return report


def main():
    try:
        import requests
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(os.environ.get("GDRIVE_SA_JSON", ""))
        if info.get("type") != "service_account":
            raise ValueError("wrong_credential_type")
        project_id = info.get("project_id")
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
        del info
        credentials.refresh(Request())
        report = diagnose(requests.Session(), credentials.token, project_id)
        report["authenticatedAsExistingServiceAccount"] = True
    except Exception:
        report = {"mode": "existing_credential_project_service_readonly", "businessWrites": 0,
                  "configurationWrites": 0, "iamWrites": 0, "credentialsExported": False,
                  "resourceIdentifiersExported": False, "impersonation": False,
                  "authenticatedAsExistingServiceAccount": False, "status": "CREDENTIAL_INITIALIZATION_FAILED"}
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
