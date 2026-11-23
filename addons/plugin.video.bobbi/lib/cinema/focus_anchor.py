"""Stable presentation identities and a window-bound native-list adapter.

Kodi 21 GUIBaseContainer::UpdateListProvider reidentifies the CURRENT item by
path synchronously on the GUI thread. We deliberately do not schedule SetFocus:
directions/select/back issued during a fetch therefore win without a Python
input poller. DirectoryProvider cancels superseded jobs through JobManager.
Existing-window Python wrappers cannot intercept native window key presses.
"""
import hashlib
import json
import re
from urllib.parse import urlencode


def opaque(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def public_card(kind, identifier):
    kind = {'movies': 'movie', 'tvshow': 'tv'}.get(kind, kind)
    if kind not in ('movie', 'tv') or not str(identifier).isdecimal() or int(identifier) <= 0:
        raise ValueError('CARD_IDENTITY_INVALID')
    return 'tmdb:%s:%d' % (kind, int(identifier))


def public_target(kind, identifier):
    key = public_card(kind, identifier)
    _, kind, identifier = key.split(':')
    return 'plugin://plugin.video.bobbi/?' + urlencode(dict(action='am6b_open_streaming_item',
        mode='movies' if kind == 'movie' else 'tv', id=identifier, media_type=kind))


def resume_key(data):
    """Only a persisted exact binding may become a stable resume card.

    Old transport-only records retain their original path; never hash a title,
    temporary URL, current progress, or a guessed work identity into a key.
    """
    binding = data.get('file_identity')
    if data.get('prepared_resource_id'):
        binding = ['prepared', data['prepared_resource_id']]
    elif data.get('video_context'):
        try:
            from bobbi_core.video_context import checked_video
            context = checked_video(data['video_context'])
            binding = ['video', context['media_id'], context['release_key'], context['selected']]
        except (ValueError, TypeError, KeyError):
            return ''
    elif not isinstance(binding, str) or not binding or '://' in binding:
        return ''
    return 'resume:' + opaque([data.get('_account') or 'local-profile', binding])


def revision_property(key):
    if not re.fullmatch('[a-z][a-z0-9_]{0,47}', key):
        raise ValueError('RAIL_KEY_INVALID')
    return 'Bobbi.Rail.Revision.' + key


def bump(window, key):
    prop = revision_property(key)
    try:
        previous = int(window.getProperty(prop) or 0)
    except ValueError:
        previous = 0
    window.setProperty(prop, str(previous + 1))


class HomeRailLifecycle:
    """Runs on the existing owner tick, with account changes as push events.

    No focus polling, queue, network, worker, playback ownership or lazy service
    creation. Account callbacks immediately hide old cards; a later owner tick
    publishes only the new scope. Failed presentation cannot stop revocation.
    """
    def __init__(self, host, window, refresh=None):
        from bobbi_platform.pan_accounts import PROVIDERS, SERVER_PROVIDERS
        self.host, self.window = host, window
        self.refresh = refresh
        self.providers = tuple(key for key, _ in PROVIDERS + SERVER_PROVIDERS)
        self.pans, self.unsubscribe, self.dirty = None, lambda: None, True
        self.clear()
        self.legacy_unsubscribe = host.accounts.subscribe(self.changed)

    def clear(self):
        self.window.setProperty('Bobbi.Rail.Scope.115.personal', '')
        for provider in self.providers:
            self.window.setProperty('Bobbi.Rail.Scope.' + provider, '')
            self.window.setProperty('Bobbi.Rail.Account.' + provider, '')
        bump(self.window, 'personal_library')
        bump(self.window, 'continue_watching')

    def changed(self, previous, current):
        self.dirty = True
        provider = previous.get('provider', '115')
        if provider == '115':
            self.window.setProperty('Bobbi.Rail.Scope.115.personal', '')
        self.window.setProperty('Bobbi.Rail.Scope.' + provider, '')
        self.window.setProperty('Bobbi.Rail.Account.' + provider, '')

    def tick(self):
        self._publish_scope()
        if self.refresh is not None:
            self.refresh()

    def _publish_scope(self):
        pans = self.host.pans
        if pans is not self.pans:
            self.unsubscribe()
            self.pans, self.dirty = pans, True
            self.unsubscribe = pans.accounts.subscribe(self.changed) if pans else lambda: None
        if not self.dirty:
            return
        # A callback during this pass leaves dirty=True for the next tick.
        self.dirty = False
        from lib.utils.views.personal_catalog import scope_key
        for provider in self.providers:
            accounts = self.host.accounts if provider == '115' else pans.accounts if pans else None
            if not accounts:
                value = ''
            else:
                # Commit and publication use the same account lock. Never
                # relabel a captured old reply with a newer account epoch.
                account = accounts.snapshot() if provider == '115' else accounts.snapshot(provider)
                def publish():
                    value = ((opaque(account) if provider == '115' else scope_key(account))
                             if account['authenticated'] else '')
                    self.window.setProperty('Bobbi.Rail.Scope.' + provider, value)
                    self.window.setProperty('Bobbi.Rail.Account.' + provider,
                        opaque(account['account_id']) if account['authenticated'] else '')
                    if provider == '115':
                        # Same original account owner, two explicit scope
                        # shapes. Preserve legacy share-card tokens unchanged.
                        self.window.setProperty('Bobbi.Rail.Scope.115.personal',
                            scope_key(dict(account, provider='115')) if account['authenticated'] else '')
                if not account['authenticated']:
                    # Clearing grants no authority and needs no live source CAS.
                    # A concurrent login callback keeps dirty=True for the next
                    # tick; a late clear can only hide, never publish old cards.
                    publish()
                    continue
                try:
                    accounts.run_if_current(account, publish, authenticated=False)
                except (ValueError, RuntimeError):
                    self.changed(account, account)
                continue
            self.window.setProperty('Bobbi.Rail.Scope.' + provider, value)
            self.window.setProperty('Bobbi.Rail.Account.' + provider, '')
        bump(self.window, 'personal_library')
        bump(self.window, 'continue_watching')

    def close(self):
        self.unsubscribe()
        self.legacy_unsubscribe()
        self.clear()
