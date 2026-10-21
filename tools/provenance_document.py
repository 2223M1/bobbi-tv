"""Read exact original notices/manifests embedded in the unified copyright file.

Only build/maintenance tools use this module; it is not a playback dependency.
The repository has one maintained document, while generated packages can keep
the upstream notice filenames expected by their consumers.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

DOCUMENT = 'addons/skin.bobbi.cinema/COPYRIGHT.zh-CN.md'
BLOCK = re.compile(r'^<!-- provenance-file (\{[^\n]+\}) -->\n````(?:text|json)\n(.*?)\n````\n<!-- /provenance-file -->', re.M | re.S)


def records(root):
    path = Path(root) / DOCUMENT
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError('Symlink provenance document')
    text = path.read_text(encoding='utf-8')
    result = {}
    for match in BLOCK.finditer(text):
        info = json.loads(match[1])
        name = info['path']
        parts = PurePosixPath(name)
        if (parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name
                or name != parts.as_posix() or name in result):
            raise ValueError('Invalid or duplicate provenance path')
        raw = match[2].encode('utf-8')
        if info['newline'] == 'crlf':
            raw = raw.replace(b'\n', b'\r\n')
        elif info['newline'] != 'lf':
            raise ValueError('Unknown provenance newline format')
        if len(raw) != info['bytes'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
            raise ValueError('Provenance content digest mismatch: ' + name)
        result[name] = raw
    if text.count('<!-- provenance-file ') != len(result):
        raise ValueError('Malformed provenance block')
    return result


def read_source(root, name):
    root = Path(root)
    bundled = records(root)
    if name in bundled:
        if (root / name).exists():
            raise ValueError('Duplicate standalone provenance source: ' + name)
        return bundled[name]
    path = root / name
    if path.is_symlink():
        raise ValueError('Symlink source')
    return path.read_bytes()


def render(name, raw):
    text = raw.decode('utf-8')
    newline = 'crlf' if b'\r\n' in raw else 'lf'
    if newline == 'crlf' and b'\n' in raw.replace(b'\r\n', b''):
        raise ValueError('Mixed newlines are not a supported original document')
    text = text.replace('\r\n', '\n')
    if '````' in text or '<!-- provenance-file ' in text:
        raise ValueError('Nested provenance delimiter')
    info = dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), newline=newline)
    language = 'json' if name.endswith('.json') else 'text'
    return ('<!-- provenance-file ' + json.dumps(info, ensure_ascii=False) + ' -->\n````'
            + language + '\n' + text + '\n````\n<!-- /provenance-file -->')


def write_source(root, name, raw):
    """Maintenance importers update the existing canonical block, not old files."""
    root = Path(root)
    if name in records(root):
        path = root / DOCUMENT
        text = path.read_text(encoding='utf-8')
        text = BLOCK.sub(lambda m: render(name, raw) if json.loads(m[1])['path'] == name else m[0], text)
        path.write_text(text, encoding='utf-8', newline='\n')
    else:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def component_records(root, component):
    try:
        prefix = Path(component).resolve().relative_to(Path(root).resolve()).as_posix() + '/'
    except ValueError:
        # Isolated fixture/external component: never inject this repository's
        # notices solely because an unrelated directory has the same basename.
        return {}
    return {name[len(prefix):]: raw for name, raw in records(root).items() if name.startswith(prefix)}
