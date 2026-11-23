import json

NUVIO_ADDONS_KEY = "nuvio_addons"
NUVIO_USER_ADDONS = "nuvio_user_addons"


def encode_selected_ids(ids_list):
    return json.dumps(ids_list)


def decode_selected_ids(raw, *, strict=False):
    if strict:
        from lib.clients.stremio.constants import decode_selected_ids as decode
        return decode(raw, strict=True)
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except (TypeError, ValueError):
        pass
    return [key for key in str(raw).split(",") if key]
