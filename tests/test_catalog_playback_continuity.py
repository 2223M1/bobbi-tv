"""A catalogue selection can never become an unrelated prepared-file selection."""
from copy import deepcopy
import sys
from types import SimpleNamespace

import pytest

from test_standard_product import product, selected, handoff


@pytest.mark.parametrize('pointer', [None, {}, [], {'guid': 'unscoped'},
                                     {'provider': 'mdsub'}, {'provider': 'deleted'}])
def test_damaged_explicit_source_never_falls_back_to_legacy_catalog_or_torrent(product, monkeypatch, pointer):
    from lib.utils.player import bt_continuity as bt, direct_continuity as direct
    data = selected(product)
    data.update(ids={'tmdb_id': 181}, indexer='漫迪 MDsub', direct_source=pointer,
                prepared_source_info_hash='f'*40)
    monkeypatch.setattr(direct, '_mdsub', lambda *_: pytest.fail('Damaged pointer used as legacy history'))
    assert direct.is_catalog_source(data) and not bt.applies(data)
    assert direct.next_direct_data(data)[0] is None
    # Losing the legacy display label must not turn a damaged pointer into a BT proof.
    data.pop('indexer')
    assert direct.is_catalog_source(data) and not bt.applies(data)


def test_legacy_catalog_with_stale_torrent_fields_still_uses_its_bound_source(product, monkeypatch):
    from lib.utils.player import bt_continuity as bt, direct_continuity as direct
    data, fields, _, _ = catalogue(product, monkeypatch, legacy=True)
    data['prepared_source_info_hash'] = 'f'*40
    assert not bt.applies(data)  # Also used by native EOF's fresh check.
    child, _ = direct.next_direct_data(data)
    assert child['direct_source']['guid'] == fields['guid']
    assert child['_next_recheck'] and child['_account'] == data['_account']


def catalogue(product, monkeypatch, *, missing=False, legacy=False):
    from lib.utils.player import direct_continuity as direct
    data = selected(product)
    title = 'Movie.Show.S01E02.Group.mkv'
    fields = dict(guid='mdsub:'+'a'*64, url='https://pan.mdsub.top/api/raw?next',
                  title=title, size=65536, indexer='漫迪 MDsub')
    data.update(ids={'tmdb_id': 181}, indexer='漫迪 MDsub',
                source_title='Movie.Show.S01E01.Group.mkv', prepared_version_key='b'*64)
    if not legacy:
        data['direct_source'] = dict(provider='mdsub', guid='mdsub:'+'c'*64,
            locator='https://pan.mdsub.top/api/raw?original', title=data['source_title'], size=65536)
    lookups, resolutions = [], []
    monkeypatch.setattr(direct, '_mdsub', lambda *args:
        (None, 'NEXT_MISSING_OR_AMBIGUOUS') if missing else (dict(fields), 'INDEXED_DIRECT_SAME_RELEASE'))
    def index(*, session):
        lookups.append(True)
        return dict(mount_root='/115', titles=[dict(kind='tv', tmdb_id=181, sources=[dict(
            key='d'*64, season=1, episode=2, state='qualified', title=title, bytes=fields['size'],
            path='/unrelated/'+title, prepared_qualification='e'*64, prepared_version_key='b'*64,
            prepared_source_info_hash='f'*40)])])
    monkeypatch.setitem(sys.modules, 'lib.clients.bobbi_library', SimpleNamespace(
        load_prepared_index=index, local_path=lambda root, path: root+path))
    def resolve(data, cancelled, *, session):
        resolutions.append(deepcopy(data))
        return dict(data, url='https://media.example/confirmed')
    monkeypatch.setattr(product.module, 'resolve_selected', resolve)
    return data, fields, lookups, resolutions


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('missing', [False, True])
def test_direct_discovery_ignores_same_title_size_and_family_in_other_index(product, monkeypatch, legacy, missing):
    data, fields, lookups, resolutions = catalogue(product, monkeypatch, missing=missing, legacy=legacy)
    child = product.module.next_data(data, lambda: False)
    assert not lookups and not resolutions, 'No unrelated index read or playable URL before EOF'
    if missing:
        assert child is None
    else:
        assert child['direct_source']['guid'] == fields['guid']
        assert child['url'] == fields['url'] and child['_next_recheck']
        assert 'prepared_resource_id' not in child
        assert child['_account'] == data['_account']


@pytest.mark.parametrize('outcome', ['same', 'replaced', 'missing', 'stop'])
def test_standard_keeps_only_original_next_file_across_pause_until_eof(product, monkeypatch, outcome):
    data, fields, lookups, resolutions = catalogue(product, monkeypatch)
    actor, state = product.actor, product.state
    handoff(product, data)
    if actor.session.worker:
        actor.session.worker.join(2)
    # The fixture episode lasts 100 seconds, so discovery starts at its first tick.
    actor.tick()
    assert actor.session.current['next_data']['direct_source']['guid'] == fields['guid']
    assert resolutions == [] and len(state.opened) == 1
    product.clock[0] += 1800
    state.position = 99
    actor.tick()
    if outcome == 'replaced':
        fields.update(guid='mdsub:'+'9'*64, url='https://pan.mdsub.top/api/raw?replacement')
    elif outcome == 'missing':
        from lib.utils.player import direct_continuity as direct
        monkeypatch.setattr(direct, '_mdsub', lambda *args: (None, 'NEXT_MISSING_OR_AMBIGUOUS'))
    state.playing = False
    if outcome == 'stop':
        actor.player.onPlayBackStopped()
    else:
        actor.player.onPlayBackEnded()
    actor.tick()
    if actor.session.worker:
        actor.session.worker.join(2)
    product.clock[0] += .3
    actor.tick()
    actor.tick()
    assert len(state.opened) == (2 if outcome == 'same' else 1)
    assert len(resolutions) == (1 if outcome == 'same' else 0)
    if resolutions:
        assert resolutions[0]['direct_source']['guid'] == fields['guid']
        assert state.opened[-1][0] == 'https://media.example/confirmed'
    assert not lookups
