"""Static research inventory only. Never import plugins or launch their daemons.

Produces member hashes for every official/group archive entry and copies only
reviewable original source/artwork. Embedded private keys and runtime account
state are indexed, never copied. Output is research, not an installable addon.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[1]
OLD = Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018/ui-redesign/review-evidence/juku-20261019/research')
TEXT = {'.py', '.xml', '.json', '.txt', '.md', '.po', '.html', '.htm', '.js', '.css', '.sh', '.conf', '.ini', '.yaml', '.yml', '.service'}
ART = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.ttf', '.otf'}
PRIVATE = re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')
CREDENTIAL_LITERAL = re.compile(rb'\b(?:[A-Z0-9_]*_)?(?:API_KEY|SECRET_KEY|ACCESS_TOKEN)\s*=\s*[\x22\x27][A-Za-z0-9_-]{16,}[\x22\x27]')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def safe_member(name):
    path = PurePosixPath(name)
    return not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name


def excluded(name, raw):
    low = name.lower()
    if PurePosixPath(low).suffix in {'.pem', '.key', '.p12', '.pfx', '.db', '.sqlite', '.sqlite3'}:
        return 'key-or-runtime-state-not-copied'
    if PRIVATE.search(raw):
        return 'embedded-private-key-not-copied'
    if CREDENTIAL_LITERAL.search(raw):
        return 'embedded-credential-literal-not-copied'
    if any(part in low.split('/') for part in ('userdata', 'addon_data', '.git')):
        return 'runtime-state-not-copied'
    if not safe_member(name):
        return 'unsafe-path-not-copied'
    return None


def source_index(name, raw):
    text = raw.decode('utf-8-sig')
    tree = ast.parse(text, filename=name)
    result = dict(path=name, lines=len(text.splitlines()), functions=[], classes=[], imports=[])
    def visit(body, prefix=''):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                label = prefix+node.name
                row = dict(name=label, line=node.lineno, end_line=getattr(node, 'end_lineno', None))
                if isinstance(node, ast.ClassDef):
                    result['classes'].append(row)
                else:
                    result['functions'].append(row)
                visit(node.body, label+'.')
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                for field in ('body', 'orelse', 'finalbody'):
                    visit(getattr(node, field, []), prefix)
                for handler in getattr(node, 'handlers', []):
                    visit(handler.body, prefix)
    visit(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result['imports'].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result['imports'].append('.'*node.level+(node.module or ''))
    result['imports'] = sorted(set(result['imports']))
    result['url_hosts'] = sorted(set(re.findall(r'https?://([a-zA-Z0-9.-]+)(?=[:/\s\x22\x27])', text)))
    return result


def inventory_zip(path, out, prefix, copy_mode='official', seen=None):
    seen = seen if seen is not None else {}
    result = dict(source=str(path), bytes=path.stat().st_size, sha256=file_hash(path), members=[], python=[])
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                result['members'].append(dict(path=entry.filename, type='directory'))
                continue
            raw = archive.read(entry)
            row = dict(path=entry.filename, type='file', bytes=len(raw), compressed_bytes=entry.compress_size,
                       sha256=digest(raw))
            suffix = PurePosixPath(entry.filename).suffix.lower()
            reason = excluded(entry.filename, raw)
            should_copy = copy_mode == 'official' and suffix in TEXT | ART
            if copy_mode == 'group':
                # Required entry points/settings plus project-owned helpers.
                should_copy = suffix in TEXT and len(raw) <= 2*1024*1024 and not any(
                    part in entry.filename.lower().split('/') for part in
                    ('site-packages', 'requests', 'urllib3', 'certifi', 'chardet', 'charset_normalizer',
                     'idna', '__pycache__', 'qrcode', 'PIL', 'numpy', 'packaging', 'crypto', 'cryptography'))
            if reason:
                row['copy_status'] = reason
            elif should_copy:
                key = (row['sha256'], suffix)
                if key in seen:
                    row['copy'] = seen[key]
                    row['copy_status'] = 'byte-identical-reference'
                else:
                    target = out/prefix/entry.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    row['copy'] = str(target.relative_to(out)).replace('\\', '/')
                    row['copy_status'] = 'original-byte-copy'
                    seen[key] = row['copy']
            else:
                row['copy_status'] = 'indexed-only'
            if copy_mode == 'official' and suffix == '.py' and not reason:
                try:
                    result['python'].append(source_index(entry.filename, raw))
                except (SyntaxError, UnicodeError) as error:
                    result['python'].append(dict(path=entry.filename, error=type(error).__name__))
            if entry.filename.endswith('/addon.xml') and not reason:
                try:
                    tree = ET.fromstring(raw)
                    row['addon'] = dict(tree.attrib, extensions=[e.attrib for e in tree.findall('extension')],
                        dependencies=[e.attrib for e in tree.findall('./requires/import')])
                except ET.ParseError:
                    row['addon_error'] = 'invalid_xml'
            result['members'].append(row)
    files = [r for r in result['members'] if r['type'] == 'file']
    result['summary'] = dict(files=len(files), directories=len(result['members'])-len(files),
        uncompressed_bytes=sum(r['bytes'] for r in files),
        extensions=dict(Counter(PurePosixPath(r['path']).suffix.lower() or '<none>' for r in files)),
        copy_status=dict(Counter(r['copy_status'] for r in files)))
    return result


def official_snapshot(out):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    result = dict(checked_utc=datetime.now(timezone.utc).isoformat(), transport='direct HTTPS with system TLS validation', files=[])
    urls = ['https://kodi.jukuku.xyz/zips/addons.xml', 'https://kodi.jukuku.xyz/zips/addons.xml.md5',
            'https://kodi.jukuku.xyz/repository.juku-1.0.1.zip']
    for arch in ('arm64', 'x64'):
        urls.append('https://kodi.jukuku.xyz/zips/plugin.video.juku/plugin.video.juku-0.80-linux-'+arch+'.zip')
    for url in urls:
        row = dict(url=url)
        try:
            request = urllib.request.Request(url, headers={'User-Agent':'Kodi/21.3'})
            with opener.open(request, timeout=30) as response:
                raw = response.read(48*1024*1024+1)
                if len(raw) > 48*1024*1024:
                    raise ValueError('bounded_download_exceeded')
                row.update(status=response.status, bytes=len(raw), sha256=digest(raw),
                    date=response.headers.get('Date'), last_modified=response.headers.get('Last-Modified'),
                    etag=response.headers.get('ETag'))
            if url.endswith(('addons.xml', 'addons.xml.md5')):
                target = out/'official'/url.rsplit('/',1)[-1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                row['copy'] = str(target.relative_to(out)).replace('\\','/')
            if url.endswith('/addons.xml'):
                tree = ET.fromstring(raw)
                result['advertised_addons'] = [a.attrib for a in tree]
            if url.endswith('/repository.juku-1.0.1.zip'):
                row['members'] = []
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for entry in archive.infolist():
                        if entry.is_dir():
                            continue
                        body = archive.read(entry)
                        member = dict(path=entry.filename, bytes=len(body), sha256=digest(body))
                        reason = excluded(entry.filename,body)
                        if reason:
                            member['copy_status'] = reason
                        elif PurePosixPath(entry.filename).suffix.lower() in TEXT | ART:
                            target = out/'official'/entry.filename
                            target.parent.mkdir(parents=True,exist_ok=True)
                            target.write_bytes(body)
                            member['copy'] = str(target.relative_to(out)).replace('\\','/')
                        row['members'].append(member)
            # ZIP bytes deliberately not republished: plugin ships device_key.pem.
        except Exception as error:
            row.update(error=type(error).__name__, status=getattr(error, 'code', None))
        result['files'].append(row)
    save_json(out/'official-versions.json', result)
    return result


def group_inventory(root, mirror, out, seen):
    summary = []
    for index, path in enumerate(sorted(root.iterdir(), key=lambda p:p.name)):
        if not path.is_file():
            continue
        row = dict(name=path.name, source=str(path), bytes=path.stat().st_size, sha256=file_hash(path))
        with path.open('rb') as stream:
            row['magic_hex'] = stream.read(16).hex()
        counterpart = mirror/path.name
        row['mirror'] = str(counterpart)
        row['mirror_byte_identical'] = counterpart.is_file() and file_hash(counterpart) == row['sha256']
        identifier = f'{index+1:02d}-{row["sha256"][:12]}'
        if path.suffix.lower() == '.zip':
            inventory = inventory_zip(path, out, 'group-original/'+identifier, 'group', seen)
            save_json(out/'group-members'/(identifier+'.json'), inventory)
            row.update(index='group-members/'+identifier+'.json', archive=inventory['summary'],
                       addons=[m['addon'] for m in inventory['members'] if 'addon' in m])
        elif path.suffix.lower() == '.tar':
            with tarfile.open(path, 'r') as archive:
                entries = []
                for entry in archive:
                    item = dict(path=entry.name, bytes=entry.size, type=entry.type.decode('ascii','replace'))
                    if entry.isfile():
                        stream = archive.extractfile(entry)
                        item['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
                    entries.append(item)
            save_json(out/'group-members'/(identifier+'.json'), dict(source=str(path), members=entries))
            row['index'] = 'group-members/'+identifier+'.json'
        elif path.suffix.lower() == '.xml':
            target = out/'group-original'/identifier/path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = path.read_bytes()
            if not excluded(path.name, raw):
                target.write_bytes(raw)
                row['copy'] = str(target.relative_to(out)).replace('\\','/')
        elif path.suffix.lower() in ('.docx', '.pdf', '.doc'):
            row['document'] = 'indexed; content extraction tracked separately'
        elif zipfile.is_zipfile(path):
            # APK / disguised ZIP: inventory only, do not copy app payload.
            inventory = inventory_zip(path, out, 'unused', 'none', seen)
            save_json(out/'group-members'/(identifier+'.json'), inventory)
            row.update(index='group-members/'+identifier+'.json', archive=inventory['summary'])
        summary.append(row)
    save_json(out/'group-index.json', dict(source_root=str(root), mirror_root=str(mirror),
        files=summary, summary=dict(files=len(summary), bytes=sum(r['bytes'] for r in summary),
                                   mirrored_identical=sum(r['mirror_byte_identical'] for r in summary))))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--official', action='store_true')
    args = parser.parse_args()
    out = REPO/'docs/research/juku-full-20261019/assets'
    seen, records = {}, []
    for arch in ('arm64','x64'):
        stem = 'plugin.video.juku-0.80-linux-'+arch
        source = OLD/'juku080'/stem/(stem+'.zip')
        value = inventory_zip(source, out, 'original/'+arch, seen=seen)
        value['architecture'] = arch
        save_json(out/('plugin-'+arch+'-index.json'), value)
        records.append(value)
    arm, x64 = [{r['path']:r for r in v['members'] if r['type']=='file'} for v in records]
    comparison = dict(identical=[], changed=[], arm_only=[], x64_only=[])
    for name in sorted(set(arm)|set(x64)):
        bucket = ('x64_only' if name not in arm else 'arm_only' if name not in x64 else
                  'identical' if arm[name]['sha256']==x64[name]['sha256'] else 'changed')
        comparison[bucket].append(name)
    save_json(out/'architecture-comparison.json', comparison)
    group = group_inventory(Path('D:/AM6B-Project/AM6B/资源'),
                            Path('C:/Users/theon/Documents/ChatGPT/AM6B/资源'), out, seen)
    official = official_snapshot(out) if args.official else None
    print(json.dumps(dict(plugins=[dict(arch=v['architecture'], sha256=v['sha256'], **v['summary']) for v in records],
                         architecture_counts={k:len(v) for k,v in comparison.items()}, group_files=len(group),
                         official=official['advertised_addons'] if official else None), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
