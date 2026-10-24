"""Real local host projection and thin Kodi routes, no live cloud effects."""
import json
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import cloud_hub
from bobbi_platform.host import Host
from test_accounts import credential
from test_onboarding import setup_ui
from test_library_ui import context as library_context


def test_empty_host_cloud_view_does_not_construct_optional_dependencies(tmp_path, monkeypatch):
    h = Host(tmp_path)
    h.start()
    try:
        def forbidden(*a, **kw): pytest.fail('Status must not start cloud IO')
        monkeypatch.setattr(h, '_shares', forbidden)
        monkeypatch.setattr(h, '_tick_preparation', forbidden)
        assert h.dispatch('cloud_status', {}) == dict(authenticated=False,
            preparation=dict(state='NOT_CONFIGURED', dependency='UNVERIFIED', ready=False))
        assert not h.preparation_attempted and h.streams is None
        with pytest.raises(ValueError): h.dispatch('cloud_status', {'refresh': True})
    finally:
        h.close()


def test_host_cloud_view_projects_current_generation_only(tmp_path):
    h = Host(tmp_path)
    h.start()
    try:
        a = h.accounts.install(credential(), h.accounts.snapshot())
        h.preparation = SimpleNamespace(snapshot=lambda: dict(state='RUNNING', account=a,
            revoke={'account': a}, dependency=dict(state='READY', ready=True,
                error='fixture-sensitive', retry_after_seconds=1)), close=lambda: None)
        before = (tmp_path/'115-os_linux.json').read_bytes()
        result = h.dispatch('cloud_status', {})
        assert result == dict(authenticated=True,
            preparation=dict(state='RUNNING', dependency='READY', ready=True))
        assert (tmp_path/'115-os_linux.json').read_bytes() == before
        assert a['account_id'] not in json.dumps(result)
        b = h.accounts.install(credential('456'), a)
        assert h.dispatch('cloud_status', {})['preparation'] == dict(
            state='STARTING', dependency='UNVERIFIED', ready=False)
        h.accounts.logout(b)
        assert h.dispatch('cloud_status', {}) == dict(authenticated=False,
            preparation=dict(state='WAITING_ACCOUNT', dependency='UNVERIFIED', ready=False))
    finally:
        h.close()


@pytest.mark.parametrize('state', ['STARTING', 'UNAVAILABLE', 'NOT_CONFIGURED'])
def test_configured_does_not_mean_connected(tmp_path, state):
    h = Host(tmp_path)
    h.start()
    try:
        if state != 'NOT_CONFIGURED': (tmp_path/'preparation.json').write_text('fixture-private')
        h.preparation_attempted = state == 'UNAVAILABLE'
        result = h.dispatch('cloud_status', {})['preparation']
        assert result['state'] == state and result['ready'] is False
    finally:
        h.close()


@pytest.mark.parametrize('state', ['UNAVAILABLE', 'STOPPED', 'WAITING_ACCOUNT'])
def test_session_without_lease_preserves_failure_not_endless_starting(tmp_path, state):
    h = Host(tmp_path)
    h.start()
    h.preparation = SimpleNamespace(snapshot=lambda: dict(state=state, account=None), close=lambda: None)
    try:
        h.accounts.install(credential(), h.accounts.snapshot())
        assert h.dispatch('cloud_status', {})['preparation']['state'] == state
    finally:
        h.close()


@pytest.mark.parametrize('error', [OSError, RuntimeError, ValueError])
def test_runtime_unavailable_is_not_reported_as_logged_out(monkeypatch, error):
    def fail(action, body, timeout):
        assert action == 'cloud_status' and body == {} and timeout <= .5
        raise error('fixture-private')
    monkeypatch.setattr(cloud_hub, 'call', fail)
    value = cloud_hub.status()
    assert value['authenticated'] is None
    assert 'fixture-private' not in cloud_hub.cd2_details(value['preparation'])


def test_running_owner_is_not_claimed_ready_without_dependency_check():
    assert cloud_hub.cd2_label({'state': 'RUNNING'}) == '尚未完成连接检查'
    assert cloud_hub.cd2_label(dict(state='RUNNING', dependency='DEPENDENCY_UNAVAILABLE')) == '连接或账号检查暂未通过'
    assert '最近' in cloud_hub.cd2_label(dict(state='RUNNING', dependency='READY', ready=True))
    text = cloud_hub.cd2_details({'state': 'NOT_CONFIGURED'})
    assert '不要求 CD2' in text and '分开管理' in text and '不代表' in text


@pytest.mark.parametrize('choices', [[-1], [1, -1], [4, -1]])
def test_overview_cd2_and_refresh_are_read_only(monkeypatch, choices):
    menus, messages, calls = [], [], []
    selected = iter(choices)
    dialog = SimpleNamespace(select=lambda *args: (menus.append(args), next(selected))[1],
                             textviewer=lambda *args: messages.append(args))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda:
        SimpleNamespace(abortRequested=lambda: False)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: dialog))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace())
    def call(action, body, timeout):
        calls.append((action, body))
        return dict(authenticated=True, preparation=dict(state='NOT_CONFIGURED'))
    monkeypatch.setattr(cloud_hub, 'call', call)
    cloud_hub.show()
    assert len(menus) == len(choices)
    assert calls == [('cloud_status', {})] * len(choices)
    assert len(messages) == int(1 in choices)
    assert '已保存登录' in str(menus) and '已登录且可播放' not in str(menus)


def test_cloud_route_goes_directly_to_hub_without_setup_probes(setup_ui, monkeypatch):
    state = setup_ui
    monkeypatch.setattr(state.module.xbmcgui, 'Dialog', lambda: state.dialog, raising=False)
    monkeypatch.setattr(sys, 'argv', ['script.bobbi.setup', 'cloud'])
    seen = []
    monkeypatch.setattr(cloud_hub, 'show', lambda dialog: seen.append(dialog))
    monkeypatch.setattr(state.module, 'probe', lambda *a: pytest.fail('No setup probe'))
    state.module.main()
    assert seen == [state.dialog] and not state.builtins


def test_open_library_leaves_hub_instead_of_covering_the_destination(library_context, monkeypatch):
    state = library_context
    state.selections = [2, 1]  # Real hub -> real library manager -> open library.
    monkeypatch.setattr(cloud_hub, 'status', lambda: dict(authenticated=True,
                       preparation={'state': 'NOT_CONFIGURED'}))
    assert cloud_hub.show(state.dialog) is True
    assert state.builtins == ['ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)']
    assert len(state.shown) == 2
