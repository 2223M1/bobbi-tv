"""TV reclassification preserves each file's independent version description."""
from copy import deepcopy
from itertools import cycle

import pytest

from bobbi_platform import catalog_ui
from test_catalog_tv_candidates import tv, writes
from test_media_library_index import index


@pytest.mark.parametrize('edit_episodes', [False, True])
def test_group_reclassification_keeps_existing_version_notes_through_real_preview_and_apply(tv, edit_episodes):
    versions = ('影院版 · 原始音轨', '导演剪辑版', None)
    initial = []
    for entry, version in zip(tv.entries, versions):
        command = deepcopy(entry['command'])
        command['mapping']['version'] = version
        initial.append(command)
    tv.index.apply(tv.expected, 'e' * 32, initial)
    tv.confirm = lambda title, message: edit_episodes if title == '需要逐项调整季集？' else True
    inputs = cycle(('3', '7'))
    tv.dialog.input = lambda *args, **kwargs: next(inputs)
    anchor = tv.index.item(tv.expected, tv.files[0]['id'])

    result = catalog_ui.review_group(tv.dialog, tv.expected, anchor,
        dict(media_kind='tv', title='Show', tmdb_id=123, year=2020))

    assert result['complete'] and result['saved'] == len(tv.files)
    for file, version in zip(tv.files, versions):
        saved = tv.index.item(tv.expected, file['id'])['mapping']
        assert saved['version'] == version
        if edit_episodes:
            assert (saved['season'], saved['episode']) == (3, 7)
    commands = [command for body in writes(tv) for command in body['commands']]
    by_id = {command['file_id']: command for command in commands}
    assert [by_id[file['id']]['mapping']['version'] for file in tv.files[:3]] == list(versions)
    # The full before/after preview describes the retained notes as well.
    preview = tv.views[0][1]
    assert preview.count('版本备注 影院版 · 原始音轨') == 2
    assert preview.count('版本备注 导演剪辑版') == 2

