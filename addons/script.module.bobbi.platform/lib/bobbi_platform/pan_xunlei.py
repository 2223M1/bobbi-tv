"""Read-only Xunlei personal files using first-party browser authorization.

Shield admission uses the public endpoint without signing secrets. If it asks
for human verification, stop; never execute a challenge URL or forge a proof.
"""
from collections import OrderedDict
import json
import time

from .pan_accounts import PanError
from .pan_device import PROFILES, RenewableClient, headers
from .pan_http import USER_AGENT
from .pan_tokens import decimal, identifier, number, original_url, page_number, text, token

API = 'https://api-pan.xunlei.com'
FILES = '/drive/v1/files'
SHIELD = 'https://xluser-ssl.xunlei.com/v1/shield/captcha/init'
CDN = ('xunlei.com',)


def entry(row):
    if (type(row) is not dict or row.get('kind') not in ('drive#file', 'drive#folder')
            or row.get('trashed') is not False
            or row.get('phase', 'PHASE_TYPE_COMPLETE') != 'PHASE_TYPE_COMPLETE'):
        raise PanError('PAN_REPLY_INVALID')
    parent = row.get('parent_id')
    if parent != '':
        identifier(parent)
    digest = row.get('hash', '')
    if digest != '':
        identifier(digest)
    return dict(file_id=identifier(row.get('id')), parent=parent,
                name=text(row.get('name')), size=int(decimal(row.get('size'))),
                directory=row['kind'] == 'drive#folder',
                modified=text(row.get('modified_time'), 128), hash=digest)


def _reply(value):
    code = value.get('error_code', 0)
    if type(code) is not int:
        raise PanError('PAN_REPLY_INVALID')
    if code in (4122, 4121, 10, 16):
        raise PanError('PAN_LOGIN_REQUIRED')
    if code == 9 or value.get('error') in ('captcha_required', 'captcha_invalid', 'review_panel'):
        raise PanError('PAN_CHALLENGE_REQUIRED')
    if code or value.get('error'):
        raise PanError('PAN_API_REJECTED')
    return value


class Client(RenewableClient):
    def __init__(self, value, monotonic=time.monotonic, **kwargs):
        super().__init__('xunlei', value, **kwargs)
        self.monotonic, self.admissions = monotonic, OrderedDict()

    def _admission(self, path):
        action = 'GET:' + path
        cached = self.admissions.get(action)
        if cached is not None and self.monotonic() < cached[0]:
            return cached[1]
        value = self.session.request(SHIELD, body=dict(
            client_id=PROFILES['xunlei'][1], action=action,
            device_id=self.saved['device_id'], meta={}),
            headers=headers('xunlei', self.saved['device_id']))
        if value.get('url'):
            raise PanError('PAN_CHALLENGE_REQUIRED')
        _reply(value)
        admission = token(value.get('captcha_token'))
        lifetime = number(value.get('expires_in'), 1)
        if lifetime > 86400:
            raise PanError('PAN_REPLY_INVALID')
        self.admissions[action] = (self.monotonic() + max(0, lifetime - 5), admission)
        while len(self.admissions) > 32:
            self.admissions.popitem(last=False)
        return admission

    def _get(self, path, query):
        # One expired-admission retry only; no retry for account/challenge errors.
        for attempt in range(2):
            value = self.session.request(API + path, query=query,
                headers=dict(headers('xunlei', self.saved['device_id']),
                    Authorization='Bearer ' + self.saved['access_token'],
                    **{'X-Captcha-Token': self._admission(path)}))
            if type(value.get('error_code')) is int and value['error_code'] == 9 and not attempt:
                self.admissions.pop('GET:' + path, None)
                continue
            return _reply(value)

    def list_files(self, parent='0', page=1, size=10, cursor=''):
        page_number(page, size)
        parent = '' if parent == '0' else identifier(parent)
        if (type(cursor) is not str or len(cursor) > 2048
                or (page == 1) != (cursor == '')):
            raise PanError('PAN_PAGE_INVALID')
        if cursor:
            token(cursor)
        value = self._get(FILES, dict(space='', __type='drive', refresh='true', __sync='true',
            parent_id=parent, page_token=cursor, with_audit='true', limit=size,
            filters=json.dumps({'phase': {'eq': 'PHASE_TYPE_COMPLETE'}, 'trashed': {'eq': False}},
                               separators=(',', ':'))))
        rows, next_cursor = value.get('files'), value.get('next_page_token', '')
        if type(rows) is not list or len(rows) > size or type(next_cursor) is not str or len(next_cursor) > 2048:
            raise PanError('PAN_REPLY_INVALID')
        if next_cursor:
            token(next_cursor)
            if next_cursor == cursor or not rows:
                raise PanError('PAN_REPLY_INVALID')
        items = [entry(row) for row in rows]
        if len({item['file_id'] for item in items}) != len(items) or any(item['parent'] != parent for item in items):
            raise PanError('PAN_REPLY_INVALID')
        return dict(items=items, page=page, has_more=bool(next_cursor), next_cursor=next_cursor)

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'parent', 'name', 'size', 'directory', 'modified', 'hash'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        number(selected['size'], 1)
        value = self._get(FILES + '/' + identifier(selected['file_id']), {'space': ''})
        if entry(value) != selected:
            raise PanError('PAN_FILE_CHANGED')
        # web_content_link is the original file; medias may contain transcoding.
        url = original_url(value.get('web_content_link'), CDN)
        return dict(url=url, size=selected['size'], original=True, headers={'User-Agent': USER_AGENT})
