"""Public projection of presentation reviews; originals remain in the Sheet."""
import json
import re

PRIVATE_KIND = "yod-presentation-private-v1"
PRIVATE_KINDS = (PRIVATE_KIND, "chinche-secuencia-v1")
PUBLIC_NOTE = "Revisión privada de presentación: consultar PRODUCCION por ID."
PIN_ID = re.compile(r"CHN-\d{8}-\d{4}-[a-f0-9]{4}")


def contains_private(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get('kind') in PRIVATE_KINDS:
                return True
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            if any(kind in item for kind in PRIVATE_KINDS):
                return True
            if item.lstrip().startswith(('{', '[')):
                try:
                    pending.append(json.loads(item))
                except (ValueError, RecursionError):
                    pass
    return False


def public_projection(value):
    """Return a detached public value, including JSON serialized inside a cell.

    A marked envelope is indivisible: retain its correlation ID and no free text.
    Truncated BITACORA cells are projected too, without depending on valid JSON.
    """
    if isinstance(value, str):
        if not contains_private(value):
            return value
        match = PIN_ID.search(value)
        return json.dumps({"id": match.group(0) if match else None,
                           "texto": PUBLIC_NOTE}, ensure_ascii=False)
    if isinstance(value, list):
        return [public_projection(item) for item in value]
    if isinstance(value, dict):
        if value.get("kind") in PRIVATE_KINDS:
            cid = str(value.get("id", ""))
            return {"id": cid if PIN_ID.fullmatch(cid) else None,
                    "texto": PUBLIC_NOTE}
        return {key: public_projection(item) for key, item in value.items()}
    return value


def assert_public_bytes(data):
    """Reject marked envelopes at snapshot and final bundle boundaries."""
    if any(kind.encode() in data for kind in PRIVATE_KINDS) or contains_private(json.loads(data)):
        raise ValueError("Revisión privada fuera de su proyección pública")
