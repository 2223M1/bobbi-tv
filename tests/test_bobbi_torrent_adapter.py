"""The signed optional resolver never depends on a retained JackTorr owner."""
import json
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit, urlencode
import xml.etree.ElementTree as ET

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'addons/plugin.video.bobbi.torrent'
for path in (ADDON / 'lib', ROOT / 'addons/script.module.bobbi.core/lib'):
    sys.path.insert(0, str(path))

from bobbi_torrent.backend import (Backend, BackendError, load_config,
    validate_backend_config, from_legacy_settings)
from bobbi_torrent.entry import execute, parse_request, failure_log
from bobbi_torrent.owner import Owner
from bobbi_torrent.resolver import Resolver, metadata_files, select_file, VIDEO

RID = 'a' * 32
HASH = '1' * 40
MAGNET = 'magnet:?xt=urn:btih:' + HASH
FILE = dict(id=2, path='Series.S01E01.1080p.mkv', length=1000000)


def config(**changes):
    return dict(dict(schema=1, endpoint='http://127.0.0.1:18090', auth=None,
        metadata_seconds=2, buffering_seconds=2), **changes)


def request(catalog=True, **changes):
    value = dict(dict(action='play_magnet', selection_policy='exact', request_id=RID,
        magnet=MAGNET, season='1', episode='1', title='Series', release_title='Series S01'), **changes)
    if catalog and 'episode_binding' not in changes:
        from episode_request_fixture import produced_request
        produced = produced_request(value['request_id'], HASH, value['season'], value['episode'],
            value['release_title'], locator=value.get('url') if value['action'] == 'play_url' else value['magnet'],
            action=value['action'])
        value['episode_binding'] = produced['episode_binding']
    return value


def status(file=None, ready=True):
    return dict(hash=HASH, name='Series S01', file_stats=[dict(file or FILE)],
        preloaded_bytes=100 if ready else 0, preload_size=100)


class Response:
    def __init__(self, value, status=200):
        self.status_code, self.raw = status, value if isinstance(value, bytes) else json.dumps(value).encode()
        self.closed = False
        self.metadata = value if isinstance(value, dict) else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def iter_content(self, chunk_size):
        yield self.raw


class Session:
    def __init__(self, replies):
        self.replies, self.calls, self.closed = list(replies), [], False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        if value.metadata.get('file_stats'):
            self.files = {f['id']:f['length'] for f in value.metadata['file_stats']}
        return value

    def close(self):
        self.closed = True

    def get(self, url, **kwargs):
        # A healthy in-memory selected file for workflow tests. Explicit HTTP
        # responses below still exercise invalid ranges and incomplete bodies.
        if '/stream/' in url and hasattr(self,'files') and not (
                self.replies and hasattr(self.replies[0], 'headers')):
            self.calls.append(('GET',url,kwargs))
            length = self.files[int(parse_qs(urlsplit(url).query)['index'][0])]
            start,end = map(int,kwargs['headers']['Range'][6:].split('-'))
            response = Response(bytes(end-start+1),206)
            response.headers = {'Content-Range':f'bytes {start}-{end}/{length}'}
            return response
        return self.request('GET', url, **kwargs)


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


class FakeOwner:
    request_id = RID

    def __init__(self, clock, selected='bt:' + HASH):
        self.clock, self.selected_identity = clock, selected
        self.cancel = False
        self.phases, self.targets, self.failures, self.bindings = [], [], [], []
        self.protocol = SimpleNamespace(resolve_torrent=self.resolve,
            validate_torrent_resolution=lambda *args: selected)

    def resolve(self, request_id, locator, info_hash, verified):
        assert request_id == RID and info_hash == verified
        return dict(selection_identity=self.selected_identity, info_hash=info_hash)

    def active(self):
        if self.cancel:
            raise BackendError('TORRENT_CANCELLED', 'cancelled')

    def wait(self, seconds):
        self.clock.now += seconds
        self.active()

    def progress(self, phase, percent=0):
        self.active()
        self.phases.append(phase)

    def selected(self, *args, **kwargs):
        self.active()
        self.targets.append((args, kwargs))

    def failure(self, category):
        self.failures.append(category)

    def bind(self, *args):
        self.active()
        self.bindings.append(args)


class Item:
    def __init__(self, **kwargs):
        self.kwargs, self.properties = kwargs, {}

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, '')

    def setMimeType(self, mime): self.mime = mime
    def setContentLookup(self, lookup): self.lookup = lookup

    def getVideoInfoTag(self):
        return SimpleNamespace(setTitle=lambda value: None, setPlot=lambda value: None)

    def setArt(self, value):
        pass


def test_config_missing_has_no_legacy_fallback(tmp_path):
    with pytest.raises(BackendError, match='TORRENT_BACKEND_NOT_CONFIGURED'):
        load_config(tmp_path / 'backend.json')


@pytest.mark.parametrize('endpoint', ['http://example.com:18090', 'http://127.0.0.1',
    'http://u:p@127.0.0.1:18090', 'http://127.0.0.1:18090/stream',
    'http://127.0.0.1:18090?key=x', 'file:///tmp/backend', 'http://127.0.0.1:0'])
def test_backend_only_explicit_loopback(endpoint):
    with pytest.raises(BackendError):
        validate_backend_config(config(endpoint=endpoint))


@pytest.mark.parametrize('key,value', [('metadata_seconds', True), ('metadata_seconds', 121),
    ('buffering_seconds', 0), ('buffering_seconds', 301), ('schema', True),
    ('auth', {'username': 'name', 'password': ''})])
def test_config_strict_bounds(key, value):
    with pytest.raises(BackendError):
        validate_backend_config(config(**{key: value}))


def test_config_migration_is_whitelist_and_does_not_mutate():
    legacy = dict(service_host='localhost', service_port='18090', ssl_connection='false',
        service_login='', service_password='', metadata_timeout='15', buffer_timeout='45',
        service_enabled='true', apply_settings_to_torrserver='true', **{'s:CacheSize': '1'})
    result = from_legacy_settings(legacy)
    assert result == config(endpoint='http://localhost:18090', metadata_seconds=15, buffering_seconds=45)
    assert legacy['service_enabled'] == 'true'
    assert not any('service_' in key for key in result)


def test_ready_uses_existing_service_read_only():
    session = Session([Response(b'MatriX.144.1')])
    backend = Backend(config(), session, Clock())
    backend.ready(lambda: None)
    assert [call[:2] for call in session.calls] == [('GET', 'http://127.0.0.1:18090/echo')]
    assert session.calls[0][2]['allow_redirects'] is False


def test_add_unknown_outcome_never_retries():
    session = Session([requests.exceptions.ReadTimeout(), requests.exceptions.ReadTimeout()])
    backend = Backend(config(), session, Clock())
    with pytest.raises(BackendError, match='TORRENT_ADD_UNCONFIRMED'):
        backend.add(HASH, MAGNET, None, 10, lambda: None)
    with pytest.raises(BackendError, match='ALREADY_ATTEMPTED'):
        backend.add(HASH, MAGNET, None, 10, lambda: None)
    assert len(session.calls) == 2
    assert session.calls[1][2]['json'] == {'action': 'get', 'hash': HASH}
    assert session.calls[0][2]['json']['save_to_db'] is False


def test_add_different_hash_is_rejected():
    backend = Backend(config(), Session([Response({'hash': '2' * 40})]), Clock())
    with pytest.raises(BackendError) as error:
        backend.add(HASH, MAGNET, None, 10, lambda: None)
    assert error.value.category == 'source_identity_mismatch'


def test_lost_add_reply_reconciles_same_hash_without_second_mutation():
    session = Session([requests.exceptions.ReadTimeout(), Response({'hash': HASH})])
    backend = Backend(config(), session, Clock())
    backend.add(HASH, MAGNET, None, 10, lambda: None)
    assert backend.add_reconciled
    assert [row[2]['json']['action'] for row in session.calls] == ['add', 'get']


def test_buffer_user_extension_does_not_resubmit_or_switch_file():
    clock = Clock()
    owner = FakeOwner(clock)
    prompts = []
    owner.wait_for_buffer = lambda detail: prompts.append(detail) or True
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status()),
        Response(b'')] + [Response(status(ready=False)) for _ in range(4)] + [Response(status())])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result['file'] == FILE and len(prompts) == 1
    assert prompts[0]['selected_file_bytes'] == FILE['length']
    assert 'ready' not in prompts[0]
    assert [row[2].get('json', {}).get('action') for row in session.calls].count('add') == 1
    assert len([row for row in session.calls if '/stream?' in row[1]]) == 1


@pytest.mark.parametrize('continue_waiting', [False, True])
def test_buffer_status_crossing_deadline_keeps_stage_and_manual_extension(continue_waiting):
    clock, prompts = Clock(), []
    class SlowStatus(Response):
        def iter_content(self, chunk_size):
            clock.now += 2.1
            yield self.raw
    owner = FakeOwner(clock)
    owner.wait_for_buffer = lambda detail: prompts.append(detail) or continue_waiting
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b''), SlowStatus(status(ready=False)), Response(status())])
    resolver = Resolver(Backend(config(), session, clock), owner, Session([]), clock)
    if continue_waiting:
        assert resolver.resolve(request())['file'] == FILE
    else:
        with pytest.raises(BackendError) as error:
            resolver.resolve(request())
        assert error.value.category == 'buffer_timeout'
        assert error.value.code == 'TORRENT_BUFFER_TIMEOUT'
    assert len(prompts) == 1
    assert sum(row[2].get('json', {}).get('action') == 'add' for row in session.calls) == 1
    assert sum('/stream?' in row[1] for row in session.calls) == 1


@pytest.mark.parametrize('body_timeout', [False, True])
def test_one_transient_readonly_buffer_poll_timeout_can_recover_without_resubmit(body_timeout):
    from urllib3.exceptions import ReadTimeoutError
    timeout = (requests.exceptions.ConnectionError(ReadTimeoutError(None, '/torrents', 'body stalled'))
               if body_timeout else requests.exceptions.ReadTimeout())
    clock, owner = Clock(), None
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b''), timeout, Response(status())])
    assert Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())['file'] == FILE
    assert sum('/stream?' in row[1] for row in session.calls) == 1
    assert clock.now <= 2


def test_readonly_buffer_poll_retry_is_not_unbounded():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b''), requests.exceptions.ReadTimeout(),
        requests.exceptions.ReadTimeout(), Response(status())])
    with pytest.raises(BackendError, match='TORRENT_HTTP_TIMEOUT'):
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert len(session.calls) == 6


def test_metadata_status_crossing_deadline_reports_metadata_timeout():
    clock = Clock()
    class SlowMetadata(Response):
        def iter_content(self, chunk_size):
            clock.now += 2.1
            yield self.raw
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       SlowMetadata(dict(hash=HASH, file_stats=[]))])
    backend = Backend(config(), session, clock)
    with pytest.raises(BackendError) as error:
        Resolver(backend, owner, Session([]), clock).resolve(request())
    assert error.value.category == 'metadata_timeout'
    assert not backend.preload_attempted


def test_no_config_or_service_is_not_a_source_retry():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([requests.exceptions.ConnectionError()])
    backend = Backend(config(), session, clock)
    with pytest.raises(BackendError, match='TORRENT_HTTP_UNAVAILABLE'):
        Resolver(backend, owner, Session([]), clock).resolve(request())
    assert len(session.calls) == 1
    assert not backend.add_attempted


def test_ready_complete_exact_episode_pipeline():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status()), Response(b''), Response(status())])
    backend = Backend(config(), session, clock)
    result = Resolver(backend, owner, Session([]), clock).resolve(request())
    assert result['file'] == FILE
    assert result['info_hash'] == HASH
    assert 'index=2' in result['url']
    assert owner.phases == ['download', 'metadata', 'buffering']
    assert owner.targets[0][0] == (HASH, FILE)
    assert len([x for x in session.calls if x[2].get('json', {}).get('action') == 'add']) == 1
    assert all(x[2]['allow_redirects'] is False for x in session.calls)


def test_http_torrent_hash_resolution_without_provider_infohash(monkeypatch):
    from bobbi_core.playback_request import digest
    clock = Clock()
    locator = 'https://example.test/chosen.torrent'
    owner = FakeOwner(clock, selected='transport:' + digest(locator))
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status()), Response(b''), Response(status())])
    monkeypatch.setattr('bobbi_torrent.resolver.resolve_http',
        lambda *args: (b'd4:infod4:name1:aee', HASH, ''))
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
        request(action='play_url', url=locator))
    assert result['info_hash'] == HASH
    assert session.calls[1][1].endswith('/torrent/upload')
    assert not session.calls[1][2].get('json')
    assert 'save' not in session.calls[1][2]['data']


def test_selected_file_cannot_change_after_buffering():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b''), Response(status(dict(FILE, length=FILE['length'] + 1)))])
    with pytest.raises(BackendError) as error:
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert error.value.category == 'selected_file_missing'


def test_wrong_episode_never_selects_first_file():
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    with pytest.raises(BackendError):
        select_file(status(), request(episode='2'), HASH, {}, p)


@pytest.mark.parametrize('file', [dict(FILE, id=True), dict(FILE, path='x\x00.mkv'),
    dict(FILE, length=-1), dict(FILE, length=True)])
def test_invalid_metadata_fails_closed(file):
    with pytest.raises(BackendError):
        metadata_files(status(file))


def test_cancel_before_add_issues_no_mutation():
    clock = Clock()
    owner = FakeOwner(clock)
    owner.cancel = True
    session = Session([])
    backend = Backend(config(), session, clock)
    with pytest.raises(BackendError) as error:
        Resolver(backend, owner, Session([]), clock).resolve(request())
    assert error.value.category == 'cancelled'
    assert not session.calls


def test_metadata_deadline_is_bounded():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH})]
        + [Response(dict(hash=HASH, file_stats=[])) for _ in range(10)])
    backend = Backend(config(), session, clock)
    with pytest.raises(BackendError) as error:
        Resolver(backend, owner, Session([]), clock).resolve(request())
    assert error.value.category == 'metadata_timeout'
    assert clock.now == 2
    assert not backend.preload_attempted


def test_preload_timeout_is_not_reissued_and_poll_can_complete():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status()),
        requests.exceptions.ReadTimeout(), Response(status())])
    backend = Backend(config(), session, clock)
    assert Resolver(backend, owner, Session([]), clock).resolve(request())['file'] == FILE
    assert len([x for x in session.calls if '/stream?' in x[1]]) == 1


def test_buffer_timeout_does_not_drop_or_remove_other_readers():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status()),
        Response(b'')] + [Response(status(ready=False)) for _ in range(10)])
    with pytest.raises(BackendError) as error:
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert error.value.category == 'buffer_timeout'
    assert all(x[2].get('json', {}).get('action') not in ('drop', 'rem', 'set') for x in session.calls)


def result_factory(backend, owner, session):
    return SimpleNamespace(resolve=lambda request: dict(info_hash=HASH, file=FILE,
        url='http://127.0.0.1:18090/stream?index=2', resolution={}))


def test_handoff_once_and_subtitles_not_on_video_path():
    owner, calls = FakeOwner(Clock()), []
    assert execute(request(), owner, None, None, Item,
        lambda *args: calls.append(args), result_factory)
    assert len(owner.bindings) == len(calls) == 1
    assert calls[0][0] is True
    assert calls[0][1].properties['no-ext-subs-scan'] == 'true'
    assert len(owner.targets) == 1


def test_uncertain_kodi_handoff_never_answers_or_plays_twice():
    owner, calls = FakeOwner(Clock()), []
    def submit(*args):
        calls.append(args)
        raise RuntimeError('lost response')
    with pytest.raises(RuntimeError):
        execute(request(), owner, None, None, Item, submit, result_factory)
    assert len(calls) == 1 and calls[0][0] is True
    assert owner.failures == ['playback_failed']


def test_pre_av_failure_reports_current_owner_and_resolves_false_once():
    owner, calls = FakeOwner(Clock()), []
    owner.cancel = True
    with pytest.raises(BackendError):
        execute(request(), owner, None, None, Item, lambda *args: calls.append(args), result_factory)
    assert owner.failures == ['cancelled']
    assert len(calls) == 1 and calls[0][0] is False
    assert not owner.bindings


def test_owner_requires_current_protocol_not_just_window_property():
    window = SimpleNamespace(getProperty=lambda key: RID if key == 'bobbi_active_player_session' else '')
    monitor = SimpleNamespace(abortRequested=lambda: False)
    def fail(*args):
        raise OSError('no native owner')
    owner = Owner(RID, SimpleNamespace(owned_state=fail), window, monitor)
    with pytest.raises(BackendError, match='OWNER_UNAVAILABLE'):
        owner.active()


def test_old_jacktook_window_property_never_grants_rights():
    window = SimpleNamespace(getProperty=lambda key: RID if key == 'jacktook_active_player_session' else '')
    owner = Owner(RID, None, window, SimpleNamespace(abortRequested=lambda: False))
    with pytest.raises(BackendError) as error:
        owner.active()
    assert error.value.category == 'superseded'


def test_failure_receipt_is_once_and_scoped_to_current_request():
    calls = []
    protocol = SimpleNamespace(owned_state=lambda rid: {'request_id': rid},
        context=lambda snapshot, rid: dict(boot_id='boot', epoch=9, request_id=rid),
        call=lambda msg: calls.append(msg) or {'recorded': True})
    owner = Owner(RID, protocol, object(), object())
    assert owner.failure('metadata_timeout') is True
    assert owner.failure('metadata_timeout') is False
    assert calls == [dict(boot_id='boot', epoch=9, request_id=RID,
        operation='resolver_failed', category='metadata_timeout')]


def test_late_failure_does_not_touch_new_owner():
    def replaced(*args):
        raise RuntimeError('selection changed')
    owner = Owner(RID, SimpleNamespace(owned_state=replaced), object(), object())
    assert owner.failure('metadata_timeout') is False


def test_entry_only_exact_current_plugin_actions():
    q = request()
    q.pop('action')
    parsed = parse_request(['plugin://plugin.video.bobbi.torrent/play_magnet', '2', '?' + urlencode(q)])
    assert parsed == request()
    with pytest.raises(BackendError):
        parse_request(['plugin://plugin.video.bobbi.torrent/play_magnet', '2',
            '?' + urlencode(dict(q, selection_policy='portable_manual'))])
    with pytest.raises(BackendError):
        parse_request(['plugin://plugin.video.bobbi.torrent/play_magnet', '2',
            '?' + urlencode(q) + '&request_id=' + RID])


def test_package_is_optional_module_without_engine_or_old_owner():
    xml = ET.parse(ADDON / 'addon.xml').getroot()
    assert xml.find("extension[@point='xbmc.service']") is None
    assert xml.find("extension[@point='xbmc.python.module']").get('library') == 'lib'
    main = ET.parse(ROOT / 'addons/plugin.video.bobbi/addon.xml').getroot()
    dependency = main.find("requires/import[@addon='plugin.video.bobbi.torrent']")
    assert dependency.get('optional') == 'true'
    code = '\n'.join(p.read_text(encoding='utf-8') for p in ADDON.rglob('*.py'))
    for forbidden in ('am6b_core', 'plugin.video.jacktook', 'subprocess', 'daemon=', 'System.Exec',
                      'InstallAddon', 'playback-control.sock', 'jacktook_active_player_session'):
        assert forbidden not in code
    assert not list(ADDON.rglob('*.so'))


def test_original_audio_hint_survives_new_child_url_and_final_claim():
    from bobbi_core.original_audio import handoff_url
    hint = dict(schema=1, request_id=RID, kind='tv', tmdb_id=100,
                language='ja', issued_at=100)
    url = 'plugin://plugin.video.bobbi.torrent/play_magnet?' + urlencode(dict(
        magnet=MAGNET, selection_policy='exact', request_id=RID))
    result = handoff_url(url, hint, RID, 101)
    assert json.loads(parse_request([result.split('?', 1)[0], '2',
        '?' + result.split('?', 1)[1]])['original_audio_hint']) == hint
    from bobbi_core.original_audio import attach
    item = Item()
    item.setProperty('bobitv.request_id', RID)
    item.setProperty('bobitv.file_identity', 'bt:' + HASH + '|file')
    assert attach(item, hint, dict(request_id=RID, file_identity='bt:' + HASH + '|file'),
                  'http://127.0.0.1:18090/stream', 101)
    assert item.getProperty('bobitv.original_audio.language') == 'ja'


def test_owner_registers_same_torrent_subtitles_only_after_claim():
    events = []
    window = SimpleNamespace(getProperty=lambda key: RID if key == 'bobbi_active_player_session' else '')
    context = dict(boot_id='boot', epoch=1, request_id=RID, file_identity='bt:' + HASH + '|file')
    protocol = SimpleNamespace(owned_state=lambda rid: {},
        resolved_torrent_file_identity=lambda *args: context['file_identity'],
        bind_and_claim=lambda *args, **kwargs: events.append('claim') or context,
        call=lambda msg: events.append(msg) or {'registered': True})
    owner = Owner(RID, protocol, window, SimpleNamespace(abortRequested=lambda: False))
    owner.bind(Item(), HASH, FILE, 'http://127.0.0.1:18090/stream', {})
    assert events[0] == 'claim'
    assert events[1] == dict(boot_id='boot', epoch=1, request_id=RID,
        operation='torrent_subtitle_context', torrent=dict(info_hash=HASH, file=FILE))


def test_transport_catalog_binding_selects_correct_anime_episode():
    from bobbi_core.episode_identity import bind_transport_episode
    from bobbi_core.playback_request import digest
    locator = 'https://example.test/pack.torrent'
    identity = 'transport:' + digest(locator)
    binding = bind_transport_episode({'tmdb_id': '67710'}, {'season': 1, 'episode': 1},
        RID, identity, locator, catalog={'tmdb_id': 67710,
            'aliases': ['Flip Flappers', 'フリップフラッパーズ'], 'year': 2016})
    file = dict(FILE, path='[SweetSub&LoliHouse] Flip Flappers - 01 [BDRip 1080p HEVC].mkv')
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: identity)
    q = request(episode_binding=json.dumps(binding, ensure_ascii=False), release_title='Flip Flappers S01')
    assert select_file(dict(status(file), name='Flip Flappers S01'), q, HASH, {}, p) == file


@pytest.mark.parametrize('cancel_call', [2, 3, 4, 5])
def test_cancel_at_every_network_boundary_cannot_bind_or_readd(cancel_call):
    clock, calls = Clock(), []
    owner = FakeOwner(clock)
    class CancelSession(Session):
        def request(self, *args, **kwargs):
            result = super().request(*args, **kwargs)
            if len(self.calls) == cancel_call:
                owner.cancel = True
            return result
    session = CancelSession([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b''), Response(status())])
    backend = Backend(config(), session, clock)
    def factory(b, o, s):
        return Resolver(b, o, s, clock)
    with pytest.raises(BackendError) as error:
        execute(request(), owner, backend, Session([]), Item, lambda *args: calls.append(args), factory)
    assert error.value.category == 'cancelled'
    assert owner.failures == ['cancelled']
    assert not owner.bindings
    assert len(calls) == 1 and calls[0][0] is False
    assert len([x for x in session.calls if x[2].get('json', {}).get('action') == 'add']) <= 1


def producer(monkeypatch, available=True):
    """Execute the actual producer function without unrelated Kodi UI imports."""
    from urllib.parse import quote
    from typing import Optional, Dict, Any
    source = ROOT / 'addons/plugin.video.bobbi/lib/utils/player/utils.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_jacktorr_url')
    namespace = dict(Optional=Optional, Dict=Dict, Any=Any, json=json, quote=quote,
        kodilog=lambda *args, **kwargs: None, LOGDEBUG=0,
        summarize_locator_for_log=lambda value: '[locator]',
        is_bobbi_torrent_addon=lambda: available,
        _jacktorr_movie_binding=lambda data, *, playback_client=None: '',
        _save_jacktorr_playback_metadata=lambda *args: None,
        _get_jacktorr_category=lambda value: 'movie', TorrentException=RuntimeError)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    monkeypatch.setattr('bobbi_torrent.backend.load_config', lambda: config())
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.episode_order',
        SimpleNamespace(selected_release_binding=lambda *args: None))
    return namespace['get_jacktorr_url']


def test_actual_producer_emits_current_adapter_and_no_old_handle(monkeypatch):
    make = producer(monkeypatch)
    data = dict(selection_policy='exact', request_id=RID, mode='movies', title='Movie')
    result = make(MAGNET, '', data)
    assert result.startswith('plugin://plugin.video.bobbi.torrent/play_magnet?')
    assert parse_request([result.split('?', 1)[0], '5', '?' + result.split('?', 1)[1]])['request_id'] == RID


def test_producer_uninstalled_or_disabled_adapter_fails_before_launch(monkeypatch):
    make = producer(monkeypatch, available=False)
    with pytest.raises(RuntimeError, match='BT 组件未安装或已禁用'):
        make(MAGNET, '', dict(selection_policy='exact'))


def test_producer_missing_backend_fails_before_launch(monkeypatch):
    make = producer(monkeypatch)
    def missing():
        raise BackendError('TORRENT_BACKEND_NOT_CONFIGURED')
    monkeypatch.setattr('bobbi_torrent.backend.load_config', missing)
    with pytest.raises(RuntimeError, match='尚未连接 BT 后台'):
        make(MAGNET, '', dict(selection_policy='exact'))


def test_producer_stock_request_is_not_given_exact_native_rights(monkeypatch):
    with pytest.raises(RuntimeError, match='请返回选源页，重新选择此 BT 片源'):
        producer(monkeypatch)(MAGNET, '', dict(selection_policy='portable_manual'))


def test_parent_budget_is_read_from_same_new_backend(monkeypatch):
    source = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    function = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == '_startup_timeout_seconds')
    from urllib.parse import urlsplit
    namespace = dict(urlsplit=urlsplit, PLAYBACK_START_TIMEOUT_SECONDS=45)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    monkeypatch.setattr('bobbi_torrent.backend.load_config', lambda: config(metadata_seconds=15, buffering_seconds=45))
    player = SimpleNamespace(data=dict(selection_policy='exact', is_torrent=True),
        url='plugin://plugin.video.bobbi.torrent/play_magnet')
    assert namespace['_startup_timeout_seconds'](player) == 30 + 30 + 30 + 45 + 30 + 60 + 45 + 135


def test_shared_subtitle_connection_uses_only_new_config(monkeypatch):
    from bobbi_torrent.backend import subtitle_connection
    monkeypatch.setattr('bobbi_torrent.backend.load_config', lambda: config(
        auth=dict(username='test-user', password='test-secret')))
    assert subtitle_connection() == ('http://127.0.0.1:18090', ('test-user', 'test-secret'))
    source = (ROOT / 'addons/plugin.video.bobbi/lib/services/subtitle_fallback.py').read_text(encoding='utf-8')
    assert "Addon('plugin.video.jacktorr')" not in source
    assert 'from bobbi_torrent.backend import subtitle_connection' in source


def native_method(name, namespace=None):
    source = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {} if namespace is None else namespace
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace[name]


def test_exact_audio_does_not_override_native_or_manual_selection():
    calls = []
    method = native_method('select_audio_stream', dict(get_setting=lambda key: calls.append(key) or True,
        sleep=lambda amount: calls.append(amount)))
    method(SimpleNamespace(data=dict(selection_policy='exact')))
    assert calls == []


def recovery_snapshot(**changes):
    return dict(boot_id='boot', epoch=4, desired=dict(dict(request_id=RID, epoch=4,
        selection_identity='bt:' + HASH, file_identity='bt:' + HASH + '|file',
        file_bound=True, start_claimed=True, cancelled=True), **changes))


def recovery_test(monkeypatch, snapshot, verifier=None):
    queries = []
    protocol = SimpleNamespace(call=lambda message: snapshot,
        startup_failure=lambda query: queries.append(dict(query)) or (verifier(query) if verifier else {'receipt': True}))
    player = SimpleNamespace(playback_client=protocol,
        _owner_context=dict(boot_id='boot', epoch=4, request_id=RID))
    original = dict(player._owner_context)
    result = native_method('_read_startup_failure')(player)
    assert player._owner_context == original
    return result, queries


def test_child_bound_failure_can_query_existing_exact_receipt_without_control(monkeypatch):
    result, queries = recovery_test(monkeypatch, recovery_snapshot())
    assert result == {'receipt': True}
    assert queries == [dict(boot_id='boot', epoch=4, request_id=RID, file_identity='bt:' + HASH + '|file')]


@pytest.mark.parametrize('where,key,value', [('root', 'boot_id', 'other'), ('root', 'epoch', 5),
    ('desired', 'epoch', 5), ('desired', 'request_id', 'b' * 32), ('desired', 'file_bound', False),
    ('desired', 'start_claimed', False), ('desired', 'file_identity', 'other-file')])
def test_failure_context_cannot_be_taken_from_unrelated_or_unbound_request(monkeypatch, where, key, value):
    snapshot = recovery_snapshot()
    (snapshot if where == 'root' else snapshot['desired'])[key] = value
    result, queries = recovery_test(monkeypatch, snapshot)
    assert result is None and not queries


def test_failure_snapshot_does_not_bypass_final_receipt_rejection(monkeypatch):
    result, queries = recovery_test(monkeypatch, recovery_snapshot(), verifier=lambda query: None)
    assert result is None and len(queries) == 1


def test_exact_failure_recovery_keeps_final_native_preav_gate(monkeypatch):
    """The helper still uses the shared receipt parser, not its own fake success."""
    from bobbi_core import playback_request
    context = dict(boot_id='boot', epoch=4, request_id=RID, file_identity='bt:' + HASH + '|file')
    reply = dict(failed=True, receipt=dict(context, native_instance='native-instance'))
    protocol = playback_request.Client(lambda message: reply)
    result, _ = recovery_test(monkeypatch, recovery_snapshot(), verifier=protocol.startup_failure)
    assert result == reply['receipt']
    reply['receipt']['file_identity'] = 'different'
    result, _ = recovery_test(monkeypatch, recovery_snapshot(), verifier=protocol.startup_failure)
    assert result is None


def test_short_video_does_not_wait_for_impossible_configured_preload():
    clock, owner = Clock(), None
    owner = FakeOwner(clock)
    short = dict(FILE, length=80)
    metadata = status(short)
    metadata.update(preloaded_bytes=80, preload_size=100)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(metadata), Response(b''), Response(metadata)])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result['file'] == short
    assert clock.now == 0
    # Resolver did not fabricate any native AV evidence from torrent cache size.
    assert 'av_started' not in result


def test_base32_transport_dimension_pack_pipeline_is_exact_and_unchanged_quality():
    """Synthetic fixture for the observed source shape, not its missing file_stats."""
    import base64
    from bobbi_core.episode_identity import bind_transport_episode
    from bobbi_core.playback_request import digest
    clock = Clock()
    magnet = 'magnet:?xt=urn:btih:' + base64.b32encode(bytes.fromhex(HASH)).decode()
    identity = 'transport:' + digest(magnet)
    proof = bind_transport_episode({'tmdb_id': '68272'}, {'season': 1, 'episode': 1},
        RID, identity, magnet, catalog={'tmdb_id': 68272, 'aliases': ['Flip Flappers'], 'year': 2016})
    target = dict(FILE, path='[Group] Flip Flappers - 01 [WebRip 1920x1080 HEVC AAC].mkv')
    other = dict(target, id=3, path=target['path'].replace(' - 01 ', ' - 02 '))
    metadata = dict(status(target), name='Flip Flappers [01-13]', file_stats=[other, target])
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(metadata), Response(b''), Response(metadata)])
    owner = FakeOwner(clock, selected=identity)
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
        request(magnet=magnet, episode_binding=json.dumps(proof), release_title='Flip Flappers [01-13]'))
    assert result['file'] == target
    assert 'index=2' in result['url']
    assert [c[2].get('json', {}).get('action') for c in session.calls].count('add') == 1
    assert len([c for c in session.calls if '/stream?' in c[1]]) == 1


def test_failure_log_has_closed_schema_and_never_exception_or_provider_text():
    error = BackendError('TORRENT_EXACT_FILE_UNRESOLVED', 'target_unresolved', dict(
        stage='selector', file_count=13, candidate_count=13, metadata_polls=1,
        binding_present=True, path='private-video-name', endpoint='http://secret:password@host'))
    text = failure_log(error, RID)
    detail = json.loads(text.split(' detail=', 1)[1])
    assert detail == dict(request_id=RID, failure_domain='file_selection', stage='selector', file_count=13,
        candidate_count=13, metadata_polls=1, binding_present=True)
    assert 'private-video' not in text and 'password' not in text and 'secret' not in text
    invalid = BackendError('url-and-secret', diagnostic=dict(stage='http://secret',
        file_count=True, candidate_count='password', metadata_polls=999999))
    assert failure_log(invalid, 'private-user') == '[BOBBI-TORRENT] reason=TORRENT_RESOLVER_FAILED detail={}'
    assert 'secret' not in failure_log(RuntimeError('secret'))


def test_filename_identity_failure_is_not_mislabeled_as_binding_schema():
    from bobbi_core.episode_identity import bind_transport_episode
    from bobbi_core.playback_request import digest
    locator = 'https://example.test/pack.torrent'
    identity = 'transport:' + digest(locator)
    proof = bind_transport_episode({'tmdb_id': '68272'}, {'season': 1, 'episode': 1},
        RID, identity, locator, catalog={'tmdb_id': 68272, 'aliases': ['Flip Flappers'], 'year': 2016})
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: identity)
    with pytest.raises(BackendError) as result:
        select_file(status(), request(episode_binding=json.dumps(proof)), HASH, {}, p)
    assert result.value.category == 'target_unresolved'
    assert result.value.diagnostic['stage'] == 'filename_identity'
    assert result.value.diagnostic['candidate_count'] == 1


def test_binding_failure_and_selector_failure_are_distinct():
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    with pytest.raises(BackendError) as malformed:
        select_file(status(), request(episode_binding='{'), HASH, {}, p)
    assert malformed.value.category == 'invalid_binding'
    assert malformed.value.diagnostic['stage'] == 'binding'
    with pytest.raises(BackendError) as missing:
        select_file(status(), request(episode='2'), HASH, {}, p)
    assert missing.value.category == 'target_unresolved'
    assert missing.value.diagnostic['stage'] == 'selector'


def test_metadata_timeout_has_bounded_poll_diagnostic_without_selecting():
    clock, session = Clock(), Session([Response(b'MatriX.144.1'), Response({'hash': HASH})]
        + [Response(dict(hash=HASH, file_stats=[])) for _ in range(4)])
    owner = FakeOwner(clock)
    with pytest.raises(BackendError) as result:
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result.value.diagnostic == dict(stage='metadata', metadata_polls=4, elapsed_ms=2000,
        stage_ms=dict(backend=0, download=0, add=0, metadata=2000))
    assert not owner.targets and not owner.bindings


@pytest.mark.parametrize('extension', VIDEO)
def test_upstream_single_file_video_formats_remain_selectable(extension):
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    target = dict(FILE, path='Series.S01E01' + extension.upper())
    assert select_file(status(target), request(), HASH, {}, p) == target


@pytest.mark.parametrize('extension', ['.001', '.iso', '.img', '.nrg', '.udf', '.bin', '.dat',
    '.bdm', '.bdmv', '.mpl', '.mpls', '.asx', '.m3u8', '.sdp', '.avs', '.srt', '.nfo'])
def test_disc_indexes_playlists_and_scripts_are_not_single_file_video(extension):
    p = SimpleNamespace(validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    with pytest.raises(BackendError) as result:
        select_file(status(dict(FILE, path='Series.S01E01' + extension)), request(), HASH, {}, p)
    assert result.value.category == 'no_candidate'


@pytest.mark.parametrize('code,span,size,works', [
    (206, 'bytes 0-999999/1000000', 1000000, True),
    (200, 'bytes 0-999999/1000000', 1000000, False),
    (206, 'bytes 0-999999/1000001', 1000000, False),
    (206, 'bytes 0-999999/1000000', 40000, False),
])
def test_partial_torrent_checks_the_selected_file_bytes(code, span, size, works):
    response = Response(b'x'*size, code)
    response.headers = {'Content-Range': span}
    session = Session([response])
    backend = Backend(config(auth={'username': 'box', 'password': 'test'}), session, Clock())
    assert backend.opening_readable(HASH, FILE, 10, lambda: None) is works
    method, url, options = session.calls[0]
    assert method == 'GET' and url == backend.stream_url(HASH, FILE)
    assert options['headers']['Range'] == 'bytes=0-999999' and 'auth' not in options
    assert not options['allow_redirects'] and response.closed


def test_large_selected_file_uses_one_reader_per_span_and_rechecks_identity():
    import time
    from bobbi_torrent.opening import ranges
    clock, row = Clock(), dict(FILE, length=600_000_000)
    owner = FakeOwner(clock)
    owner.wait = lambda seconds: time.sleep(.005)
    owner.cache_chunk_size = lambda: 4*1024**2
    partial = dict(status(row), preloaded_bytes=1, preload_size=32_212_254)
    control = Session([Response(b'MatriX.144.1'),Response({'hash':HASH})]+[Response(partial)]*10)
    media = Session([])
    media.files = {row['id']:row['length']}
    backend = Backend(config(),control,clock,media_session_factory=lambda:media)
    result = Resolver(backend,owner,Session([]),clock).resolve(request())
    assert result['file'] == row and result['file_evidence'] == 'AUTO_VERIFIED_FILE'
    assert [call[2]['headers']['Range'] for call in media.calls] == [
        'bytes=%d-%d' % span for span in ranges(row['length'],4*1024**2)]
    assert len(media.calls)==2 and len({c[1] for c in media.calls})==1
    assert all(c[1]==result['url'] and not c[2]['allow_redirects'] and 'auth' not in c[2] for c in media.calls)
    assert media.closed and not backend.preload_attempted and control.calls[-1][2]['json']['action']=='get'

def test_kodi_seek_span_covers_configured_chunk_and_reads_short_files_once():
    from bobbi_torrent.opening import MIB, PREFIX, ranges
    length = 655703121
    assert ranges(length,4*MIB)[0] == (length-4*MIB,length-1)
    assert ranges(length,524288)[0][0] <= length-524288
    assert ranges(1024,524288) == ((0,1023),)
    assert ranges(length,False)[1] == (0,PREFIX-1)


@pytest.mark.parametrize('finish', ['back','invalid-range','file-changed'])
def test_complete_swarm_counter_cannot_release_unreadable_or_replaced_file(finish):
    """Real HTTP headers held back while global preload reports 100 percent."""
    import time
    from threading import Event, Thread
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from bobbi_torrent.opening import MIB
    requested, allow, closed = Event(), Event(), Event()
    calls = []
    length = 655703121
    row = dict(FILE,length=length)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self):
            a,b = map(int,self.headers['Range'][6:].split('-'))
            calls.append((a,b,self.headers.get('Authorization')))
            requested.set()
            try:
                allow.wait(3)
                if finish=='back':return
                self.send_response(206)
                self.send_header('Content-Range',f'bytes {a}-{b}/{length+(finish=="invalid-range")}')
                self.send_header('Content-Length',str(b-a+1));self.end_headers()
                block = bytes(65536)
                for pos in range(a,b+1,len(block)):
                    self.wfile.write(block[:min(len(block),b+1-pos)])
            except OSError: pass
            finally:closed.set()
    with ThreadingHTTPServer(('127.0.0.1',0), Handler) as server:
        service=Thread(target=server.serve_forever,kwargs={'poll_interval':.05});service.start()
        try:
            cfg=config(endpoint='http://127.0.0.1:'+str(server.server_port),auth={'username':'control','password':'private'})
            backend=Backend(cfg)
            owner=FakeOwner(Clock())
            owner.cache_chunk_size=lambda:2*MIB
            owner.wait=lambda seconds: time.sleep(.005)
            def active():
                if requested.is_set() and finish=='back':
                    raise BackendError('TORRENT_CANCELLED','cancelled')
            owner.active=active
            owner.progress=lambda *args: (requested.wait(.2),allow.set()) if finish!='back' else None
            def state(*_):
                return status(dict(row,length=length+1)) if finish=='file-changed' and len(calls)==2 else status(row)
            backend.status=state
            resolver=Resolver(backend,owner,Session([]))
            with pytest.raises(BackendError) as ex:
                resolver._seekable_opening(HASH,row,time.monotonic()+2,lambda *_:None)
            assert ex.value.code == {'back':'TORRENT_CANCELLED','invalid-range':'TORRENT_OPENING_RANGE_INVALID',
                                     'file-changed':'TORRENT_SELECTED_FILE_CHANGED'}[finish]
            assert requested.is_set() and len(calls)==(2 if finish=='file-changed' else 1)
            assert all(auth is None for _,_,auth in calls)
            assert not any(t.name=='bobbi-selected-file-opening' for t in __import__('threading').enumerate())
        finally:
            allow.set();server.shutdown();service.join()

def _mkv_duration_header(seconds):
    import struct
    def elt(tag, data):
        return bytes.fromhex(tag) + bytes([128+len(data)]) + data
    info = elt('1549a966',elt('2ad7b1',bytes.fromhex('0f4240')) +
               elt('4489',struct.pack('>d',seconds*1000)))
    return elt('1a45dfa3',elt('4282',b'matroska')) + bytes.fromhex('18538067ff') + info


def test_optional_duration_cannot_require_new_network_reads_or_guess_missing_metadata():
    from bobbi_torrent.opening import duration_hint, extra_prefix, MIB
    h = _mkv_duration_header(1602.7)
    assert duration_hint(h) == pytest.approx(1602.7)
    for invalid in (b'',h[:-1],b'x'+h,_mkv_duration_header(float('nan')),_mkv_duration_header(0)):
        assert duration_hint(invalid) is None
    for duration, rate, remaining in ((None,100000,200),(1500,900000,100),(1500,100,200),(1500,100000,12)):
        assert extra_prefix(1255184472,duration,rate,remaining,1254135896)==0


@pytest.mark.parametrize('consented,fast,expect_extra',[(False,False,True),(True,True,False),(True,False,True)])
def test_only_a_measured_slow_file_reads_an_adjacent_runway(consented,fast,expect_extra):
    from bobbi_torrent.opening import SelectedOpening, MIB, PREFIX
    import time
    length = 1255184472
    clock = Clock()
    calls = []
    class Media(Session):
        def get(self,url,**options):
            start,end = map(int,options['headers']['Range'][6:].split('-'))
            calls.append((start,end))
            class Chunk(Response):
                def iter_content(self,chunk_size):
                    header = _mkv_duration_header(1602.7) if start==0 else b''
                    for pos in range(start,end+1,chunk_size):
                        size = min(chunk_size,end+1-pos)
                        yield (header+bytes(size-len(header))) if pos==start else bytes(size)
                        clock.now += size/(4*MIB if fast else .22*MIB)
            v=Chunk(b'',206);v.headers={'Content-Range':f'bytes {start}-{end}/{length}'}
            return v
    media=Media([])
    opening=SelectedOpening('http://127.0.0.1:8090/stream/selected.mkv',length,524288,390,lambda:media,clock)
    if consented:opening.continued(360)
    with opening:
        assert opening.done.wait(2)
        completed,verified,target,base_ready=opening.snapshot()
    assert completed and base_ready and verified==target and media.closed
    assert len(calls)==(3 if expect_extra else 2)
    if expect_extra:
        assert calls[2][0]==PREFIX and calls[1][1]+1==calls[2][0]
        assert calls[2][1]<calls[0][0] and 12*MIB<verified<=65*MIB

def test_skin_parity_does_not_count_a_different_copy_or_a_stalled_clock(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('parity',ROOT/'tools/check_bt_playback_parity.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    def save(name,data):
        (tmp_path/name).write_text(json.dumps(data),encoding='utf8')
    samples = [dict(at=t,s=t,w=1920,h=1080,actual=True,exact_file=True,speed=1,window=12005) for t in range(61)]
    # Stall in the middle; two snippets from the same file cannot be added together.
    stalled = [dict(r,s=min(r['s'],10) if r['at']<50 else r['s']-40) for r in samples]
    assert gate.contiguous(stalled)==10 and gate.contiguous(samples)==60
    cold='cold.json'; product='product.json'
    save(cold,{'exact_torrent_absent':True})
    save(product,dict(case='one',windows=[[0,12005]],file_fingerprint='a'*64,av=samples,target=dict(id=4,bytes=655703121),file_dialogs=0,slow_waits=0))
    views=[]
    for skin in ('skin.bobbi.cinema','skin.arctic.fuse.3'):
        name=skin+'.json';views.append(dict(skin=skin,receipt=name))
        save(name,dict(case='one',skin=skin,file_fingerprint=('a' if skin=='skin.bobbi.cinema' else 'b')*64,file_id=4,
                       bytes=655703121,trigger='remote Select',cache='warm',observations=samples))
    m=tmp_path/'cases.json'
    save(m.name,{'cases':[dict(name='one',product=product,cold_before=cold,file_dialogs=0,views=views)]})
    with pytest.raises(ValueError,match='same file'):
        gate.evaluate(m)

    # Correct the identity; stalls on the household skin expose a reference-only success.
    for skin, playback in (('skin.bobbi.cinema',stalled),('skin.arctic.fuse.3',samples)):
        receipt = json.loads((tmp_path/(skin+'.json')).read_text(encoding='utf8'))
        receipt.update(file_fingerprint='a'*64,observations=playback)
        save(skin+'.json',receipt)
    grade = gate.evaluate(m)['one']
    assert grade['reference_opens_household_does_not'] and not grade['same_path_parity_passed']
    assert grade['cold_start_passed'] and grade['cold_endurance_passed']
    valid_case = json.loads(m.read_text(encoding='utf8'))['cases'][0]
    save(m.name,{'cases':[dict(valid_case,name='lost',product='absent.json'),valid_case]})
    result = gate.evaluate(m,report_incomplete=True)
    assert result['lost']=={'incomplete':'Missing receipt: absent.json'} and result['one']==grade
    save(m.name,{'cases':[dict(valid_case,views=[views[1]])]})
    with pytest.raises(ValueError,match='household skin'):
        gate.evaluate(m)


    # No AV from the public flow is an actionable failure if selection and the reference really match.
    save(m.name,{'cases':[dict(valid_case,selected='selected.json')]})
    save('selected.json',dict(id=4,bytes=655703121,file_fingerprint='a'*64,matched_active_request=True))
    save(product,dict(case='one',target={},av=[],windows=[[0,13001]],file_dialogs=0,slow_waits=1))
    cold_failure = gate.evaluate(m)['one']
    assert cold_failure['cold_first_confirmed_fullscreen_wall_s'] is None
    assert cold_failure['reference_opens_product_does_not'] and not cold_failure['cold_start_passed']


def test_first_buffer_deadline_still_requires_the_user_even_when_extra_prefix_is_loading():
    clock=Clock();owner=FakeOwner(clock)
    prompts=[]
    owner.wait_for_buffer=lambda detail:prompts.append(detail) or False
    class Opening:
        closed=False
        def __enter__(self):return self
        def __exit__(self,*_):self.closed=True
        def snapshot(self):
            # Core head and tail were verified; only the adjacent extra span is in flight.
            return False,13*1024**2,40*1024**2,True
        def continued(self,*_):pytest.fail('A timed-out or declined prompt must never extend buffering')
    opened=Opening()
    row=dict(FILE,length=600000000)
    backend=SimpleNamespace(config=config(buffering_seconds=2),selected_opening=lambda *_:opened,
                            status=lambda *_:status(row))
    resolver=Resolver(backend,owner,Session([]),clock)
    with pytest.raises(BackendError,match='TORRENT_BUFFER_TIMEOUT'):
        resolver._seekable_opening(HASH,row,2,lambda *_:None)
    assert len(prompts)==1 and opened.closed and clock.now==2 and not owner.bindings
