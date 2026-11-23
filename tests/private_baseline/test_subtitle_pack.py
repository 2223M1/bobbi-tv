"""Real JackTorr matcher plus synthetic text; not playback/translation acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sqlite3

import pytest

from lib.cinema.subtitle_binding import binding
from lib.cinema.subtitle_pack import select, timing, validate
from lib.cinema.subtitle_store import SubtitleStore
from lib.cinema.metadata_cache import MetadataCache
from lib.cinema.ledger import Ledger
from test_subtitle_binding import video


@pytest.fixture
def matcher():
    source = Path(__file__).resolve().parents[3] / 'plugin.video.jacktorr/lib/subtitles.py'
    if not source.is_file():
        # Frozen production compatibility shim; the current core owns matching.
        import hashlib
        source = Path(__file__).resolve().parents[1] / 'fixtures/jacktorr-release317/subtitles.py'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == (
            'a41ee2093925629b5b5ea45ff5ec48ee853114fbe6bbe99dbe30baa7acd5c6cc')
    spec = importlib.util.spec_from_file_location('b_full_existing_sidecar_matcher', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.matching_chinese_sidecars


def data(text='完整中文对白', sparse=False):
    rows = []
    for i in range(6):
        for j in range(5):
            t = i * 200 + 10 + j * 10
            start = f'{t//3600:02}:{t//60%60:02}:{t%60:02},000'
            stop = f'{t//3600:02}:{t//60%60:02}:{t%60+2:02},000'
            label = text if not sparse or i == 0 else 'Foreign dialogue'
            rows.append(f'{len(rows)+1}\n{start} --> {stop}\n{label}\n')
    return '\n'.join(rows).encode()


def metadata(raw):
    return dict(hash='a' * 40, title='Series', file_stats=[
        dict(id=7, path='Series S01E01.mkv', length=1000),
        dict(id=8, path='Series S01E01.chs.srt', length=len(raw))])


def make(matcher, raw=None):
    raw = raw if raw is not None else data()
    meta = metadata(raw)
    proof = timing(video(), raw, select(video(), meta, matcher), 1200)
    return raw, meta, proof


def test_same_release_membership_and_content_not_visual_acceptance(matcher):
    raw, meta, proof = make(matcher)
    assert proof['chinese_cues'] == 30
    assert 'chinese_windows' not in proof and 'duration' not in proof
    assert validate(video(), raw, proof)
    result = binding(video(), raw, '.srt', 'zh', True, False,
                     dict(kind='same_release_pack', id='torrent:8'), proof)
    assert result['state'] == 'READY_NOT_VISUAL_PROOF'
    assert proof['state'] == 'SAME_RELEASE_CHINESE_TEXT'


@pytest.mark.parametrize('change', ['hash', 'size', 'file_id', 'path', 'duplicate'])
def test_wrong_or_ambiguous_video_membership_rejected(matcher, change):
    meta = metadata(data())
    if change == 'hash': meta['hash'] = 'b' * 40
    elif change == 'size': meta['file_stats'][0]['length'] += 1
    elif change == 'file_id': meta['file_stats'][0]['id'] += 100
    elif change == 'path': meta['file_stats'][0]['path'] = 'Series S01E02.mkv'
    else: meta['file_stats'].append(dict(meta['file_stats'][0]))
    with pytest.raises(ValueError):
        select(video(), meta, matcher)


@pytest.mark.parametrize('change', ['episode', 'different_cut', 'ambiguous'])
def test_no_guessing_episode_cut_or_duplicate_sidecars(matcher, change):
    meta = metadata(data())
    if change == 'episode': meta['file_stats'][1]['path'] = 'Series S01E02.chs.srt'
    elif change == 'different_cut': meta['file_stats'][1]['path'] = 'Series S01E01 Extended.chs.srt'
    else: meta['file_stats'].append(dict(id=9, path='chs/Series S01E01.srt', length=len(data())))
    assert select(video(), meta, matcher) is None


@pytest.mark.parametrize('raw', [data('English dialogue')])
def test_language_filename_does_not_prove_chinese_dialogue(matcher, raw):
    _, _, proof = make(matcher, raw)
    assert not validate(video(), raw, proof)
    assert proof['state'] == 'CHINESE_DIALOGUE_NOT_PROVEN'


@pytest.mark.parametrize('change', ['bytes', 'video', 'verdict', 'dialogue'])
def test_mutation_cannot_reuse_timing(matcher, change):
    raw, _, proof = make(matcher)
    v = video()
    if change == 'bytes': raw += b'\n'
    elif change == 'video': v = video(torrent_file_bytes=1001)
    elif change == 'verdict': proof['state'] = 'PASS'
    else: proof['chinese_cues'] += 1
    with pytest.raises(ValueError):
        validate(v, raw, proof)


def test_store_rechecks_actual_metadata_not_caller_digest(tmp_path, matcher, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    raw, meta, proof = make(matcher)
    cache = MetadataCache(tmp_path / 'metadata')
    cache.store(meta)
    with Ledger(tmp_path / 'ledger.sqlite') as ledger:
        store = SubtitleStore(ledger, tmp_path / 'subs', metadata_cache=cache, release_matcher=matcher)
        opts = dict(video=video(), raw=raw, extension='.srt', language='zh', full_dialogue=True,
                    forced=False, origin=dict(kind='same_release_pack', id='torrent:8'), timing=proof)
        assert store.put(**opts)['state'] == 'READY_NOT_VISUAL_PROOF'
        assert len(store.records(video(), current_manual_intent=0, ready_only=True)) == 1
        forged = deepcopy(proof)
        forged['selection']['metadata_sha256'] = 'f' * 64
        with pytest.raises(ValueError):
            store.put(**dict(opts, timing=forged))
        store.metadata_cache = None
        with pytest.raises(ValueError):
            store.records(video(), current_manual_intent=0, ready_only=True)
