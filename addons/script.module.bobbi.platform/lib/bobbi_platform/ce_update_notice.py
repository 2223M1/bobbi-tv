"""Idle signed-ZIP discovery. Installing is always a separate, confirmed transaction."""
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

from .ce_installer import installed_watermark, read_installation
from .online_updates import Cancelled, latest, selected_track
from .paths import ProfileBinding
from .updates import UpdateError, _atomic, _json, _safe_path, auto_update_enabled

MAX_LEGACY_SETTINGS_BYTES = 256 * 1024
auto_enabled = auto_update_enabled
_AUTO_ATTEMPTS = {}


class NoticeProfile(ProfileBinding):
    # Capture the *same* profile whose journal and preference we read.
    ADDONS = ('script.bobbi.start',)


def coreelec(os_release=Path('/etc/os-release')):
    if sys.platform != 'linux':
        return False
    try:
        return any(line.strip().lower() in ('id=coreelec', 'id="coreelec"', "id='coreelec'")
                   for line in os_release.read_text(encoding='utf-8').splitlines())
    except (OSError, UnicodeError):
        return False


def supported():
    """Choose the update owner by installation, not the name of the OS."""
    from .android_ui import bundled_host
    if bundled_host():
        return False  # The bundled Android application owns its APK updates.
    try:
        binding = NoticeProfile()
        state = read_installation(binding.root('script.bobbi.start'))
        return bool(state and state['phase'] in ('complete', 'restored')
                    and not state.get('host_pending') and binding.is_current())
    except (OSError, RuntimeError, ValueError, UpdateError):
        return False  # Unmanaged, changing or damaged profiles need no worker.


def _small(path, default):
    if not path.exists():
        return default
    if path.stat().st_size > 1024:
        raise UpdateError('UPDATE_NOTICE_INVALID')
    return _json(path.read_bytes())


def _default_legacy_settings_path(work):
    work = Path(work)
    if work.name == 'script.bobbi.start':
        return work.parent / 'plugin.video.bobbi' / 'settings.xml'
    return None


def _read_explicit_legacy_update_action(settings_path):
    if settings_path is None:
        return None
    path = Path(settings_path)
    try:
        if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file():
            return None
        size = path.stat().st_size
        if not 0 < size <= MAX_LEGACY_SETTINGS_BYTES:
            return None
        raw = path.read_bytes()
        if len(raw) != size:
            return None
        root = ET.fromstring(raw.decode('utf-8'))
    except (OSError, UnicodeDecodeError, ET.ParseError):
        return None
    matches = [node for node in root.findall('.//setting') if node.get('id') == 'update_action']
    if not matches:
        return None
    node = matches[-1]
    if str(node.get('default') or '').strip().lower() == 'true':
        return None
    raw_value = node.text if node.text is not None else node.get('value', '')
    normalized = str(raw_value or '').strip().lower()
    if normalized in ('2', 'none'):
        return False
    if normalized in ('0', '1', 'ask', 'notify'):
        return True
    return None


def migrate_legacy_update_action(work, *, legacy_settings=None):
    """One-time idempotent migration from explicit legacy update_action when new owner has no choice."""
    work = Path(work)
    path = _safe_path(work / 'update-notices.json')
    if path.exists():
        return None
    candidate = legacy_settings if legacy_settings is not None else _default_legacy_settings_path(work)
    migrated = _read_explicit_legacy_update_action(candidate)
    if migrated is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic(path, migrated)
    return migrated


def enabled(work, value=None, *, legacy_settings=None):
    work = Path(work)
    path = _safe_path(work / 'update-notices.json')
    if value is not None:
        if type(value) is not bool:
            raise ValueError('Boolean expected')
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(path, value)
    elif not path.exists():
        migrate_legacy_update_action(work, legacy_settings=legacy_settings)
    result = _small(path, True)
    if type(result) is not bool:
        raise UpdateError('UPDATE_NOTICE_INVALID')
    return result


def _context(work, *, legacy_settings=None):
    state = read_installation(work)
    if not state or state['phase'] not in ('complete', 'restored') or state.get('host_pending'):
        return None
    if not enabled(work, legacy_settings=legacy_settings):
        return None
    return selected_track(work), installed_watermark(state), state['tx']


def check(work, cancelled, notify, *, lookup=latest, legacy_settings=None):
    if cancelled():
        return 'deferred'
    context = _context(work, legacy_settings=legacy_settings)
    if context is None:
        return 'inactive'
    track, watermark, _ = context
    try:
        offer = lookup(cancelled, track=track)
    except Cancelled:
        return 'deferred'
    if cancelled() or _context(work, legacy_settings=legacy_settings) != context:
        return 'deferred'
    if offer['sequence'] <= watermark:
        return 'current'
    # Separate preference and per-track receipt: changing a preference must
    # not clobber the receipt, and a preview must never silence stable.
    receipt = _safe_path(work / ('update-notified-' + track + '.json'))
    previous = _small(receipt, 0)
    if type(previous) is not int or previous < 0:
        raise UpdateError('UPDATE_NOTICE_INVALID')
    if previous >= offer['sequence']:
        return 'seen'
    if cancelled():
        return 'deferred'
    notify(offer['tag'].upper())
    _atomic(receipt, offer['sequence'])
    return 'notified'


def reset_auto_update_cooldowns():
    _AUTO_ATTEMPTS.clear()


def sync_update_properties(work=None):
    """Sync Bobbi.AutoUpdate.* and Bobbi.Update.CurrentSeq to Window(10000)."""
    try:
        import xbmcgui
        from .i18n import current_locale
        if work is None:
            binding = NoticeProfile()
            if not binding.is_current():
                return None
            work = binding.root('script.bobbi.start')
        work = Path(work)
        on = auto_enabled(work)
        en = current_locale() == 'en_gb'
        label = (
            ('On (Idle Auto)' if en else '已开启（空闲自动）')
            if on else
            ('Off (Disabled)' if en else '已禁止自动更新')
        )
        state = read_installation(work)
        seq = int(state.get('sequence', 0)) if isinstance(state, dict) else 0
        seq_label = f'CE{str(seq)[-4:]}' if seq >= 2026100000 else (str(seq) if seq > 0 else '')
        win = xbmcgui.Window(10000)
        win.setProperty('Bobbi.AutoUpdate.Enabled', 'true' if on else 'false')
        win.setProperty('Bobbi.AutoUpdate.Label', label)
        win.setProperty('Bobbi.Update.CurrentSeq', seq_label)
        return {'enabled': on, 'label': label, 'sequence_label': seq_label}
    except Exception:
        return None


def check_auto_update(work, cancelled, dispatch, notify=None, *, lookup=latest, cooldown_seconds=300, clock=time.monotonic):
    """Discover newer signed release when idle and dispatch unattended update if auto-update is enabled."""
    if cancelled():
        return 'deferred'
    work = Path(work)
    state = read_installation(work)
    if not state or state['phase'] not in ('complete', 'restored') or state.get('host_pending'):
        return 'inactive'
    if not auto_enabled(work):
        return 'disabled'
    if (work / 'installation.lock').exists():
        return 'deferred'
    track, watermark, tx = selected_track(work), installed_watermark(state), state['tx']
    try:
        offer = lookup(cancelled, track=track)
    except Cancelled:
        return 'deferred'
    if cancelled():
        return 'deferred'
    now_state = read_installation(work)
    if (not now_state or now_state.get('tx') != tx or now_state['phase'] not in ('complete', 'restored')
            or now_state.get('host_pending') or not auto_enabled(work)):
        return 'deferred'
    if offer['sequence'] <= watermark:
        return 'current'
    key = (str(work), track, int(offer['sequence']))
    now = float(clock())
    prev_at = _AUTO_ATTEMPTS.get(key)
    if prev_at is not None and (now - prev_at) < cooldown_seconds:
        return 'cooldown'
    if cancelled():
        return 'deferred'
    _AUTO_ATTEMPTS[key] = now
    if len(_AUTO_ATTEMPTS) > 32:
        oldest = min(_AUTO_ATTEMPTS, key=_AUTO_ATTEMPTS.get)
        _AUTO_ATTEMPTS.pop(oldest, None)
    if callable(notify):
        notify(offer['tag'].upper())
    dispatch(offer['tag'].upper())
    return 'dispatched'
