"""Production entrypoints survive removal of two unreferenced IO implementations.

Only host metadata lookup, Kodi imports and external HTTP are substituted. The
real discovery dispatcher, exact torrent matcher, body inspection/publication,
current Stremio client/parser and manager constructor execute unchanged.
"""
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'addons/plugin.video.bobbi/lib'
CORE = ROOT / 'addons/script.module.bobbi.core/lib'
sys.path.insert(0, str(CORE))


def load(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def stub(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_retired_download_implementations_have_no_live_entrypoints():
    from bobbi_core import torrent_subtitles
    assert not hasattr(torrent_subtitles, 'cache_chinese_sidecar')
    assert not hasattr(torrent_subtitles, '_valid_chinese_subtitle')
    assert not (CORE / 'bobbi_core/subtitle_provider.py').exists()
    assert not (LIB / 'cinema/subtitle_provider.py').exists()
    assert torrent_subtitles.MATCHER_POLICY == 'declared-group-language-v1'
    # Do not confuse the retired adapter with the current user-facing client.
    assert (LIB / 'clients/subtitle/opensubstremio.py').is_file()
    assert (LIB / 'clients/subtitle/submanager.py').is_file()


@pytest.mark.parametrize('same_torrent', [True, False])
def test_discovery_uses_current_torrent_pipeline_and_preserves_existing_files(tmp_path, monkeypatch, same_torrent):
    from bobbi_core import subtitle_candidates, subtitle_io
    from bobbi_core.playback_request import torrent_file_identity
    root = tmp_path / 'subtitles'
    root.mkdir()
    raw = '1\n00:30:00,000 --> 00:30:02,000\n中文字幕\nChinese dialogue\n'.encode()
    # More than the retired cache's 32-file ceiling; no existing cache is evicted.
    old = {root / (format(i, '064x') + '.zh-Hans.srt'): raw for i in range(35)}
    for path, data in old.items():
        path.write_bytes(data)
    monkeypatch.setattr(subtitle_candidates, 'ROOT', root)
    stub(monkeypatch, 'lib.clients.tmdb.movie_years', cached_movie_years=lambda _: None)
    stub(monkeypatch, 'bobbi_torrent.backend', subtitle_connection=lambda: ('http://127.0.0.1:8090', None))
    fallback = load('ce2029_architecture_fallback', LIB / 'services/subtitle_fallback.py', monkeypatch)
    video = dict(id=1, path='Fixture.2025.mkv', length=10000)
    subtitle = dict(id=2, path='Fixture.2025.chs.srt', length=len(raw))
    info_hash, calls, remote_calls = 'a' * 40, [], []
    def transport(url, deadline, cancelled, limit, **options):
        assert deadline > time.monotonic() and not cancelled()
        assert options['mode'] == 'torrent'
        calls.append(url)
        if url.endswith('/torrents'):
            return json.dumps(dict(hash=info_hash, file_stats=[video] + ([subtitle] if same_torrent else []))).encode()
        assert 'index=2&play' in url
        return raw
    monkeypatch.setattr(subtitle_io, 'read_http', transport)
    def remote(context, deadline, cancelled):
        remote_calls.append(context)
        assert not same_torrent
        return dict(state='candidate', origin='fixture-remote')
    context = dict(mode='movie', tmdb=1, year=2025, title='Fixture', duration=60,
                   _torrent=dict(info_hash=info_hash, file=video))
    receipt = dict(file_identity=torrent_file_identity(info_hash, video['id'], video['path'], video['length']))
    result = fallback.discover_candidate(context, time.monotonic()+20, lambda: False,
                                        SimpleNamespace(candidates=remote), torrent_receipt=receipt)
    assert result['state'] == 'candidate'
    if same_torrent:
        assert result['origin'] == 'same-torrent' and not remote_calls
        assert Path(result['file']['path']).read_bytes() == raw
        assert result['bilingual'] is True and len(calls) == 2
    else:
        assert result['origin'] == 'fixture-remote' and len(remote_calls) == 1 and len(calls) == 1
    assert all(path.read_bytes() == data for path, data in old.items())


def test_existing_matcher_compatibility_shim_still_exports_the_authoritative_functions(monkeypatch):
    from bobbi_core import torrent_subtitles
    shim = load('ce2029_legacy_matcher', ROOT / 'tests/fixtures/jacktorr-release317/subtitles.py', monkeypatch)
    assert shim.matching_chinese_sidecars is torrent_subtitles.matching_chinese_sidecars
    assert shim.fetch_candidate is torrent_subtitles.fetch_candidate
    files = [dict(id=1, path='Series S01E01.mkv', length=1000),
             dict(id=2, path='Series S01E01.chs.srt', length=100)]
    assert shim.matching_chinese_sidecars(files[0]['path'], files) == [files[1]]


def test_current_stremio_manager_uses_current_client_and_real_response_parser(tmp_path, monkeypatch):
    from bobbi_core import http_policy
    stub(monkeypatch, 'xbmc', LOGWARNING=2, LOGDEBUG=0)
    stub(monkeypatch, 'xbmcgui')
    stub(monkeypatch, 'lib.clients.stremio.protocol',
         build_resource_url=http_policy.build_resource_url,
         is_safe_http_url=http_policy.is_safe_http_url,
         request_with_safe_redirects=http_policy.request_with_safe_redirects,
         response_json=http_policy.response_json)
    stub(monkeypatch, 'lib.clients.subtitle.utils', get_language_code=lambda value: value,
         language_code_to_name=lambda value: value, slugify_title=lambda value: value,
         subtitle_language_matches=lambda *args: True)
    stub(monkeypatch, 'lib.utils.general.utils', USER_AGENT_HEADER={})
    stub(monkeypatch, 'lib.utils.kodi.settings', get_int_setting=lambda *args: 1,
         subtitle_automation_enabled=lambda: True)
    stub(monkeypatch, 'lib.utils.kodi.utils', ADDON_PROFILE_PATH=str(tmp_path),
         get_setting=lambda key, default=None: default, kodilog=lambda *args, **kwargs: None,
         translation=str)
    stub(monkeypatch, 'lib.clients.subtitle.deepl', DeepLTranslator=lambda *args: object())
    client = load('lib.clients.subtitle.opensubstremio', LIB / 'clients/subtitle/opensubstremio.py', monkeypatch)
    manager_module = load('ce2029_current_submanager', LIB / 'clients/subtitle/submanager.py', monkeypatch)
    manager = manager_module.SubtitleManager({}, lambda *args: None)
    assert isinstance(manager.opensub_client, client.OpenSubtitleStremioClient)
    rows = [dict(id='fixture', lang='zho', url='https://8.8.8.8/fixture.srt'),
            dict(id='invalid', lang='zho', url='file:///untrusted.srt')]
    requests = []
    def get(url, **options):
        requests.append((url, options))
        return SimpleNamespace(status_code=200, url=url, headers={},
                               content=json.dumps(dict(subtitles=rows)).encode())
    monkeypatch.setattr(client.requests, 'get', get)
    result = manager.opensub_client._fetch_subtitles_data_for_source(
        'https://8.8.8.8', 'tv', 'tt1234567', season=1, episode=2, max_retries=0)
    assert result == [rows[0]]
    assert len(requests) == 1 and 'tt1234567%3A1%3A2' in requests[0][0]
    assert requests[0][1]['allow_redirects'] is False
