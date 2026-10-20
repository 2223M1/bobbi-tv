"""Account UI contract only: mocked Kodi/QR/runtime, no cloud or device I/O."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import account_manager, cloud115, cloud_ui as ui, runtime
from bobbi_platform._vendor import segno


OLD = {'app': 'os_linux', 'cookies': {'UID': '501_old', 'CID': 'fixture-old', 'SEID': 'fixture-old'}}
NEW = {'app': 'os_linux', 'cookies': {'UID': '502_new', 'CID': 'fixture-new', 'SEID': 'fixture-new'}}
SCOPE = {'account_id': '115:' + 'a' * 64, 'epoch': 7, 'authenticated': True}


@pytest.fixture
def context(monkeypatch, tmp_path):
    state = SimpleNamespace(
        snapshot=deepcopy(SCOPE), current=deepcopy(OLD), selections=[0], confirmations=[],
        dialogs=[], menus=[], yesnos=[], calls=[], builtins=[], events=[], labels=[],
        polls=[('confirmed', deepcopy(NEW))], flows=[], windows=[], qr_images=[],
        status_error=None, commit_error=None, committed_before_error=False,
        refresh_error=None, begin_error=None, cancel_on_show=None, cancel_on_poll=None,
        aborted=False, abort_on_wait=False, waits=0,
    )
    # A real sentinel catches accidental direct credential-file replacement/deletion.
    state.path = tmp_path / '115-os_linux.json'
    sentinel = b'fixture: existing credentials owned by Runtime, not the UI\n'
    state.path.write_bytes(sentinel)

    def forbidden(*args, **kwargs):
        raise AssertionError('Account UI must not write credentials or start a second owner')

    def select(*args):
        state.menus.append(args)
        return state.selections.pop(0)

    def yesno(*args):
        state.yesnos.append(args)
        return state.confirmations.pop(0)

    def ok(*args):
        state.dialogs.append(args)
        state.events.append(('dialog', args[0]))

    def call(action, body):
        state.calls.append((action, deepcopy(body)))
        state.events.append(('call', action))
        if action == 'account_status':
            assert body == {}
            if state.status_error is not None:
                raise state.status_error
            return deepcopy(state.snapshot)
        assert action in ('account_install', 'account_logout')
        assert body['expected'] == state.snapshot
        if state.commit_error is not None and not state.committed_before_error:
            raise state.commit_error
        if action == 'account_logout':
            assert set(body) == {'expected'}
            state.current = None
        else:
            assert set(body) == {'credentials', 'expected'}
            state.current = deepcopy(body['credentials'])
        state.events.append(('committed', action))
        if state.commit_error is not None:
            raise state.commit_error
        return deepcopy(state.snapshot)

    def builtin(command):
        state.builtins.append(command)
        state.events.append(('builtin', command))
        assert command == 'Container.Refresh', 'No player stop, skin reload or service startup'
        if state.refresh_error is not None:
            raise state.refresh_error

    class Window:
        def __init__(self, *args):
            self.closed = 0
            self.controls = []
            state.windows.append(self)

        def setCoordinateResolution(self, value):
            assert value == 5

        def addControls(self, controls):
            self.controls.extend(controls)

        def show(self):
            self.onInit()
            if state.cancel_on_show is not None:
                self.onAction(SimpleNamespace(getId=lambda: state.cancel_on_show))

        def close(self):
            self.closed += 1

        def getControl(self, control_id): return Control()
        def setFocusId(self, control_id): assert control_id == 9001

    class Control:
        def __init__(self, *args, **kwargs):
            pass

        def setLabel(self, label, **kwargs):
            state.labels.append(label)

        def setImage(self, image): pass

    class Monitor:
        def abortRequested(self):
            return state.aborted

        def waitForAbort(self, seconds):
            assert seconds == 2
            state.waits += 1
            assert state.waits <= 8, 'Mock poll must remain bounded'
            if state.abort_on_wait:
                state.aborted = True
            return state.aborted

    class Login:
        def __init__(self):
            self.began = self.polled = self.cancelled = 0
            state.flows.append(self)

        def begin(self):
            self.began += 1
            if state.begin_error is not None:
                raise state.begin_error
            return 'https://example.invalid/local-qr-fixture'

        def poll(self):
            self.polled += 1
            if state.cancel_on_poll is not None:
                state.windows[-1].onAction(SimpleNamespace(getId=lambda: state.cancel_on_poll))
            value = state.polls.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        def cancel(self):
            self.cancelled += 1

    def make_qr(value, micro):
        assert value == 'https://example.invalid/local-qr-fixture' and micro is False

        def save(path, scale, border):
            state.qr_images.append(Path(path))
            assert Path(path).parent.parent == tmp_path
            assert scale == 10 and border == 4

        return SimpleNamespace(save=save)

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=Monitor, executebuiltin=builtin, getSkinDir=lambda: 'skin.bobbi.cinema'))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Dialog=lambda: SimpleNamespace(select=select, yesno=yesno, ok=ok),
        WindowXMLDialog=Window, ControlImage=Control, ControlLabel=Control))
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(
        Addon=lambda name: SimpleNamespace(getAddonInfo=lambda _: str(tmp_path))))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))
    monkeypatch.setattr(ui, 'call', call)
    monkeypatch.setattr(ui, 'Login', Login)
    monkeypatch.setattr(segno, 'make', make_qr)
    monkeypatch.setattr(cloud115, 'save', forbidden)
    monkeypatch.setattr(account_manager, '_write', forbidden)
    monkeypatch.setattr(account_manager.AccountManager, '__init__', forbidden)
    monkeypatch.setattr(runtime.Runtime, 'start', forbidden)
    yield state
    assert state.path.read_bytes() == sentinel
    assert all(command == 'Container.Refresh' for command in state.builtins)
    assert all(flow.cancelled == 1 for flow in state.flows)
    assert all(window.closed >= 1 for window in state.windows)
    assert not list(tmp_path.glob('bobbi-qr-*'))


def mutations(state):
    return [(action, body) for action, body in state.calls if action != 'account_status']


def assert_committed_before_refresh(state, action):
    assert state.events.index(('committed', action)) < state.events.index(('builtin', 'Container.Refresh'))


def test_logout_commits_once_then_refreshes(context):
    context.selections, context.confirmations = [1], [True]
    assert ui.login() is True
    assert context.current is None
    assert mutations(context) == [('account_logout', {'expected': SCOPE})]
    assert len(context.yesnos) == 1
    assert not context.flows
    assert context.builtins == ['Container.Refresh']
    assert context.dialogs[-1][0] == '已退出本机 115'
    assert_committed_before_refresh(context, 'account_logout')


@pytest.mark.parametrize('selection, confirmations', [(-1, []), (1, [False])])
def test_cancel_menu_or_logout_preserves_current_account(context, selection, confirmations):
    context.selections, context.confirmations = [selection], confirmations
    assert ui.login() is False
    assert context.current == OLD
    assert not mutations(context) and not context.builtins and not context.flows


@pytest.mark.parametrize('error', [RuntimeError('runtime offline'), OSError('ipc unavailable'), ValueError('bad reply')])
def test_unavailable_account_status_never_opens_login_or_writes(context, error):
    context.status_error = error
    assert ui.login() is False
    assert context.dialogs[-1][0] == '115 账号服务尚未就绪'
    assert context.current == OLD
    assert not context.flows and not context.menus and not context.builtins
    assert not mutations(context)


def test_invalid_status_scope_is_not_treated_as_logged_out(context):
    context.snapshot = {'authenticated': False}
    assert ui.login() is False
    assert context.dialogs[-1][0] == '115 账号服务尚未就绪'
    assert not context.flows and not mutations(context)


@pytest.mark.parametrize('authenticated', [True, False])
def test_confirmed_qr_commits_once_then_refreshes_without_reconfirmation(context, authenticated):
    if not authenticated:
        context.snapshot = {'account_id': '', 'epoch': 8, 'authenticated': False}
        context.current = None
    context.polls = [('scanned', None), ('confirmed', deepcopy(NEW))]
    expected = deepcopy(context.snapshot)
    assert ui.login() is True
    assert context.current == NEW
    assert mutations(context) == [('account_install', {'credentials': NEW, 'expected': expected})]
    assert context.yesnos == []
    assert bool(context.menus) == authenticated
    assert context.builtins == ['Container.Refresh']
    assert context.dialogs[-1][0] == '115 登录已保存'
    assert context.labels == ['登录自己的 115 网盘', '用「115 生活」App 扫码',
        '扫描后，请在手机上确认登录', '取消并返回', '已扫描，请在手机上确认登录']
    assert_committed_before_refresh(context, 'account_install')


@pytest.mark.parametrize('action', [9, 10, 13, 92, 216])
def test_cancel_qr_before_poll_preserves_current_login(context, action):
    context.cancel_on_show = action
    assert ui.login() is False
    assert context.current == OLD
    assert context.flows[0].polled == 0
    assert not mutations(context) and not context.builtins and not context.yesnos


def test_cancel_while_poll_confirms_does_not_commit_late_credentials(context):
    context.cancel_on_poll = 92
    assert ui.login() is False
    assert context.current == OLD
    assert context.flows[0].polled == 1
    assert not mutations(context) and not context.builtins


def test_kodi_abort_during_wait_does_not_commit(context):
    context.abort_on_wait = True
    assert ui.login() is False
    assert context.current == OLD
    assert context.flows[0].polled == 0
    assert not mutations(context) and not context.builtins


@pytest.mark.parametrize('phase', ['begin', 'poll'])
def test_expired_qr_preserves_current_login(context, phase):
    error = cloud115.CloudError('QR_EXPIRED')
    if phase == 'begin':
        context.begin_error = error
    else:
        context.polls = [error]
    assert ui.login() is False
    assert context.current == OLD
    assert context.dialogs[-1][0] == '本次登录未确认'
    assert not mutations(context) and not context.builtins


@pytest.mark.parametrize('operation', ['login', 'logout'])
@pytest.mark.parametrize('committed', [False, True])
def test_commit_failure_or_uncertain_receipt_is_not_retried_or_refreshed(context, operation, committed):
    context.commit_error = RuntimeError('commit receipt unavailable')
    context.committed_before_error = committed
    if operation == 'logout':
        context.selections, context.confirmations = [1], [True]
    assert ui.login() is False
    assert len(mutations(context)) == 1
    assert not context.builtins
    assert context.dialogs[-1][0] == ('账号状态已变化' if operation == 'logout' else '本次登录未确认')
    assert all('没有修改已有登录' not in str(row) for row in context.dialogs)
    expected = None if operation == 'logout' else NEW
    assert context.current == (expected if committed else OLD)


@pytest.mark.parametrize('operation', ['login', 'logout'])
def test_refresh_failure_does_not_misreport_successful_commit(context, operation):
    context.refresh_error = RuntimeError('Kodi container unavailable')
    if operation == 'logout':
        context.selections, context.confirmations = [1], [True]
    assert ui.login() is True
    assert context.current == (None if operation == 'logout' else NEW)
    assert len(mutations(context)) == 1
    assert context.builtins == ['Container.Refresh']
    assert context.dialogs[-1][0] == ('已退出本机 115' if operation == 'logout' else '115 登录已保存')


def test_transient_qr_poll_error_retries_before_single_commit(context):
    context.polls = [cloud115.CloudError('QR_POLL_RETRY'), ('confirmed', deepcopy(NEW))]
    assert ui.login() is True
    assert context.flows[0].polled == 2
    assert len(mutations(context)) == 1
    assert context.builtins == ['Container.Refresh']


def test_exhausted_network_retries_keep_current_account(context):
    context.polls = [cloud115.CloudError('NETWORK_ERROR') for _ in range(4)]
    assert ui.login() is False
    assert context.flows[0].polled == 4
    assert context.current == OLD
    assert not mutations(context) and not context.builtins
