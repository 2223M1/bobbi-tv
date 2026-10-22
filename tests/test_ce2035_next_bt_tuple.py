"""Service-proved next BT files remain exact through the real plugin boundary."""
import json
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from test_bobbi_torrent_adapter import (
    Backend, BackendError, Clock, FakeOwner, FILE, HASH, MAGNET, RID,
    Resolver, Response, Session, config, parse_request, producer, request,
    select_file, status,
)


def selected(**changes):
    return dict(dict(source_info_hash=HASH, torrent_file_id=FILE['id'],
                     torrent_path=FILE['path'], torrent_file_bytes=FILE['length']), **changes)


def parsed(raw):
    query = request(expected_file=raw)
    query.pop('action')
    return parse_request(['plugin://plugin.video.bobbi.torrent/play_magnet', '2',
                          '?' + urlencode(query)])


def test_service_proved_tuple_survives_actual_producer_and_plugin_parser(monkeypatch):
    make = producer(monkeypatch)
    data = dict(selection_policy='exact', request_id=RID, mode='movies',
                title='Series', _bt_next_selected=selected())
    url = make(MAGNET, '', data)
    result = parse_request([url.split('?', 1)[0], '2', '?' + url.split('?', 1)[1]])
    assert json.loads(result['expected_file']) == selected()


@pytest.mark.parametrize('value', [None, {}, [], selected(extra=True),
    selected(source_info_hash='A' * 40), selected(source_info_hash='1' * 39),
    selected(torrent_file_id=0), selected(torrent_file_id=True),
    selected(torrent_file_bytes=0), selected(torrent_file_bytes=True),
    selected(torrent_path='dir\\file.mkv'), selected(torrent_path='../file.mkv'),
    selected(torrent_path='/file.mkv'), selected(torrent_path='a//file.mkv'),
    selected(torrent_path='C:/file.mkv'), selected(torrent_path='a\nfile.mkv'),
    selected(torrent_path='a' * 4097)])
def test_producer_rejects_present_but_invalid_next_tuple(monkeypatch, value):
    with pytest.raises((ValueError, RuntimeError)):
        producer(monkeypatch)(MAGNET, '', dict(selection_policy='exact', request_id=RID,
                                             mode='movies', _bt_next_selected=value))


@pytest.mark.parametrize('value', [None, {}, [], selected(extra=True),
    selected(source_info_hash='A' * 40), selected(source_info_hash='1' * 39),
    selected(torrent_file_id=0), selected(torrent_file_id=True),
    selected(torrent_file_bytes=0), selected(torrent_file_bytes=True),
    selected(torrent_path='dir\\file.mkv'), selected(torrent_path='../file.mkv'),
    selected(torrent_path='/file.mkv'), selected(torrent_path='a//file.mkv'),
    selected(torrent_path='C:/file.mkv'), selected(torrent_path='a\nfile.mkv'),
    selected(torrent_path='a' * 4097)])
def test_parser_rejects_invalid_expected_file(value):
    with pytest.raises(BackendError, match='TORRENT_REQUEST_INVALID'):
        parsed(json.dumps(value))


@pytest.mark.parametrize('raw', ['', '{', '[]',
    '{"source_info_hash":"' + HASH + '",' + json.dumps(selected())[1:],
    json.dumps(selected()) + ' ' * 8192])
def test_parser_rejects_malformed_duplicate_or_oversized_tuple(raw):
    with pytest.raises(BackendError, match='TORRENT_REQUEST_INVALID'):
        parsed(raw)


def test_parser_accepts_valid_exact_tuple_and_selector_reproves_it():
    q = parsed(json.dumps(selected()))
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *a: 'bt:' + HASH)
    assert select_file(status(), q, HASH, {}, protocol) == FILE


@pytest.mark.parametrize('changes', [dict(source_info_hash='2' * 40),
    dict(torrent_file_id=FILE['id'] + 1), dict(torrent_path='Series.S01E01.other.mkv'),
    dict(torrent_file_bytes=FILE['length'] + 1)])
def test_real_selector_must_match_every_service_proved_field(changes):
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *a: 'bt:' + HASH)
    with pytest.raises(BackendError, match='TORRENT_EXPECTED_FILE_MISMATCH'):
        select_file(status(), request(expected_file=json.dumps(selected(**changes))),
                    HASH, {}, protocol)


def test_unresolved_automatic_next_never_opens_manual_file_dialog():
    file = dict(FILE, path='video.mkv')
    clock, choices = Clock(), []
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: choices.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status(file)), Response(status(file)),
                       Response(b''), Response(status(file))])
    with pytest.raises(BackendError, match='TORRENT_EXACT_FILE_UNRESOLVED'):
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
            request(expected_file=json.dumps(selected(torrent_path=file['path']))))
    assert choices == [] and owner.targets == [] and owner.bindings == []
    assert not any('/stream?' in call[1] for call in session.calls)


def test_exact_automatic_next_preloads_only_the_proved_file():
    clock, choices = Clock(), []
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: choices.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status()), Response(b''), Response(status())])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
        request(expected_file=json.dumps(selected())))
    assert result['file'] == FILE and result['file_evidence'] == 'AUTO_VERIFIED_FILE'
    assert choices == []


def test_changed_torrent_hash_stops_before_add():
    clock = Clock()
    owner = FakeOwner(clock)
    session = Session([Response(b'MatriX.144.1')])
    with pytest.raises(BackendError, match='TORRENT_EXPECTED_FILE_MISMATCH'):
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
            request(expected_file=json.dumps(selected(source_info_hash='2' * 40))))
    assert not owner.targets and not owner.bindings
    assert len(session.calls) == 1 and session.calls[0][1].endswith('/echo')


def test_changed_selected_file_stops_before_preload_or_manual_choice():
    clock, choices = Clock(), []
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: choices.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status(dict(FILE, id=FILE['id'] + 1)))])
    with pytest.raises(BackendError, match='TORRENT_EXPECTED_FILE_MISMATCH'):
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
            request(expected_file=json.dumps(selected())))
    assert not choices and not owner.targets and not owner.bindings
    assert not any('/stream?' in call[1] for call in session.calls)


def test_manual_legacy_request_keeps_unknown_file_choice():
    file = dict(FILE, path='video.mkv')
    clock, choices = Clock(), []
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: choices.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
                       Response(status(file)), Response(status(file)),
                       Response(b''), Response(status(file))])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request(catalog=False))
    assert result['file'] == file and result['file_evidence'] == 'USER_CONFIRMED_FILE'
    assert choices == [[file]]
