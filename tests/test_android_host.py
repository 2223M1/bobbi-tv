import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bobbi_platform import android_engine as engine, android_updates as updates
from bobbi_platform.updates import UpdateError


def test_engine_starts_lazily_and_returns_host_config(tmp_path):
    path = tmp_path/'no_backup/engine-backend.json'
    path.parent.mkdir()
    value = {'schema': 1, 'endpoint': 'http://127.0.0.1:8090', 'auth': None,
             'metadata_seconds': 30, 'buffering_seconds': 90}
    path.write_text(json.dumps(value))
    calls = []
    def rpc(action):
        calls.append(action)
        if action == 'engine_start':
            return {'state': 'REQUESTED'}
        return ({'state': 'STOPPED'} if len(calls) == 1 else
                {'state': 'RUNNING', 'config_path': str(path)})
    assert engine.configuration(call=rpc, wait=lambda _: False) == value
    assert calls == ['engine_status', 'engine_start', 'engine_status']


def test_cancelled_engine_does_not_start():
    calls = []
    with pytest.raises(RuntimeError, match='CANCELLED'):
        engine.configuration(cancelled=lambda: True, call=calls.append, wait=lambda _: False)
    assert calls == []


@pytest.mark.parametrize('state', ['STOPPING', 'STOP_UNCONFIRMED'])
def test_engine_does_not_duplicate_unconfirmed_owner(state):
    calls = []
    with pytest.raises(RuntimeError, match='STOPPING'):
        engine.configuration(call=lambda action: calls.append(action) or {'state': state}, wait=lambda _: False)
    assert calls == ['engine_status']


def test_engine_timeout_is_bounded():
    now = [0]
    def wait(amount):
        now[0] += amount
        return False
    with pytest.raises(RuntimeError, match='TIMEOUT'):
        engine.configuration(call=lambda _: {'state': 'STARTING'}, clock=lambda: now[0], wait=wait)
    assert 32 <= now[0] < 33


def offer(abi='arm64-v8a', version=2026102073):
    return dict(version_code=version, abi=abi, size=250*1024**2, sha256='a'*64,
        url='https://github.com/2223M1/bobbi-tv/releases/download/android2073/BobbiTV-2073-android-'+abi+'.apk')


def feed(rows):
    return json.dumps({'schema': 1, 'releases': rows})


def test_updates_choose_abi_and_monotonic_version():
    rows = [offer(), offer('armeabi-v7a')]
    assert updates.parse_feed(feed(rows), 'arm64-v8a', 2026102072) == rows[0]
    assert updates.parse_feed(feed(rows), 'arm64-v8a', 2026102073) is None
    assert updates.parse_feed(feed([]), 'arm64-v8a', 0) is None


def test_empty_mirror_does_not_hide_new_origin_release(monkeypatch):
    def transfer(url, maximum, consume, cancelled):
        consume(feed([] if url == updates.FEEDS[0] else [offer()]).encode())
    monkeypatch.setattr(updates, 'transfer', transfer)
    assert updates.latest('arm64-v8a', 2026102072) == offer()


@pytest.mark.parametrize('field,value', [('url', 'https://example.com/x.apk'), ('size', 2**40),
    ('version_code', True), ('sha256', 'broken'), ('abi', 'x86_64')])
def test_bad_android_offers_fail_closed(field, value):
    row = offer()
    row[field] = value
    with pytest.raises(UpdateError):
        updates.parse_feed(feed([row]), 'arm64-v8a', 0)


def test_duplicate_android_offers_are_not_arbitrarily_selected():
    with pytest.raises(UpdateError):
        updates.parse_feed(feed([offer(), offer()]), 'arm64-v8a', 0)


def test_cancelled_download_keeps_previous_candidate(tmp_path):
    directory = tmp_path/'bobbi-update'
    directory.mkdir()
    old = directory/'update.apk'
    old.write_bytes(b'old complete apk')
    def partial(stream):
        stream.write(b'partial')
        raise updates.Cancelled('cancelled')
    with pytest.raises(updates.Cancelled):
        updates.stage(directory, partial)
    assert old.read_bytes() == b'old complete apk'
    assert list(directory.iterdir()) == [old]


def test_completed_stage_publishes_only_after_writer_returns(tmp_path):
    directory = tmp_path/'bobbi-update'
    path = updates.stage(directory, lambda stream: stream.write(b'complete'))
    assert path.read_bytes() == b'complete'


def test_download_detects_corruption_before_candidate_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, 'transfer', lambda url, maximum, consume, *args: consume(b'bad'))
    with pytest.raises(UpdateError, match='INCOMPLETE'):
        updates.download(offer(), tmp_path/'bobbi-update')
    assert not (tmp_path/'bobbi-update/update.apk').exists()
