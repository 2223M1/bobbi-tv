"""Separate IO lanes must share renewal, not requests.Session or mutations."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import authenticated_cd2 as auth
from bobbi_core.cd2 import CD2, CD2Error, field


def clients(monkeypatch, *, rejected=False, barrier=None):
    calls, secrets, lock = [], [], Lock()
    def credentials():
        value = dict(username='fixture', password='fixture')
        secrets.append(value)
        return value
    def rpc(self, method, payload=b''):
        with lock:
            calls.append(method)
        if method == 'GetToken':
            assert self.token is None
            if rejected:
                raise CD2Error('16')
            return [field(1, 1) + field(3, 'renewed')]
        expired = self.token != 'renewed'
        if expired and barrier:
            barrier.wait(2)
        if expired:
            raise CD2Error('16')
        return [b'result']
    monkeypatch.setattr(CD2, 'rpc', rpc)
    # Also executable against the frozen old implementation: it exposes the
    # duplicate-login failure, rather than failing only on a missing import.
    shared = (auth.CD2Authentication('expired', credentials, clock=lambda: 100)
              if hasattr(auth, 'CD2Authentication') else None)
    options = {'authentication': shared} if shared is not None else {}
    providers = [auth.AuthenticatedCD2('expired', 'http://127.0.0.1:19798/', credentials,
                                    clock=lambda: 100, **options) for _ in range(2)]
    assert providers[0].session is not providers[1].session
    return providers, calls, secrets


def test_concurrent_expiration_is_one_login_across_io_lanes(monkeypatch):
    providers, calls, secrets = clients(monkeypatch, barrier=Barrier(2))
    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda p: p.rpc('GetSubFiles'), providers))
        assert results == [[b'result'], [b'result']]
        assert calls.count('GetToken') == 1
        assert secrets == [{}]
    finally:
        for p in providers: p.session.close()


def test_rejected_login_backoff_is_shared_not_per_lane(monkeypatch):
    providers, calls, secrets = clients(monkeypatch, rejected=True)
    try:
        for p in providers:
            with pytest.raises(CD2Error): p.rpc('GetSubFiles')
        assert calls.count('GetToken') == 1
        assert secrets == [{}]
    finally:
        for p in providers: p.session.close()


def test_failed_mutation_is_not_replayed_and_next_lane_reuses_renewal(monkeypatch):
    providers, calls, _ = clients(monkeypatch)
    try:
        with pytest.raises(CD2Error): providers[0].rpc('AddOfflineFiles')
        assert providers[1].rpc('GetSubFiles') == [b'result']
        assert calls.count('AddOfflineFiles') == 1
        assert calls.count('GetToken') == 1
    finally:
        for p in providers: p.session.close()


def test_new_generation_of_same_token_still_suppresses_late_renewal(monkeypatch):
    providers, calls, _ = clients(monkeypatch)
    p = providers[0]
    try:
        shared = p.authentication
        _, old_revision = shared.snapshot()
        p.rpc('GetSubFiles')
        # Generation, not string inequality, controls a late rejected request.
        shared.token = 'expired'
        assert shared.renew(providers[1], old_revision) is True
        assert calls.count('GetToken') == 1
    finally:
        for p in providers: p.session.close()


def test_second_read_failure_is_not_an_unbounded_retry(monkeypatch):
    calls = []
    def rpc(self, method, payload=b''):
        calls.append(method)
        if method == 'GetToken': return [field(1, 1) + field(3, 'still-rejected')]
        raise CD2Error('16')
    monkeypatch.setattr(CD2, 'rpc', rpc)
    p = auth.AuthenticatedCD2('expired', 'http://127.0.0.1:19798/',
                             lambda: dict(username='fixture', password='fixture'))
    try:
        with pytest.raises(CD2Error): p.rpc('GetSubFiles')
        assert calls == ['GetSubFiles', 'GetToken', 'GetSubFiles']
    finally:
        p.session.close()


def test_shared_auth_never_crosses_endpoints_and_rejected_client_closes(monkeypatch):
    closed = []
    def init(self, token=None, base=''):
        self.token, self.base = token, base.rstrip('/') + '/'
        self.session = type('Session', (), {'close': lambda self: closed.append(True)})()
    monkeypatch.setattr(CD2, '__init__', init)
    shared = auth.CD2Authentication('fixture', lambda: {})
    auth.AuthenticatedCD2('fixture', 'http://127.0.0.1:1/', lambda: {}, authentication=shared)
    with pytest.raises(ValueError):
        auth.AuthenticatedCD2('fixture', 'http://127.0.0.1:2/', lambda: {}, authentication=shared)
    assert closed == [True]
