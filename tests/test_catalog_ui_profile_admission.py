"""Old dialogs cannot write to a cloned account/file in another Kodi profile."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from test_media_library_index import scope, ref, insert
from test_catalog_file_projection_contract import describe
from bobbi_core.media_library_index import MediaIndex
from bobbi_platform import catalog_ui, runtime


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi'))
    from lib.utils.views import catalog_supplement_ui, personal_catalog
    state = SimpleNamespace(active='A', calls=[], bindings=[], builtins=[], messages=[], views=[],
                            choices=[], inputs=[], after_dialog=None, after_call=None)
    state.expected = scope()
    state.main, state.extra = ref(1), ref(2)
    state.indexes = {}
    for name in ('A', 'B'):
        index = MediaIndex(tmp_path / name / 'index.db')
        insert(index, [state.main, state.extra])
        describe(index, state.main, '主文件')
        state.indexes[name] = index
    state.item = state.indexes['A'].item(state.expected, state.extra['id'])
    works = state.indexes['A'].query(state.expected)['items']
    state.work_choice = next(number for number, row in enumerate(works) if row.get('metadata_key'))

    def event(kind, title, result):
        if state.after_dialog:
            state.after_dialog(kind, title)
        return result

    state.dialog = SimpleNamespace(
        select=lambda title, *a, **kw: event('select', title, state.choices.pop(0)),
        input=lambda title, **kw: event('input', title, state.inputs.pop(0)),
        yesno=lambda title, *a, **kw: event('yesno', title, True),
        textviewer=lambda title, text: state.views.append((title, text)),
        notification=lambda *a: state.messages.append(a),
        ok=lambda *a: state.messages.append(a))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        getInfoLabel=lambda _: 'plugin://plugin.video.bobbi/?action=personal_catalog',
        executebuiltin=state.builtins.append))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda path: str(tmp_path / state.active / path.rsplit('/', 1)[-1])))

    def dispatch(profile, action, body, **kwargs):
        state.calls.append((profile, action, deepcopy(body)))
        index = state.indexes[profile]
        if action in ('catalog_mount_scope', 'catalog_local_scope'):
            result = dict(reference_kind='local_path' if action == 'catalog_local_scope' else 'mounted_path',
                          source_id='a'*32, namespace='b'*64, generation='c'*64)
        elif action == 'pan_status':
            result = dict(providers=[dict(provider='quark', account=deepcopy(state.expected))])
        elif action == 'catalog_sources':
            result = dict(items=[dict(id='a'*32, name='测试来源')])
        elif action == 'catalog_jobs':
            result = dict(items=[dict(task_id='b'*32, state='running', cancel_requested=False,
                counts=dict(scanned=1, discovered=2), result_summary='')], next_offset=None)
        elif action in ('catalog_scan', 'catalog_cancel', 'catalog_remove'):
            result = dict(accepted=True)
        else:
            method = {'catalog_query': index.query, 'catalog_item': index.item,
                      'catalog_preview': index.preview, 'catalog_apply': index.apply,
                      'catalog_receipt': index.receipt}[action]
            result = method(**body)
        if state.after_call:
            state.after_call(action)
        return result

    def bind(path):
        name = Path(path).parent.parent.name
        state.bindings.append(name)
        return lambda action, body, **kw: dispatch(name, action, body, **kw)

    state.rpc = lambda action, body, **kw: dispatch(state.active, action, body, **kw)
    monkeypatch.setattr(runtime, 'bind_call', bind)
    monkeypatch.setattr(runtime, 'call', state.rpc)
    monkeypatch.setattr(catalog_ui, 'call', state.rpc)
    state.supplement, state.catalog = catalog_supplement_ui, personal_catalog
    state.params = dict(provider='quark', scope=personal_catalog.scope_key(state.expected),
                        object_id=state.extra['id'])
    yield state
    for index in state.indexes.values():
        index.close()


def unchanged(ui):
    assert all(index.item(ui.expected, ui.extra['id'])['revision'] == 0 for index in ui.indexes.values())
    assert not any(action == 'catalog_apply' for _, action, _ in ui.calls)
    assert not any(profile == 'B' for profile, _, _ in ui.calls)


def test_supplement_profile_switch_before_review_cannot_rebind_to_clone(ui):
    ui.choices, ui.inputs = [0, ui.work_choice, 0, 0], ['', '制作花絮']
    ui.after_dialog = lambda kind, title: setattr(ui, 'active', 'B') if title.startswith('补充内容名称') else None
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        ui.supplement.edit(ui.dialog, ui.expected, ui.item, ui.rpc)
    unchanged(ui)


def test_regular_review_profile_switch_in_first_dialog_cannot_rebind_to_clone(ui):
    ui.choices = [3]
    ui.after_dialog = lambda *a: setattr(ui, 'active', 'B')
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        catalog_ui.review_item(ui.dialog, ui.expected, ui.item)
    unchanged(ui)


@pytest.mark.parametrize('mode', ['', 'supplement'])
def test_manage_captures_profile_before_reading_file_record(ui, mode):
    ui.after_call = lambda action: setattr(ui, 'active', 'B') if action == 'catalog_item' else None
    ui.catalog.manage(dict(ui.params, mode=mode))
    unchanged(ui)
    assert ui.bindings == ['A'] and ui.messages and not ui.builtins


@pytest.mark.parametrize('mode', ['', 'supplement'])
def test_manage_uses_one_admission_binding_for_full_review(ui, mode):
    ui.choices, ui.inputs = ([0, ui.work_choice, 0, 0], ['', '制作花絮']) if mode else ([3], [])
    result = ui.catalog.manage(dict(ui.params, mode=mode))
    assert result['complete'] and result['saved'] == 1
    assert ui.indexes['A'].item(ui.expected, ui.extra['id'])['revision'] == 1
    assert ui.indexes['B'].item(ui.expected, ui.extra['id'])['revision'] == 0
    assert ui.bindings == ['A'] and all(profile == 'A' for profile, _, _ in ui.calls)
    assert ui.builtins == ['Container.Refresh']


@pytest.mark.parametrize('mode', ['', 'supplement'])
def test_cancel_first_review_dialog_preserves_both_profiles(ui, mode):
    ui.choices = [-1]
    ui.catalog.manage(dict(ui.params, mode=mode))
    unchanged(ui)
    assert not ui.views and not ui.builtins


@pytest.mark.parametrize('choice', [6, 7, 8])
def test_filter_apply_clear_or_save_rejects_profile_switch_before_next_action(ui, choice, monkeypatch):
    from lib.utils.views import catalog_saved_views
    monkeypatch.setattr(catalog_saved_views, 'save', lambda *a, **kw: pytest.fail('New-profile save UI opened'))
    ui.choices = [choice]
    ui.after_dialog = lambda *a: setattr(ui, 'active', 'B')
    params = dict(ui.params, mode='filters', view='files', text='旧关键词')
    params.pop('object_id')
    ui.catalog.manage(params)
    unchanged(ui)
    assert ui.messages and not ui.builtins


@pytest.mark.parametrize('choice', [2, 3])
def test_source_scan_or_remove_does_not_follow_profile_changed_in_confirmation(ui, choice):
    ui.choices = [0, choice]
    ui.after_dialog = lambda kind, title: setattr(ui, 'active', 'B') if (
        kind == 'yesno' or title == '测试来源' and choice == 2) else None
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        catalog_ui.manage_sources(ui.expected, ui.dialog)
    assert not any(action in ('catalog_scan', 'catalog_remove') for _, action, _ in ui.calls)
    unchanged(ui)


def test_cancel_scan_does_not_follow_profile_changed_in_yesno(ui):
    ui.choices = [0]
    ui.after_dialog = lambda kind, title: setattr(ui, 'active', 'B') if kind == 'yesno' else None
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        catalog_ui._jobs(ui.dialog, ui.expected)
    assert not any(action == 'catalog_cancel' for _, action, _ in ui.calls)
    unchanged(ui)


def test_add_source_does_not_follow_profile_changed_before_confirmation(ui):
    ui.inputs = ['新片库']
    ui.after_dialog = lambda kind, title: setattr(ui, 'active', 'B') if kind == 'input' else None
    assert catalog_ui.add_directory(ui.expected, 'folder') is False
    unchanged(ui)
    assert not ui.calls and ui.messages


def test_stale_named_view_can_still_be_deleted_without_runtime(ui, monkeypatch):
    from lib.utils.views import catalog_saved_views
    calls = []
    monkeypatch.setattr(runtime, 'bind_call', lambda path: pytest.fail('Offline local view operation bound runtime'))
    monkeypatch.setattr(catalog_saved_views, 'manage', lambda params, rpc: calls.append(params['mode']))
    ui.catalog.manage(dict(mode='view_edit', view_id='a'*32))
    assert calls == ['view_edit'] and not ui.messages


@pytest.mark.parametrize('kind', ['mounted_path', 'local_path'])
def test_typed_scan_confirmation_keeps_entry_profile(ui, kind):
    ui.after_dialog = lambda *a: setattr(ui, 'active', 'B')
    ui.catalog.manage(dict(source='a'*32, reference_kind=kind, mode='scan'))
    assert [(profile, action) for profile, action, _ in ui.calls] == [
        ('A', 'catalog_local_scope' if kind == 'local_path' else 'catalog_mount_scope')]
    assert ui.bindings == ['A'] and ui.messages


@pytest.mark.parametrize('mode', ['', 'supplement'])
def test_profile_change_at_final_confirmation_keeps_both_cloned_records(ui, mode):
    ui.choices, ui.inputs = ([0, ui.work_choice, 0, 0], ['', '制作花絮']) if mode else ([3], [])
    ui.after_dialog = lambda kind, title: setattr(ui, 'active', 'B') if kind == 'yesno' else None
    ui.catalog.manage(dict(ui.params, mode=mode))
    unchanged(ui)
    assert ui.bindings == ['A'] and any(action == 'catalog_preview' for _, action, _ in ui.calls)
    assert not ui.builtins
