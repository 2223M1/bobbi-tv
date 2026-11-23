"""Catalogue-checked library tags keep the actual media tuple unchanged."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.catalog_identity import Catalog, prove_work
from bobbi_core.source_intent import verified_intents
from bobbi_core.torrent_selection import select_exact_file

PATH = ('Nightcrawler (2014) {imdb-tt2872718}/Nightcrawler (2014) '
        '{imdb-tt2872718} 2160p Bluray Remux h265 DV HDR10 Atmos 7.1.mkv')
MEDIA = dict(tmdb_id=242582, kind='movie', season=0, episode=0, anime=False,
             title='Nightcrawler', release_title='Nightcrawler (2014) 2160p Bluray Remux h265 DV HDR10 Atmos 7.1')
CATALOG = dict(provider='tmdb', id=242582, kind='movie', aliases=['Nightcrawler'],
               year=2014, ambiguous=False, response_sha256='c' * 64, imdb_id='tt2872718')


def test_actual_basename_annotation_does_not_block_verified_preparation():
    file = dict(id=2, path=PATH, length=83084010252)
    body = dict(request_id='f' * 32, purpose='current', media=MEDIA,
        selected=dict(source_info_hash='a' * 40, torrent_file_id=2, torrent_path=PATH,
                      torrent_file_bytes=file['length']))
    metadata = dict(hash='a' * 40, title=MEDIA['release_title'],
                    name='Nightcrawler (2014) {imdb-tt2872718}', file_stats=[file])
    before = deepcopy((body, metadata))
    result = verified_intents(body, metadata, 'account', '/115open/cinema', select_exact_file, CATALOG)
    assert len(result) == 1
    assert result[0][1]['file'] == file
    assert result[0][1]['work_identity']['matched_title'] == 'nightcrawler'
    assert (body, metadata) == before


@pytest.mark.parametrize('path', [
    PATH.replace('tt2872718', 'tt0000001'),
    PATH.replace('2014', '2015'),
    PATH.replace('Nightcrawler', 'Another Movie'),
    PATH.replace('{imdb-tt2872718}', '{imdb-tt2872718 Unknown Arc}'),
    PATH.replace('{imdb-tt2872718}', '{Unknown Arc}'),
    PATH.replace('{imdb-tt2872718}', '{imdb-tt2872718} {imdb-tt0000001}'),
    PATH.replace('{imdb-tt2872718}', '{imdb-tt2872718} Unknown Arc'),
])
def test_library_tag_does_not_override_other_identity_fields(path):
    with pytest.raises(ValueError):
        prove_work(MEDIA, path, CATALOG)


@pytest.mark.parametrize('identity', [None, '', True, 'tt0000001', 'tt2872718 extra'])
def test_no_self_claimed_external_identity(identity):
    with pytest.raises(ValueError):
        prove_work(MEDIA, PATH, dict(CATALOG, imdb_id=identity))


def test_untagged_file_keeps_existing_path_without_external_id():
    assert prove_work(MEDIA, PATH.replace('{imdb-tt2872718}', ''),
                      dict(CATALOG, imdb_id=None))['id'] == 242582


@pytest.mark.parametrize('identity,retained', [('tt2872718', True), (None, False),
                                            ('tt2872718 extra', False), (True, False)])
def test_catalogue_retains_id_from_existing_details_without_extra_request(identity, retained):
    catalogue = Catalog(None, 'fixture-key')
    calls = []
    def fetch(path, params):
        calls.append(path)
        if path.startswith('search/'):
            return dict(total_pages=1, results=[]), 'd' * 64
        return dict(id=242582, title='Nightcrawler', original_title='Nightcrawler',
            release_date='2014-10-31', runtime=118, imdb_id=identity), 'e' * 64
    catalogue._get = fetch
    result = catalogue.lookup(MEDIA)
    assert ('imdb_id' in result) is retained
    assert calls == ['movie/242582', 'search/movie']
