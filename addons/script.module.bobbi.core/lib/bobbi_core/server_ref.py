"""Reversible server entry/version/part identity; never a path or a token."""
import json
import re

PROVIDERS = frozenset(('plex', 'jellyfin', 'emby'))


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('SERVER_ID_INVALID')
    return value


def file_id(entry, media, part, index=1, count=1):
    values = [identifier(entry), identifier(media), identifier(part), index, count]
    if type(index) is not int or type(count) is not int or not 1 <= index <= count <= 256:
        raise ValueError('SERVER_ID_INVALID')
    return json.dumps(values, separators=(',', ':'))


def parts(value):
    try:
        values = json.loads(value)
        if type(values) is not list or len(values) != 5 or file_id(*values) != value:
            raise ValueError
        return tuple(values)
    except (ValueError, TypeError):
        raise ValueError('SERVER_ID_INVALID') from None


def resumable(ref):
    # Entry/media/part IDs and size can survive an equal-size replacement.
    # Until a separate content-observation contract exists, local progress is
    # display-only for every server file (including single-part originals).
    return ref['provider'] not in PROVIDERS
