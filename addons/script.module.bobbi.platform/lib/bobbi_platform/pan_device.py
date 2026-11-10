"""First-party device authorization. Public web client identifiers, no secrets.

No Juku device identity, CAPTCHA signing keys, mock QR or pending-on-error.
"""
from copy import deepcopy
import time
from urllib.parse import urlencode
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
        result.update({'X-Device-Sign': 'wdi10.' + device, 'X-Platform-Version': '1',
                       'X-Protocol-Version': '301', 'X-SDK-Version': '9.0.2'})
    return result


def account_reply(value):
    if value.get('error') or value.get('error_code'):
        raise PanError('PAN_CHALLENGE_REQUIRED' if 'captcha' in str(value.get('error', '')).lower()
            else 'PAN_LOGIN_REQUIRED')
    return value


def exchanged(provider, value, device, clock):
    account_reply(value)
    if type(value.get('token_type', 'Bearer')) is not str or value.get('token_type', 'Bearer').lower() != 'bearer':
        raise PanError('PAN_CREDENTIALS_INVALID')
    lifetime = number(value.get('expires_in'), 1)
    if lifetime > 31 * 86400:
        raise PanError('PAN_REPLY_INVALID')
    # Do not derive the account from a rotating token. /user/me supplies sub.
    return dict(provider=provider, access_token=token(value.get('access_token')),
        refresh_token=token(value.get('refresh_token')), expires_at=int(clock()) + lifetime,
        device_id=device)


def identity(provider, session, value):
    profile = PROFILES[provider]
    value = dict(value)
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

    def __repr__(self):
        return '<Cloud device authorization: credentials hidden>'

    def cancel(self):
        self.terminal, self.code, self.pending = True, None, None

    def begin(self):
        if self.terminal or self.code is not None:
            raise PanError('PAN_QR_FINISHED')
        value = account_reply(self.session.request(self.profile[0] + '/v1/auth/device/code',
            body={'client_id': self.profile[1], 'scope': 'user pan profile offline'},
            headers=headers(self.provider, self.device)))
        code = token(value.get('device_code'))
        lifetime = number(value.get('expires_in'), 1)
        interval = number(value.get('interval', 5), 1)
        if lifetime > 86400 or interval > 30:
            raise PanError('PAN_REPLY_INVALID')
        qr = value.get('verification_uri_complete')
        if not qr and self.provider == 'xunlei':
            qr = 'https://i.xunlei.com/center/account/personal/qrcode-login/?' + urlencode(dict(
                client_id=self.profile[1], scope='user pan profile offline', user_code=token(value.get('user_code'))))
        qr = original_url(qr, self.profile[2])
        self.code, self.interval = code, max(2, interval)
        self.deadline, self.next_poll = self.clock() + min(180, lifetime), self.clock() + self.interval
        return qr

    def poll(self):
        if self.terminal or self.code is None:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() >= self.deadline:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')
        if self.clock() < self.next_poll:
            return 'waiting', None  # Enforce the server's polling interval.
        if self.pending is None:
            self.next_poll = self.clock() + self.interval
            value = self.session.request(self.profile[0] + '/v1/auth/token', body=dict(
                client_id=self.profile[1], grant_type='urn:ietf:params:oauth:grant-type:device_code',
                device_code=self.code), headers=headers(self.provider, self.device))
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
        result = identity(self.provider, self.session, self.pending)
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
        current = exchanged(self.provider, value, previous['device_id'], self.clock)
        # The authenticated response must attest the same stable identity before
        # rotating storage. Never use a decoded, unverified JWT as identity.
        current = identity(self.provider, self.session, current)
        if current['subject'] != previous['subject']:
            raise PanError('PAN_RENEW_IDENTITY_CHANGED')
        publish(current, previous)
        self.saved = current
