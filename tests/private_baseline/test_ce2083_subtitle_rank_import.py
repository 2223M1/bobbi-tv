"""A slow compatibility alias must not lose whole batches of valid sources."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import ModuleType
import sys
import subprocess
from pathlib import Path

from lib.domain.torrent import TorrentStream
from lib.utils.general.cinema_source_rank import chinese_subtitle_preference, rank_sources
from lib.utils.parsers.title_parser import source_has_chinese_subtitles


def test_parallel_ranking_uses_canonical_subtitle_metadata(monkeypatch):
    # The observed ImportError names this alias, not the installed core module.
    # Model its unfinished namespace while real source transforms run in parallel.
    monkeypatch.setitem(sys.modules, 'lib.cinema.subtitle_projection',
                        ModuleType('lib.cinema.subtitle_projection'))
    barrier = Barrier(4)
    def rank(index):
        source = TorrentStream(title='[LoliHouse] Fixture - 01 [1080p][简繁外挂字幕]',
                               type='Torrent', infoHash=f'{index:040x}')
        barrier.wait(2)
        for _ in range(20):
            assert source_has_chinese_subtitles(source)
            assert chinese_subtitle_preference(source)[0] == 2
            assert rank_sources([source], {'mode': 'tv', 'genre_ids': [16]}) == [source]
        return source.infoHash
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(rank, range(1, 5)))) == 4


def test_real_ranking_does_not_wait_for_initializing_compatibility_alias():
    script = r'''
import importlib, runpy, sys, threading
fixture = runpy.run_path('tests/private_baseline/conftest.py')
from lib.domain.torrent import TorrentStream
from lib.utils.general.cinema_source_rank import rank_sources
from lib.utils.parsers.title_parser import source_has_chinese_subtitles
import lib.cinema
import bobbi_core.subtitle_projection as canonical
alias = 'lib.cinema.subtitle_projection'
assert alias not in sys.modules
entered, release, ranked = [threading.Event() for _ in range(3)]
original = importlib.import_module
errors = []
def controlled(name, package=None):
    if name == 'bobbi_core.subtitle_projection' and threading.current_thread().name == 'alias-loader':
        entered.set()
        assert release.wait(5)
    return original(name, package)
def load_alias():
    try:
        from lib.cinema.subtitle_projection import source_label
        assert source_label is canonical.source_label
    except BaseException as error:
        errors.append(error)
def transform():
    try:
        source = TorrentStream(title='Fixture - 01 [1080p][CHS external subtitles]', type='Torrent')
        assert source_has_chinese_subtitles(source)
        assert rank_sources([source], {'mode': 'tv'}) == [source]
        ranked.set()
    except BaseException as error:
        errors.append(error)
importlib.import_module = controlled
loader = threading.Thread(target=load_alias, name='alias-loader')
worker = threading.Thread(target=transform, name='source-transform')
try:
    loader.start()
    assert entered.wait(2)
    temporary = sys.modules[alias]
    assert temporary is not canonical and temporary.__spec__._initializing
    worker.start()
    assert ranked.wait(2), 'Real ranking must not wait for or observe the unfinished compatibility module'
finally:
    release.set()
    loader.join(5)
    if worker.ident is not None:
        worker.join(5)
    importlib.import_module = original
    fixture['pytest_sessionfinish'](None, 0)
assert not loader.is_alive() and not worker.is_alive()
assert not errors, errors
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', script],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True,
                            text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
