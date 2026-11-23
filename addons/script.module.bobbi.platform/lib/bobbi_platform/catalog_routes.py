"""Stable catalog URL values shared by independent Kodi presentation entries.

These hashes retain saved-route identity; they are not playback authorization.
No renderer, Host lookup, plugin import or account store is discovered here.
"""
import hashlib
import json
from urllib.parse import urlencode

from bobbi_core.typed_ref import KINDS as TYPED_KINDS


def scope_key(account):
    if account.get('reference_kind') in TYPED_KINDS:
        checked = {key: account[key] for key in ('reference_kind', 'source_id', 'namespace')}
        if account['reference_kind'] == 'network_path':
            checked['generation'] = account['generation']
        return hashlib.sha256(json.dumps(checked, sort_keys=True).encode('utf-8')).hexdigest()
    from .pan_accounts import scope
    checked = scope(account, authenticated=True)
    return hashlib.sha256(json.dumps(checked, sort_keys=True).encode('utf-8')).hexdigest()


def route(**params):
    return 'plugin://plugin.video.bobbi/?' + urlencode(
        {key: value for key, value in params.items() if value is not None})


def scope_params(expected):
    if expected.get('reference_kind') in TYPED_KINDS:
        return dict(source=expected['source_id'], namespace=expected['namespace'], scope=scope_key(expected),
                    **({'reference_kind': expected['reference_kind']} if expected['reference_kind'] != 'mounted_path' else {}))
    return dict(provider=expected['provider'], scope=scope_key(expected))
