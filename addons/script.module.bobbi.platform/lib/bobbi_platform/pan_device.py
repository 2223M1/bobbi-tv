"""First-party device authorization. Public web client identifiers, no secrets.

No Juku device identity, CAPTCHA signing keys, mock QR or pending-on-error.
"""
from copy import deepcopy
import time
from urllib.parse import quote, urlencode
from uuid import uuid4

from .pan_accounts import PanError
from .pan_http import Session
from .pan_tokens import identifier, number, original_url, saved, token

# Public browser identifiers observed in first-party JS, 2026-11-09.
# www.guangyapan.com/static/js/index.1523698a.js
# static-pan.xunlei.com/_nuxt/dist/client/utils-initial.ddef3a9e719ae0793f69.js
PROFILES = {
    'guangya': ('https://account.guangyapan.com', 'aMe-8VSlkrbQXpUR',
                ('account.guangyapan.com', 'www.guangyapan.com')),
    'xunlei': ('https://xluser-ssl.xunlei.com', 'Xqp0kJBXWhwaTpB6',
               ('i.xunlei.com', 'xluser-ssl.xunlei.com')),
}


def credentials(provider, value):
    if provider not in PROFILES:
        raise PanError('PAN_PROVIDER_INVALID')
    value = saved(provider, value, {'provider', 'subject', 'access_token', 'refresh_token',
        'expires_at', 'device_id'})
    token(value['refresh_token'])
    number(value['expires_at'], 1)
    identifier(value['device_id'])
    return value['subject'], value


def headers(provider, device):
    result = {'X-Client-Id': PROFILES[provider][1], 'X-Device-Id': identifier(device),
              'X-Client-Version': '0.0.1'}
    if provider == 'guangya':
        # Public wire-format padding, not a shared credential or signing key.
        # Keep our independently generated identity across login and refresh.
        result.update({'X-Device-Sign': 'wdi10.' + device + 'x' * 32, 'X-Platform-Version': '1',
                       'X-Protocol-Version': '301', 'X-SDK-Version': '9.0.2'})
    return result


def account_reply(value):
    if value.get('error') or value.get('error_code'):
        raise PanError('PAN_CHALLENGE_REQUIRED' if 'captcha' in str(value.get('error', '')).lower()
            else 'PAN_LOGIN_REQUIRED')
    return value


def exchanged(provider, value, device, clock, previous_refresh=None):
    account_reply(value)
    if type(value.get('token_type', 'Bearer')) is not str or value.get('token_type', 'Bearer').lower() != 'bearer':
        raise PanError('PAN_CREDENTIALS_INVALID')
    # Some first-party login responses omit the optional token lifetime.
    # This is a local renewal deadline, not an assertion of remote validity.
    lifetime = number(value.get('expires_in', 300), 1)
    if lifetime > 31 * 86400:
        raise PanError('PAN_REPLY_INVALID')
    result = dict(provider=provider, access_token=token(value.get('access_token')),
        refresh_token=token(value.get('refresh_token', previous_refresh)), expires_at=int(clock()) + lifetime,
        device_id=device)
    # Xunlei's authenticated token response attests user_id directly (Juku
    # 0.81 PollQrLogin). Never decode an unverified JWT to invent this identity.
    if provider == 'xunlei' and value.get('user_id') not in (None, ''):
        result['subject'] = identifier(value['user_id'])
    return result


def identity(provider, session, value):
    profile = PROFILES[provider]
    value = dict(value)
    if 'subject' in value:
        return credentials(provider, value)[1]
    me = account_reply(session.request(profile[0] + '/v1/user/me',
        headers=dict(headers(provider, value['device_id']), Authorization='Bearer ' + value['access_token'])))
    value['subject'] = identifier(me.get('sub'))
    return credentials(provider, value)[1]


class Login:
    def __init__(self, provider, session=None, clock=time.monotonic, wall_clock=time.time):
        if provider not in PROFILES:
            raise PanError('PAN_PROVIDER_INVALID')
        self.provider, self.profile = provider, PROFILES[provider]
        self.session = session if session is not None else Session(provider)
        self.clock, self.wall_clock = clock, wall_clock
        self.device, self.code, self.pending = uuid4().hex, None, None
        self.terminal, self.deadline, self.next_poll, self.interval = False, 0, 0, 2
        self.phase = 'qr'

    def __repr__(self):
        return '<Cloud device authorization: credentials hidden>'

    def cancel(self):
        self.terminal, self.code, self.pending = True, None, None
        self.phase = 'closed'

    def _active(self):
        if self.terminal:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() >= self.deadline:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')

    def begin(self):
        if self.terminal or self.code is not None:
            raise PanError('PAN_QR_FINISHED')
        started = self.clock()
        self.deadline = started + 180
        value = account_reply(self.session.request(self.profile[0] + '/v1/auth/device/code',
            body={'client_id': self.profile[1],
                  'scope': 'user' if self.provider == 'guangya' else 'user pan profile offline'},
            headers=headers(self.provider, self.device)))
        self._active()
        code = token(value.get('device_code'))
        # Guangya's device-code response may omit expires_in; use our fixed
        # local QR ceiling, never an unbounded waiting state.
        lifetime = number(value.get('expires_in', 180 if self.provider == 'guangya' else None), 1)
        interval = number(value.get('interval', 5), 1)
        if lifetime > 86400 or interval > 30:
            raise PanError('PAN_REPLY_INVALID')
        qr = value.get('verification_uri_complete')
        if not qr and self.provider == 'guangya':
            qr = value.get('verification_url')
        if not qr and self.provider == 'xunlei':
            redirect = 'https://i.xunlei.com/center/account/personal/qrcode-login/?' + urlencode(dict(
                client_id=self.profile[1], scope='user pan profile offline',
                user_code=token(value.get('user_code'))), quote_via=quote)
            qr = self.profile[0] + '/xluser.core.login/v3/qrlogin?' + urlencode({'redirect_uri': redirect})
        qr = original_url(qr, self.profile[2])
        self.deadline = started + min(180, lifetime)
        self._active()
        self.code, self.interval = code, max(2, interval)
        self.next_poll = self.clock() + self.interval
        return qr

    def poll(self):
        if self.terminal or self.code is None:
            raise PanError('PAN_QR_FINISHED')
        self._active()
        if self.clock() < self.next_poll:
            return 'waiting', None  # Enforce the server's polling interval.
        if self.pending is None:
            self.phase = 'confirm'
            self.next_poll = self.clock() + self.interval
            value = self.session.request(self.profile[0] + '/v1/auth/token', body=dict(
                client_id=self.profile[1], grant_type='urn:ietf:params:oauth:grant-type:device_code',
                device_code=self.code), headers=headers(self.provider, self.device))
            self._active()
            error = value.get('error')
            if error in ('authorization_pending', 'slow_down'):
                if error == 'slow_down':
                    self.interval = min(30, self.interval + 5)
                    self.next_poll = self.clock() + self.interval
                return 'waiting', None
            if error in ('expired_token', 'access_denied'):
                self.cancel()
                raise PanError('PAN_QR_EXPIRED' if error == 'expired_token' else 'PAN_QR_CANCELLED')
            self.pending = exchanged(self.provider, value, self.device, self.wall_clock)
        self.phase = 'identity'
        self._active()
        result = identity(self.provider, self.session, self.pending)
        self._active()
        self.cancel()
        return 'ready', result


class RenewableClient:
    def __init__(self, provider, value, session=None, clock=time.time):
        self.provider, self.saved = provider, credentials(provider, value)[1]
        self.session = session if session is not None else Session(provider)
        self.clock = clock

    def __repr__(self):
        return '<Cloud device client: credentials hidden>'

    def renew_if_needed(self, publish):
        if self.saved['expires_at'] > self.clock() + 60:
            return
        previous = deepcopy(self.saved)
        profile = PROFILES[self.provider]
        value = self.session.request(profile[0] + '/v1/auth/token', body=dict(
            client_id=profile[1], grant_type='refresh_token', refresh_token=previous['refresh_token']),
            headers=headers(self.provider, previous['device_id']))
        # OAuth refresh responses need not rotate refresh_token. Only a
        # missing field preserves it; an explicit empty/invalid value fails.
        current = exchanged(self.provider, value, previous['device_id'], self.clock,
                            previous_refresh=previous['refresh_token'])
        # Reuse an identity attested by the token response; otherwise only the
        # actual identity endpoint may supply it. No drive/capability probes.
        current = identity(self.provider, self.session, current)
        if current['subject'] != previous['subject']:
            raise PanError('PAN_RENEW_IDENTITY_CHANGED')
        publish(current, previous)
        self.saved = current
