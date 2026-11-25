"""Exercise actual subtitle callers against bounded, locally controlled peers."""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event, Thread
import time
from types import ModuleType

import pytest

from bobbi_core import http_policy


@pytest.fixture
def client_module(tmp_path, monkeypatch):
    def stub(name, **attrs):
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)

    stub('xbmc', LOGWARNING=2, LOGDEBUG=0, LOGINFO=1)
    stub('xbmcgui')
    stub('lib.clients.stremio.protocol', build_resource_url=http_policy.build_resource_url,
         is_safe_http_url=http_policy.is_safe_http_url,
         request_with_safe_redirects=http_policy.request_with_safe_redirects,
         response_json=http_policy.response_json)
    stub('lib.clients.subtitle.utils', get_language_code=lambda value: value,
         language_code_to_name=lambda value: value, slugify_title=lambda value: value,
         subtitle_language_matches=lambda *args: True)
    stub('lib.utils.general.utils', USER_AGENT_HEADER={})
    stub('lib.utils.kodi.settings', get_int_setting=lambda *args: 1,
         subtitle_automation_enabled=lambda: True)
    stub('lib.utils.kodi.utils', ADDON_PROFILE_PATH=str(tmp_path),
         get_setting=lambda key, default=None: default, kodilog=lambda *args, **kwargs: None,
         translation=str)
    source = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/clients/subtitle/opensubstremio.py'
    spec = importlib.util.spec_from_file_location('_round2_subtitle_client', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Only network destination policy is substituted: every request, response
    # parser, deadline and tempfile publication path remains production code.
    monkeypatch.setattr(module, 'is_safe_http_url',
        lambda url, **_kw: isinstance(url, str) and url.startswith('http://127.0.0.1:'))
    return module


@pytest.fixture
def peer():
    done = Event()
    seen = []
    subtitle = '1\n00:00:01,000 --> 00:00:02,000\n测试字幕\n'.encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            seen.append(self.path)
            mode = self.path.split('/')[1]
            body = json.dumps({'subtitles': []}).encode() if 'subtitles/' in self.path else subtitle
            try:
                if mode == 'headers':
                    raw = b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body
                    for byte in raw:
                        if done.wait(.025):
                            return
                        self.connection.sendall(bytes([byte]))
                    return
                if mode == 'retry':
                    self.send_response(503)
                    self.send_header('Retry-After', '5')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                self.send_response(200)
                if mode == 'bomb':
                    body = b'x' * 20000
                if mode in ('gzip', 'bomb'):
                    body = gzip.compress(body)
                    self.send_header('Content-Encoding', 'gzip')
                if mode == 'chunked':
                    self.send_header('Transfer-Encoding', 'chunked')
                else:
                    self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if mode == 'chunked':
                    for byte in b'1;slowextension=abcdefghijklmnopqrstuvwxyz\r\n':
                        if done.wait(.025):
                            return
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                    self.wfile.write(b'x\r\n0\r\n\r\n')
                elif mode == 'body':
                    for byte in body:
                        if done.wait(.025):
                            return
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except OSError:
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield 'http://127.0.0.1:%d' % server.server_port, seen, subtitle
    done.set()
    server.shutdown()
    server.server_close()
    worker.join(1)


@pytest.mark.parametrize('mode', ['headers', 'body', 'chunked'])
def test_catalog_client_deadline_covers_headers_body_and_chunk_framing(client_module, peer, mode):
    base, _seen, _subtitle = peer
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    started = time.monotonic()
    assert client._fetch_subtitles_data_for_source(base + '/' + mode, 'movie', 'tt1',
                                                  timeout=.15, max_retries=0) is None
    assert time.monotonic() - started < .6


@pytest.mark.parametrize('mode', ['headers', 'body', 'chunked', 'retry'])
def test_download_deadline_covers_socket_and_retry_wait_preserving_existing_file(client_module, peer, tmp_path, mode):
    base, seen, _subtitle = peer
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    destination = tmp_path / 'Subtitle No.0.Movie.zh.srt'
    destination.write_bytes(b'previous valid subtitle')
    started = time.monotonic()
    with pytest.raises(client_module.SubtitleDownloadStopped):
        client.download_subtitle({'url': base + '/' + mode + '/file.srt', 'lang': 'zh'},
            0, 'tt1', 'Movie', folder_path=str(tmp_path), timeout=2, deadline=started + .15)
    assert time.monotonic() - started < .6
    assert destination.read_bytes() == b'previous valid subtitle'
    assert not list(tmp_path.glob('*.part'))
    assert len(seen) == 1


def test_download_cancel_interrupts_headers(client_module, peer, tmp_path):
    base, _seen, _subtitle = peer
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    started = time.monotonic()
    with pytest.raises(client_module.SubtitleDownloadStopped):
        client.download_subtitle({'url': base + '/headers/file.srt', 'lang': 'zh'},
            0, 'tt1', 'Movie', folder_path=str(tmp_path), timeout=2, deadline=started + 2,
            cancelled=lambda: time.monotonic() - started > .1)
    assert time.monotonic() - started < .6
    assert not list(tmp_path.glob('*.srt'))
    assert not list(tmp_path.glob('*.part'))


def test_download_real_gzip_and_decoded_cap(client_module, peer, tmp_path, monkeypatch):
    base, _seen, subtitle = peer
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    record = {'url': base + '/gzip/file.srt', 'lang': 'zh'}
    result = client.download_subtitle(record, 0, 'tt1', 'Movie', folder_path=str(tmp_path), timeout=2)
    assert Path(result).read_bytes() == subtitle
    monkeypatch.setattr(client_module, 'MAX_SUBTITLE_BYTES', 200)
    with pytest.raises(ValueError):
        client.download_subtitle(dict(record, url=base + '/bomb/file.srt'),
                                 0, 'tt1', 'Movie', folder_path=str(tmp_path), timeout=2)
    assert Path(result).read_bytes() == subtitle
    assert not list(tmp_path.glob('*.part'))


def test_confirmed_empty_subtitle_catalog_remains_success(client_module, peer):
    base, seen, _subtitle = peer
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    assert client._fetch_subtitles_data_for_source(base + '/normal', 'movie', 'tt1',
                                                  timeout=1, max_retries=0) == []
    assert len(seen) == 1


def test_records_do_not_resolve_dns_but_download_checks_actual_destination(client_module, peer, monkeypatch, tmp_path):
    import socket
    base, seen, _subtitle = peer
    port = int(base.rsplit(':', 1)[1])
    calls = []

    def private_dns(*args):
        calls.append(args)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', port))]

    monkeypatch.setattr(client_module, 'is_safe_http_url', http_policy.is_safe_http_url)
    monkeypatch.setattr(http_policy.socket, 'getaddrinfo', private_dns)
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    record = {'url': 'http://private.invalid:%d/file.srt' % port, 'lang': 'zh'}
    assert client._valid_subtitle_record(record)
    assert not calls
    with pytest.raises(ValueError):
        client.download_subtitle(record, 0, 'tt1', 'Movie', folder_path=str(tmp_path),
                                 timeout=1, max_retries=0)
    assert calls and not seen
    assert not list(tmp_path.glob('*.srt'))


def test_automatic_query_cancels_active_pool_work_at_shared_deadline(client_module, peer, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    base, seen, _subtitle = peer
    executors = []

    def executor(*args, **kwargs):
        created = ThreadPoolExecutor(*args, **kwargs)
        executors.append(created)
        return created

    monkeypatch.setattr(client_module, 'ThreadPoolExecutor', executor)
    monkeypatch.setattr(client_module, 'AUTO_SELECT_ENDPOINT_TIMEOUT', .15)
    client = client_module.OpenSubtitleStremioClient(lambda *_: None)
    try:
        started = time.monotonic()
        client._query_and_merge_subtitle_sources(
            [(str(i), base + '/headers', str(i)) for i in range(8)],
            'movie', 'tt1', None, None, True,
        )
        assert time.monotonic() - started < .6
        for worker in executors[0]._threads:
            worker.join(.3)
            assert not worker.is_alive()
        assert 1 <= len(seen) <= 4
    finally:
        for owned in executors:
            owned.shutdown(wait=True, cancel_futures=True)
