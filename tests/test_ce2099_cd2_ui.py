"""Mounted file access stays independent of Bobbi-native account setup."""
from copy import deepcopy
from types import SimpleNamespace
import sys

import pytest

from bobbi_platform import catalog_ui, cd2_mounts, cloud_hub, library_ui, pan_ui
from bobbi_platform.pan_accounts import empty_scope
from test_library_ui import context


@pytest.fixture
def ui(monkeypatch, tmp_path):
    state = SimpleNamespace(choices=[], confirmations=[], menus=[], messages=[], prompts=[],
                            opened=[], mounts=('/mounted-fixture',), rows=[], unavailable=False)
    state.row = dict(provider='quark', account=empty_scope('quark'),
                     capabilities=['qr_login', 'list_files', 'personal_play'])
    state.rows = [state.row]

    def select(title, labels):
        state.menus.append((title, list(labels)))
        return state.choices.pop(0)

    def yesno(title, message, **kwargs):
        state.prompts.append((title, message, kwargs))
        return state.confirmations.pop(0)

    def status():
        if state.unavailable:
            raise OSError('private-fixture')
        return deepcopy(state.rows)

    def forbidden(*args, **kwargs):
        pytest.fail('Mounted navigation must not start native login or cloud IO')

    state.dialog = SimpleNamespace(select=select, yesno=yesno,
        ok=lambda *args: state.messages.append(args),
        textviewer=lambda *args: state.messages.append(args))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(
        abortRequested=lambda: False)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))
    monkeypatch.setattr(cd2_mounts, 'discover', lambda: state.mounts)
    monkeypatch.setattr(pan_ui, '_status', status)
    monkeypatch.setattr(pan_ui, 'login', forbidden)
    monkeypatch.setattr(pan_ui, 'call', forbidden)
    monkeypatch.setattr(catalog_ui, 'call', forbidden)
    monkeypatch.setattr(library_ui, 'open_existing_cd2',
        lambda dialog: state.opened.append('cd2') or True)
    monkeypatch.setattr(library_ui, 'open_library',
        lambda dialog: state.opened.append('library') or True)
    monkeypatch.setattr(pan_ui, 'browse',
        lambda row, dialog: state.opened.append(row['provider']) or True)
    return state


def test_native_files_offer_existing_cd2_without_native_login(ui):
    ui.choices = [0]
    assert pan_ui.choose_files(ui.dialog) is True
    assert ui.opened == ['cd2'] and not ui.messages
    assert ui.menus[0][1] == ['使用已有 CD2 网盘 · 无需扫码', '原生网盘登录 / 管理']
    assert ui.row['account']['authenticated'] is False


def test_mounted_and_native_files_remain_distinct_choices(ui):
    ui.row['account']['authenticated'] = True
    ui.choices = [1]
    assert pan_ui.choose_files(ui.dialog) is True
    assert ui.opened == ['quark']
    assert ui.menus[0][1][1] == '夸克 · 原生登录'


@pytest.mark.parametrize('entry', [pan_ui.choose_files, pan_ui.manage])
def test_cancel_mounted_choice_never_opens_or_logs_in(ui, entry):
    ui.choices = [-1]
    assert entry(ui.dialog) is None
    assert not ui.opened and not ui.messages


def test_native_account_page_labels_login_scope_and_links_existing_mount(ui):
    ui.choices = [2]  # Existing provider and support rows retain their indexes.
    assert pan_ui.manage(ui.dialog) is True
    assert ui.opened == ['cd2']
    assert '原生未登录' in ui.menus[0][1][0]
    assert '无需扫码' in ui.menus[0][1][2]
    assert '/mounted-fixture' not in repr(ui.menus)


def test_cancelled_mount_picker_returns_to_native_account_menu(ui, monkeypatch):
    monkeypatch.setattr(library_ui, 'open_existing_cd2', lambda dialog: False)
    ui.choices = [2, -1]
    assert pan_ui.manage(ui.dialog) is None
    assert len(ui.menus) == 2 and not ui.opened


def test_support_text_never_counts_mount_as_native_authentication(ui):
    ui.choices = [1, -1]
    pan_ui.manage(ui.dialog)
    text = ui.messages[0][1]
    assert '相互独立' in text and '无需在这里再次扫码' in text
    assert '不代表账号已验证或文件可读' in text
    assert ui.row['account']['authenticated'] is False and not ui.opened


@pytest.mark.parametrize('entry', [pan_ui.choose_files, pan_ui.manage])
def test_native_backend_failure_does_not_block_cd2_navigation(ui, entry):
    ui.unavailable = True
    ui.choices = [0]
    assert entry(ui.dialog) is True
    assert ui.opened == ['cd2']
    assert 'private-fixture' not in repr(ui.messages + ui.menus)


def test_unmounted_single_native_account_keeps_direct_browsing(ui):
    ui.mounts = ()
    ui.row['account']['authenticated'] = True
    assert pan_ui.choose_files(ui.dialog) is True
    assert ui.opened == ['quark'] and not ui.menus


def test_no_mount_does_not_offer_or_claim_cd2_access(ui):
    ui.mounts = ()
    ui.choices = [-1]
    pan_ui.choose_files(ui.dialog)
    assert len(ui.menus) == 1 and len(ui.menus[0][1]) == 2
    assert 'CD2' not in repr(ui.menus) and not ui.opened


@pytest.mark.parametrize('mounted,label', [(True, '片库与 CD2 索引'), (False, '浏览片库')])
def test_index_explains_supported_cd2_and_preserves_file_access(ui, mounted, label):
    ui.mounts = ui.mounts if mounted else ()
    ui.confirmations = [True]
    assert catalog_ui.manage() is True
    assert ui.opened == ['library']
    _, message, buttons = ui.prompts[0]
    assert '115 除外' in message and '管理片库来源' in message and '我的作品片库' in message
    assert 'CD2 / WebDAV / SMB / NFS / 本机目录暂不支持此索引' not in message
    assert 'WebDAV / SMB / NFS / 普通本机目录仍使用原文件浏览' in message
    assert '无需为此再次扫码' in message and buttons['yeslabel'] == label


def test_index_scope_dialog_cancel_preserves_everything(ui):
    ui.confirmations = [False]
    assert catalog_ui.manage() is None
    assert not ui.opened


def test_cd2_preparation_copy_only_requires_matching_115_for_115_preparation():
    text = cloud_hub.cd2_details({'state': 'WAITING_ACCOUNT'})
    assert text.startswith('115 提前存片（CD2）')
    assert '仅使用 115 提前存片时' in text and '其他网盘挂载不需要 115 登录' in text
    assert '或挂载网盘时' not in text


@pytest.mark.parametrize('mounted', [False, True])
def test_index_browse_navigation_closes_all_parent_management_menus(context, monkeypatch, mounted):
    monkeypatch.setattr(cloud_hub, 'status', lambda: dict(authenticated=False,
        preparation={'state': 'NOT_CONFIGURED'}))
    monkeypatch.setattr(pan_ui, '_status', lambda: [])
    monkeypatch.setattr(cd2_mounts, 'discover', lambda: ('/mounted-fixture',) if mounted else ())
    context.dialog.yesno = lambda *args, **kwargs: True
    context.selections = [4 if mounted else 3, 2, 2]  # Hub -> details -> library -> index scope.
    assert cloud_hub.show(context.dialog) is True
    assert len(context.builtins) == 1
    assert context.builtins[0].startswith('ActivateWindow(Videos,plugin://plugin.video.bobbi.library/')
    assert context.builtins[0] == 'ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)'
    assert not context.store.sources()  # Opening management must not register/scan a mount.
