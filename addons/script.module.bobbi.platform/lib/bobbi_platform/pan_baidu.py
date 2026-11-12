"""Baidu first-party web QR and read-only directories; no borrowed app secret.

No speed-limit bypass, transcoding fallback, password input, or remote cookie
broker. Login authority comes from the official QR exchange, not a separate
netdisk template API. Directory and playback capabilities are checked on use.
"""
import base64
import json
import logging
import re
import time
from urllib.parse import parse_qsl, urlsplit

from .pan_accounts import PanError
from .pan_http import Session

QR_CALLBACK = 'bd__cbs__cupstt'
IDENTITY_URL = 'https://mbd.baidu.com/userx/v1/info/get'
MAX_JSON_DEPTH = 64  # Container depth, including the root exchange object.


def _exchange_object(raw):
    """Parse the first-party callback as data, including its single-quoted key.

    Baidu emits JSON strings but spells one object key as 'data'. Normalize
    only that literal outside JSON strings; never evaluate returned script.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise PanError('PAN_REPLY_INVALID')
    try:
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            text = raw.decode('gb18030')
        text = text.strip()
        if text.endswith(';'):
            text = text[:-1].rstrip()
        prefix = QR_CALLBACK + '('
        if text.startswith(prefix) and text.endswith(')'):
            text = text[len(prefix):-1].strip()
        # Strings are matched first so their content is never rewritten.
        text = re.sub(r'''"(?:[^"\\]|\\.)*"|'data'(?=\s*:)''',
                      lambda match: '"data"' if match.group() == "'data'" else match.group(), text)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        def invalid_constant(value):
            raise ValueError
        value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
        if type(value) is not dict:
            raise ValueError
        # JSON decoder recursion limits differ across Python versions. Keep
        # this exchange contract explicit without parsing JSON syntax again.
        pending = [(value, 1)]
        while pending:
            node, depth = pending.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError
            children = node.values() if type(node) is dict else node
            pending.extend((child, depth + 1) for child in children
                           if type(child) in (dict, list))
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise PanError('PAN_REPLY_INVALID') from None


def _subject(value):
    if type(value) is int:
        value = str(value)
    if type(value) is not str or not re.fullmatch(r'[1-9][0-9]{0,31}', value):
        raise PanError('PAN_ACCOUNT_ID_INVALID')
    return value


def _exchange_subject(raw):
    try:
        value = _exchange_object(raw)
    except PanError as error:
        if str(error) != 'PAN_REPLY_INVALID':
            raise
        # Browser-oriented exchange bodies are not executable input or proof
        # of identity. With a real scoped BDUSS, _complete instead verifies
        # the account through MBD. The one-use ticket is never replayed.
        return None
    info = value.get('errInfo')
    if type(info) is not dict or type(info.get('no')) not in (str, int):
        raise PanError('PAN_REPLY_INVALID')
    if info['no'] not in ('0', 0):
        raise PanError('PAN_QR_EXCHANGE_FAILED')
    data = value.get('data')
    if type(data) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    user = data.get('user')
    if user is None:
        return None  # Lost/missing identity is read from the account API only.
    if type(user) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    identity = user.get('userId')
    return None if identity in (None, '') else _subject(identity)


def _login_probe(phase, session, reply=None):
    """Bounded protocol facts only, never response text or credential values."""
    if phase not in ('exchange', 'identity'):
        return
    value, envelope = reply, 'json'
    if type(reply) is bytes:
        value, envelope = None, 'other'
        try:
            value = _exchange_object(reply)
            envelope = 'jsonp' if reply.strip().startswith((QR_CALLBACK + '(').encode()) else 'json'
        except PanError:
            pass
    def kind(item):
        return {type(None): 'null', bool: 'bool', int: 'int', str: 'str',
                dict: 'dict', list: 'list'}.get(type(item), 'other')
    has_bduss = _has_bduss(session)
    facts = dict(phase=phase, envelope=envelope, bduss_present=has_bduss)
    if type(value) is dict:
        facts['errno_type'] = kind(value['errno']) if 'errno' in value else 'absent'
        code = value.get('errno')
        if type(code) is int and -(2**31) <= code < 2**31:
            facts['errno'] = code
        error_info = value.get('errInfo')
        if type(error_info) is dict:
            code = error_info.get('no')
            facts['exchange_code_type'] = kind(code) if 'no' in error_info else 'absent'
            if type(code) is str and re.fullmatch(r'-?[0-9]{1,9}', code):
                code = int(code)
            if type(code) is int and -(2**31) <= code < 2**31:
                facts['exchange_code'] = code
        facts['result_type'] = kind(value['result']) if 'result' in value else 'absent'
    message = '[Bobbi login protocol] provider=baidu ' + json.dumps(facts, sort_keys=True)
    try:
        import xbmc
        xbmc.log(message, xbmc.LOGINFO)
    except (ImportError, AttributeError, RuntimeError):
        logging.getLogger(__name__).info(message)


def _has_bduss(session, url='https://pan.baidu.com/api/list'):
    header = session.cookie_header(url)
    for part in header.split(';'):
        name, separator, value = part.lstrip().partition('=')
        if (separator and name == 'BDUSS' and 64 <= len(value) <= 4096
                and value.isascii() and not re.search(r'[;\x00-\x20\x7f]', value)):
            return True
    return False


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
        if not _has_bduss(self.session, IDENTITY_URL):
            raise PanError('PAN_CREDENTIALS_INVALID')
        value = self.session.request(IDENTITY_URL,
            dict(appname='baiduboxapp', fields='["bg_image","member","uid","avatar","avatar_member"]',
                 lang='zh-cn'))
        _login_probe('identity', self.session, value)
        for key in ('errno', 'error_code'):
            if key in value and (type(value[key]) is not int or value[key] != 0):
                raise PanError('PAN_API_REJECTED')
        data = value.get('data')
        fields = data.get('fields') if type(data) is dict else None
        return _subject(fields.get('uid') if type(fields) is dict else None)

    def list_files(self, parent='/', page=1, size=10):
        if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 20:
            raise PanError('PAN_PAGE_INVALID')
        value = _success(self.session.request('https://pan.baidu.com/api/list',
            dict(dir=path(parent), page=page, num=size, order='name', desc=0,
                 clienttype=0, web=1, app_id=250528)))
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
            dict(target=json.dumps([filepath], ensure_ascii=False), dlink=1,
                 clienttype=0, web=1, app_id=250528)))
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
        self.subject = None
        self.phase = 'qr'

    def __repr__(self):
        return '<Baidu web QR: credentials hidden>'

    def cancel(self):
        self.terminal, self.sign = True, None
        self.exchanged = False
        self.subject = None
        self.phase = 'closed'

    def _active(self):
        if self.terminal:
            raise PanError('PAN_QR_FINISHED')
        if self.clock() - self.started >= 180:
            self.cancel()
            raise PanError('PAN_QR_EXPIRED')

    def begin(self):
        if self.sign is not None or self.terminal:
            raise PanError('PAN_QR_FINISHED')
        self.started = self.clock()
        value = _success(self.session.request('https://passport.baidu.com/v2/api/getqrcode',
            dict(lp='pc', _=int(self.wallclock() * 1000))))
        self._active()
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
        self._active()
        if len(raw) < 33 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
            raise PanError('PAN_QR_IMAGE_INVALID')
        width, height = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
        if not 32 <= width <= 1024 or not 32 <= height <= 1024:
            raise PanError('PAN_QR_IMAGE_INVALID')
        self.sign = sign
        return {'png': base64.b64encode(raw).decode('ascii')}

    def poll(self):
        if self.terminal or self.sign is None:
            raise PanError('PAN_QR_FINISHED')
        self._active()
        if self.exchanged:
            return self._complete()  # Retry identity, not the consumed QR ticket.
        timestamp = str(int(self.wallclock() * 1000))
        self.phase = 'confirm'
        value = self.session.request('https://passport.baidu.com/channel/unicast',
            dict(channel_id=self.sign, tpl='netdisk', callback='', apiver='v3', tt=timestamp, _=timestamp))
        self._active()
        # A channel delivery may omit errno; its channel_v is the success
        # envelope. An explicit errno is still strictly checked. Missing errno
        # alone is never success: validate status/ticket below and then require
        # both the exchanged cookie and a verified account identity.
        if 'errno' in value:
            if type(value['errno']) is not int:
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
        self.phase = 'exchange'
        timestamp = str(int(self.wallclock() * 1000))
        # v is a temporary exchange ticket, never the saved BDUSS cookie.
        try:
            reply = self.session.request_raw('https://passport.baidu.com/v3/login/main/qrbdusslogin',
                dict(v=timestamp, bduss=temporary, u='', loginVersion='v4', qrcode='1',
                     tpl='netdisk', apiver='v3', tt=timestamp, traceid='', callback=QR_CALLBACK))
        except PanError as error:
            # Cookie processing precedes reading the response body. If the
            # body times out after receiving BDUSS, retry identity next time,
            # not the consumed channel/ticket. A cookie alone is never ready.
            self._active()
            _login_probe('exchange', self.session)
            if str(error) == 'PAN_NETWORK_ERROR' and self._exchange_cookie_received():
                self.exchanged = True
            else:
                # The one-use ticket may already be consumed even when the
                # response is lost. Never submit it a second time.
                self.cancel()
                self.phase = 'exchange'
            raise
        self._active()
        _login_probe('exchange', self.session, reply)
        try:
            subject = _exchange_subject(reply)
            if not self._exchange_cookie_received():
                raise PanError('PAN_QR_EXCHANGE_FAILED')
        except PanError:
            self.cancel()
            self.phase = 'exchange'
            raise
        self.subject = subject
        self.exchanged = True
        return self._complete()

    def _exchange_cookie_received(self):
        # Check only cookies actually applicable to the personal file API. The
        # normal export still validates the whole jar after identity succeeds.
        return _has_bduss(self.session)

    def _complete(self):
        self._active()
        self.phase = 'identity'
        subject = self.subject
        if subject is None:
            subject = Client(session=self.session).subject()
        self._active()
        self.subject = subject
        saved = self.session.export(subject=subject)
        self._active()
        self.cancel()
        return 'ready', saved
