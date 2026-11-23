"""Portable paths and explicit configuration; importing does not touch the disk."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

ADDON_ID = 'script.module.bobbi.platform'
DEFAULTS = {
    'schema': 1, 'profile': 'kodi', 'update_channel': 'preview',
    'automatic_updates': False, 'source_selection': 'manual',
    'audio': 'original', 'subtitles': 'zh', 'transcode': False,
    'library_root': '', 'cd2_url': '', 'helper_url': '',
}


def private_path(translate, relative=''):
    translated = Path(translate('special://profile/addon_data/' + ADDON_ID))
    if not translated.is_absolute():
        raise ValueError('Kodi profile must resolve to an absolute local directory')
    root = translated.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError('Path outside bobbi profile')
    return target


def validate_config(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULTS)
            or type(value['schema']) is not int or value['schema'] != 1):
        raise ValueError('Unknown bobbi configuration schema')
    if value['profile'] not in ('kodi', 'coreelec', 'android'):
        raise ValueError('Unknown platform')
    if value['update_channel'] not in ('preview', 'stable'):
        raise ValueError('Unknown update channel')
    if type(value['automatic_updates']) is not bool:
        raise ValueError('Invalid update preference')
    if (value['source_selection'] != 'manual' or value['audio'] != 'original'
            or value['subtitles'] != 'zh' or value['transcode'] is not False):
        raise ValueError('Unsupported playback policy')
    for key in ('library_root', 'cd2_url', 'helper_url'):
        if not isinstance(value[key], str) or len(value[key]) > 2048 or any(ord(c) < 32 for c in value[key]):
            raise ValueError('Invalid configured endpoint')
    for key in ('cd2_url', 'helper_url'):
        if not value[key]:
            continue
        url = urlsplit(value[key])
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username
                or url.password or url.fragment or url.query):
            raise ValueError('Endpoint must not embed credentials or query parameters')
        if key == 'helper_url' and url.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Android helper is device-local')
    return dict(value)


def load_config(path):
    path = Path(path)
    if not path.exists():
        return dict(DEFAULTS)
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('Invalid configuration file')
    return validate_config(json.loads(path.read_text(encoding='utf-8')))


def save_config(path, value):
    data = json.dumps(validate_config(value), ensure_ascii=False, indent=2) + '\n'
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink configuration path')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.config-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
