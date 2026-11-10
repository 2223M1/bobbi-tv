"""Progressive disclosure belongs to account management, never source selection."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bobbi_platform import cloud_hub, cloud_ui
from test_library_ui import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))


@pytest.fixture
def ui(monkeypatch):
    state = SimpleNamespace(choices=[], menus=[], messages=[], calls=[], account=False,
                            mounted=(), aborted=False)
    state.dialog = SimpleNamespace(
        select=lambda *args: (state.menus.append(args), state.choices.pop(0))[1],
        textviewer=lambda *args: state.messages.append(args))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda:
        SimpleNamespace(abortRequested=lambda: state.aborted)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog))
    monkeypatch.setattr(cloud_hub.cd2_mounts, 'discover', lambda: state.mounted)

    def call(action, body, timeout):
        assert action == 'cloud_status' and body == {} and timeout <= .5
        state.calls.append(action)
        return dict(authenticated=state.account, preparation={'state': 'NOT_CONFIGURED'})
    monkeypatch.setattr(cloud_hub, 'call', call)
    return state


def test_default_layer_hides_transport_and_keeps_quick_actions(ui, monkeypatch):
    monkeypatch.setattr(cloud_hub, 'transport', lambda *a: pytest.fail('No implicit transport change'))
    ui.choices = [-1]
    cloud_hub.show()
    labels = ui.menus[0][1]
    assert len(labels) == 5
    assert '115 分享播放' in labels[0] and '我的片库' in labels[2]
    assert labels[3] == '详细管理'
    assert '读取方式' not in str(labels)


def test_details_cancel_returns_to_same_simple_menu(ui):
    ui.choices = [3, -1, -1]
    cloud_hub.show()
    assert [row[0] for row in ui.menus] == ['网盘账号与连接', '网盘详细管理', '网盘账号与连接']
    assert len(ui.calls) == 3 and not ui.messages


def test_transport_is_only_called_after_explicit_advanced_action(ui, monkeypatch):
    seen = []
    monkeypatch.setattr(cloud_hub, 'transport', lambda dialog: seen.append(dialog))
    ui.choices = [3, 4, -1, -1]
    cloud_hub.show()
    assert seen == [ui.dialog]


def test_read_only_summary_and_refresh_do_not_login_or_manage_connections(ui, monkeypatch):
    def forbidden(*args):
        pytest.fail('Overview must not change accounts or enumerate network directories')
    monkeypatch.setattr(cloud_ui, 'login', forbidden)
    monkeypatch.setattr(cloud_hub, '_manage_library', forbidden)
    ui.choices = [3, 0, 5, -1, -1]
    cloud_hub.show()
    assert len(ui.messages) == 1 and len(ui.calls) == 5
    text = ui.messages[0][1]
    assert '内置扫码与原生接入进度请查看“原生多网盘”' in text
    assert '不会重新登录、扫描网盘、转存或删除文件' in text


@pytest.mark.parametrize('account', [False, True, None])
def test_summary_never_exposes_paths_account_ids_or_claims_mount_authenticated(ui, account):
    text = cloud_hub.connection_details(dict(authenticated=account,
        preparation={'state': 'RUNNING', 'account_id': 'secret-identity', 'error': 'secret-error'}),
        ('/private/mount-secret',))
    assert '发现 1 个' in text and '不代表已验证' in text
    assert 'secret' not in text
    assert '后台暂不可用' in text if account is None else '后台暂不可用' not in text


def test_account_action_reuses_existing_generation_guard_and_refreshes(ui, monkeypatch):
    def login():
        ui.account = True
    monkeypatch.setattr(cloud_ui, 'login', login)
    ui.choices = [1, -1]
    cloud_hub.details(ui.dialog)
    assert '未登录' in ui.menus[0][1][1]
    assert '已保存登录' in ui.menus[1][1][1]


def test_details_library_navigation_closes_both_parent_menus(context, monkeypatch):
    monkeypatch.setattr(cloud_hub, 'status', lambda: dict(authenticated=False,
        preparation={'state': 'NOT_CONFIGURED'}))
    context.selections = [3, 2, 1]  # Hub -> details -> real library manager -> open.
    assert cloud_hub.show(context.dialog) is True
    assert len(context.shown) == 3
    assert context.builtins == ['ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)']


@pytest.mark.parametrize('choice', [-1, 7, 100])
def test_cancel_or_invalid_details_action_is_noop(ui, choice):
    ui.choices = [choice]
    assert cloud_hub.details(ui.dialog) is None
    assert not ui.messages and ui.calls == ['cloud_status']
