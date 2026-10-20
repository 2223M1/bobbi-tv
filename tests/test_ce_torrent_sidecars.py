"""Real observed basename grammar; actual fetch/publish and negative siblings."""
from copy import deepcopy
import json
import time

import pytest

from bobbi_core.playback_request import torrent_file_identity
from bobbi_core.torrent_subtitles import matching_chinese_sidecars, fetch_candidate
from test_anime_range_file_identity import observed_files, HASH


def test_observed_group_language_sidecars_are_episode_bound():
    files = observed_files()
    assert matching_chinese_sidecars(files[2]['path'], files) == [files[0]]
    assert matching_chinese_sidecars(files[5]['path'], files) == [files[3]]
    assert matching_chinese_sidecars(files[2]['path'], files[1:]) == [files[1]]


@pytest.mark.parametrize('suffix', ['Extended-SC', 'Commentary-SC', 'Other-SC', 'Forced-SC', 'SweetSub-EN'])
def test_group_suffix_cannot_hide_other_editions_or_nonchinese(suffix):
    files = observed_files()[:3]
    files[0]['path'] = files[0]['path'].replace('SweetSub-SC', suffix)
    assert matching_chinese_sidecars(files[2]['path'], [files[0]]) == []


def test_ambiguous_same_language_sidecars_are_not_guessed():
    files = observed_files()[:3]
    files.append(dict(files[0], id=99))
    assert matching_chinese_sidecars(files[2]['path'], files) == []


def test_actual_fetch_checks_metadata_and_publishes_chinese_text(tmp_path):
    raw = ('[Script Info]\nScriptType: v4.00+\n[Events]\n'
           'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' +
           '\n'.join('Dialogue: 0,0:{:02d}:{:02d}.00,0:{:02d}:{:02d}.00,Default,,0,0,0,,完整中文对白'.format(
               (i*20)//60, (i*20)%60, (i*20+2)//60, (i*20+2)%60) for i in range(30))).encode()
    files = deepcopy(observed_files())
    files[0]['length'] = len(raw)
    selected = files[2]
    calls = []
    def transport(url, deadline, cancelled, limit, **kwargs):
        calls.append((url, kwargs))
        return json.dumps(dict(hash=HASH, file_stats=files)).encode() if url.endswith('/torrents') else raw
    result = fetch_candidate(None, 'http://127.0.0.1:8090', None,
        dict(info_hash=HASH, file=selected),
        dict(file_identity=torrent_file_identity(HASH, selected['id'], selected['path'], selected['length'])),
        dict(duration=1421), time.monotonic()+8, lambda:False, root=tmp_path, transport=transport)
    assert result['origin'] == 'same-torrent' and result['state'] == 'candidate'
    assert len(calls) == 2 and 'index=1&play' in calls[1][0]
    assert 'SweetSub-SC.ass' in calls[1][0]
