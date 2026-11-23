"""The reachable TV editor and settings entry run the real SQLite pipeline."""
from copy import deepcopy

import pytest

from bobbi_platform import catalog_ui
from test_media_library_index import index, insert
from test_catalog_tv_candidates import tv, writes
from test_catalog_segments import segment_command, apply
from test_catalog_transfer_settings_ui import ui as transfer_ui


def controls(tv, choices, inputs=()):
    choices, inputs = list(choices), list(inputs)
    tv.dialog.select = lambda title, labels: choices.pop(0)
    tv.dialog.input = lambda title, **kwargs: inputs.pop(0)


@pytest.mark.parametrize('kind,choice', [('intro', 0), ('recap', 1), ('outro', 2), ('credits_scene', 3)])
def test_tv_real_editor_displays_manual_evidence_and_uses_preview_apply_receipt(tv, kind, choice):
    file = tv.files[0]
    tv.index.now = lambda: 1234
    item = tv.index.item(tv.expected, file['id'])
    controls(tv, [8, choice], ['600', '5.125', '30.250'])
    result = catalog_ui.review_item(tv.dialog, tv.expected, item)
    assert result['complete'] and result['saved'] == 1
    assert [action for action, _ in tv.calls] == ['catalog_preview', 'catalog_preview', 'catalog_apply']
    cmds = [body['commands'][0] for _, body in tv.calls]
    assert cmds[0] == cmds[1] == cmds[2]
    assert cmds[0] == dict(file_id=file['id'], expected_revision=0, action='segments', mapping=dict(
        observation_key=item['file']['observation_key'], duration_ms=600000,
        items=[dict(kind=kind, start_ms=5125, end_ms=30250)]))
    request = writes(tv)[0]['request_id']
    assert tv.index.receipt(tv.expected, request)['items'] == [dict(index=0, status='applied', revision=1)]
    preview = tv.views[0][1]
    assert '人工观察' in preview and '并非媒体探测结果' in preview and '1234' in preview
    assert kind in preview and '5.125–30.25 秒' in preview and '不自动跳过' in preview
    saved = tv.index.item(tv.expected, file['id'])
    calls = list(tv.calls)
    controls(tv, [9])
    catalog_ui.review_item(tv.dialog, tv.expected, saved)
    assert tv.calls == calls
    assert saved['segments']['observation_key'] in tv.views[-1][1]


def test_tv_delete_one_clear_and_undo_retain_other_domains(tv):
    file = tv.files[0]
    initial = deepcopy(tv.entries[0]['command'])
    initial['mapping']['version'] = 'Director cut'
    apply(tv.index, initial, tv.expected)
    apply(tv.index, segment_command(tv.index, file, [dict(kind='intro', start_ms=0, end_ms=30000),
        dict(kind='credits_scene', start_ms=580000, end_ms=599000)]), tv.expected)
    before = tv.index.item(tv.expected, file['id'])
    controls(tv, [8, 4, 0])
    assert catalog_ui.review_item(tv.dialog, tv.expected, before)['complete']
    remaining = tv.index.item(tv.expected, file['id'])
    assert remaining['mapping'] == before['mapping'] and remaining['state'] == before['state']
    assert [row['kind'] for row in remaining['segments']['items']] == ['credits_scene']
    controls(tv, [8, 5])
    assert catalog_ui.review_item(tv.dialog, tv.expected, remaining)['complete']
    cleared = tv.index.item(tv.expected, file['id'])
    assert 'segments' not in cleared and cleared['mapping'] == before['mapping']
    controls(tv, [4])
    assert catalog_ui.review_item(tv.dialog, tv.expected, cleared)['complete']
    assert tv.index.item(tv.expected, file['id'])['segments'] == remaining['segments']
    assert '修改后片段' in tv.views[-2][1] and 'credits_scene' in tv.views[-2][1]


def test_cancel_unknown_duration_invalid_time_and_overlap_do_not_write(tv):
    file = tv.files[0]
    item = tv.index.item(tv.expected, file['id'])
    for inputs in ([''], ['600', '1:30'], ['600', '30', '20'], ['600', '0', '601']):
        controls(tv, [8, 0], inputs)
        assert catalog_ui.review_item(tv.dialog, tv.expected, item) is None
    assert not writes(tv) and not tv.calls
    apply(tv.index, segment_command(tv.index, file,
        [dict(kind='outro', start_ms=500000, end_ms=600000)]), tv.expected)
    before = tv.index.item(tv.expected, file['id'])
    controls(tv, [8, 3], ['600', '550', '590'])
    assert catalog_ui.review_item(tv.dialog, tv.expected, before) is None
    assert '重叠' in tv.messages[-1][0] and not writes(tv)
    assert tv.index.item(tv.expected, file['id']) == before


def test_tv_cancel_confirmation_is_preview_only_and_lost_reply_uses_original_receipt(tv):
    file = tv.files[0]
    item = tv.index.item(tv.expected, file['id'])
    tv.confirm = lambda *args: False
    controls(tv, [8, 0], ['100', '0', '10'])
    assert catalog_ui.review_item(tv.dialog, tv.expected, item) is None
    assert [action for action, _ in tv.calls] == ['catalog_preview']
    assert tv.index.item(tv.expected, file['id']) == item
    tv.confirm = lambda *args: True
    tv.lose_reply = True
    controls(tv, [8, 0], ['100', '0', '10'])
    result = catalog_ui.review_item(tv.dialog, tv.expected, item)
    assert result['complete'] and len(writes(tv)) == 1
    assert tv.calls[-1][0] == 'catalog_receipt'
    assert tv.calls[-1][1]['request_id'] == writes(tv)[0]['request_id']


def test_tv_observation_change_after_first_preview_stops_write(tv):
    file = tv.files[0]
    item = tv.index.item(tv.expected, file['id'])

    def replace(title, message):
        insert(tv.index, [dict(file, size=file['size'] + 1)])
        return True

    tv.confirm = replace
    controls(tv, [8, 0], ['100', '0', '10'])
    result = catalog_ui.review_item(tv.dialog, tv.expected, item)
    assert result['saved'] == 0 and not writes(tv)
    assert 'segments' not in tv.index.item(tv.expected, file['id'])


def test_tv_stale_edit_never_rebinds_other_old_ranges_and_undo_keeps_old_evidence(tv):
    file = tv.files[0]
    apply(tv.index, segment_command(tv.index, file, [dict(kind='intro', start_ms=0, end_ms=10000),
        dict(kind='credits_scene', start_ms=580000, end_ms=599000)]), tv.expected)
    old = tv.index.item(tv.expected, file['id'])['segments']
    insert(tv.index, [dict(file, size=file['size'] + 1)])
    stale = tv.index.item(tv.expected, file['id'])
    controls(tv, [8, 0], ['600', '5', '25'])
    assert catalog_ui.review_item(tv.dialog, tv.expected, stale)['complete']
    saved = tv.index.item(tv.expected, file['id'])
    assert saved['segments']['items'] == [dict(kind='intro', start_ms=5000, end_ms=25000)]
    assert saved['segments']['observation_key'] != old['observation_key']
    controls(tv, [4])
    assert catalog_ui.review_item(tv.dialog, tv.expected, saved)['complete']
    assert tv.index.item(tv.expected, file['id'])['segments'] == dict(old, state='verification_required')


def test_settings_exports_v2_segments_and_legacy_import_preserves_them(transfer_ui):
    ui = transfer_ui
    file = ui.files[0]
    apply(ui.service.index, segment_command(ui.service.index, file, expected=ui.expected), ui.expected)
    before = ui.service.index.item(ui.expected, file['id'])
    ui.subject.export_settings_backup()
    assert ui.messages[-1][0] == '已导出人工片库描述'
    paths = list(ui.root.parent.glob('bobbi-manual-descriptions-*.json'))
    assert len(paths) == 1
    from bobbi_core import catalog_transfer
    exported = catalog_transfer.loads(paths[0].read_text(encoding='utf-8'))
    assert exported['schema'] == catalog_transfer.SEGMENT_SCHEMA
    assert exported['entries'][0]['segments']['observation_key'] == before['segments']['observation_key']
    result = ui.subject._restore_catalog_descriptions(ui.payload, ui.dialog)
    assert result['complete'] and result['saved'] == 6
    assert ui.service.index.item(ui.expected, file['id']) == before
    assert any('人工片段保留原观察' in text for _, text in ui.views)
