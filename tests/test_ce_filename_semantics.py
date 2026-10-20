"""Cross-consumer regressions, including the observed 40-file pack's real chain."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.filename_semantics import parse_filename
from bobbi_core.release_identity import bound_family
from bobbi_core.episode_revision import continuation_family
from bobbi_core.catalog_release import release_envelope
from bobbi_core.catalog_identity import release_title
from bobbi_core.subtitle_candidates import episode_tags
from bobbi_core.torrent_selection import select_exact_file
from bobbi_core.source_intent import verified_intents
from test_anime_range_file_identity import observed_files, HASH, TITLE


@pytest.mark.parametrize('geometry', ['1920x1080', '1922x1080', '3840x2160', '720x480'])
@pytest.mark.parametrize('marker', ['S01E01', '1x01', '- 01'])
def test_shared_parser_across_subtitles_family_catalog_and_revision(geometry, marker):
    name = '[Group] Audit Show {} [{} HEVC AAC].mkv'.format(marker, geometry)
    next_name = name.replace(marker, marker[:-2] + '02')
    assert bound_family(name, 1, 1) == bound_family(next_name, 1, 2)
    assert continuation_family(name, 1, 1) == continuation_family(next_name, 1, 2)
    assert release_envelope(name, 1, 1) == release_envelope(next_name, 1, 2)
    assert release_envelope(name, 1, 1) is not None
    assert release_title(name, 'tv') == ('audit show', None)
    assert episode_tags(name) == ({(1, 1)} if marker != '- 01' else set())
    assert parse_filename(name).technical_spans


@pytest.mark.parametrize('token', ['S01E01E02', 'S01E01-02', 'S01E01v2-02', '1x01+02'])
def test_multi_episode_remains_multi_in_all_consumers(token):
    name = 'Series ' + token + ' [1920x1080 HEVC].mkv'
    with pytest.raises(ValueError):
        bound_family(name, 1, 1)
    assert episode_tags(name) == {(1, 1), (1, 2)}
    assert release_envelope(name, 1, 1) is None


def test_old_successful_family_bytes_are_unchanged():
    assert bound_family('[Group] 86 Part 2 S01E01v2 [1080p HEVC AAC] [7E23ABCD].mkv', 1, 1) == (
        'group 86 part 2 EP v2 1080p hevc aac')
    a = '[Group] Series - 01v2 [1080p HEVC AAC].mkv'
    b = '[Group] Series - 02 [1080p HEVC AAC].mkv'
    assert bound_family(a, 1, 1) != bound_family(b, 1, 2)
    assert continuation_family(a, 1, 1) == continuation_family(b, 1, 2)
    assert continuation_family(a + ' v10', 1, 1) != continuation_family(b, 1, 2)


@pytest.mark.parametrize('template', [
    'ODD TAXI S01E{episode:02}-[1080p][JP.BD.Remux][lolice-mix].mkv',
    '[Group] Series S01E{episode:02} (1080p HEVC FLAC).mkv',
    'Series S01E{episode:02} [REPACK] [1080p HEVC].mkv',
    'Series S01E{episode:02} v2 [1080p HEVC].mkv',
])
def test_bracketed_season_episode_releases_reuse_strict_family(template):
    first, following = (template.format(episode=n) for n in (1, 2))
    fingerprint = release_envelope(first, 1, 1)
    assert fingerprint is not None
    assert fingerprint == release_envelope(following, 1, 2)
    assert release_envelope(following, 1, 1) is None
    assert release_envelope(following, 2, 2) is None
    for changed in (following.replace('1080p', '720p'),
                    following.replace('.mkv', '.mp4'),
                    following.replace('Series', 'Different Series').replace('ODD TAXI', 'Different Work'),
                    following.replace('[1080p', '[Extended] [1080p').replace('(1080p', '(Dubbed) (1080p')):
        assert release_envelope(changed, 1, 2) != fingerprint
    for token in ('REPACK', 'v2', 'lolice-mix'):
        if token in following:
            assert release_envelope(following.replace(token, 'Other'), 1, 2) != fingerprint


def test_episode_local_revision_survives_bracketed_technical_tags():
    a = 'Series S01E01v2-[1080p][BD][Group].mkv'
    b = 'Series S01E02-[1080p][BD][Group].mkv'
    assert release_envelope(a, 1, 1) == release_envelope(b, 1, 2)
    assert release_envelope(a, 1, 1) is not None
    assert release_envelope(b.replace('E02', 'E02-E03'), 1, 2) is None


def test_real_current_file_preparation_and_next_not_just_exact_selector():
    files = observed_files()
    body = dict(request_id='a'*32, purpose='current',
        media=dict(tmdb_id=68272, kind='tv', season=1, episode=1, anime=True,
                   title='Flip Flappers', release_title=TITLE),
        selected=dict(source_info_hash=HASH, torrent_file_id=3,
                      torrent_path=files[2]['path'], torrent_file_bytes=411570230))
    metadata = dict(hash=HASH, name=TITLE, file_stats=files)
    catalog = dict(provider='tmdb', id=68272, kind='tv', aliases=['Flip Flappers'],
                   year=2016, response_sha256='c'*64, ambiguous=False)
    targets = verified_intents(body, metadata, 'test-account', '/test', select_exact_file, catalog)
    assert len(targets) == 2
    assert [target[1]['file']['id'] for target in targets] == [3, 6]
    assert [target[0]['purpose'] for target in targets] == ['current', 'next']
    assert targets[0][0]['version_key'] == targets[1][0]['version_key']
    assert targets[0][0]['version_key'] == hashlib.sha256(
        bound_family(files[2]['path'].rsplit('/', 1)[1], 1, 1).encode()).hexdigest()
    # A later wrong-work file cannot block preparing the exact current file.
    altered = deepcopy(metadata)
    altered['file_stats'][5]['path'] = altered['file_stats'][5]['path'].replace('Flip Flappers -', 'Other Show -')
    assert len(verified_intents(body, altered, 'test-account', '/test', select_exact_file, catalog)) == 1
