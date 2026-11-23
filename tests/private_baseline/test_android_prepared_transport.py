from types import SimpleNamespace

import pytest

from test_cinema_prepared_index_resolve import prepared, Provider, body
from bobbi_core.prepared_resolver import PreparedResolver
from bobbi_core.prepared_transport import checked_url, playback_path
from bobbi_core import preparation_client
from bobbi_core.prepared_index import document


URL = 'http://127.0.0.1:19798/static/file/opaque-selected-file'


def test_http_resolver_rechecks_file_and_account_and_does_not_persist_url(prepared):
    queue, resource, _ = prepared
    provider = Provider()
    provider.accounts += ['account']
    used = []
    resolver = PreparedResolver(queue, 'account', provider,
        address=lambda p, item: used.append(item['file_id']) or URL)
    plan = resolver.plan(body(resource))
    result = resolver.finish(plan, resolver.perform(plan))
    assert result['state'] == 'ready' and result['playback_url'] == URL
    assert used == ['cloud-file'] and not provider.accounts
    assert URL not in str(document(queue, 'account'))


def test_account_change_after_address_prevents_playback(prepared):
    queue, resource, _ = prepared
    provider = Provider()
    provider.accounts += ['different-account']
    resolver = PreparedResolver(queue, 'account', provider, address=lambda *_: URL)
    plan = resolver.plan(body(resource))
    assert resolver.finish(plan, resolver.perform(plan)) == {'state': 'unavailable'}


def test_changed_file_never_requests_an_address(prepared):
    queue, resource, _ = prepared
    provider = Provider()
    provider.rows[0]['bytes'] += 1
    resolver = PreparedResolver(queue, 'account', provider, address=lambda *_: pytest.fail('wrong file'))
    plan = resolver.plan(body(resource))
    assert resolver.finish(plan, resolver.perform(plan)) == {'state': 'unavailable'}


@pytest.mark.parametrize('value', ['https://example.com/file', 'http://localhost:80/file',
    'http://127.0.0.1:1/file|Authorization=bad', 'http://user@127.0.0.1:1/file',
    'http://127.0.0.1:1/file\n', 'file:///storage/movie.mkv'])
def test_nonlocal_or_header_injecting_addresses_rejected(value):
    with pytest.raises(ValueError):
        checked_url(value)


def test_fresh_client_receipt_carries_url_without_mutating_snapshot(prepared, monkeypatch):
    queue, resource, _ = prepared
    snapshot = document(queue, 'account')
    entry = snapshot['titles'][0]['sources'][0]
    before = dict(entry)
    provider = Provider()
    provider.accounts += ['account']
    resolver = PreparedResolver(queue, 'account', provider, address=lambda *_: URL)
    def call(method, request, **kwargs):
        assert method == 'resolve'
        plan = resolver.plan(request)
        return resolver.finish(plan, resolver.perform(plan))
    monkeypatch.setattr(preparation_client, 'capture_account', lambda data: {})
    monkeypatch.setattr(preparation_client, 'call', call)
    data = dict(request_id='f'*32, mode='tv', ids={'tmdb_id': 1}, tv_data={'season': 1, 'episode': 1})
    resolved = preparation_client.resolve_entry(data, snapshot, entry)
    assert playback_path(snapshot['mount_root'], resolved) == URL
    assert entry == before and '_playback_url' not in entry


def test_ordinary_ce_mount_path_is_unchanged():
    assert playback_path('/storage/videos/Clouddrive/CloudDrive', {'path': '/115open/movie.mkv'}) == \
        '/storage/videos/Clouddrive/CloudDrive/115open/movie.mkv'
