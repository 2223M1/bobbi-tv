from dataclasses import replace
import json
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import library_ui as ui
from bobbi_platform.libraries import LibraryError, Registry, import_catalog, vfs_source


@pytest.fixture
def context(monkeypatch, tmp_path):
    state = SimpleNamespace(inputs=[], selections=[], confirmations=[], paths=[], shown=[],
        input_options=[], builtins=[], raw=b'', closed=0, addon=True, aborted=False)
    state.path = tmp_path / 'libraries.sqlite3'
    state.store = Registry(state.path)

    def input_value(*args, **kwargs):
        state.input_options.append((args, kwargs))
        return state.inputs.pop(0)

    def select(*args):
        state.shown.append(args)
        return state.selections.pop(0)

    state.dialog = SimpleNamespace(input=input_value, select=select,
        browse=lambda *a, **kw: state.paths.pop(0),
        yesno=lambda *a: state.confirmations.pop(0),
        ok=lambda *args: state.shown.append(args))
    stream = SimpleNamespace(readBytes=lambda size: state.raw[:size],
        close=lambda: setattr(state, 'closed', state.closed + 1))
    state.vfs = SimpleNamespace(File=lambda _: stream, exists=lambda _: True,
        listdir=lambda _: ([], ['one.mkv']), translatePath=lambda _: str(tmp_path))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ALPHANUM_HIDE_INPUT=917,
        Dialog=lambda: state.dialog))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: state.aborted),
        getCondVisibility=lambda _: state.addon,
        executebuiltin=lambda command: state.builtins.append(command)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', state.vfs)
    monkeypatch.setattr(ui, 'registry', lambda _: Registry(state.path))
    yield state
    state.store.close()


def test_smb_wizard_uses_hidden_password_and_saves_after_confirmation(context):
    context.selections = [0]
    context.inputs = ['nas.local/Movies', '我的 NAS', 'me', 'secret-test-value']
    context.confirmations = [True]
    assert ui.add_source(context.dialog, context.vfs, context.store)
    source = context.store.sources()[0]
    assert source.location == 'smb://nas.local/Movies/'
    assert source.password == 'secret-test-value'
    assert context.input_options[-1][1]['option'] == 917
    assert 'secret-test-value' not in str(context.shown)


@pytest.mark.parametrize('url,confirmations,expected', [
    ('https://nas.example:5006/Movies', [True], 'davs://nas.example:5006/Movies/'),
    ('http://nas.example:5005/Movies', [True, True], 'dav://nas.example:5005/Movies/'),
    ('nas.example/dav', [True], 'davs://nas.example/dav/'),
])
def test_webdav_accepts_browser_form_and_requires_http_confirmation(context, url, confirmations, expected):
    context.selections = [2]
    context.inputs = [url, 'My cloud', '']
    context.confirmations = confirmations
    assert ui.add_source(context.dialog, context.vfs, context.store)
    assert context.store.sources()[0].location == expected


def test_declined_plaintext_webdav_does_not_save(context):
    context.selections = [2]
    context.inputs = ['http://nas.example/dav', 'My cloud', '']
    context.confirmations = [False]
    assert not ui.add_source(context.dialog, context.vfs, context.store)
    assert context.store.sources() == ()


def test_nfs_does_not_ask_for_or_send_password(context):
    context.selections = [1]
    context.inputs = ['nas.local/volume1/video', 'NAS']
    context.confirmations = [True]
    assert ui.add_source(context.dialog, context.vfs, context.store)
    assert len(context.input_options) == 2
    assert not context.store.sources()[0].password


def test_wrong_protocol_in_smb_wizard_does_not_save(context):
    context.selections = [0]
    context.inputs = ['nfs://nas.local/video']
    with pytest.raises(LibraryError):
        ui.add_source(context.dialog, context.vfs, context.store)
    assert context.store.sources() == ()


def test_cancelled_file_dialog_and_final_confirmation_are_noops(context):
    context.selections = [4]
    context.paths = ['']
    assert not ui.add_source(context.dialog, context.vfs, context.store)
    assert context.closed == 0
    context.selections = [0]
    context.inputs = ['nas.local/Movies', 'My NAS', '']
    context.confirmations = [False]
    assert not ui.add_source(context.dialog, context.vfs, context.store)
    assert context.store.sources() == ()


def test_edit_reuses_id_and_preserves_password_without_prefilling_it(context):
    source = vfs_source('Before', 'smb://nas.local/Movies', 'user', 'keep-secret')
    context.store.save(source)
    context.inputs = ['smb://nas.local/New', 'After']
    context.selections = [0]
    context.confirmations = [True]
    assert ui.edit_source(context.dialog, context.vfs, context.store, source)
    updated = context.store.get(source.id)
    assert updated == replace(source, name='After', location='smb://nas.local/New/')
    assert 'keep-secret' not in str(context.input_options) + str(context.shown)
    assert len(context.store.sources()) == 1


def test_edit_cancel_leaves_previous_credentials(context):
    source = vfs_source('NAS', 'smb://nas.local/Movies', 'user', 'old-secret')
    context.store.save(source)
    context.inputs = ['smb://nas.local/Movies', 'NAS', 'new-user', 'new-secret']
    context.selections = [1]
    context.confirmations = [False]
    assert not ui.edit_source(context.dialog, context.vfs, context.store, source)
    assert context.store.get(source.id) == source


def test_failed_catalog_update_keeps_existing_and_closes_file(context):
    source = import_catalog(json.dumps({'schema': 'bobbi-library-v1', 'name': 'My list',
        'items': [{'id': '1', 'title': 'One', 'url': 'https://example/one.mkv'}]}))
    context.store.save(source)
    context.raw, context.paths = b'{bad-json', ['new.json']
    with pytest.raises(LibraryError):
        ui.edit_source(context.dialog, context.vfs, context.store, source)
    assert context.store.get(source.id) == source and context.closed == 1


def test_check_is_readonly_and_not_claimed_as_playback(context):
    source = vfs_source('NAS', 'smb://nas/Movies')
    ui.check_source(context.dialog, context.vfs, source)
    assert context.shown[-1][0] == '连接成功'
    assert '文件夹或视频' in context.shown[-1][1] and '选片' in context.shown[-1][1]
    context.vfs.listdir = lambda _: ([], [])
    ui.check_source(context.dialog, context.vfs, source)
    assert context.shown[-1][0] == '目录中没有可显示的内容'
    assert not context.builtins


@pytest.mark.parametrize('confirm', [True, False])
def test_remove_connection_requires_confirmation_and_no_remote_io(context, confirm):
    source = vfs_source('NAS', 'smb://nas/Movies')
    context.store.save(source)
    context.selections = [2, 2, -1]
    context.confirmations = [confirm]
    def forbidden(*args):
        raise AssertionError('Removal must not access remote media')
    context.vfs.exists = context.vfs.listdir = context.vfs.File = forbidden
    ui.manage()
    assert len(context.store.sources()) == (0 if confirm else 1)
    assert context.builtins == (['Container.Refresh'] if confirm else [])


def test_missing_library_plugin_shows_actionable_notice(context):
    context.addon = False
    context.selections = [1, -1]
    ui.manage()
    assert any(row[0] == '片库组件未安装' for row in context.shown)
    assert not context.builtins


def test_registry_initialization_failure_shows_notice_not_traceback(context, monkeypatch):
    def failed(_):
        raise LibraryError('STORAGE_UNAVAILABLE')
    monkeypatch.setattr(ui, 'registry', failed)
    ui.manage()
    assert context.shown[-1][0] == '片库设置暂时不可用'


def test_user_facing_error_never_contains_internal_secret(context):
    assert 'unknown-secret' not in ui.message(RuntimeError('unknown-secret'))
