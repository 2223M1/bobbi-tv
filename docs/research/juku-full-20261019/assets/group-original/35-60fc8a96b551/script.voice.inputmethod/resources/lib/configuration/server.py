"""Authenticated LAN configuration bridge.

Kodi's settings window is painful to drive with a remote, and a Doubao API Key
is far easier to paste on a phone than to type on a TV.  This module serves a
small web page over the LAN so both can be done from another device.

Security model, all enforced here rather than in the page:

* The server only answers while an entry is *activated*, and activation
  (``Configuration.activate``) is triggered from the TV itself.
* Every request must carry a 32-byte URL-safe token.  The token rides in the
  QR code fragment (``#token``), which browsers never send to the server, so it
  does not end up in access logs or Referer headers.
* A typed 6-digit PIN exists for the case where the phone cannot scan.  PIN
  attempts are rate limited per client address.
* Requests must come from a private or loopback address, and a cross-origin
  ``Origin`` is rejected.
* Everything expires after 30 minutes.

Nothing here touches ``xbmcaddon`` off the Kodi main thread: HTTP handlers only
enqueue work, and ``pump()`` performs it while the service loop runs.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import fcntl
import hmac
import json
from pathlib import Path
import queue
import secrets
import threading
import time
from urllib.parse import urlsplit
import wave
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..settings import Settings, web_schema
from ..storage import atomic_write


@contextmanager
def capture_idle(profile):
    """Refuse to configure while a dictation is recording."""
    with (Path(profile) / 'capture.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('请先结束当前语音，再保存或测试配置。') from None
        yield


class Configuration:
    # Other add-ons on a real box already squat on common ports (8767 is taken
    # by service.ysp.live), so walk a short range instead of trusting one.
    PORTS = (8767, 8768, 8769, 8770, 8771)
    ENTRY_MINUTES = 30
    PIN_ATTEMPTS = 5

    def __init__(self, root, profile, addon, ports=PORTS):
        self.root, self.profile = Path(root), Path(profile)
        self.settings = Settings(addon)
        self.queue = queue.Queue()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.job_stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='voice-config')
        self.token = secrets.token_urlsafe(32)
        self.expires = 0.0
        self.pin = ''
        self.pair_attempts = {}
        self.snapshot = {'settings': self.settings.values(), 'schema': web_schema(),
                         'keys': {}, 'jobs': {}, 'version': addon.getAddonInfo('version')}
        self.http = self.listen(ports)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever,
                                       name='voice-input-web', daemon=True)
        self.thread.start()
        self.refresh_keys()

    def listen(self, ports):
        """Listen on the first free port; raise only if every candidate is taken."""
        error = None
        for port in ports:
            try:
                return ThreadingHTTPServer(('0.0.0.0', port), self.handler())
            except OSError as caught:
                error = caught
        raise error

    @property
    def port(self):
        return self.http.server_port

    def activate(self):
        """Open a fresh 30-minute entry and return its token."""
        # A new entry gets a new token too: the old one may already be in a
        # phone's sessionStorage from an earlier session.
        self.token = secrets.token_urlsafe(32)
        self.pin = str(secrets.randbelow(1000000)).zfill(6)
        self.pair_attempts.clear()
        self.expires = time.monotonic() + self.ENTRY_MINUTES * 60
        return self.token

    def authenticated(self, supplied):
        return time.monotonic() < self.expires and hmac.compare_digest(supplied or '', self.token)

    def state(self):
        with self.lock:
            return copy.deepcopy(self.snapshot)

    def refresh_keys(self):
        with self.lock:
            self.snapshot['keys'] = {
                'doubao': (self.profile / 'doubao-api-key.txt').is_file()}

    def pump(self):
        """Called from the Kodi service loop; handlers never touch xbmcaddon."""
        with self.lock:
            self.snapshot['settings'] = self.settings.values()
        for unused in range(10):
            try:
                action, payload, event, result = self.queue.get_nowait()
            except queue.Empty:
                return
            try:
                if action == 'config':
                    with capture_idle(self.profile):
                        result.update(self.save_config(payload))
                else:
                    raise ValueError('未知配置操作。')
            except ValueError as error:
                result['error'] = str(error)
            except Exception:
                result['error'] = '无法保存设置，请重试。'
            finally:
                event.set()

    def save_config(self, payload):
        from ..doubao_config import save_key as save_doubao, validate_key
        changes, keys = payload.get('settings', {}), payload.get('keys', {})
        if not isinstance(keys, dict) or set(keys) - {'doubao'}:
            raise ValueError('凭据类型无效。')
        validated = {name: validate_key(value) for name, value in keys.items() if value}
        changes = dict(changes)
        # The key is always stored in the profile directory, never wherever an
        # older doubao_key_file pointed, so switching machines stays correct.
        changes.pop('doubao_key_file', None)
        validated_changes = self.settings.validate_changes(changes)
        for key in validated.values():
            save_doubao(self.profile, key)
        if validated:
            validated_changes['doubao_key_file'] = str(self.profile / 'doubao-api-key.txt')
        self.settings.apply(validated_changes)
        with self.lock:
            self.snapshot['settings'] = self.settings.values()
        self.refresh_keys()
        return {'ok': True}

    def request(self, action, payload):
        event, result = threading.Event(), {}
        self.queue.put((action, payload, event, result))
        if not event.wait(5):
            raise ValueError('配置服务忙，请稍后重试。')
        if result.get('error'):
            raise ValueError(result['error'])
        return result

    def job(self, kind):
        if kind != 'doubao':
            raise ValueError('未知测试操作。')
        with self.lock:
            if any(value.get('state') == 'running' for value in self.snapshot['jobs'].values()):
                raise ValueError('请先等待当前测试结束。')
            identifier = secrets.token_hex(12)
            self.snapshot['jobs'] = {identifier: {'state': 'running', 'kind': kind}}
            values = dict(self.snapshot['settings'])
            cancelled_event = threading.Event()
            self.job_stop = cancelled_event

        def cancelled():
            return self.stop.is_set() or cancelled_event.is_set()

        def work():
            began = time.monotonic()
            try:
                with capture_idle(self.profile):
                    from ..doubao_recognizer import DoubaoRecognizer
                    with wave.open(str(self.root / 'resources/config/asr-test.wav'), 'rb') as source:
                        if (source.getnchannels(), source.getsampwidth(),
                                source.getframerate()) != (1, 2, 16000):
                            raise ValueError('测试音频格式不正确。')
                        pcm = source.readframes(source.getnframes())
                    with DoubaoRecognizer(self.root, self.profile, values['doubao_resource_id'],
                                          values['doubao_timeout'], cancelled,
                                          key_file=values['doubao_key_file']) as engine:
                        for offset in range(0, len(pcm), 3200):
                            engine.accept(pcm[offset:offset + 3200])
                        text = engine.finish()
                result = {'state': 'done', 'kind': kind, 'text': text,
                          'expected': '甚至出现交易几乎停滞的情况。',
                          'elapsed_seconds': round(time.monotonic() - began, 3)}
            except InterruptedError:
                result = {'state': 'cancelled', 'kind': kind}
            except Exception as error:
                message = str(error) if isinstance(error, (ValueError, RuntimeError)) \
                    else '测试失败，请检查网络和配置。'
                result = {'state': 'error', 'kind': kind, 'error': message[:600]}
            with self.lock:
                self.snapshot['jobs'][identifier] = result

        self.pool.submit(work)
        return {'job': identifier}

    def cancel_job(self):
        self.job_stop.set()
        return {'ok': True}

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value, content_type='application/json; charset=utf-8'):
                data = value if isinstance(value, bytes) else json.dumps(
                    value, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(data)

            def valid_origin(self):
                host = self.headers.get('Host', '')
                try:
                    import ipaddress
                    hostname = urlsplit('http://' + host).hostname
                    valid_host = hostname == 'localhost' or ipaddress.ip_address(hostname).is_private
                except (ValueError, TypeError):
                    valid_host = False
                origin = self.headers.get('Origin')
                return valid_host and (not origin or origin == 'http://' + host)

            def valid_request(self):
                supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
                return self.valid_origin() and owner.authenticated(supplied)

            def do_GET(self):
                if self.path in ('/', '/index.html'):
                    return self.reply(200, (owner.root / 'resources/web/index.html').read_bytes(),
                                      'text/html; charset=utf-8')
                if not self.valid_request():
                    return self.reply(401, {'error': '配置入口已关闭或过期，请重新扫码。'})
                if self.path == '/api/state':
                    return self.reply(200, owner.state())
                self.reply(404, {'error': '页面不存在。'})

            def do_POST(self):
                pairing = self.path == '/api/pair'
                if not self.valid_origin() or (not pairing and not self.valid_request()):
                    return self.reply(401, {'error': '配置入口已关闭或过期，请重新扫码。'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 32768 or \
                            self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                        raise ValueError('配置数据无效。')
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError('配置数据无效。')
                    if pairing:
                        address = self.client_address[0]
                        with owner.lock:
                            attempts = owner.pair_attempts.get(address, 0) + 1
                            owner.pair_attempts[address] = attempts
                            code = payload.get('code', '')
                            if (attempts > owner.PIN_ATTEMPTS or not isinstance(code, str) or
                                    len(code) != 6 or not code.isascii() or
                                    not hmac.compare_digest(code, owner.pin) or
                                    time.monotonic() >= owner.expires):
                                raise ValueError('配置码错误或已过期，请重新打开电视上的扫码配置。')
                        value = {'token': owner.token}
                    elif self.path == '/api/config':
                        value = owner.request('config', payload)
                    elif self.path == '/api/job/cancel':
                        value = owner.cancel_job()
                    elif self.path.startswith('/api/job/'):
                        value = owner.job(self.path[len('/api/job/'):])
                    else:
                        return self.reply(404, {'error': '操作不存在。'})
                    self.reply(200, value)
                except (ValueError, TypeError) as error:
                    self.reply(400, {'error': str(error)[:400]})
                except Exception:
                    self.reply(500, {'error': '配置服务暂时不可用。'})

        return Handler

    def close(self):
        self.stop.set()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=1)
        self.pool.shutdown(wait=True)
