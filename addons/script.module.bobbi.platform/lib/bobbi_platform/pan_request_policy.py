"""One Host operation budget across waits, HTTP attempts and directory pages."""
from email.utils import parsedate_to_datetime
from collections import OrderedDict
from contextlib import contextmanager
import re
import time
from threading import Event, Lock

from .pan_accounts import PanError, scope

MAX_COOLDOWN = 5.0
SAFE_OPERATIONS = frozenset(('directory', 'metadata', 'scan'))
SCAN_LIMITS = dict(seconds=1800, max_requests=2400, max_pages=1200, max_items=12000)


def retry_after(value, wall=time.time):
    """Malformed/oversized advice never extends a local deadline."""
    if type(value) is not str or not 0 < len(value) <= 128:
        return 1.0
    if re.fullmatch(r'[0-9]{1,10}', value):
        return min(MAX_COOLDOWN, float(value))
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None or not re.fullmatch(r'[A-Za-z]{3}, [0-9]{2} [A-Za-z]{3} [0-9]{4} [0-9:]{8} GMT', value):
            return 1.0
        return min(MAX_COOLDOWN, max(0.0, parsed.timestamp() - wall()))
    except (ValueError, OverflowError, TypeError):
        return 1.0


class RateLimited(PanError):
    def __init__(self, delay=1.0):
        super().__init__('PAN_RATE_LIMITED')
        self.delay = min(MAX_COOLDOWN, max(0.0, delay))


class Cooldowns:
    """Only current account scopes share advice; no global provider stall."""
    def __init__(self, clock=time.monotonic):
        self.clock, self.lock, self.values = clock, Lock(), OrderedDict()

    @staticmethod
    def key(expected):
        return expected['provider'], expected['account_id'], expected['epoch']

    def mark(self, expected, delay):
        with self.lock:
            for key, until in tuple(self.values.items()):
                if until <= self.clock():
                    del self.values[key]
            key = self.key(expected)
            self.values[key] = max(self.values.get(key, 0), self.clock() + min(MAX_COOLDOWN, delay))
            self.values.move_to_end(key)
            while len(self.values) > 128:
                self.values.popitem(last=False)

    def remaining(self, expected):
        with self.lock:
            return max(0, self.values.get(self.key(expected), 0) - self.clock())


class Operation:
    def __init__(self, expected, request_id, kind, *, clock=time.monotonic,
                 seconds=24, max_requests=16, max_pages=1, max_items=100,
                 current=None, cooldowns=None):
        if (type(request_id) is not str or not re.fullmatch(r'[0-9a-f]{32}', request_id)
                or kind not in SAFE_OPERATIONS | {'login', 'resolve'}
                or type(seconds) not in (int, float) or not 0 < seconds <= SCAN_LIMITS['seconds']
                or any(type(value) is not int or value < 1 for value in (max_requests, max_pages, max_items))):
            raise PanError('PAN_OPERATION_EXPIRED')
        self.expected, self.id, self.kind = scope(expected), request_id, kind
        limits = SCAN_LIMITS if kind == 'scan' else dict(seconds=24, max_requests=16, max_pages=8, max_items=160)
        self.clock, self.deadline = clock, clock() + min(limits['seconds'], seconds)
        self.max_requests, self.max_pages, self.max_items = (
            min(limits['max_requests'], max_requests), min(limits['max_pages'], max_pages), min(limits['max_items'], max_items))
        self.requests = self.pages = self.items = 0
        self.cancelled, self.lock, self.current = Event(), Lock(), current
        self.cooldowns, self.maintaining = cooldowns, False

    @contextmanager
    def maintenance(self):
        """Finish an initiated credential rotation under the original CAS.

        User cancellation stops business work, not the bounded identity check
        necessary to save a rotated token. Account revocation still wins.
        """
        self.check()
        self.maintaining = True
        try:
            yield
        finally:
            self.maintaining = False

    def check(self):
        if self.current:
            self.current(self.expected)
        if self.cancelled.is_set() and not self.maintaining:
            raise PanError('PAN_OPERATION_CANCELLED')
        if self.clock() >= self.deadline:
            raise PanError('PAN_BUDGET_EXHAUSTED')

    def consume_request(self):
        self.check()
        if self.cooldowns:
            self.wait(self.cooldowns.remaining(self.expected))
        with self.lock:
            if self.requests >= self.max_requests:
                raise PanError('PAN_BUDGET_EXHAUSTED')
            self.requests += 1

    def consume_page(self, count):
        self.check()
        with self.lock:
            if self.pages >= self.max_pages or self.items + count > self.max_items:
                raise PanError('PAN_BUDGET_EXHAUSTED')
            self.pages += 1
            self.items += count

    def wait(self, delay):
        self.check()
        if self.clock() + delay >= self.deadline:
            raise PanError('PAN_RATE_LIMITED')
        # Account checks every tick; explicit cancel wakes immediately.
        end = self.clock() + delay
        while self.clock() < end:
            (Event() if self.maintaining else self.cancelled).wait(min(.1, end - self.clock()))
            self.check()


def safe_read(provider, method, url):
    """Explicit business-route whitelist, never a blanket GET/POST retry."""
    routes = {
        'quark': {('GET', 'https://drive-pc.quark.cn/1/clouddrive/file/sort')},
        'uc': {('GET', 'https://pc-api.uc.cn/1/clouddrive/file/sort')},
        'baidu': {('GET', 'https://pan.baidu.com/api/list'), ('GET', 'https://pan.baidu.com/api/filemetas')},
        'aliyun': {('POST', 'https://api.alipan.com/adrive/v3/file/list'), ('POST', 'https://api.alipan.com/v2/file/get'),
                   ('POST', 'https://api.aliyundrive.com/adrive/v3/file/list'), ('POST', 'https://api.aliyundrive.com/v2/file/get')},
        '123': {('GET', 'https://yun.123pan.com/b/api/file/list/new')},
        '189': {('GET', 'https://cloud.189.cn/api/open/file/listFiles.action'),
                ('GET', 'https://cloud.189.cn/api/open/file/getFileInfo.action')},
        '139': {('POST', 'https://yun.139.com/orchestration/personalCloud/catalog/v1.0/getDirectoryCatalog')},
        'guangya': {('POST', 'https://api.guangyapan.com/userres/v1/file/get_file_list')},
        'xunlei': {('GET', 'https://api-pan.xunlei.com/drive/v1/files')},
    }
    return ((method, url) in routes.get(provider, ()) or
            provider == '139' and method == 'POST' and bool(re.fullmatch(
                r'https://personal(?:-[a-z0-9]+){0,3}\.yun\.139\.com/hcy/file/list', url)))
