"""Idle signed-ZIP discovery. Installing is always a separate, confirmed transaction."""
import sys
from pathlib import Path

from .ce_installer import installed_watermark, read_installation
from .online_updates import Cancelled, latest, selected_track
from .paths import ProfileBinding
from .updates import UpdateError, _atomic, _json, _safe_path


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


def enabled(work, value=None):
    path = _safe_path(work / 'update-notices.json')
    if value is not None:
        if type(value) is not bool:
            raise ValueError('Boolean expected')
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(path, value)
    result = _small(path, True)
    if type(result) is not bool:
        raise UpdateError('UPDATE_NOTICE_INVALID')
    return result


def _context(work):
    if not enabled(work):
        return None
    state = read_installation(work)
    if not state or state['phase'] not in ('complete', 'restored') or state.get('host_pending'):
        return None
    return selected_track(work), installed_watermark(state), state['tx']


def check(work, cancelled, notify, *, lookup=latest):
    if cancelled():
        return 'deferred'
    context = _context(work)
    if context is None:
        return 'inactive'
    track, watermark, _ = context
    try:
        offer = lookup(cancelled, track=track)
    except Cancelled:
        return 'deferred'
    if cancelled() or _context(work) != context:
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
