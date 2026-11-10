"""Native cloud UI uses only Host IPC, never another account owner or player."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from bobbi_platform import pan_ui, pan_service, account_dialog, environment
from bobbi_platform.host import Host
from bobbi_platform.pan_accounts import empty_scope, PanError
from test_accounts import credential


@pytest.fixture
def ui(tmp_path, monkeypatch):
    state = SimpleNamespace(calls=[], messages=[], selections=[], menus=[], statuses=[], window=None,
                            cancel_poll=False, lost_commit=False, aborted=False, polls=0,
                            close_error=None, closes=0)
    state.row = dict(provider='quark', account=empty_scope('quark'), capabilities=['qr_login', 'list_files'])
    state.dialog = SimpleNamespace(ok=lambda *a: state.messages.append(a),
        select=lambda *a, **kw: (state.menus.append(a), state.selections.pop(0))[1],
        textviewer=lambda *a: state.messages.append(a))
    state.progress_cancel, state.progress_opened, state.progress_closed = False, 0, 0
    def progress():
        def opened(*a): state.progress_opened += 1
        def closed(): state.progress_closed += 1
        return SimpleNamespace(create=opened, close=closed, iscanceled=lambda: state.progress_cancel)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(DialogProgress=progress))
    monkeypatch.setattr(environment, 'private_path', lambda *a: tmp_path / 'pan-accounts-v1.json')
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda p: str(tmp_path)))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(
        abortRequested=lambda: state.aborted, waitForAbort=lambda seconds: state.aborted),
        executebuiltin=lambda value: None))
    def window(*args):
        def close():
            state.closes += 1
            if state.close_error is not None:
                raise state.close_error
        state.window = SimpleNamespace(cancelled=False, show=lambda: None, close=close,
                                       set_status=state.statuses.append, set_image=lambda *a: None)
        return state.window
    monkeypatch.setattr(account_dialog, 'create', window)
    def call(action, body, **kwargs):
        state.calls.append((action, deepcopy(body)))
        assert 'credentials' not in body
        if action == 'pan_login_begin':
            return dict(state='waiting', qr='https://su.quark.cn/fixture')
        if action == 'pan_login_poll':
            state.polls += 1
            assert state.polls <= 3
            state.window.cancelled = state.cancel_poll
            return dict(state='ready')
        if action == 'pan_login_commit':
            if state.lost_commit:
                raise OSError('fixture-sensitive')
            return dict(state='committed')
        if action == 'pan_login_cancel':
            return dict(state='committed' if state.lost_commit else 'cancelled')
        raise AssertionError(action)
    monkeypatch.setattr(pan_ui, 'call', call)
    return state


def test_ui_separate_commit_no_cookie_or_authorization_material(ui, tmp_path):
    assert pan_ui.login(ui.row, ui.dialog)
    assert [a for a, b in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_commit']
    assert not (tmp_path / 'pan-accounts-v1.json').exists()
    assert not list(tmp_path.glob('bobbi-pan-qr-*'))
    assert '播放尚未接入' in ui.messages[-1][1]


def test_return_during_inflight_poll_never_commits_ready_credentials(ui):
    ui.cancel_poll = True
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [a for a, b in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert not ui.messages


@pytest.mark.parametrize('abort', [False, True])
def test_cancel_does_not_wait_for_slow_poll_and_late_ready_never_commits(ui, monkeypatch, abort):
    from threading import Event
    release, finished = Event(), Event()
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action != 'pan_login_poll':
            return original(action, body, **kwargs)
        ui.calls.append((action, deepcopy(body)))
        if abort:
            ui.aborted = True
        else:
            ui.window.cancelled = True
        assert release.wait(2)
        finished.set()
        return dict(state='ready')
    monkeypatch.setattr(pan_ui, 'call', call)
    try:
        assert pan_ui.login(ui.row, ui.dialog) is False
        assert not finished.is_set()
        assert ui.calls[-1][0] == 'pan_login_cancel'
        assert 'pan_login_commit' not in [action for action, _ in ui.calls]
        assert not ui.messages
    finally:
        release.set()
    assert finished.wait(1)
    assert 'pan_login_commit' not in [action for action, _ in ui.calls]
    assert not ui.messages


def test_lost_commit_reply_cancel_reports_actual_commit_not_unchanged(ui):
    ui.lost_commit = True
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert ui.calls[-1][0] == 'pan_login_cancel'
    assert ui.messages[-1][0] == '登录已保存'
    assert 'fixture-sensitive' not in repr(ui.messages)


def test_kodi_close_failure_does_not_misreport_acknowledged_native_login(ui):
    ui.close_error = RuntimeError('synthetic Kodi window already closed')
    assert pan_ui.login(ui.row, ui.dialog) is True
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_commit']
    assert ui.messages[-1][0].startswith('已保存 ')
    assert not any(title == '未确认登录结果' for title, _ in ui.messages)


def test_kodi_close_failure_cannot_skip_native_cancel(ui):
    ui.close_error = RuntimeError('synthetic Kodi window already closed')
    ui.cancel_poll = True
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert not ui.messages


@pytest.mark.parametrize('code,message', [
    ('PAN_API_REJECTED', '网盘未接受本次请求'),
    ('PAN_HTTP_REJECTED', '网盘服务暂不接受连接'),
    ('PAN_REPLY_INVALID', '网盘返回的信息无法安全识别'),
    ('PAN_CHALLENGE_REQUIRED', '额外验证'),
    ('PAN_ACCOUNT_CHANGED', '账号已变更'),
])
def test_terminal_login_error_is_not_repolled_or_replaced_by_expiry(ui, monkeypatch, code, message):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action != 'pan_login_poll':
            return original(action, body, **kwargs)
        ui.calls.append((action, deepcopy(body)))
        ui.polls += 1
        if ui.polls == 1:
            raise PanError(code)
        return dict(state='failed')  # Host retains terminal failure, not its cause.
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert ui.polls == 1 and message in ui.messages[-1][1]
    assert '二维码已失效' not in repr(ui.messages)
    assert not any('正在重试' in status for status in ui.statuses)


@pytest.mark.parametrize('error', [
    PanError('PAN_NETWORK_ERROR'), PanError('PAN_QR_POLL_RETRY'),
    OSError('fixture-sensitive'), TimeoutError('fixture-sensitive'),
])
def test_transient_login_transport_error_retries_and_still_requires_commit(ui, monkeypatch, error):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action == 'pan_login_poll' and not ui.polls:
            ui.calls.append((action, deepcopy(body)))
            ui.polls += 1
            raise error
        return original(action, body, **kwargs)
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is True
    assert [action for action, _ in ui.calls] == [
        'pan_login_begin', 'pan_login_poll', 'pan_login_poll', 'pan_login_commit']
    assert any('正在重试' in status for status in ui.statuses)
    assert 'fixture-sensitive' not in repr(ui.messages + ui.statuses)


def test_login_transport_retries_are_bounded_and_never_commit_on_exhaustion(ui, monkeypatch):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action == 'pan_login_poll':
            ui.calls.append((action, deepcopy(body)))
            raise TimeoutError('fixture-sensitive')
        return original(action, body, **kwargs)
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == [
        'pan_login_begin', 'pan_login_poll', 'pan_login_poll', 'pan_login_poll', 'pan_login_cancel']
    assert sum('正在重试' in status for status in ui.statuses) == 2
    assert 'fixture-sensitive' not in repr(ui.messages + ui.statuses)
    assert '二维码已失效' not in repr(ui.messages)


@pytest.mark.parametrize('error', [PanError('PAN_API_REJECTED'), TimeoutError('fixture-sensitive')])
def test_cancel_during_error_reply_wins_without_retry_commit_or_failure_dialog(ui, monkeypatch, error):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action == 'pan_login_poll':
            ui.calls.append((action, deepcopy(body)))
            ui.window.cancelled = True
            raise error
        return original(action, body, **kwargs)
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert not ui.messages
    assert not any('正在重试' in status for status in ui.statuses)


@pytest.mark.parametrize('error', [
    ValueError('fixture-sensitive'), RuntimeError('fixture-sensitive'),
    TypeError('fixture-sensitive'), Exception('fixture-sensitive'),
    PanError('PAN_private-fixture-sensitive'),
    HTTPError('https://fixture-sensitive/', 403, 'fixture-sensitive', {}, None),
])
def test_unknown_login_failure_stops_without_retry_or_exception_text(ui, monkeypatch, error):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action == 'pan_login_poll':
            ui.calls.append((action, deepcopy(body)))
            raise error
        return original(action, body, **kwargs)
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert 'fixture-sensitive' not in repr(ui.messages + ui.statuses)
    assert '二维码已失效' not in repr(ui.messages)
    assert not any('正在重试' in status for status in ui.statuses)


@pytest.mark.parametrize('state,message', [
    ('failed', '本次登录未完成'), ('account_changed', '账号已变更'),
    ('cancelled', '本次扫码已结束'), ('unexpected', 'INVALID_STATE'),
])
def test_terminal_login_state_does_not_invent_qr_expiry(ui, monkeypatch, state, message):
    original = pan_ui.call
    def call(action, body, **kwargs):
        if action == 'pan_login_poll':
            ui.calls.append((action, deepcopy(body)))
            return dict(state=state)
        return original(action, body, **kwargs)
    monkeypatch.setattr(pan_ui, 'call', call)
    assert pan_ui.login(ui.row, ui.dialog) is False
    assert [action for action, _ in ui.calls] == ['pan_login_begin', 'pan_login_poll', 'pan_login_cancel']
    assert message in ui.messages[-1][1]
    assert '二维码已失效' not in repr(ui.messages)


def test_browse_baidu_navigates_paths_and_never_plays(ui, monkeypatch):
    rows = [dict(items=[dict(file_id='1', name='目录', path='/目录', directory=True, size=0)], has_more=False),
            dict(items=[dict(file_id='2', name='片.mkv', path='/目录/片.mkv', directory=False, size=3)], has_more=False),
            dict(items=[], has_more=False), dict(items=[], has_more=False)]
    expected = dict(provider='baidu', account_id='baidu:'+'a'*64, authenticated=True, epoch=1)
    def call(action, body, **kwargs):
        ui.calls.append((action, body))
        assert action == 'pan_list_files' and body['expected'] == expected
        return rows.pop(0)
    monkeypatch.setattr(pan_ui, 'call', call)
    ui.selections = [0, 0, -1, -1]
    pan_ui.browse(dict(provider='baidu', account=expected), ui.dialog)
    assert [b['parent'] for a, b in ui.calls] == ['/', '/目录', '/目录', '/']
    assert '播放接入尚未完成' in ui.messages[-1][1]


def test_host_cloud_status_is_local_lazy_and_115_account_remains_untouched(tmp_path, monkeypatch):
    from bobbi_platform.pan_http import Session
    def forbidden(*a, **kw):
        pytest.fail('Status must not perform cloud IO')
    monkeypatch.setattr(Session, 'request', forbidden)
    host = Host(tmp_path)
    host.start()
    try:
        before = host.accounts.install(credential(), host.accounts.snapshot())
        original = (tmp_path / '115-os_linux.json').read_bytes()
        assert host.pans is None
        rows = host.dispatch('pan_status', {})['providers']
        assert len(rows) == 10
        assert {r['provider'] for r in rows if r['capabilities']} == {
            '115', 'quark', 'uc', 'baidu', 'aliyun', '123', 'guangya', 'xunlei', '139', '189'}
        assert all(r['capabilities'] == ['qr_login', 'list_files', 'personal_play']
                   and r['verification'] == 'not_device_verified' for r in rows if r['provider'] != '115')
        assert not (tmp_path / 'pan-accounts-v1.json').exists()
        assert host.accounts.snapshot() == before
        assert (tmp_path / '115-os_linux.json').read_bytes() == original
        assert host.streams is None and not host.preparation_attempted
        with pytest.raises(PanError):
            host.dispatch('pan_play', {})
    finally:
        host.close()
    assert host.pans.closed


def test_corrupt_optional_pan_store_does_not_break_existing_115_startup(tmp_path):
    (tmp_path / 'pan-accounts-v1.json').write_text('{malformed', encoding='utf-8')
    host = Host(tmp_path)
    host.start()
    try:
        assert host.dispatch('account_status', {})['authenticated'] is False
        with pytest.raises(PanError):
            host.dispatch('pan_status', {})
        assert host.dispatch('cloud_status', {})['authenticated'] is False
    finally:
        host.close()


def test_directory_result_after_service_close_is_not_published(tmp_path):
    from test_ce2096_pan_accounts import saved
    service = pan_service.PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    def listing(*args, **kwargs):
        service.close()
        return {'items': []}
    service.client_factory = lambda *a: SimpleNamespace(list_files=listing)
    with pytest.raises(PanError, match='CLOSED'):
        service.list_files(expected, '0', 1)


@pytest.mark.parametrize('provider', ['aliyun', '139', 'xunlei'])
def test_transient_directory_error_retries_same_folder_page_cursor(ui, monkeypatch, provider):
    expected = dict(provider=provider, account_id=provider+':'+'a'*64, authenticated=True, epoch=1)
    replies = [dict(items=[], has_more=True, next_cursor='cursor1'), PanError('PAN_NETWORK_ERROR'),
               dict(items=[], has_more=False)]
    def call(action, body, **kw):
        ui.calls.append((action, deepcopy(body)))
        value = replies.pop(0)
        if isinstance(value, Exception): raise value
        return value
    monkeypatch.setattr(pan_ui, 'call', call)
    ui.selections = [0, 0, -1]
    pan_ui.browse(dict(provider=provider, account=expected), ui.dialog)
    assert {k: v for k, v in ui.calls[1][1].items() if k != 'operation_id'} == {
        k: v for k, v in ui.calls[2][1].items() if k != 'operation_id'}
    assert ui.calls[2][1]['page'] == 2 and ui.calls[2][1]['cursor'] == 'cursor1'
    assert ui.menus[1][1][0] == '重试当前位置' and not ui.messages


def test_slow_directory_can_cancel_and_late_reply_cannot_open_menu(ui, monkeypatch):
    from threading import Event
    release, finished = Event(), Event()
    def read(*a, **kw):
        assert release.wait(2)
        finished.set()
        return dict(items=[], has_more=False)
    monkeypatch.setattr(pan_ui, 'call', read)
    expected = dict(provider='quark', account_id='quark:'+'a'*64, authenticated=True, epoch=1)
    ui.progress_cancel = True
    try:
        pan_ui.browse(dict(provider='quark', account=expected), ui.dialog)
        assert ui.progress_opened == ui.progress_closed == 1
        assert not ui.menus and not ui.messages and not finished.is_set()
    finally:
        release.set()
    assert finished.wait(1)
    assert not ui.menus and not ui.messages


def test_fast_directory_has_no_progress_dialog_flicker(ui, monkeypatch):
    monkeypatch.setattr(pan_ui, 'call', lambda *a, **kw: dict(items=[], has_more=False))
    expected = dict(provider='quark', account_id='quark:'+'a'*64, authenticated=True, epoch=1)
    ui.selections = [-1]
    pan_ui.browse(dict(provider='quark', account=expected), ui.dialog)
    assert ui.progress_opened == ui.progress_closed == 0


def test_directory_play_passes_only_one_shot_ticket_to_plugin(ui, monkeypatch):
    import sys
    expected = dict(provider='quark', account_id='quark:'+'a'*64, authenticated=True, epoch=1)
    selected = dict(file_id='file1', name='movie.mkv', size=8, directory=False)
    builtins = []
    monkeypatch.setattr(sys.modules['xbmc'], 'executebuiltin', builtins.append)
    def call(action, body, **kw):
        ui.calls.append((action, deepcopy(body)))
        if action == 'pan_list_files': return dict(items=[selected], has_more=False)
        assert action == 'pan_prepare_play' and body == dict(expected=expected, selected=selected)
        return dict(ticket='a'*32)
    monkeypatch.setattr(pan_ui, 'call', call)
    ui.selections = [0, 0]
    assert pan_ui.browse(dict(provider='quark', account=expected, capabilities=['personal_play']), ui.dialog) is True
    assert builtins == ['RunPlugin(plugin://plugin.video.bobbi/?action=pan_play&ticket='+'a'*32+')']
