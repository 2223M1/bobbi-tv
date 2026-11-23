"""Opt-in CoreELEC engine; fixed hashes, private files, no system service edits."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import tempfile
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler, Request
from urllib.parse import urlsplit
from .paths import profile
from .pairing import Pairing, load, save, engine_document
from .torrserver import TorrServerClient, TorrServerError

VERSION = 'MatriX.147'
BINARIES = {
    'arm7': (62259360, '2c70daa57ebbc390024ef5276bdf2dda905ea1cb6e61eb791ba2c706b1505f16'),
    'arm64': (60948640, 'fbe0f668a2a22801db891afb52e1b96e4ec762dcbf979bec2a45917848456a1c'),
}
SETTINGS = {'BitTorr': dict(CacheSize=67108864, PreloadCache=50, ConnectionsLimit=25,
    TorrentDisconnectTimeout=30, ReaderReadAHead=95, ResponsiveMode=True, ShowFSActiveTorr=True,
    StoreSettingsInJson=True, StoreViewedInJson=False, RetrackersMode=0, TrackersListURL='',
    DefaultTrackers='', UseDisk=False, TorrentsSavePath='', EnableBonjour=False, EnableLPD=False,
    EnableDLNA=False, EnableRutorSearch=False, EnableTorznabSearch=False, DisableUPNP=True,
    EnableDebug=False, EnableIPv6=False)}


def architecture():
    try:
        release = Path('/etc/os-release').read_text()
    except OSError:
        raise ValueError('Only CoreELEC is supported by this installer') from None
    if platform.system() != 'Linux' or ('id="coreelec"' not in release.lower() and 'id=coreelec' not in release.lower()):
        raise ValueError('Only CoreELEC is supported by this installer')
    if platform.machine().lower() not in ('aarch64', 'arm64', 'armv7l', 'armv8l'):
        raise ValueError('Unsupported CoreELEC CPU')
    return 'arm64' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'arm7'


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if (parts.scheme != 'https' or parts.hostname not in
                ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com')
                or parts.username or parts.password):
            raise ValueError('Engine download redirect rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def install(cancelled=lambda: False, progress=lambda value: None):
    arch = architecture()
    root = profile(name='engine')
    root.mkdir(exist_ok=True)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Invalid engine path')
    target = root / ('TorrServer-' + VERSION + '-' + arch)
    size, digest = BINARIES[arch]
    if not target.exists() or target.stat().st_size != size or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        fd, temporary = tempfile.mkstemp(dir=str(root), prefix='.engine-')
        try:
            url = 'https://github.com/YouROK/TorrServer/releases/download/' + VERSION + '/TorrServer-linux-' + arch
            opener = build_opener(ProxyHandler({}), Redirect())
            hashed, total = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as output, opener.open(Request(url), timeout=10) as response:
                while True:
                    if cancelled():
                        raise ValueError('Installation cancelled')
                    block = response.read(128 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > size:
                        raise ValueError('Engine size mismatch')
                    output.write(block)
                    hashed.update(block)
                    progress(int(100 * total / size))
                output.flush()
                os.fsync(output.fileno())
            if total != size or hashed.hexdigest() != digest:
                raise ValueError('Engine hash mismatch')
            os.chmod(temporary, 0o700)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    pair_path = profile(name='helper-pairing.json')
    pairing = load(pair_path)
    if pairing is None:
        pairing = Pairing('http://127.0.0.1:8090', 'bobbi_' + secrets.token_hex(6), secrets.token_hex(24))
        save(pair_path, pairing)
    elif pairing.endpoint != 'http://127.0.0.1:8090':
        raise ValueError('Existing helper configuration must be removed explicitly first')
    # Generated files belong exclusively to this addon, never ~/.config or /storage services.
    for name, value in [('accs.db', {pairing.username: pairing.password}), ('settings.json', SETTINGS)]:
        fd, temp = tempfile.mkstemp(dir=str(root), prefix='.config-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(value, output)
            os.replace(temp, root / name)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    (root / 'enabled').write_text(arch, encoding='ascii')


class Engine:
    def __init__(self):
        self.process = None
        self.attempted = False

    def tick(self, cancelled=lambda: False):
        if self.attempted or cancelled():
            return
        root = profile(name='engine')
        if not (root / 'enabled').is_file():
            return
        self.attempted = True
        arch = architecture()
        if (root / 'enabled').read_text() != arch:
            raise ValueError('Installed engine architecture changed')
        binary = root / ('TorrServer-' + VERSION + '-' + arch)
        size, digest = BINARIES[arch]
        if binary.is_symlink() or binary.stat().st_size != size or hashlib.sha256(binary.read_bytes()).hexdigest() != digest:
            raise ValueError('Installed engine does not match lock')
        if cancelled():
            return
        pairing = load(profile(name='helper-pairing.json'))
        try:
            TorrServerClient(engine_document(pairing)).ready()
            return  # Already running with this installation's authenticated credentials.
        except (TorrServerError, ValueError):
            pass
        with socket.socket() as check:
            check.bind(('127.0.0.1', 8090))  # Busy port is a failure, never kill another service.
        if cancelled():
            return
        self.process = subprocess.Popen([str(binary), '-i', '127.0.0.1', '-p', '8090', '-d', str(root),
            '-a', '-l', '/dev/null', '-w', '/dev/null'], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
