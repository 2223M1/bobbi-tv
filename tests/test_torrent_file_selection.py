"""Pure selector regressions; synthetic filenames are not device playback evidence."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.torrent_episode_matching import match_episode_file
from bobbi_core.torrent_selection import ExactSelectionError, select_exact_file

HASH = '1' * 40


def file(path, index=1):
    return dict(id=index, path=path, length=1000)


def binding(season=1, episode=1, absolute=1):
    return json.dumps(dict(media_id='tmdb:1', season=season, episode=episode,
        absolute_episode=absolute, source_info_hash=HASH, provenance='anibridge-v3-anidb-regular'))


@pytest.mark.parametrize('geometry', ['720x480', '1280x720', '1920x1080', '1920x800', '3840x2160'])
@pytest.mark.parametrize('where', ['basename', 'directory'])
def test_geometry_never_overrules_explicit_episode(geometry, where):
    path = ('Series S01E01 [' + geometry + '].mkv' if where == 'basename'
            else 'Series [' + geometry + ']/Series S01E01.mkv')
    target = file(path)
    assert select_exact_file([target], 1, 1) == target


@pytest.mark.parametrize('geometry', ['720x480', '1920x1080', '3840x2160'])
def test_geometry_does_not_block_bound_anime_episode(geometry):
    target = file('[Group] Series - 01 [' + geometry + ' HEVC AAC].mkv')
    other = file('[Group] Series - 02 [' + geometry + ' HEVC AAC].mkv', 2)
    assert select_exact_file([other, target], 1, 1, 'Series [01-13]', HASH, binding()) == target


@pytest.mark.parametrize('token,season,episode', [('1x02', 1, 2), ('01x002', 1, 2),
    ('12x003', 12, 3), ('00x01', 0, 1), ('S100E01', 100, 1)])
def test_normal_explicit_episode_syntax_is_preserved(token, season, episode):
    target = file('Series ' + token + ' [1920x1080].mkv')
    assert match_episode_file([target], season, episode) == target


def test_geometry_cannot_supply_episode_identity():
    target = file('Series [1920x1080].mkv')
    assert match_episode_file([target], 1920, 1080) is None
    with pytest.raises(ExactSelectionError):
        select_exact_file([target], 1, 1, '', HASH, binding())


@pytest.mark.parametrize('path', ['Series S02E01 [1920x1080].mkv',
    'Series 2x01 [1920x1080].mkv', 'Series S01E02 [1920x1080].mkv',
    'Series S01E01E02 [1920x1080].mkv', 'Series - 01-02 [1920x1080].mkv',
    'Series S01E01 EP02 [1920x1080].mkv'])
def test_geometry_fix_never_weakens_conflicting_or_multi_episode_checks(path):
    with pytest.raises(ExactSelectionError):
        select_exact_file([file(path)], 1, 1, '', HASH, binding())


def test_two_matching_files_remain_ambiguous():
    files = [file('A/Series - 01 [1920x1080].mkv'),
             file('B/Series - 01 [1280x720].mkv', 2)]
    with pytest.raises(ExactSelectionError):
        select_exact_file(files, 1, 1, '', HASH, binding())


def test_dimensions_do_not_invent_missing_season_or_absolute_offset():
    with pytest.raises(ExactSelectionError):
        select_exact_file([file('Series - 01 [1920x1080].mkv')], 1, 1)
    with pytest.raises(ExactSelectionError):
        select_exact_file([file('Series S02 - 13 [1920x1080].mkv')], 2, 1)


def test_audio_codec_tag_keeps_previous_fix():
    target = file('Series DD2.0.x264/Series S01E01.mkv')
    assert select_exact_file([target], 1, 1) == target


def test_extras_remain_excluded_without_largest_file_guess():
    target = file('Movie.2020.2160p.mkv')
    extra = file('Extras/Movie.trailer.mkv', 2)
    assert select_exact_file([extra, target]) == target
    with pytest.raises(ExactSelectionError):
        select_exact_file([target, file('Movie.2020.Directors.Cut.mkv', 3)])
