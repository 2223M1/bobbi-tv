"""Real loopback Range admission with fake upstream; not cloud playback QA."""
from copy import deepcopy
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_core.share_stream import Binding, checked as checked_115
from bobbi_platform import pan_stream
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from bobbi_platform.host import Host
from bobbi_platform.account_manager import AccountError, validate_snapshot
from test_ce2096_pan_accounts import saved


FILE = dict(file_id='file1', name='movie.mkv', size=8, directory=False)


@pytest.fixture
def service(tmp_path):
    owner = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    current = owner.accounts.install(saved(), owner.accounts.snapshot('quark'))
    calls = []
    def resolve(selected):
        calls.append(deepcopy(selected))
        return dict(original=True, url='https://download.quark.cn/original?fixture=private', size=selected['size'],
            headers={'User-Agent': 'test', 'Referer': 'https://pan.quark.cn/', 'Cookie': 'fixture=private-cookie'})
    owner.client_factory = lambda *a: SimpleNamespace(resolve_original=resolve,
        list_files=lambda *a, **kw: dict(items=[deepcopy(FILE)], has_more=False, page=1))
    yield owner, current, calls
    owner.close()


class Upstream:
    def __init__(self, seen):
        self.seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, headers, **kw):
        self.seen.append((url, dict(headers), kw))
        start, end = map(int, headers['Range'][6:].split('-'))
        class Reply:
            status_code = 206
            headers = {'Content-Range': 'bytes %d-%d/8' % (start, end), 'Content-Length': str(end-start+1)}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, size): yield b'abcdefgh'[start:end+1]
        return Reply()


def read(url):
    parsed = urlsplit(url)
    conn = HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        conn.request('GET', parsed.path, headers={'Range': 'bytes=2-5'})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_personal_file_uses_existing_range_engine_secrets_never_leave_host(service):
    owner, current, calls = service
    ready = owner.open_stream(current, FILE, 'a'*32)
    seen = []
    owner.streams.session_factory = lambda: Upstream(seen)
    assert 'private' not in json.dumps(ready) and ready['media'].startswith('file:')
    assert ready['url'].startswith('http://127.0.0.1:')
    status, headers, payload = read(ready['url'])
    assert status == 206 and payload == b'cdef'
    assert 'private' not in repr(headers)
    assert seen[0][1]['Cookie'] == 'fixture=private-cookie'
    assert seen[0][2]['allow_redirects'] is False
    assert owner.open_stream(current, FILE, 'a'*32) == ready and len(calls) == 1
    with pytest.raises(ValueError, match='RETARGETED'):
        owner.open_stream(current, dict(FILE, name='other.mkv'), 'a'*32)
    owner.accounts.logout(current)
    assert read(ready['url'])[0] == 404


def test_personal_binding_is_not_a_fake_115_locator(service):
    owner, current, calls = service
    value = pan_stream.body('quark', FILE, 'b'*32)
    with pytest.raises(ValueError):
        checked_115(value)
    with pytest.raises(ValueError):
        checked_115({k: value[k] for k in ('request_id', 'locator', 'guid', 'title', 'size', 'media')})
    legacy = Binding(dict(value), lambda *_: 'https://download.quark.cn/f|User-Agent=x&Cookie=private', lambda _: True)
    with pytest.raises(ValueError, match='TRANSPORT_INVALID'):
        legacy.grant()


@pytest.mark.parametrize('change', [dict(url='https://evil.test/video'), dict(headers={'User-Agent': 'x', 'Authorization': 'secret'}),
    dict(headers={'User-Agent': 'x', 'Referer': 'https://evil.test/'}), dict(size=9), dict(original=False)])
def test_foreign_cdn_credentials_and_changed_size_rejected(change):
    value = dict(url='https://download.quark.cn/file', headers={'User-Agent': 'x'}, size=8, original=True)
    value.update(change)
    with pytest.raises(PanError):
        pan_stream.address(pan_stream.body('quark', FILE, 'b'*32), value)


def test_ticket_is_single_use_current_account_and_real_listed_selection(service):
    owner, current, calls = service
    with pytest.raises(PanError, match='PLAY_EXPIRED'):
        owner.prepare_play(current, FILE)
    owner.list_files(current, '0', 1)
    ticket = owner.prepare_play(current, FILE)['ticket']
    assert owner.claim_play(ticket)['selected'] == FILE
    with pytest.raises(PanError, match='PLAY_EXPIRED'):
        owner.claim_play(ticket)
    ticket = owner.prepare_play(current, FILE)['ticket']
    owner.accounts.logout(current)
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        owner.claim_play(ticket)
    assert not calls


def test_cancel_before_or_during_resolution_cannot_publish_a_late_url(service):
    owner, current, calls = service
    owner.close_stream(current, 'a'*32)
    with pytest.raises(PanError, match='CANCELLED'):
        owner.open_stream(current, FILE, 'a'*32)
    started, release, errors = Event(), Event(), []
    def resolve(selected):
        started.set()
        assert release.wait(2)
        return dict(url='https://download.quark.cn/file', headers={'User-Agent': 'x'}, size=8, original=True)
    owner.client_factory = lambda *a: SimpleNamespace(resolve_original=resolve)
    def work():
        try: owner.open_stream(current, FILE, 'b'*32)
        except Exception as e: errors.append(e)
    thread = Thread(target=work)
    thread.start()
    assert started.wait(2)
    owner.close_stream(current, 'b'*32)
    release.set()
    thread.join(2)
    assert not thread.is_alive() and len(errors) == 1
    assert owner.streams.records['b'*32].address is None


def test_playback_scope_router_never_widens_115_preparation(tmp_path):
    host = Host(tmp_path)
    host.start()
    try:
        assert host.pans is None
        pans = host._pans()
        current = pans.accounts.install(saved(), pans.accounts.snapshot('quark'))
        assert host.playback_accounts.run_if_current(current, lambda: 'allowed') == 'allowed'
        with pytest.raises(AccountError):
            host.accounts.require_current(current)
        with pytest.raises(AccountError):
            validate_snapshot(current)
        uc = pans.accounts.install(saved('uc'), pans.accounts.snapshot('uc'))
        pans.accounts.logout(uc)
        assert host.playback_accounts.is_current(current)
        pans.accounts.logout(current)
        assert not host.playback_accounts.is_current(current)
        assert host.account_changes.is_set()
    finally:
        host.close()


def test_foreign_account_cannot_cancel_or_tombstone_another_stream(service):
    owner, current, calls = service
    owner.open_stream(current, FILE, 'a'*32)
    other = owner.accounts.install(saved('uc'), owner.accounts.snapshot('uc'))
    with pytest.raises(PanError, match='SCOPE_INVALID'):
        owner.close_stream(other, 'a'*32)
    assert 'a'*32 not in owner.cancelled_streams
    assert not owner.streams.records['a'*32].cancelled()
    assert owner.open_stream(current, FILE, 'a'*32)['state'] == 'ready'


@pytest.mark.parametrize('changed', [False, True])
def test_expired_upstream_rechecks_exact_file_before_retry_not_another_source(service, changed):
    owner, current, calls = service
    resolved, fetched = [], []
    def resolve(selected):
        resolved.append(deepcopy(selected))
        if len(resolved) > 1 and changed:
            raise PanError('PAN_FILE_CHANGED')
        return dict(original=True, size=8, url='https://download.quark.cn/file?v=%d' % len(resolved),
                    headers={'User-Agent': 'test'})
    owner.client_factory = lambda *a: SimpleNamespace(resolve_original=resolve)
    ready = owner.open_stream(current, FILE, 'c'*32)
    class Expiring(Upstream):
        def get(self, url, headers, **kw):
            fetched.append(url)
            if len(fetched) == 1:
                class Denied:
                    status_code, headers = 403, {}
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return Denied()
            return super().get(url, headers, **kw)
    owner.streams.session_factory = lambda: Expiring([])
    status, headers, payload = read(ready['url'])
    assert resolved == [FILE, FILE]
    if changed:
        assert status == 503 and len(fetched) == 1
        assert b'PAN_' not in payload and b'quark.cn' not in payload
    else:
        assert status == 206 and payload == b'cdef' and len(fetched) == 2
        assert fetched[0] != fetched[1]
