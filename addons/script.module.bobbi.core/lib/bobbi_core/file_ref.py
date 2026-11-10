"""Stable personal-file identity, not playback authority or a transport locator.

Only explicit adapter fields enter this versioned whitelist. A title, account
epoch, library membership and a temporary URL never participate in identity.
"""
from hashlib import sha256
import json
import re

VERSION = 1
PROVIDERS = frozenset(('quark', 'uc', 'baidu', 'aliyun', '123', '139', '189', 'guangya', 'xunlei'))
FIELDS = frozenset(('version', 'id', 'provider', 'account_id', 'namespace', 'file_id',
                    'parent', 'name', 'size', 'fingerprint'))


def _text(value, maximum=1024, empty=False):
    if (type(value) is not str or len(value) > maximum or (not value and not empty)
            or re.search(r'[\x00-\x1f\x7f]', value) or '://' in value):
        raise ValueError('FILE_REF_INVALID')
    return value


def identity(provider, account_id, namespace, file_id):
    if provider not in PROVIDERS:
        raise ValueError('FILE_REF_UNSUPPORTED')
    _text(account_id, 256)
    if not re.fullmatch(re.escape(provider) + r':[0-9a-f]{64}', account_id):
        raise ValueError('FILE_REF_INVALID')
    _text(namespace, 256, empty=True)
    _text(file_id, 256)
    return sha256(json.dumps([provider, account_id, namespace, file_id],
        ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()


def validate(value):
    if type(value) is not dict or set(value) != FIELDS or type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('FILE_REF_SCHEMA_UNSUPPORTED')
    ref = dict(value)
    expected = identity(ref['provider'], ref['account_id'], ref['namespace'], ref['file_id'])
    if ref['id'] != expected or type(ref['size']) is not int or not 0 < ref['size'] <= 512 * 1024**3:
        raise ValueError('FILE_REF_INVALID')
    _text(ref['parent'], 4096, empty=True)
    _text(ref['name'])
    if '/' in ref['name'] or '\\' in ref['name']:
        raise ValueError('FILE_REF_INVALID')
    fingerprint = ref['fingerprint']
    if fingerprint is not None:
        if (type(fingerprint) is not dict or set(fingerprint) != {'kind', 'value'}
                or fingerprint['kind'] not in ('aliyun_content_hash', 'xunlei_hash')
                or fingerprint['kind'].split('_')[0] != ref['provider']
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', _text(fingerprint['value'], 256))):
            raise ValueError('FILE_REF_INVALID')
        ref['fingerprint'] = dict(fingerprint)
    if bool(ref['namespace']) != (ref['provider'] == 'aliyun'):
        raise ValueError('FILE_REF_INVALID')
    return ref


def from_selected(expected, selected, parent):
    if (type(expected) is not dict or expected.get('authenticated') is not True
            or type(selected) is not dict or selected.get('directory') is not False):
        raise ValueError('FILE_REF_UNSUPPORTED')
    provider, file_id = expected['provider'], selected['file_id']
    namespace = ''
    if provider == 'aliyun':
        if type(file_id) is not str or file_id.count(':') != 1:
            raise ValueError('FILE_REF_INVALID')
        namespace, file_id = file_id.split(':')
    # Preserve provider-declared content evidence without guessing its hash
    # algorithm. Etag/storage keys are deliberately not promoted to hashes.
    field = {'aliyun': 'content_hash', 'xunlei': 'hash'}.get(provider)
    fingerprint = (dict(kind=provider + '_' + field, value=selected[field])
                   if field and selected.get(field) else None)
    return validate(dict(version=VERSION,
        id=identity(provider, expected['account_id'], namespace, file_id),
        provider=provider, account_id=expected['account_id'], namespace=namespace,
        file_id=file_id, parent=parent, name=selected['name'], size=selected['size'],
        fingerprint=fingerprint))


def same_file(saved, current):
    saved, current = validate(saved), validate(current)
    return (saved['id'] == current['id'] and saved['size'] == current['size']
            and (saved['fingerprint'] is None or saved['fingerprint'] == current['fingerprint']))


def locator(value):
    ref = validate(value)
    return 'bobbipan://' + ref['provider'] + '/' + ref['id']
