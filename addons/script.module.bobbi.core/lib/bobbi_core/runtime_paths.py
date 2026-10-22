"""Lazy host paths, with one explicit adapter for the deployed CE F9 ABI.

Only the verified historical native binary uses the legacy subtitle directory.
The host publishes a small non-secret ABI selector in the bobbi profile so
independent Kodi GUI/provider interpreters agree; no arbitrary root is accepted.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

_profile = None
CE_F9_ROOT = '/storage/.kodi/userdata/addon_data/plugin.video.jacktook/subtitle-browser'
CE_F9_SHA256 = '8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
# Exact reviewed descendants only. The directory-lifetime repair preserves this
# subtitle ABI; populate its immutable artifact hash after the native build.
CE_F9_REVIEWED_PATCHES = frozenset((
    'd750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3',
    # CE2035 same-file transport capsule; identical external-subtitle ABI.
    '632758f5d1ca5494e9b049446d3908bead70589b4d18640bb5d06e830a2b57eb',
    # CE2038 restores original audio and the matching player layout with the capsule.
    '8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14',
    # CE2043 registers the complete handoff RPC schema; other 8bb2 objects unchanged.
    'ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991',
))
CONFIG = 'runtime-paths.json'


def _no_links(path):
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('RUNTIME_PATH_SYMLINK')


def _coreelec():
    if os.name != 'posix':
        return False
    try:
        data = Path('/etc/os-release').read_text(encoding='utf-8')
        return len(data) <= 8192 and any(line.strip().lower() in
            ('id=coreelec', 'id="coreelec"') for line in data.splitlines())
    except (OSError, UnicodeError):
        return False


def native_executable_sha256(executable):
    """Hash the opened executable object, not a resolved namespace pathname.

    Linux /proc/PID/exe is a kernel reference to the running inode. Resolving
    its link and reopening the resulting pathname can read another binary in
    the caller's mount namespace. Callers deliberately supply that proc path.
    """
    try:
        digest = hashlib.sha256()
        with Path(executable).open('rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 1024 * 1024 <= info.st_size <= 512 * 1024 * 1024:
                return None
            total = 0
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                total += len(chunk)
                if total > info.st_size:
                    return None
                digest.update(chunk)
            if total != info.st_size:
                return None
        return digest.hexdigest()
    except OSError:
        return None


def known_ce_native(digest):
    return isinstance(digest, str) and (digest == CE_F9_SHA256 or digest in CE_F9_REVIEWED_PATCHES)


def native_subtitle_abi(capabilities, executable=None):
    """Probe once at host startup, never on the playback actor or each lookup."""
    if capabilities.get('native_contract_available') is not True or not _coreelec():
        return None
    # Kodi embeds Python. sys.executable need not name Kodi; even a seemingly
    # correct path can select another mount namespace's inode.
    path = executable if executable is not None else '/proc/self/exe'
    digest = native_executable_sha256(path)
    return dict(root=CE_F9_ROOT, sha256=digest) if known_ce_native(digest) else None


def native_subtitle_root(capabilities, executable=None):
    abi = native_subtitle_abi(capabilities, executable)
    return abi['root'] if abi else None


def configure(profile, subtitle_root=None, native_sha256=None):
    global _profile
    base = Path(profile)
    if not base.is_absolute():
        raise ValueError('ABSOLUTE_PROFILE_REQUIRED')
    _no_links(base)
    base = base.resolve()
    selected = 'profile'
    if subtitle_root is not None:
        value = os.fspath(subtitle_root)
        if value == CE_F9_ROOT and _coreelec():
            if native_sha256 is not None and not known_ce_native(native_sha256):
                raise ValueError('NATIVE_ABI_NOT_REVIEWED')
            _no_links(Path(value))
            selected = 'ce-f9'
        elif Path(value) != base / 'subtitle-browser':
            raise ValueError('SUBTITLE_ROOT_NOT_ALLOWED')
    _no_links(base / 'subtitle-browser')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    # F9's native ABI expects this directory even on a new account/profile.
    # Creating only this empty export directory does not require old
    # credentials, settings or a pre-migration userdata backup.
    export = Path(CE_F9_ROOT) if selected == 'ce-f9' else base / 'subtitle-browser'
    _no_links(export)
    export.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = base / CONFIG
    _no_links(target)
    data = dict(schema=1, subtitle_abi=selected)
    if selected == 'ce-f9':
        data['native_sha256'] = native_sha256 or CE_F9_SHA256
    fd, temporary = tempfile.mkstemp(prefix='.runtime-paths-', dir=str(base))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _profile = base


def _subtitle_path(base):
    config = base / CONFIG
    _no_links(config)
    if not config.exists():
        return str(base / 'subtitle-browser')
    if not config.is_file() or config.stat().st_size > 512:
        raise ValueError('RUNTIME_PATH_CONFIG_INVALID')
    try:
        data = json.loads(config.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as error:
        raise ValueError('RUNTIME_PATH_CONFIG_INVALID') from error
    if not isinstance(data, dict) or type(data.get('schema')) is not int:
        raise ValueError('RUNTIME_PATH_CONFIG_INVALID')
    if data == dict(schema=1, subtitle_abi='profile'):
        return str(base / 'subtitle-browser')
    if (set(data) == {'schema', 'subtitle_abi', 'native_sha256'} and data.get('schema') == 1
            and data.get('subtitle_abi') == 'ce-f9' and known_ce_native(data.get('native_sha256'))
            and _coreelec()):
        _no_links(Path(CE_F9_ROOT))
        return CE_F9_ROOT
    raise ValueError('RUNTIME_PATH_CONFIG_INVALID')


class ProfilePath(os.PathLike):
    def __init__(self, name):
        if not name or '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('One profile component required')
        self.name = name

    def __fspath__(self):
        base = _profile
        if base is None:
            try:
                import xbmcvfs
                base = Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi'))
            except ImportError:
                # CLI tools must explicitly configure or pass paths; this
                # fallback is per-user, never the root of a mounted device.
                base = Path.home() / '.bobbi' / 'plugin.video.bobbi'
        _no_links(base / self.name)
        return _subtitle_path(base) if self.name == 'subtitle-browser' else str(base / self.name)

    def __str__(self):
        return self.__fspath__()
