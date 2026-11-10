"""Offline wire, stable-page and cancellation regressions for the review work."""
from copy import deepcopy
from io import BytesIO
from threading import Event, Thread
from types import SimpleNamespace
from urllib.error import HTTPError
import time

import pytest

from bobbi_platform import runtime, pan_service, pan_stream, pan_ui
from bobbi_platform.pan_accounts import PanError, empty_scope
from bobbi_platform.pan_http import Session
from bobbi_platform.pan_providers import DESCRIPTORS, descriptor
from bobbi_platform.pan_request_policy import Operation, Cooldowns, retry_after, safe_read
from test_ce2096_pan_accounts import saved
from test_ce2096_pan_ui import ui


@pytest.mark.parametrize('size', [16383, 16384, 16385])
@pytest.mark.parametrize('kind', ['request', 'reply'])
def test_real_runtime_utf8_exact_byte_boundaries(tmp_path, monkeypatch, size, kind):
    path = tmp_path / 'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    text = '中文🙂'
    container = (lambda value: dict(action='boundary', body=dict(text=value))) if kind == 'request' else (
        lambda value: dict(ok=True, result=value))
    text += 'x' * (size - len(runtime.encode_message(container(text))))
    assert len(runtime.encode_message(container(text))) == size
    server = runtime.Runtime(lambda *args: text if kind == 'reply' else {}, path)
    server.start()
    try:
        if size > runtime.MAX_MESSAGE_BYTES:
            with pytest.raises(ValueError):
                runtime.call('boundary', dict(text=text) if kind == 'request' else {})
        else:
            assert runtime.call('boundary', dict(text=text) if kind == 'request' else {}) == (text if kind == 'reply' else {})
    finally:
        server.close()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object(), '\ud800'])
def test_wire_invalid_objects_never_serialize(value):
    with pytest.raises((ValueError, TypeError)):
        runtime.encode_message(dict(value=value))


@pytest.fixture
def listing(tmp_path):
    service = pan_service.PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    items = [dict(file_id=str(i), name='同名长中文' * 12 + '.mkv', directory=False, size=8) for i in range(7)]
    calls = []
    def read(parent, page, size):
        calls.append((parent, page, size))
        return dict(items=deepcopy(items), page=page, has_more=False)
    service.client_factory = lambda *args: SimpleNamespace(list_files=read)
    yield service, expected, items, calls
    service.close()


def split_budget(monkeypatch, items):
    limit = len(runtime.encode_message(dict(ok=True, result=dict(items=items[:3], page=1,
        has_more=True, upstream_has_more=False, continuation='a'*32 + '.3'))))
    monkeypatch.setattr(pan_service, 'DIRECTORY_REPLY_BYTES', limit)


def test_terminal_upstream_page_splits_3_3_1_replay_and_back(listing, monkeypatch):
    service, expected, items, calls = listing
    split_budget(monkeypatch, items)
    first = service.list_files(expected, '0', 1)
    second = service.list_files(expected, '0', 1, continuation=first['continuation'])
    assert second == service.list_files(expected, '0', 1, continuation=first['continuation'])
    last = service.list_files(expected, '0', 1, continuation=second['continuation'])
    assert second == service.list_files(expected, '0', 1, continuation=first['continuation'])
    assert [len(r['items']) for r in (first, second, last)] == [3, 3, 1]
    assert first['has_more'] and second['has_more'] and not last['has_more']
    assert not first['upstream_has_more'] and 'continuation' not in last
    assert first['items'] + second['items'] + last['items'] == items
    assert calls == [('0', 1, 10)]


@pytest.mark.parametrize('change', ['time', 'refresh', 'account', 'parent', 'page'])
def test_continuation_invalidates_without_silent_empty_directory(listing, monkeypatch, change):
    service, expected, items, calls = listing
    split_budget(monkeypatch, items)
    first = service.list_files(expected, '0', 1)
    parent, page = '0', 1
    if change == 'time':
        now = service.clock()
        service.clock = lambda: now + 21
    elif change == 'refresh':
        service.list_files(expected, '0', 1, refresh=True)
    elif change == 'account':
        expected = service.accounts.install(saved(), expected)
    elif change == 'parent':
        parent = '1'
    else:
        page = 2
    with pytest.raises(PanError, match='PAGE_EXPIRED'):
        service.list_files(expected, parent, page, continuation=first['continuation'])


def test_one_large_item_is_explicit_and_cache_has_no_selection_proof(listing, monkeypatch):
    service, expected, items, calls = listing
    monkeypatch.setattr(pan_service, 'DIRECTORY_REPLY_BYTES', 100)
    with pytest.raises(PanError, match='ITEM_TOO_LARGE'):
        service.list_files(expected, '0', 1)
    assert not service.directory_cache and not service.directory_pages


def test_cancel_before_begin_and_operation_have_bounded_tombstones(listing):
    service, expected, items, calls = listing
    assert service.cancel('quark', 'a'*32)['state'] == 'cancel_requested'
    assert service.begin('quark', 'a'*32, expected)['state'] == 'cancelled'
    service.cancel_operation(expected, 'b'*32)
    with pytest.raises(PanError, match='OPERATION_EXPIRED'):
        service.list_files(expected, '0', 1, operation_id='b'*32)
    assert not calls
    for i in range(160):
        service.cancel('quark', '%032x' % i)
        service.cancel_operation(expected, '%032x' % i)
    assert len(service.cancelled_attempts) <= 128 and len(service.operation_receipts) <= 128


def test_scan_budget_shared_across_pages_and_window_fixed(listing):
    service, expected, items, calls = listing
    with service.scan_operation(expected, max_pages=2, max_items=14) as op:
        assert len(service.list_for_scan(expected, '0', 1, operation=op)['items']) == 7
        service.list_for_scan(expected, '0', 2, operation=op)
        with pytest.raises(PanError, match='BUDGET_EXHAUSTED'):
            service.list_for_scan(expected, '0', 3, operation=op)
        assert op.pages == 2 and op.items == 14
    assert calls == [('0', 1, 20), ('0', 2, 20)]


def test_cancel_during_directory_rejects_late_publication(listing):
    service, expected, items, calls = listing
    def read(*args, **kwargs):
        service.cancel_operation(expected, 'c'*32)
        return dict(items=items, has_more=False)
    service.client_factory = lambda *args: SimpleNamespace(list_files=read)
    with pytest.raises(PanError, match='OPERATION_CANCELLED'):
        service.list_files(expected, '0', 1, operation_id='c'*32)
    assert not service.directory_cache and not service.directory_pages


def test_cancelled_business_keeps_completed_rotation_cas_but_not_directory(listing):
    service, expected, items, calls = listing
    def renew(publish):
        service.cancel_operation(expected, 'd'*32)
        # Identity validation after token exchange is maintenance, not another
        # directory request. It shares the finite original call budget.
        operation = service.operations['d'*32]
        operation.consume_request()
        publish(saved(session='rotated'), saved())
    service.client_factory = lambda *args: SimpleNamespace(renew_if_needed=renew,
        list_files=lambda *args, **kw: pytest.fail('Cancelled business cannot run'))
    with pytest.raises(PanError, match='OPERATION_CANCELLED'):
        service.list_files(expected, '0', 1, operation_id='d'*32)
    assert service.accounts.credentials(expected) == saved(session='rotated')
    assert not service.directory_cache


def test_account_revocation_during_rotation_still_rejects_cas(listing):
    service, expected, items, calls = listing
    def renew(publish):
        service.accounts.logout(expected)
        publish(saved(session='rotated'), saved())
    service.client_factory = lambda *args: SimpleNamespace(renew_if_needed=renew)
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        service.list_files(expected, '0', 1)
    assert not service.accounts.snapshot('quark')['authenticated']


@pytest.mark.parametrize('value,expected', [('0', 0), ('3', 3), ('9999999999', 5),
    ('-1', 1), ('nan', 1), ('1.5', 1), ('x'*129, 1), (None, 1),
    ('Thu, 01 Jan 1970 00:00:04 GMT', 4), ('Thu, 01 Jan 1970 00:00:00 GMT', 0)])
def test_retry_after_strict_bounded_seconds_and_dates(value, expected):
    assert retry_after(value, wall=lambda: 0) == expected


@pytest.mark.parametrize('url,body,safe', [
    ('https://api.alipan.com/adrive/v3/file/list', {}, True),
    ('https://auth.alipan.com/v2/account/token', {}, False),
    ('https://passport.aliyundrive.com/newlogin/qrcode/generate.do', None, False)])
def test_only_semantically_read_only_routes_replay_429(url, body, safe):
    calls = []
    class Reply(BytesIO):
        status, headers = 200, {'Content-Length': '2'}
    def open(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(url, 429, 'secret-body', {'Retry-After': '0'}, BytesIO(b'secret'))
        return Reply(b'{}')
    session = Session('aliyun', opener=SimpleNamespace(open=open))
    session.operation = Operation(empty_scope('aliyun'), 'a'*32, 'directory')
    if safe:
        assert session.request(url, body=body) == {}
    else:
        with pytest.raises(PanError, match='^PAN_RATE_LIMITED$'):
            session.request(url, body=body)
    assert len(calls) == (2 if safe else 1)


def test_retries_use_shared_attempt_limit():
    calls = []
    def open(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 429, 'secret', {'Retry-After': '0'}, BytesIO())
    session = Session('aliyun', opener=SimpleNamespace(open=open))
    session.operation = Operation(empty_scope('aliyun'), 'a'*32, 'scan', max_requests=1)
    with pytest.raises(PanError, match='BUDGET_EXHAUSTED'):
        session.request('https://api.alipan.com/adrive/v3/file/list', body={})
    assert len(calls) == 1


def test_cooldown_cancel_wakes_and_is_account_scoped():
    policy = Cooldowns()
    first, other = empty_scope('quark'), empty_scope('uc')
    policy.mark(first, 5)
    assert policy.remaining(first) > 0 and policy.remaining(other) == 0
    operation = Operation(first, 'a'*32, 'directory', cooldowns=policy)
    started, finished, errors = Event(), Event(), []
    def work():
        started.set()
        try:
            operation.consume_request()
        except PanError as error:
            errors.append(str(error))
        finally:
            finished.set()
    worker = Thread(target=work)
    worker.start()
    assert started.wait(1)
    operation.cancelled.set()
    assert finished.wait(.5)
    worker.join(1)
    assert errors == ['PAN_OPERATION_CANCELLED'] and operation.requests == 0


@pytest.mark.parametrize('expiry', [True, '123', float('nan'), float('inf'), 100, 100 + 8*86400])
def test_expiry_requires_finite_future_absolute_time(expiry):
    selected = dict(file_id='file', name='movie.mkv', size=8, directory=False)
    body = pan_stream.body('quark', selected, 'a'*32)
    result = dict(url='https://download.quark.cn/file', size=8, original=True,
                  headers={'User-Agent': 'test'}, expires_at=expiry)
    with pytest.raises(PanError, match='EXPIRY_INVALID'):
        pan_stream.address(body, result, clock=lambda: 100)


def test_expiry_reuses_existing_resource_type_and_none_is_not_guessed():
    from bobbi_core.share_stream import ResolvedResource
    body = pan_stream.body('quark', dict(file_id='file', name='movie.mkv', size=8, directory=False), 'a'*32)
    result = dict(url='https://download.quark.cn/file?expire=99999999', size=8, original=True,
                  headers={'User-Agent': 'test'})
    resource = pan_stream.address(body, result, clock=lambda: 100)
    assert isinstance(resource, ResolvedResource) and resource.expires_at is None
    assert pan_stream.address(body, dict(result, expires_at=200), clock=lambda: 100).expires_at == 200


def test_descriptor_is_static_and_public_contract_has_no_credentials():
    assert set(DESCRIPTORS) == {'quark', 'uc', 'baidu', 'aliyun', '123', '139', '189', 'guangya', 'xunlei'}
    assert descriptor('baidu').root == '/' and descriptor('baidu').parent_field == 'path'
    assert {p for p in DESCRIPTORS if descriptor(p).pagination == 'cursor'} == {'aliyun', '139', 'xunlei'}
    for row in DESCRIPTORS.values():
        assert set(row.public()) == {'root', 'pagination', 'parent_field', 'capabilities', 'verification'}
        assert row.public()['verification'] == 'not_device_verified'
    with pytest.raises(PanError):
        descriptor('unknown')


def test_begin_is_visible_before_network_cancel_does_not_wait_for_receipt(ui, tmp_path, monkeypatch):
    release, finished, cancel_started = Event(), Event(), Event()
    def call(action, body, **kw):
        ui.calls.append((action, body))
        if action == 'pan_login_begin':
            assert ui.window is not None
            ui.window.cancelled = True
            assert release.wait(2)
            finished.set()
            return dict(state='waiting', qr='https://example.invalid/late')
        if action == 'pan_login_cancel':
            cancel_started.set()
            assert release.wait(2)
            return dict(state='cancelled')
        pytest.fail('Late begin cannot poll/commit')
    monkeypatch.setattr(pan_ui, 'call', call)
    started = time.monotonic()
    try:
        assert pan_ui.login(ui.row, ui.dialog) is False
        assert time.monotonic() - started < .5
        assert cancel_started.wait(.2) and not finished.is_set()
        assert not list(tmp_path.glob('bobbi-pan-qr-*'))
    finally:
        release.set()
    assert finished.wait(1)
    assert not list(tmp_path.glob('bobbi-pan-qr-*')) and not ui.messages


def test_navigation_survives_reopen_but_is_not_a_selected_file_capability(ui, tmp_path):
    expected=dict(provider='quark',account_id='quark:'+'a'*64,epoch=1,authenticated=True)
    stack=[dict(parent='folder1',title='我的目录',page=3,positions={3:dict(page=3,cursor='')},focus=4)]
    pan_ui._save_navigation(expected,stack)
    restored=pan_ui._load_navigation(expected)
    assert restored[0]['parent']=='folder1' and restored[0]['focus']==4
    assert restored[0]['positions'][1]==dict(page=3,cursor='')
    assert pan_ui._load_navigation(dict(expected,epoch=2)) is None
    path=tmp_path/'pan-navigation-quark.json'
    raw=path.read_text(encoding='utf-8')
    assert 'selected' not in raw and 'ticket' not in raw and 'Cookie' not in raw
    stack[0]['positions'][3]['url']='https://signed.invalid/private'
    pan_ui._save_navigation(expected,stack)
    assert path.read_text(encoding='utf-8')==raw


def test_expiry_refreshes_before_rejection_once_per_concurrent_grant(listing, monkeypatch):
    from bobbi_core import share_stream
    service,expected,items,calls=listing
    now=[100.0]
    original=pan_stream.address
    monkeypatch.setattr(pan_stream,'address',lambda value,resolved: original(value,resolved,clock=lambda:now[0]))
    monkeypatch.setattr(share_stream.time,'time',lambda:now[0])
    resolutions=[]
    def resolve(selected):
        resolutions.append(now[0])
        return dict(url='https://download.quark.cn/file',size=8,original=True,
                    headers={'User-Agent':'test'},expires_at=now[0]+100)
    service.client_factory=lambda *args: SimpleNamespace(resolve_original=resolve)
    service.open_stream(expected,items[0],'f'*32)
    entry=service.streams.records['f'*32]
    first=entry.grant()
    assert resolutions==[100.0]
    now[0]=186.0
    values=[]
    workers=[Thread(target=lambda: values.append(entry.grant())) for _ in range(6)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(1)
    assert values==[first]*6 and resolutions==[100.0,186.0]
    assert entry.expires_at==286
    # Original shared 4 attempts / 300 seconds remains unchanged.
    for tick in (272,358):
        now[0]=tick;entry.grant()
    now[0]=444
    with pytest.raises(ValueError,match='SHARE_REFRESH_BUDGET'):
        entry.grant()
    assert len(resolutions)==4


@pytest.mark.parametrize('action,error,expected', [
    ('catalog_items',PanError('PAN_ACCOUNT_CHANGED'),'PAN_ACCOUNT_CHANGED'),
    ('catalog_preview',ValueError('CATALOG_REPLY_LIMIT'),'CATALOG_REPLY_LIMIT'),
    ('pan_status',ValueError('CATALOG_REPLY_LIMIT'),'Local service rejected request'),
    ('catalog_items',ValueError('CATALOG_secret_cookie'),'Local service rejected request')])
def test_catalog_ipc_errors_are_closed_and_action_scoped(tmp_path,monkeypatch,action,error,expected):
    path=tmp_path/'runtime.json'
    monkeypatch.setattr(runtime,'profile',lambda **kw:path)
    def dispatch(*args): raise error
    server=runtime.Runtime(dispatch,path);server.start()
    try:
        with pytest.raises(ValueError,match=expected): runtime.call(action,{})
    finally: server.close()
