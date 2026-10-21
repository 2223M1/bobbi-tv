"""UI-only CE transaction engine. No player, account or installation-state writes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib

BASE = Path('/storage/.bobbi-ui-preview')
LIVE = {'skin': Path('/storage/.kodi/addons/skin.bobbi.cinema'),
        'dialogs': Path('/storage/.kodi/addons/plugin.video.bobbi/resources/skins')}


def allowed(name):
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith('/') or '\\' in name or ':' in name
            or any(part in ('..', '.') for part in parts) or '/'.join(parts) != name):
        return False
    if parts[0] == 'dialogs':
        return len(parts) > 2 and Path(name).suffix.lower() in ('.xml', '.png', '.jpg', '.jpeg', '.webp')
    return parts[0] == 'skin' and (name == 'skin/sounds.xml'
        or name == 'skin/scripts/cinema_keyboard.py'
        or len(parts) > 2 and parts[1] in ('1080p', 'media', 'fonts', 'sounds', 'colors')
        and Path(name).suffix.lower() in ('.xml', '.png', '.jpg', '.jpeg', '.webp', '.ttf', '.otf', '.wav', '.xbt'))


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def hashes(root):
    if not root.is_dir() or root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise RuntimeError('UNSAFE_COMPONENT')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('SYMLINK_IN_COMPONENT')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def save(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != 'nt':
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def rpc(method, params=None):
    query = urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params or {})).encode(),
        {'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(query, timeout=5) as stream:
        response = json.load(stream)
    if 'error' in response:
        raise RuntimeError('KODI_RPC_FAILED')
    return response['result']


def idle():
    if rpc('Player.GetActivePlayers'):
        raise RuntimeError('PLAYBACK_ACTIVE')
    gui = rpc('GUI.GetProperties', {'properties': ['skin', 'currentwindow']})
    if gui['skin']['id'] != 'skin.bobbi.cinema':
        raise RuntimeError('BOBBI_SKIN_NOT_ACTIVE')
    return gui


def reload_skin():
    idle()
    rpc('Input.ExecuteAction', {'action': 'noop'})
    time.sleep(1.3)  # Allow the DIM overlay's close animation to finish.
    subprocess.run(['kodi-send', '--action=ReloadSkin()'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    time.sleep(2)
    return idle()


def framebuffer_png(root=Path('/sys/class/graphics/fb0'), device=Path('/dev/fb0'), height=1080):
    stride = int((root / 'stride').read_text())
    width, virtual_height = map(int, (root / 'virtual_size').read_text().strip().split(','))
    if not 0 < width * 4 <= stride <= 32768 or not 0 < height <= virtual_height <= 16384:
        raise RuntimeError('INVALID_FRAMEBUFFER_DIMENSIONS')
    if (root / 'bits_per_pixel').exists() and int((root / 'bits_per_pixel').read_text()) != 32:
        raise RuntimeError('UNSUPPORTED_FRAMEBUFFER_FORMAT')
    for _ in range(3):
        pan = int((root / 'pan').read_text().split(',')[1])
        if not 0 <= pan <= virtual_height - height:
            raise RuntimeError('INVALID_FRAMEBUFFER_OFFSET')
        with device.open('rb', buffering=0) as stream:
            stream.seek(pan * stride)
            raw = stream.read(height * stride)
        if len(raw) != height * stride:
            raise RuntimeError('INCOMPLETE_FRAMEBUFFER')
        if pan == int((root / 'pan').read_text().split(',')[1]):
            break
    else:
        raise RuntimeError('FRAMEBUFFER_MOVING')
    raw = b''.join(raw[row * stride:row * stride + width * 4] for row in range(height))
    rgba = bytearray(raw)
    rgba[0::4], rgba[2::4] = raw[2::4], raw[0::4]
    scan = b''.join(b'\0' + rgba[row * width * 4:(row + 1) * width * 4] for row in range(height))
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scan, 3)) + chunk(b'IEND', b''))


def capture(run):
    idle()
    path = run / ('framebuffer-' + str(time.time_ns()) + '.png')
    path.write_bytes(framebuffer_png())
    return dict(remote_path=str(path), sha256=digest(path), bytes=path.stat().st_size,
                method='displayed GUI framebuffer; excludes hardware video plane')


def transaction(name):
    if not re.fullmatch(r'preview-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', name or ''):
        raise RuntimeError('INVALID_TRANSACTION')
    path = BASE / name
    if path.is_symlink() or path.resolve().parent != BASE.resolve():
        raise RuntimeError('UNSAFE_TRANSACTION')
    return path


def pending(except_run=None):
    for journal in BASE.glob('preview-*/journal.json'):
        if journal.parent == except_run:
            continue
        if json.loads(journal.read_text())['state'] not in ('committed', 'restored', 'prepared'):
            raise RuntimeError('RECOVER_PREVIOUS_TRANSACTION_FIRST')


def restore(run, journal):
    """All conflicts checked before changing anything. Backups remain immutable."""
    idle()
    for component in journal['components']:
        live = LIVE[component]
        before, after = journal['before'][component], journal['after'][component]
        if live.exists() and hashes(live) not in (before, after):
            raise RuntimeError('ROLLBACK_CONFLICT')
        backup = run / 'backup' / component
        if backup.exists() and hashes(backup) != before:
            raise RuntimeError('BACKUP_CHANGED')
        if not backup.exists() and (not live.exists() or hashes(live) != before):
            raise RuntimeError('BACKUP_MISSING')
    journal['state'] = 'restoring'
    save(run / 'journal.json', journal)
    for component in reversed(journal['components']):
        live = LIVE[component]
        if live.exists() and hashes(live) == journal['before'][component]:
            continue
        staged = run / ('restore-' + component + '-' + str(time.time_ns()))
        shutil.copytree(run / 'backup' / component, staged)
        if live.exists():
            os.replace(live, run / ('retired-' + component + '-' + str(time.time_ns())))
        os.replace(staged, live)
    journal['state'] = 'restored'
    save(run / 'journal.json', journal)
    return reload_skin()


def deploy(run, package_sha):
    journal = json.loads((run / 'journal.json').read_text())
    if journal['state'] != 'prepared':
        raise RuntimeError('TRANSACTION_ALREADY_USED')
    pending(run)
    idle()
    archive = run / 'candidate.zip'
    if digest(archive) != package_sha:
        raise RuntimeError('PACKAGE_CHANGED')
    for component in journal['components']:
        if hashes(LIVE[component]) != journal['before'][component]:
            raise RuntimeError('DEPLOYMENT_BASE_CHANGED')
    stage = run / 'stage'
    stage.mkdir()
    for component in journal['components']:
        shutil.copytree(LIVE[component], stage / component)
    with zipfile.ZipFile(archive) as zipped:
        if len(set(zipped.namelist())) != len(zipped.namelist()) or set(zipped.namelist()) != set(journal['files']):
            raise RuntimeError('PACKAGE_MANIFEST_MISMATCH')
        for info in zipped.infolist():
            if not allowed(info.filename) or info.file_size > 64 * 1024 * 1024 or info.external_attr >> 16 & 0o170000 == 0o120000:
                raise RuntimeError('UNSAFE_PACKAGE_ENTRY')
            raw = zipped.read(info)
            if hashlib.sha256(raw).hexdigest() != journal['files'][info.filename]:
                raise RuntimeError('FILE_CHANGED')
            if info.filename.endswith('.xml'):
                ET.fromstring(raw)
            elif info.filename.endswith('.py'):
                compile(raw, info.filename, 'exec')  # Validate only; never run submitted code here.
            target = stage / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    journal['after'] = {component: hashes(stage / component) for component in journal['components']}
    journal['state'] = 'switching'
    (run / 'backup').mkdir()
    save(run / 'journal.json', journal)
    try:
        idle()
        # No reload until both components are installed. Journaling also covers
        # process death between the two renames; recover/rollback is idempotent.
        for component in journal['components']:
            if hashes(LIVE[component]) != journal['before'][component]:
                raise RuntimeError('DEPLOYMENT_BASE_CHANGED')
            os.replace(LIVE[component], run / 'backup' / component)
            os.replace(stage / component, LIVE[component])
        gui = reload_skin()
        screenshot = capture(run)
        journal['state'] = 'committed'
        save(run / 'journal.json', journal)
        return dict(state='committed', gui=gui, screenshot=screenshot)
    except BaseException:
        restore(run, journal)
        raise


def main(mode, params):
    import fcntl
    if BASE.is_symlink() or any(p.is_symlink() for p in BASE.parents):
        raise RuntimeError('UNSAFE_PREVIEW_ROOT')
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (BASE / 'lease').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if mode == 'status':
            return dict(gui=idle(), manifest={key: hashes(value) for key, value in LIVE.items()})
        run = transaction(params['transaction'])
        if mode == 'prepare':
            pending()
            idle()
            files = params['files']
            if not files or len(files) > 5000 or any(not allowed(name) for name in files):
                raise RuntimeError('INVALID_FILE_SELECTION')
            components = sorted({name.split('/')[0] for name in files})
            before = {component: hashes(LIVE[component]) for component in components}
            if before != params['before']:
                raise RuntimeError('DEPLOYMENT_BASE_CHANGED')
            run.mkdir(mode=0o700)
            save(run / 'journal.json', dict(state='prepared', components=components, before=before, files=files))
            return dict(state='prepared', remote_path=str(run / 'candidate.zip'))
        if mode == 'deploy':
            return deploy(run, params['sha256'])
        if mode == 'rollback':
            journal = json.loads((run / 'journal.json').read_text())
            if journal['state'] == 'prepared':
                return dict(state='prepared', unchanged=True)
            gui = restore(run, journal)
            return dict(state='restored', gui=gui, screenshot=capture(run))
        if mode == 'screenshot':
            return dict(screenshot=capture(run))
        raise RuntimeError('UNKNOWN_OPERATION')


if __name__ == '__main__':
    try:
        print(json.dumps(main(MODE, PARAMS), ensure_ascii=True))
    except Exception as error:
        print(json.dumps(dict(error=type(error).__name__, code=str(error) if re.fullmatch('[A-Z_]+', str(error)) else 'PREVIEW_FAILED')))
        raise SystemExit(1)
