from copy import deepcopy

import pytest

from bobbi_core.source_intent import verified_intents


@pytest.fixture
def intent():
    files = [dict(id=7, path='Series/Series S01E01 [Group].mkv', length=1000),
             dict(id=19, path='Series/Series S01E02 [Group].mkv', length=1000)]
    body = dict(request_id='f' * 32, purpose='current',
                media=dict(tmdb_id=1, kind='tv', season=1, episode=1, anime=False, title='Series', release_title='Series [Group]'),
                selected=dict(source_info_hash='a' * 40, torrent_file_id=7, torrent_path=files[0]['path'], torrent_file_bytes=1000))
    return body, dict(hash='a' * 40, title='Series', file_stats=files)


def selector(files, season, episode, *_):
    values = [item for item in files if 'S01E{:02}'.format(episode) in item['path']]
    if len(values) != 1:
        raise ValueError('Unresolved target')
    return values[0]


def verified(intent):
    catalog = dict(provider='tmdb', id=1, kind='tv', aliases=['Series'], year=2026, response_sha256='c' * 64, ambiguous=False)
    return verified_intents(*intent, 'account', '/115open/波比TV', selector, catalog)


def test_pack_prepares_current_and_same_version_next_without_submitting_twice(intent):
    targets = verified(intent)
    assert len(targets) == 2
    assert targets[0][0]['source_info_hash'] == targets[1][0]['source_info_hash']
    assert targets[0][0]['version_key'] == targets[1][0]['version_key']
    assert [item[0]['purpose'] for item in targets] == ['current', 'next']
    assert targets[0][0]['bytes_required'] == 2000
    assert targets[1][1]['file']['id'] == 19  # not an array index


@pytest.mark.parametrize('change', ['wrong_hash', 'wrong_id', 'wrong_path', 'wrong_size', 'self_verified',
    'duplicate_id', 'duplicate_path', 'traversal', 'missing_selected', 'boolean_id'])
def test_untrusted_selection_cannot_claim_verification(intent, change):
    body, metadata = deepcopy(intent)
    if change == 'wrong_hash':
        metadata['hash'] = 'b' * 40
    elif change == 'wrong_id':
        body['selected']['torrent_file_id'] = 0
    elif change == 'wrong_path':
        body['selected']['torrent_path'] = 'another.mkv'
    elif change == 'wrong_size':
        body['selected']['torrent_file_bytes'] = 999
    elif change == 'self_verified':
        body['verified'] = True
    elif change == 'duplicate_id':
        metadata['file_stats'][1]['id'] = 7
    elif change == 'duplicate_path':
        metadata['file_stats'][1]['path'] = metadata['file_stats'][0]['path']
    elif change == 'traversal':
        metadata['file_stats'][1]['path'] = '../escape.mkv'
    elif change == 'missing_selected':
        metadata['file_stats'] = metadata['file_stats'][1:]
    else:
        body['selected']['torrent_file_id'] = True
    with pytest.raises(ValueError):
        verified((body, metadata))


def test_missing_next_not_guessed_or_substituted(intent):
    intent[1]['file_stats'] = intent[1]['file_stats'][:1]
    assert len(verified(intent)) == 1


@pytest.mark.parametrize('titles', [
    ('Series/Series S01E01 [Group][x265_flac].mkv', 'Series/Series S01E02 [Group][x265_flac_aac].mkv'),
    ('Series/Series S01E01 [Group][x264_aac_ac3].mkv', 'Series/Series S01E02 [Group][x264_aac].mkv'),
])
def test_same_pack_extra_audio_is_prepared_under_its_own_version_not_declared_same(intent, titles):
    body, meta = intent
    for row, title in zip(meta['file_stats'], titles): row['path'] = title
    body['selected']['torrent_path'] = titles[0]
    targets = verified(intent)
    assert len(targets) == 2
    assert targets[0][0]['version_key'] != targets[1][0]['version_key']
    assert targets[1][0]['purpose'] == 'next'
    assert 'compatible' not in targets[1][1]


@pytest.mark.parametrize('following', [
    'Other/Series S01E02 [Group][x265_flac_aac].mkv',
    'Series/Series S01E02 [Group][x264_flac_aac].mkv',
    'Series/Series S01E02 [OtherGroup][x265_flac_aac].mkv',
    'Series/Series S01E02 [Group][x265_aac_flac].mkv',
    'Series/Series S01E02 v2 [Group][x265_flac_aac].mkv',
    'Series/Series S01E02 [Group] flac aac.mkv',
])
def test_audio_suffix_preparation_does_not_relax_other_release_fields(intent, following):
    body, meta = intent
    meta['file_stats'][0]['path'] = 'Series/Series S01E01 [Group][x265_flac].mkv'
    body['selected']['torrent_path'] = meta['file_stats'][0]['path']
    meta['file_stats'][1]['path'] = following
    assert len(verified(intent)) == 1


def test_different_group_or_revision_is_not_same_version_next(intent):
    intent[1]['file_stats'][1]['path'] = 'Series/Series S01E02 [OtherGroup].mkv'
    assert len(verified(intent)) == 1


@pytest.mark.parametrize('following', ['Series S01E02 EP03 [Group].mkv',
                                     'Other Series S01E02 [Group].mkv'])
def test_unprovable_following_file_does_not_discard_proven_current(intent, following):
    intent[1]['file_stats'][1]['path'] = 'Series/' + following
    targets = verified(intent)
    assert len(targets) == 1
    assert targets[0][0]['media_id'] == 'tmdb:tv:1:s1:e1'
    assert targets[0][1]['file']['id'] == 7


def native_selector():
    from bobbi_core.torrent_selection import select_exact_file
    return select_exact_file


@pytest.mark.parametrize('release_title', ['Series [S1 Fin]', 'Series Season 1 Complete'])
def test_preparation_preserves_the_same_release_season_context_as_playback(intent, monkeypatch, release_title):
    from bobbi_core import source_intent
    monkeypatch.setattr(source_intent, 'bind_selected_episode', lambda *a: None)
    body, metadata = intent
    body['media']['release_title'] = release_title
    for number, item in enumerate(metadata['file_stats'], 1):
        item['path'] = 'Series/Series [{:02}] [Group].mkv'.format(number)
    body['selected']['torrent_path'] = metadata['file_stats'][0]['path']
    exact = native_selector()
    selected = exact(metadata['file_stats'], 1, 1, metadata['title'] + ' ' + release_title)
    assert selected == metadata['file_stats'][0]
    catalog = dict(provider='tmdb', id=1, kind='tv', aliases=['Series'], year=2026,
                   response_sha256='c' * 64, ambiguous=False)
    targets = verified_intents(body, metadata, 'account', '/115open/波比TV', exact, catalog)
    assert [r['media_id'] for r, _ in targets] == ['tmdb:tv:1:s1:e1', 'tmdb:tv:1:s1:e2']
    assert [s['file']['id'] for _, s in targets] == [7, 19]


@pytest.mark.parametrize('case', ['no_season', 'conflicting_season', 'wrong_path', 'duplicate_episode'])
def test_release_context_does_not_override_exact_target_proofs(intent, monkeypatch, case):
    from bobbi_core import source_intent
    monkeypatch.setattr(source_intent, 'bind_selected_episode', lambda *a: None)
    body, metadata = intent
    body['media']['release_title'] = 'Series [S1 Fin]'
    metadata['file_stats'][0]['path'] = 'Series/Series [01] [Group].mkv'
    metadata['file_stats'][1]['path'] = 'Series/Series [02] [Group].mkv'
    body['selected']['torrent_path'] = metadata['file_stats'][0]['path']
    if case == 'no_season': body['media']['release_title'] = 'Series Complete'
    elif case == 'conflicting_season': metadata['title'] = 'Series Season 2'
    elif case == 'wrong_path': body['selected']['torrent_path'] = metadata['file_stats'][1]['path']
    else: metadata['file_stats'].append(dict(id=24, path='Alternate/Series [01] [Group].mkv', length=1000))
    catalog = dict(provider='tmdb', id=1, kind='tv', aliases=['Series'], year=2026,
                   response_sha256='c' * 64, ambiguous=False)
    with pytest.raises(ValueError):
        verified_intents(body, metadata, 'account', '/115open/波比TV', native_selector(), catalog)
