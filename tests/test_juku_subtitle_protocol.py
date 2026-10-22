"""Subtitle compatibility fixtures + local SQLite; no daemon or cloud requests."""
from contextlib import closing
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))
from bobbi_core import juku_catalog as cat


def row(url='https://115.com/s/sabcdef#sub_fid=11%2C22', main=False):
    work = dict(tmdbId=101, typeId=1, year=2024, title='Protocol Film', id=1)
    link = dict(url=url, fid='5', file_name='Protocol.Film.2024.mkv', size=1234,
                fileId='5', fileName='Protocol.Film.2024.mkv', fileSize=1234)
    return cat._row(work, link, 'main:1' if main else 'shared:audit', main=main)


def test_arm64_and_amd64_exact_length_literals_agree():
    root = ROOT / 'tests/fixtures/catalog-subtitle-protocol'
    for architecture, pattern, comma in (
        ('arm64', '00a1eaa4-51.bin', '00c0a5f0-1.bin'),
        ('amd64', '00f475cf-51.bin', '011331d8-1.bin'),
    ):
        value = (root / architecture / pattern).read_bytes()
        assert len(value) == 51
        assert value.decode('ascii') == cat._SUBTITLE_PATTERN
        assert (root / architecture / comma).read_bytes() == b','


@pytest.mark.parametrize('prefix', ['#', '?', '&', '/'])
@pytest.mark.parametrize('key', ['sub_fid', 'SUB_ID', 'Subtitle_ID'])
def test_recovered_delimiters_and_case_insensitive_keys(prefix, key):
    assert cat.subtitle_fids('https://115.com/s/sabcdef' + prefix + key + '=11,22') == ['11', '22']


def test_decodes_once_trims_and_deduplicates_in_order():
    url = 'https://115.com/s/sabcdef?sub_id=%2011%20%2C22,,11&subtitle_id=33%2c22#sub_fid=44'
    assert cat.subtitle_fids(url) == ['11', '22', '33', '44']
    assert cat.subtitle_fids('#sub_fid=%2531,%E3%80%8032%E3%80%80') == ['32']


def test_path_unescape_does_not_convert_plus_to_space():
    assert cat.subtitle_fids('#sub_fid=+11+,22,%2B33%2B') == ['22']


def test_malformed_escape_preserves_entire_capture_before_splitting():
    assert cat.subtitle_fids('#sub_fid=%31,%ZZ,22&sub_id=%33') == ['22', '3']
    assert cat.subtitle_fids('#sub_fid=%31,%FF,22') == ['1', '22']


def test_go_trimspace_and_ascii_re2_whitespace():
    assert cat.subtitle_fids('#sub_fid=%1C11%1D,%8512%A0,%E3%80%8013%E3%80%80') == ['13']
    # Go unescape does not decode arbitrary bytes as Latin-1. Use UTF-8 for NEL/NBSP.
    assert cat.subtitle_fids('#sub_fid=%C2%8512%C2%A0') == ['12']
    assert cat.subtitle_fids('#sub_fid=11\v,22') == ['11', '22']
    assert cat.subtitle_fids('#sub_fid=11\u00a0,22') == ['11', '22']


@pytest.mark.parametrize('value', [None, 17, {}, [], 'x' * 8193])
def test_untrusted_input_is_bounded(value):
    assert cat.subtitle_fids(value) == []


def test_only_numeric_fids_are_retained_without_guessing_other_fields():
    invalid = ['abc', '-1', '1.1', '1e3', '1/2', '１', '1' * 33, 'http://evil.invalid/x']
    assert cat.subtitle_fids('#sub_fid=' + ','.join(invalid) + ',0012') == ['0012']
    assert cat.subtitle_fids('#subtitles=11&subtitle_fids=22&other_sub_fid=33&fid=44') == []
    assert cat.subtitle_fids('#sub_fid=11 22') == ['11']


def test_at_most_sixteen_unique_fids():
    ids = ','.join(str(value) for value in range(1, 80))
    assert cat.subtitle_fids('#sub_fid=1,1,' + ids) == [str(value) for value in range(1, 17)]


@pytest.mark.parametrize('main', [False, True])
def test_main_and_shared_rows_preserve_protocol_fids(main):
    value = row(main=main)
    assert value['subtitle_fids'] == ['11', '22']
    assert value['share'] == dict(code='sabcdef', password='')
    assert value['fid'] == '5'
    assert value['key'] == row('https://115.com/s/sabcdef', main=main)['key']


def test_rejects_nonshare_before_creating_subtitle_binding():
    with pytest.raises(ValueError, match='Not a 115 share'):
        row('https://foreign.invalid/path#sub_fid=11')


def test_duplicate_video_rows_merge_subtitle_refs_but_not_other_works():
    first, second = row(), row('https://115.com/s/sabcdef#subtitle_id=22,33')
    second['origins'] = ['shared:second']
    merged = cat._unique([first, second])
    assert len(merged) == 1
    assert merged[0]['subtitle_fids'] == ['11', '22', '33']
    assert first['subtitle_fids'] == ['11', '22']
    second['tmdb'] = 102
    assert cat._unique([first, second]) == []


def test_duplicate_merge_retains_maximum_sixteen():
    rows = [row('https://115.com/s/sabcdef#sub_fid=' + str(value)) for value in range(1, 80)]
    assert cat._unique(rows)[0]['subtitle_fids'] == [str(value) for value in range(1, 17)]


def test_refs_survive_snapshot_and_selected_video_roundtrip(tmp_path):
    value = row()
    spec = cat._spec(dict(tmdb_id=101, mode='movies', year=2024, aliases=['Protocol Film']))
    with closing(cat.Cache(tmp_path)) as cache:
        cache.replace_library('audit', 1, [value])
        local = cache.local(spec)
        assert local[0]['subtitle_fids'] == ['11', '22']
        cache.remember(local, spec)
        selected = cache.select(value['key'], spec['media_key'])
        assert selected['subtitle_fids'] == ['11', '22']
        assert selected['fid'] == '5'
