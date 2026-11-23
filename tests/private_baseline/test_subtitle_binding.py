import hashlib
from copy import deepcopy

import pytest

from lib.cinema.subtitle_binding import (
    binding, checked_video, prepared_video, same_file_timing, video_identity,
)
from legacy_subtitle_timing_evidence import six_window_timing
from test_cinema_prepared_index_resolve import prepared


RAW = '1\n00:00:01,000 --> 00:00:03,000\n中文字幕\n'.encode('utf-8')
SHA = hashlib.sha256(RAW).hexdigest()


def video(**changes):
    selected = dict(source_info_hash='a' * 40, torrent_file_id=7,
                    torrent_path='Series S01E01.mkv', torrent_file_bytes=1000)
    selected.update(changes)
    return video_identity('tmdb:tv:1:s1:e1', 'b' * 64, selected)


def windows(duration=1200):
    return [dict(at=(i + .5) * duration / 6, samples=5, outliers=0,
                 residuals=[.1, -.1, 0, .2, -.2], overlap_f1=.9) for i in range(6)]


def candidate(v=None, **changes):
    v = v or video()
    options = dict(extension='.srt', language='zh', full_dialogue=True, forced=False,
                   origin=dict(kind='media_attachment', id='track:2'),
                   timing=same_file_timing(v, SHA, v['key']))
    options.update(changes)
    return binding(v, RAW, **options)


@pytest.mark.parametrize('change', [dict(source_info_hash='c' * 40), dict(torrent_file_id=8),
    dict(torrent_path='Series S01E01 extended.mkv'), dict(torrent_file_bytes=1001)])
def test_same_episode_different_file_never_shares_cache_key(change):
    assert video()['key'] != video(**change)['key']
    assert candidate()['key'] != candidate(video(**change))['key']


def test_media_episode_and_release_are_part_of_binding():
    v = video()
    assert video_identity('tmdb:tv:1:s1:e2', v['release_key'], v['selected'])['key'] != v['key']
    assert video_identity(v['media_id'], 'd' * 64, v['selected'])['key'] != v['key']


@pytest.mark.parametrize('change', [dict(torrent_file_id=True), dict(torrent_file_bytes=0),
    dict(torrent_path='../episode.mkv'), dict(torrent_path='/episode.mkv'), dict(torrent_path='a//b.mkv'),
    dict(source_info_hash='A' * 40)])
def test_invalid_source_identity_is_rejected(change):
    with pytest.raises(ValueError):
        video(**change)


def test_mutated_key_is_not_trusted():
    v = video()
    v['key'] = 'f' * 64
    with pytest.raises(ValueError):
        checked_video(v)


def test_qualified_cloud_mapping_has_same_identity_as_bt(prepared):
    queue, rid, _ = prepared
    assert prepared_video(queue, rid, 'a' * 40) == video()
    queue.db.execute("UPDATE prepared_bindings SET evidence='{}'")
    with pytest.raises(ValueError):
        prepared_video(queue, rid, 'a' * 40)


def test_downloaded_chinese_does_not_require_timing_proof():
    result = candidate(timing=None, origin=dict(kind='provider', id='subtitle:123'))
    assert result['state'] == 'READY_NOT_VISUAL_PROOF'
    assert result['chinese_ready']
    assert result['fonts_ready']


@pytest.mark.parametrize('change', [dict(language='eng'), dict(full_dialogue=False), dict(forced=True)])
def test_english_or_forced_is_not_full_chinese(change):
    assert candidate(**change)['state'] == 'CANDIDATE_NOT_READY'


def test_exact_extracted_chinese_track_is_ready_not_visual_acceptance():
    assert candidate()['state'] == 'READY_NOT_VISUAL_PROOF'


@pytest.mark.parametrize('origin', ['provider', 'same_release_pack', 'legacy_candidate', 'manual'])
def test_same_name_or_release_cannot_claim_demuxed_track(origin):
    with pytest.raises(ValueError):
        candidate(origin=dict(kind=origin, id='subtitle:1'))


def test_timing_cannot_move_to_other_video_or_subtitle():
    with pytest.raises(ValueError):
        candidate(video(torrent_file_bytes=1001), timing=same_file_timing(video(), SHA, video()['key']))
    timing = same_file_timing(video(), 'e' * 64, video()['key'])
    with pytest.raises(ValueError):
        candidate(timing=timing)


def test_six_distributed_windows_preserve_transform_and_evidence():
    evidence = six_window_timing(video(), SHA, 'd' * 64, 1200, windows(), offset=1.25, scale=1.001)
    result = candidate(origin=dict(kind='provider', id='subtitle:123'), timing=evidence)
    assert result['state'] == 'READY_NOT_VISUAL_PROOF'
    assert result['timing']['offset'] == 1.25
    assert len(result['timing']['windows']) == 6
    assert result['timing']['windows'][0]['samples'] == 5


@pytest.mark.parametrize('change', [dict(outliers=1), dict(residuals=[0, 0, 0, 0, .51]), dict(overlap_f1=.74)])
def test_legacy_bad_timing_window_does_not_gate_content_loading(change):
    measurements = windows()
    measurements[4].update(change)
    proof = six_window_timing(video(), SHA, 'd' * 64, 1200, measurements)
    assert proof['state'] == 'TIMING_REJECTED'
    assert candidate(origin=dict(kind='provider', id='subtitle:123'), timing=proof)['state'] == 'READY_NOT_VISUAL_PROOF'


@pytest.mark.parametrize('change', [dict(at=0), dict(samples=0), dict(outliers=True),
    dict(residuals=[float('nan')] * 5), dict(overlap_f1=float('inf'))])
def test_empty_nonfinite_or_nondispersed_measurements_rejected(change):
    measurements = windows()
    measurements[4].update(change)
    with pytest.raises(ValueError):
        six_window_timing(video(), SHA, 'd' * 64, 1200, measurements)


def test_legacy_timing_verdict_is_not_a_loading_gate():
    measurements = windows()
    measurements[2]['residuals'] = [1.0] * 5
    evidence = six_window_timing(video(), SHA, 'd' * 64, 1200, measurements)
    evidence['state'] = 'TIMING_CORRELATION_NOT_VISUAL_PROOF'
    assert candidate(origin=dict(kind='provider', id='subtitle:123'), timing=evidence)['state'] == 'READY_NOT_VISUAL_PROOF'


def test_ass_font_state_independent_of_video_and_chinese():
    from lib.cinema.fonts import ass_font_requirements
    raw = ('[Script Info]\n[V4+ Styles]\nFormat: Name,Fontname,Bold,Italic\n'
           'Style: Default,Test Font,0,0\n[Events]\nFormat: Start,End,Style,Text\n'
           'Dialogue: 0:00:01.00,0:00:03.00,Default,中文字幕\n').encode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    def ass_candidate(**changes):
        return binding(video(), raw, '.ass', 'zh', True, False, dict(kind='media_attachment', id='track:2'),
                       same_file_timing(video(), sha, video()['key']), **changes)
    result = ass_candidate()
    assert result['chinese_ready'] and not result['fonts_ready']
    assert result['state'] == 'READY_NOT_VISUAL_PROOF'
    fonts = dict(subtitle_sha256=sha, status='EXACT_FONTS_READY_NOT_VISUAL_PROOF', missing=[],
                 selected=[dict(sha256='f' * 64, synthetic_style_may_be_needed=False,
                                request=ass_font_requirements(raw)['fonts'][0])])
    assert ass_candidate(font_result=fonts)['state'] == 'READY_NOT_VISUAL_PROOF'
    fonts['selected'][0]['synthetic_style_may_be_needed'] = True
    assert not ass_candidate(font_result=fonts)['fonts_ready']
    fonts['subtitle_sha256'] = 'd' * 64
    with pytest.raises(ValueError):
        ass_candidate(font_result=fonts)


def test_signed_url_cannot_be_recorded_as_origin():
    with pytest.raises(ValueError):
        candidate(origin=dict(kind='provider', id='https://example.test/sub?secret=value'))


@pytest.mark.parametrize('raw,extension', [(b'<html>Error</html>', '.srt'), (b'random text', '.srt'),
    (RAW, '.ass'), (b'[Script Info]\n[Events]\n', '.ass')])
def test_bytes_must_match_actual_subtitle_representation(raw, extension):
    v = video()
    with pytest.raises(ValueError):
        binding(v, raw, extension, 'zh', True, False, dict(kind='media_attachment', id='track:2'),
                same_file_timing(v, hashlib.sha256(raw).hexdigest(), v['key']))


@pytest.mark.parametrize('extension', ['.sup', '.sub'])
def test_picture_subtitle_needs_native_parse_proof_not_extension_only(extension):
    assert candidate(extension=extension)['state'] == 'CANDIDATE_NOT_READY'
