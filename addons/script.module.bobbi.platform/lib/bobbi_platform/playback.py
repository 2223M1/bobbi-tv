"""Single-shot stock Kodi handoff, explicitly NOT private native ownership.

No retry/fallback, delayed Stop/Seek/fullscreen, playlist clearing or fabricated
startup receipt. The caller resolves one user-selected source and attaches its
identity. Kodi alone owns playback after this submission.
"""
import hashlib
import re
import threading
from urllib.parse import urlsplit


class UnsupportedPlayback(ValueError):
    pass


def selected_identity(locator):
    if not isinstance(locator, str) or not locator:
        raise ValueError('Missing selected source identity')
    return hashlib.sha256(locator.encode('utf-8')).hexdigest()


def check_media(data):
    if not isinstance(data, dict):
        raise ValueError('Invalid playback data')
    url = data.get('url', '')
    if not isinstance(url, str) or not url or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid media URL')
    scheme = urlsplit(url).scheme.lower()
    if re.match(r'^[A-Za-z]:[/\\]', url):
        scheme = ''
    # Explicit playable paths only. No arbitrary Kodi builtins/plugin/script
    # execution, ambiguous torrent pack, or raw magnet routed as a movie.
    if scheme not in ('http', 'https', 'smb', 'nfs', 'dav', 'davs', 'file', ''):
        raise UnsupportedPlayback('Unsupported direct media protocol')
    if scheme == '' and not (url.startswith('/') or (len(url) > 2 and url[1:3] in (':/', ':\\'))):
        raise ValueError('Relative media path is not portable')
    if (data.get('is_torrent') or data.get('magnet') or data.get('is_pack')
            or data.get('require_catalog_episode_binding') or data.get('direct_cloud_required')):
        raise UnsupportedPlayback('This source requires a verified backend/file resolver')
    return url


class Handoff:
    def __init__(self, identity, handle, resolve, play, make_item, ready=lambda: True):
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
            raise ValueError('Stable selected identity required')
        if type(handle) is not int:
            raise ValueError('Kodi handle must be an integer')
        self.identity = identity
        self.handle = handle
        self.resolve, self.play, self.make_item = resolve, play, make_item
        self.ready = ready
        self._lock = threading.RLock()
        self._state = 'selected'

    @property
    def state(self):
        with self._lock:
            return self._state

    def cancel(self):
        with self._lock:
            if self._state == 'selected':
                self._state = 'cancelled'
                return True
            return False  # After submission we do not control global playback.

    def submit(self, identity, data):
        url = check_media(data)
        with self._lock:
            if identity != self.identity:
                raise ValueError('Resolution changed the selected source identity')
            if self._state != 'selected':
                return {'status': self._state, 'opened': False}
            item = self.make_item(url, data)
            if self.ready() is not True:
                self._state = 'cancelled'
                return {'status': 'cancelled', 'opened': False}
            # Claim before sending. A lost reply must not trigger another open.
            self._state = 'submitted'
            try:
                if self.handle >= 0:
                    self.resolve(self.handle, True, item)
                else:
                    self.play(url, item)
            except Exception:
                self._state = 'submission_unknown'
                raise
            return {'status': 'submitted', 'opened': True,
                    'evidence': 'standard-kodi-handoff-only'}
