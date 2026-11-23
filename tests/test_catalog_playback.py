"""Real catalog + PanService tickets; fake upstream is not device validation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.file_ref import from_selected
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from test_ce2096_pan_accounts import saved
from test_media_library_index import insert, command

FILE = dict(file_id='original', name='Movie.mkv', size=100, directory=False)


@pytest.fixture
def catalog(tmp_path):
    pans = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = pans.accounts.install(saved(), pans.accounts.snapshot('quark'))
    registry = Registry(tmp_path / 'libraries.sqlite3')
    source = registry.save_directory('Movies', expected, 'folder')
    registry.close()
    state = SimpleNamespace(items=[deepcopy(FILE)], calls=0, before=lambda: None, more=False)
    def listing(parent, page, size):
        state.calls += 1
        state.before()
        return dict(items=deepcopy(state.items), page=page, has_more=state.more)
    pans.client_factory = lambda *args: SimpleNamespace(list_files=listing,
        stat_by_reference=lambda *a: pytest.fail('Stat alone cannot authorize indexed playback'))
    service = CatalogService(tmp_path, pans)
    ref = from_selected(expected, FILE, 'folder')
    insert(service.index, [ref], source['id'], expected)
    yield service, pans, expected, ref, source, state
    service.close()
    pans.close()


def play(catalog, request=None, **changes):
    service, pans, expected, ref, source, state = catalog
    body = dict(expected=expected, object_id=ref['id'], request_id=request or uuid4().hex, intent='play')
    body.update(changes)
    return service.dispatch('catalog_prepare_play', body)


def test_fresh_directory_required_then_existing_ticket_and_exact_history_identity(catalog):
    service, pans, expected, ref, source, state = catalog
    result = play(catalog)
    assert state.calls == 1 and pans.directory_cache
    claimed = pans.claim_play(result['ticket'])
    assert claimed['file_ref'] == ref and claimed['selected'] == FILE and claimed['account'] == expected
    with pytest.raises(PanError, match='PLAY_EXPIRED'):
        pans.claim_play(result['ticket'])


def test_queries_previews_and_mapping_do_not_generate_playback_authority(catalog):
    service, pans, expected, ref, source, state = catalog
    service.dispatch('catalog_query', dict(expected=expected))
    service.dispatch('catalog_preview', dict(expected=expected, commands=[command(ref)]))
    assert not pans.play_tickets and not pans.directory_cache and state.calls == 0
    with pytest.raises(ValueError, match='ACTION_INVALID'):
        play(catalog, selected=FILE)
    assert not pans.play_tickets


@pytest.mark.parametrize('change', ['size', 'same_name_replacement', 'epoch', 'source', 'cancel', 'account'])
def test_invalid_or_cancelled_exact_file_never_mints_ticket(catalog, change):
    service, pans, expected, ref, source, state = catalog
    key = uuid4().hex
    if change == 'size':
        state.items[0]['size'] += 1
    elif change == 'same_name_replacement':
        state.items[0]['file_id'] = 'replacement'
    elif change == 'epoch':
        pans.accounts.install(saved(session='new'), expected)
    elif change == 'account':
        pans.accounts.install(saved(uid='other'), expected)
    elif change == 'source':
        service.dispatch('catalog_remove', dict(expected=expected, source_id=source['id']))
    elif change == 'cancel':
        pans.close_stream(expected, key)
    with pytest.raises((ValueError, PanError)):
        play(catalog, key)
    assert not pans.play_tickets


def test_duplicate_confirmation_concurrent_and_after_claim_does_not_reissue(catalog):
    service, pans, expected, ref, source, state = catalog
    key = uuid4().hex
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: play(catalog, key), range(2)))
    assert results == [dict(ticket=key)] * 2 and state.calls == 1
    pans.claim_play(key)
    assert play(catalog, key) == dict(ticket=key) and not pans.play_tickets
    with pytest.raises(ValueError, match='REQUEST_REUSED'):
        play(catalog, key, object_id='a' * 64)


@pytest.mark.parametrize('change', ['cancel', 'logout', 'source', 'replace', 'close'])
def test_late_directory_cannot_publish_after_invalidating_event(catalog, change):
    service, pans, expected, ref, source, state = catalog
    key = uuid4().hex
    def invalidate():
        if change == 'cancel':
            pans.cancel_operation(expected, key)
        elif change == 'logout':
            pans.accounts.logout(expected)
        elif change == 'source':
            service.dispatch('catalog_remove', dict(expected=expected, source_id=source['id']))
        elif change == 'replace':
            insert(service.index, [dict(ref, size=200)], source['id'], expected)
        elif change == 'close':
            service.stop.set()
    state.before = invalidate
    with pytest.raises((ValueError, PanError)):
        play(catalog, key)
    assert not pans.play_tickets


def test_page_nine_target_is_incomplete_not_deleted_or_silently_replaced(catalog):
    service, pans, expected, ref, source, state = catalog
    state.items = [dict(FILE, file_id='not-original')]
    state.more = True
    with pytest.raises(ValueError, match='CATALOG_RECHECK_INCOMPLETE'):
        play(catalog)
    assert state.calls == 8 and not pans.play_tickets


def test_index_does_not_forge_real_directory_admission(catalog, monkeypatch):
    service, pans, expected, ref, source, state = catalog
    # A fabricated/standalone stat result has exact metadata but did not pass
    # the provider list cache. Existing prepare_play must still reject it.
    monkeypatch.setattr(pans, 'list_files', lambda *a, **k: dict(items=[FILE], has_more=False))
    with pytest.raises(PanError, match='PLAY_EXPIRED'):
        play(catalog)
    assert not pans.play_tickets and not pans.directory_cache


def test_query_account_guard_and_receipt_dispatch(catalog):
    service, pans, expected, ref, source, state = catalog
    key = uuid4().hex
    service.dispatch('catalog_apply', dict(expected=expected, request_id=key, commands=[command(ref)]))
    assert service.dispatch('catalog_receipt', dict(expected=expected, request_id=key))['items'][0]['status'] == 'applied'
    pans.accounts.logout(expected)
    with pytest.raises(PanError):
        service.dispatch('catalog_query', dict(expected=expected))
