"""Baidu first-party web QR and read-only directories; no borrowed app secret.

No speed-limit bypass, transcoding fallback, password input, or remote cookie
broker. Auth HTML is never evaluated. A QR exchange is accepted only after
the cookie jar and a read-only account identity request both succeed.
"""
import base64
import json
import re
import time
from urllib.parse import parse_qsl, urlsplit

from .pan_accounts import PanError
from .pan_http import Session


def _text(value, maximum=4096):
    if (type(value) is not str or not 0 < len(value) <= maximum
            or re.search(r'[\x00-\x1f\x7f]', value)):
        raise PanError('PAN_REPLY_INVALID')
    return value


def path(value):
    value = _text(value)
    if not value.startswith('/') or '\\' in value or any(p in ('.', '..') for p in value.split('/')):
        raise PanError('PAN_FILE_PATH_INVALID')
    return value


def _success(value):
    if type(value.get('errno')) is not int or value['errno'] != 0:
        raise PanError('PAN_API_REJECTED')
    return value


class Client:
    def __init__(self, saved=None, session=None):
        self.session = session if session is not None else Session('baidu', saved)

    def subject(self):
        value = _success(self.session.request('https://pan.baidu.com/api/gettemplatevariable',
            dict(fields='["uk"]', clienttype='0', web='1')))
        result = value.get('result')
        subject = result.get('uk') if type(result) is dict else None
        if type(subject) is int:
            subject = str(subject)
        if type(subject) is not str or not re.fullmatch(r'[1-9][0-9]{0,31}', subject):
            raise PanError('PAN_ACCOUNT_ID_INVALID')
        return subject

    def list_files(self, parent='/', page=1, size=10):
        if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 20:
            raise PanError('PAN_PAGE_INVALID')
        value = _success(self.session.request('https://pan.baidu.com/api/list',
            dict(dir=path(parent), page=page, num=size, order='name', desc=0, clienttype=0, web=1)))
        rows = value.get('list')
        if type(rows) is not list or len(rows) > size:
            raise PanError('PAN_REPLY_INVALID')
        items = []
        for row in rows:
            if (type(row) is not dict or type(row.get('fs_id')) is not int or row['fs_id'] <= 0
                    or type(row.get('isdir')) is not int or row['isdir'] not in (0, 1)
                    or type(row.get('size')) is not int or not 0 <= row['size'] < 2**63):
                raise PanError('PAN_REPLY_INVALID')
            filename, filepath = _text(row.get('server_filename'), 1024), path(row.get('path'))
            if filepath.rsplit('/', 1)[-1] != filename or filepath.rsplit('/', 1)[0] != parent.rstrip('/'):
                raise PanError('PAN_REPLY_INVALID')
            items.append(dict(file_id=str(row['fs_id']), name=filename, size=row['size'],
                              directory=row['isdir'] == 1, path=filepath))
        if len({r['file_id'] for r in items}) != len(items):
            raise PanError('PAN_REPLY_INVALID')
        # Web list has no trustworthy total. At most one empty trailing page;
        # never recursively scan the whole account just to draw this page.
        return dict(items=items, page=page, has_more=len(items) == size)

    def resolve_original(self, selected):
        if (type(selected) is not dict
                or set(selected) != {'file_id', 'name', 'size', 'directory', 'path'}
                or selected['directory'] is not False or type(selected['size']) is not int
                or not 0 < selected['size'] < 2**63 or type(selected['file_id']) is not str
                or not re.fullmatch(r'[1-9][0-9]{0,31}', selected['file_id'])):
            raise PanError('PAN_SELECTION_INVALID')
        filepath = path(selected['path'])
        if filepath.rsplit('/', 1)[-1] != _text(selected['name'], 1024):
            raise PanError('PAN_SELECTION_INVALID')
        value = _success(self.session.request('https://pan.baidu.com/api/filemetas',
            dict(target=json.dumps([filepath], ensure_ascii=False), dlink=1, clienttype=0, web=1)))
        rows = value.get('info')
        if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        row = rows[0]
        if (type(row.get('fs_id')) is not int or str(row['fs_id']) != selected['file_id']
                or type(row.get('size')) is not int or row['size'] != selected['size']
                or row.get('path') != filepath or type(row.get('isdir')) is not int or row['isdir'] != 0):
            raise PanError('PAN_FILE_CHANGED')
        url = _text(row.get('dlink'), 16384)
        parts = urlsplit(url)
        try:
            allowed = (parts.scheme == 'https' and parts.hostname is not None
                and (parts.hostname.endswith('.baidupcs.com') or parts.hostname == 'd.pcs.baidu.com')
                and not parts.username and not parts.password and parts.port in (None, 443) and not parts.fragment)
        except ValueError:
            allowed = False
        if not allowed:
            raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
        # Internal stream input only. No mediainfo/DLNA or transcoded URL
        # fallback; a denied original file remains denied, not lower quality.
        return dict(url=url, original=True, size=selected['size'], headers={
            'Cookie': self.session.cookie_header(url), 'Referer': 'https://pan.baidu.com/',
            'User-Agent': 'netdisk'})


class Login:
    def __init__(self, session=None, clock=time.monotonic, wallclock=time.time):
        self.session = session if session is not None else Session('baidu')
        self.clock, self.wallclock = clock, wallclock
        self.started, self.sign, self.terminal = 0, None, False
        self.exchanged = False

    def __repr__(self):
        return '<Baidu web QR: credentials hidden>'

    def cancel(self):
        self.terminal, self.sign = True, None
        self.exchanged = False

    def begin(self):
        if self.sign is not None or self.terminal:
            raise PanError('PAN_QR_FINISHED')
        value = _success(self.session.request('https://passport.baidu.com/v2/api/getqrcode',
            dict(lp='pc', tpl='netdisk', _=int(self.wallclock() * 1000))))
        sign = _text(value.get('sign'), 512)
        image_url = _text(value.get('imgurl'), 2048)
        if image_url.startswith('//'):
            image_url = 'https:' + image_url
        elif image_url.startswith('passport.baidu.com/'):
            image_url = 'https://' + image_url
        parsed = urlsplit(image_url)
        if (parsed.scheme != 'https' or parsed.netloc != 'passport.baidu.com'
                or parsed.path != '/v2/api/qrcode' or parsed.fragment):
            raise PanError('PAN_QR_IMAGE_ORIGIN_REJECTED')
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if len(query) > 8 or len(dict(query)) != len(query) or dict(query).get('sign') != sign:
            raise PanError('PAN_QR_IMAGE_INVALID')
        raw = self.session.request_raw('https://passport.baidu.com/v2/api/qrcode', dict(query), limit=8192)
        if len(raw) < 33 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
            raise PanError('PAN_QR_IMAGE_INVALID')
        width, height = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
        if not 32 <= width <= 1024 or not 32 <= height <= 1024:
            raise PanError('PAN_QR_IMAGE_INVALID')
        self.sign, self.started = sign, self.clock()
        return {'png': base64.b64encode(raw).decode('ascii')}

    def poll(self):
        if self.terminal or self.sign is None:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')
        if self.exchanged:
            return self._complete()  # Retry identity, not the consumed QR ticket.
        timestamp = str(int(self.wallclock() * 1000))
        value = self.session.request('https://passport.baidu.com/channel/unicast',
            dict(channel_id=self.sign, tpl='netdisk', callback='', apiver='v3', tt=timestamp, _=timestamp))
        if type(value.get('errno')) is not int:
            raise PanError('PAN_REPLY_INVALID')
        if value['errno'] == 1:
            return 'waiting', None
        _success(value)
        channel = value.get('channel_v')
        try:
            channel = json.loads(_text(channel, 8192))
        except ValueError:
            raise PanError('PAN_REPLY_INVALID') from None
        if type(channel) is not dict or type(channel.get('status')) is not int:
            raise PanError('PAN_REPLY_INVALID')
        if channel['status'] == 1:
            return 'waiting', None
        if channel['status'] != 0:
            self.cancel()
            raise PanError('PAN_QR_CANCELLED')
        temporary = _text(channel.get('v'), 4096)
        # v is a temporary exchange ticket, never the saved BDUSS cookie.
        self.session.request_raw('https://passport.baidu.com/v3/login/main/qrbdusslogin',
            dict(v=timestamp, bduss=temporary, u='', loginVersion='v4', qrcode='1',
                 tpl='netdisk', apiver='v3', tt=timestamp, traceid='', callback='bd__cbs__bobbi'))
        self.exchanged = True
        return self._complete()

    def _complete(self):
        subject = Client(session=self.session).subject()
        saved = self.session.export(subject=subject)
        self.cancel()
        return 'ready', saved
