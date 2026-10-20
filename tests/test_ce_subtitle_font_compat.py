"""Observed ASS zero-duration event and same-release RAR compatibility."""
from copy import deepcopy

import pytest

from bobbi_core.font_archive import release_assets, parse_listing
from bobbi_core.subtitle_cues import parse
from bobbi_core.subtitle_candidates import inspect_text
from test_anime_range_file_identity import observed_files, HASH
from test_subtitle_binding import video


def ass(end='0:09:12.88'):
    return ('[Script Info]\n[Events]\nFormat: Start,End,Text\n'
            'Dialogue: 0:09:12.88,' + end + ',无声\n'
            'Dialogue: 0:09:13.00,0:09:16.00,真实中文对白\n').encode()


def test_zero_duration_ass_does_not_discard_other_dialogue_or_rewrite_bytes():
    raw = ass()
    assert len(parse(raw, '.ass')) == 1
    assert inspect_text(raw, '.ass', 60)[0] == raw


@pytest.mark.parametrize('end', ['0:09:11.88', 'invalid'])
def test_malformed_or_reversed_ass_still_rejected(end):
    with pytest.raises(ValueError):
        parse(ass(end), '.ass')


def test_only_invisible_ass_events_are_not_dialogue_proof():
    with pytest.raises(ValueError, match='No subtitle dialogue'):
        parse(ass().split(b'Dialogue: 0:09:13')[0], '.ass')


def test_actual_pack_rar_selected_without_other_release_subtree():
    files = observed_files()
    selected = files[2]
    current = video(source_info_hash=HASH, torrent_file_id=selected['id'],
                    torrent_path=selected['path'], torrent_file_bytes=selected['length'])
    metadata = dict(hash=HASH, title='Flip Flappers', file_stats=files)
    assert release_assets(current, metadata) == [files[-1]]
    wrong = deepcopy(metadata)
    wrong['file_stats'][-1]['path'] = 'Other Season/Fonts/fonts.rar'
    assert release_assets(current, wrong) == []


def test_observed_rar5_listing_retains_empty_final_property():
    raw = ('archive\n----------\nPath = fonts/font.ttf\nSize = 100\nAttributes = A\n'
           'Folder = -\nCopy Link = \nSplit Before = -\nSplit After = -\n'
           'Alternate Stream = -\nNT Security = \n\n').encode()
    assert parse_listing(raw) == [dict(path='fonts/font.ttf', bytes=100)]


@pytest.mark.parametrize('extra', ['Encrypted = +\n', 'Symbolic Link = /tmp/font\n', 'Hard Link = font.ttf\n',
                                  'Copy Link = font.ttf\n', 'Alternate Stream = +\n',
                                  'Split Before = +\n', 'Split After = +\n'])
def test_archive_controls_remain_rejected(extra):
    raw = ('archive\n----------\nPath = fonts/font.ttf\nSize = 100\nAttributes = A\n' + extra).encode()
    with pytest.raises(ValueError):
        parse_listing(raw)
