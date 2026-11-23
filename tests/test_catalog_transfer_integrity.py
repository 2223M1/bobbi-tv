"""Undo may restore filename suggestions; they must not poison manual export."""
from uuid import uuid4

import pytest

from test_media_library_index import index, scope, ref, insert, command
from bobbi_core import catalog_transfer


@pytest.mark.parametrize('name,state', [('Show.S01E01.mkv', 'proposed'), ('Movie.1999.2004.mkv', 'ambiguous')])
def test_undo_to_filename_suggestion_does_not_abort_other_manual_exports(index, name, state):
    suggestion, manual = ref(101, name=name), ref(102)
    insert(index, [suggestion, manual])
    assert index.item(scope(), suggestion['id'])['state'] == state
    edited = index.apply(scope(), uuid4().hex, [command(suggestion), command(manual, title='Keep this note')])
    assert all(row['status'] == 'applied' for row in edited['items'])
    assert index.apply(scope(), uuid4().hex, [command(suggestion, revision=1, action='undo')])['items'][0]['status'] == 'applied'
    before = index.item(scope(), suggestion['id'])
    assert before['state'] == state and before['provenance'] == 'manual'
    # Follow the actual export's bounded record/revision pagination.
    records, offset, revision = [], 0, None
    while True:
        page = index.manual_records(scope(), offset=offset, limit=1, projection_revision=revision)
        revision = page['projection_revision']
        records.extend(page['items'])
        if page['next_offset'] is None:
            break
        offset = page['next_offset']
        assert offset < 5
    payload = catalog_transfer.export_records(scope(), records)
    assert [entry['reference']['id'] for entry in payload['entries']] == [manual['id']]
    assert catalog_transfer.loads(catalog_transfer.dumps(payload)) == payload
    assert index.item(scope(), suggestion['id']) == before
    # Target lookup for imports must still expose every requested actual state.
    lookup = index.manual_records(scope(), file_ids=[suggestion['id']])['items']
    assert len(lookup) == 1 and lookup[0]['state'] == state and lookup[0]['revision'] == 2


def test_only_undone_automatic_records_produce_an_empty_manual_export_page(index):
    file = ref(103, name='Show.S01E02.mkv')
    insert(index, [file])
    index.apply(scope(), uuid4().hex, [command(file)])
    index.apply(scope(), uuid4().hex, [command(file, revision=1, action='undo')])
    page = index.manual_records(scope())
    assert page['items'] == [] and page['next_offset'] is None
    assert index.item(scope(), file['id'])['state'] == 'proposed'
    assert index.db.execute('SELECT COUNT(*) FROM review_changes WHERE file=?', (file['id'],)).fetchone()[0] == 2
