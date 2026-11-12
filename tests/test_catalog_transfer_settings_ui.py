"""Settings entry -> real catalog owner -> existing review/receipt pipeline."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bobbi_core import catalog_transfer as transfer
from bobbi_platform import catalog_ui, runtime
from bobbi_platform.catalog_service import CatalogService
from test_catalog_service import Pans
from test_media_library_index import scope, ref, insert, command


@pytest.fixture
def ui(tmp_path, monkeypatch):
    noop = lambda *args, **kwargs: None
    imports = {
        'lib.api.stremio.addon_manager': ['build_addon_instance_key', 'build_legacy_addon_instance_key'],
        'lib.clients.stremio.constants': ['STREMIO_ADDONS_CATALOGS_KEY', 'STREMIO_ADDONS_KEY',
            'STREMIO_TV_ADDONS_KEY', 'STREMIO_USER_ADDONS', 'decode_selected_ids', 'encode_selected_ids'],
        'lib.db.cached': ['cache'], 'lib.db.pickle_db': ['PickleDatabase'],
        'lib.utils.general.utils': ['clear_all_cache', 'clear_debrid_cache', 'clear_mdblist_cache',
            'clear_stremio_cache', 'clear_tmdb_cache', 'clear_trakt_db_cache'],
        'lib.utils.kodi.utils': ['ADDON', 'ADDON_ID', 'ADDON_PATH', 'ADDON_PROFILE_PATH', 'ADDON_VERSION',
            'dialog_ok', 'get_cached_setting_property', 'get_setting', 'notification',
            'set_cached_setting_property', 'set_setting', 'translatePath', 'translation'],
    }
    for name, fields in imports.items():
        module = SimpleNamespace(**{field: field if field.isupper() else noop for field in fields})
        monkeypatch.setitem(sys.modules, name, module)
    state = SimpleNamespace(root=tmp_path / 'A', active=tmp_path / 'A', calls=[], views=[], messages=[],
                            selections=[], after=None, chosen=None, properties={})
    state.root.mkdir()
    state.dialog = SimpleNamespace(select=lambda *args: 1, yesno=lambda *args: True,
        textviewer=lambda *args: state.views.append(args), ok=lambda *args: state.messages.append(args))
    def multiselect(title, labels, preselect):
        state.selections.append((labels, preselect))
        return list(range(len(labels))) if state.chosen is None else state.chosen
    state.dialog.multiselect = multiselect
    window = SimpleNamespace(getProperty=lambda key: state.properties.get(key, ''),
                             setProperty=state.properties.__setitem__)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog, Window=lambda _: window))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(state.active)))
    subject_path = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/utils/kodi/settings_backup.py'
    spec = importlib.util.spec_from_file_location('catalog_backup_test', subject_path)
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)
    state.subject = subject
    state.expected = scope()
    state.service = CatalogService(state.root, Pans(state.expected, lambda *a: pytest.fail('No network')))
    state.files = [ref(number, name='特别篇.S00E%02d.mkv' % number) for number in range(1, 8)]
    insert(state.service.index, state.files)
    state.payload = dict(schema=transfer.SCHEMA,
        scope={key: state.expected[key] for key in ('provider', 'account_id')},
        entries=[dict(reference=file, state='confirmed', source_revision=99,
            mapping=dict(kind='tv', title='中文 Mixed Case', tmdb_id=42,
                         season=0, episode=index + 1, version=None if index == 0 else '版本 %s' % index))
            for index, file in enumerate(state.files)])
    def dispatch(action, body, **kwargs):
        state.calls.append((action, deepcopy(body)))
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', label='Quark', account=deepcopy(state.expected))])
        result = state.service.dispatch(action, body)
        if state.after:
            state.after(action, body)
        return result
    monkeypatch.setattr(runtime, 'bind_call', lambda path: dispatch)
    monkeypatch.setattr(subject, '_get_export_path', lambda template: str(tmp_path / template.format(timestamp='test')))
    yield state
    state.service.close()


def test_settings_manual_import_uses_real_preview_apply_receipt_and_target_revisions(ui):
    result = ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    assert result['complete'] and result['saved'] == 7
    assert ui.selections[0][1] == []  # No hash: explicit user selection, never automatic.
    applies = [body for action, body in ui.calls if action == 'catalog_apply']
    assert [len(body['commands']) for body in applies] == [5, 2]
    assert all(cmd['expected_revision'] == 0 for body in applies for cmd in body['commands'])
    assert all(len(ui.service.index.receipt(ui.expected, body['request_id'])['items']) == len(body['commands']) for body in applies)
    assert ui.service.index.item(ui.expected, ui.files[0]['id'])['mapping']['season'] == 0
    ui.calls.clear()
    assert ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog) is None
    assert not any(action == 'catalog_apply' for action, _ in ui.calls)


def test_weak_matches_canceled_in_selector_never_write(ui):
    ui.chosen = []
    assert ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog) is None
    assert not any(action == 'catalog_apply' for action, _ in ui.calls)
    assert all(ui.service.index.item(ui.expected, row['id'])['revision'] == 0 for row in ui.files)


def test_missing_target_file_is_unresolved_and_other_selected_files_still_import(ui):
    ui.payload['entries'].append(dict(ui.payload['entries'][0], reference=ref(99)))
    result = ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    assert result['saved'] == 7
    assert any('未找到当前文件' in text for _, text in ui.views)


def test_manual_export_entry_is_credential_free_and_never_overwrites_existing_artifact(ui, monkeypatch):
    ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    monkeypatch.setattr(ui.subject, 'build_backup_payload', lambda *a: pytest.fail('Credential settings path used'))
    ui.subject.export_settings_backup()
    path = ui.root.parent / 'bobbi-manual-descriptions-test-0.json'
    exported = transfer.loads(path.read_bytes())
    assert len(exported['entries']) == 7
    assert exported['entries'][0]['source_revision'] == 1
    assert 'epoch' not in path.read_text(encoding='utf-8') and 'request_id' not in path.read_text(encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        ui.subject._export_catalog_descriptions(ui.dialog)
    assert path.read_bytes() == before


def test_profile_switch_after_committed_apply_preserves_original_unknown_request_only_in_a(ui):
    def switch(action, body):
        if action == 'catalog_apply':
            ui.active = ui.root.parent / 'B'
    ui.after = switch
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    applies = [body for action, body in ui.calls if action == 'catalog_apply']
    assert len(applies) == 1
    request = applies[0]['request_id']
    assert len(ui.service.index.receipt(ui.expected, request)['items']) == 5
    assert catalog_ui._pending_receipts(ui.expected) == []
    assert not any(title.startswith('真实回执') for title, _ in ui.views)
    ui.active = ui.root
    assert catalog_ui._pending_receipts(ui.expected) == [dict(request_id=request, count=5)]
    assert ui.service.index.item(ui.expected, ui.files[-1]['id'])['revision'] == 0


def test_profile_switch_after_preview_blocks_all_writes(ui):
    def switch(action, body):
        if action == 'catalog_preview':
            ui.active = ui.root.parent / 'B'
    ui.after = switch
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    assert not any(action == 'catalog_apply' for action, _ in ui.calls)


def test_export_uses_one_snapshot_and_rejects_changed_revision(ui):
    ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    changed = []
    def edit(action, body):
        if action == 'catalog_manual_records' and not changed:
            changed.append(True)
            file = ui.files[-1]
            ui.service.index.apply(ui.expected, uuid4().hex, [command(file, revision=1, title='Later edit')])
    ui.after = edit
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        ui.subject._export_catalog_descriptions(ui.dialog)
    assert not list(ui.root.parent.glob('bobbi-manual-descriptions-*.json'))


def test_file_restore_parser_rejects_duplicate_fields_before_review(ui):
    path = ui.root.parent / 'duplicate.json'
    path.write_text('{"schema":"bad","schema":"bobbi-catalog-manual-v1"}', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate'):
        ui.subject._load_backup_payload_from_file(path)
    assert not ui.calls


def test_url_restore_cannot_enter_manual_import(ui, monkeypatch):
    monkeypatch.setattr(ui.subject, '_get_restore_source', lambda: 'url')
    monkeypatch.setattr(ui.subject, '_get_restore_url', lambda: 'https://example.invalid/manual.json')
    monkeypatch.setattr(ui.subject, '_load_backup_payload_from_url', lambda _: ui.payload)
    monkeypatch.setattr(ui.subject, 'apply_backup_payload', lambda *a: pytest.fail('Not a settings backup'))
    ui.subject.restore_settings_backup()
    assert not ui.calls
