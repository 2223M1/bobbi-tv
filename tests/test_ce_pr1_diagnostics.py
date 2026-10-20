"""Real backend JSON -> resolver -> log/wait path; no device/torrent traffic."""
import json
import sys
from types import SimpleNamespace

import pytest

from test_bobbi_torrent_adapter import (Clock, FakeOwner, Session, Response,
    request, config, status, HASH, RID)
from bobbi_torrent.backend import Backend, BackendError
from bobbi_torrent.entry import failure_log
from bobbi_torrent.owner import Owner
from bobbi_torrent.resolver import Resolver


SPEEDS = [
    (98409.04851425653, 98409), (0.0, 0), (98409, 98409), (-1, None),
    (True, None), (float('nan'), None), (float('inf'), None), ('98409', None),
    (False, None), (float('-inf'), None), (None, None), (0, 0),
    (512*1024**3, 512*1024**3), (512*1024**3 + 1, None),
    (512*1024**3 + .5, None), (10**400, None), (-.1, None), (.5, 0),
]


@pytest.mark.parametrize('speed,expected', SPEEDS)
def test_speed_survives_real_backend_buffer_timeout_log_and_wait(speed, expected):
    clock, prompts = Clock(), []
    owner = FakeOwner(clock)
    owner.wait_for_buffer = lambda detail: prompts.append(detail) or False
    raw = dict(status(ready=False), download_speed=speed, active_peers=2)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(status()), Response(b'')] + [Response(raw) for _ in range(4)])
    resolver = Resolver(Backend(config(), session, clock), owner, Session([]), clock)
    with pytest.raises(BackendError, match='TORRENT_BUFFER_TIMEOUT') as failure:
        resolver.resolve(request())
    assert len(prompts) == 1
    log = json.loads(failure_log(failure.value, RID).split(' detail=', 1)[1])
    for snapshot in (resolver.buffer_snapshot, failure.value.diagnostic, prompts[0], log):
        if expected is None:
            assert 'download_bps' not in snapshot
        else:
            assert snapshot['download_bps'] == expected
            assert type(snapshot['download_bps']) is int
    assert resolver.buffer_snapshot['torrent_preloaded'] == 0
    assert 'ready' not in resolver.buffer_snapshot
    assert log['stage'] == 'buffering'


@pytest.mark.parametrize('detail,text', [
    ({'download_bps': 98409}, '98,409 B/s'),
    ({'download_bps': 0}, '0 B/s'), ({}, '未知'),
])
def test_actual_wait_dialog_keeps_zero_distinct_from_unknown(monkeypatch, detail, text):
    shown, logged = [], []
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(
        yesno=lambda *args, **kwargs: shown.append((args, kwargs)) or False)))
    owner = SimpleNamespace(active=lambda: None, diagnostic=logged.append)
    assert not Owner.wait_for_buffer(owner, detail)
    assert text in shown[0][0][1]
    assert '总下载速度' in shown[0][0][1]
    assert logged == [dict(detail, stage='buffering')]
