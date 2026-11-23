"""A late domain/projection rejection cannot commit half a review command."""
from uuid import uuid4

import pytest

from bobbi_core import catalog_query, catalog_segments, catalog_supplements
from test_media_library_index import index, scope, ref, insert, command
from test_catalog_segments import segment_command


@pytest.mark.parametrize('stage', ['supplement', 'segments', 'projection', 'revision'])
def test_late_rejection_rolls_back_domains_but_keeps_failed_receipt_and_next_item(index, monkeypatch, stage):
    first, second = ref(1), ref(2)
    insert(index, [first, second])
    before = index.item(scope(), first['id'])
    generation = index.db.execute('SELECT revision FROM catalog_meta').fetchone()[0]
    calls = []
    target, name = {
        'supplement': (catalog_supplements, 'write'),
        'segments': (catalog_segments, 'write'),
        'projection': (catalog_query, 'project'),
        'revision': (index, '_changed'),
    }[stage]
    real = getattr(target, name)

    def reject_after_write(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('LATE_DOMAIN_REJECTION')
        return result

    monkeypatch.setattr(target, name, reject_after_write)
    request = uuid4().hex
    commands = [segment_command(index, first), command(second)]
    result = index.apply(scope(), request, commands)
    assert result['items'][0]['status'] == 'failed'
    assert result['items'][1]['status'] == 'applied'
    assert index.item(scope(), first['id']) == before
    assert index.item(scope(), second['id'])['revision'] == 1
    for table in ('review_changes', 'supplement_changes', 'file_supplements', 'segment_changes', 'file_segments'):
        assert index.db.execute('SELECT COUNT(*) FROM ' + table + ' WHERE file=?', (first['id'],)).fetchone()[0] == 0
    assert index.db.execute('SELECT revision FROM catalog_meta').fetchone()[0] == generation + 1
    after = index.db.total_changes
    assert index.receipt(scope(), request)['items'] == [dict(index=n, **value) for n, value in enumerate(result['items'])]
    assert index.db.total_changes == after
    assert index.apply(scope(), request, commands) == result
    assert len(calls) == 2, 'A receipt lookup or replay may not retry a failed domain write'


def test_unexpected_projection_io_failure_rolls_back_item_and_keeps_request_unknown(index, monkeypatch):
    file = ref(); insert(index, [file])
    before = index.item(scope(), file['id'])
    real = catalog_query.project

    def fail(*args, **kwargs):
        real(*args, **kwargs)
        raise OSError('projection IO fixture')

    monkeypatch.setattr(catalog_query, 'project', fail)
    request = uuid4().hex
    with pytest.raises(OSError):
        index.apply(scope(), request, [segment_command(index, file)])
    assert index.item(scope(), file['id']) == before
    assert index.db.execute('SELECT COUNT(*) FROM review_receipts WHERE request=?', (request,)).fetchone()[0] == 0
    assert index.db.execute('SELECT COUNT(*) FROM review_requests WHERE request=?', (request,)).fetchone()[0] == 1
