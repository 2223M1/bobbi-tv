"""A remote disc can deliver thousands of TLS fragments in a second. Only
the local peer probe can be sampled; identity and cancellation must stay live."""
from threading import Event
from types import SimpleNamespace
from bobbi_core import share_stream as stream


def test_small_prefixes_share_only_the_peer_probe(monkeypatch):
    now=[1.0]
    monkeypatch.setattr(stream.time,'monotonic',lambda:now[0])
    h=stream.Handler.__new__(stream.Handler)
    revoked, stopped = Event(), Event()
    authorizations, probes = [], []
    h.entry=SimpleNamespace(diagnostic_expired=lambda:False,
        cancelled=lambda:authorizations.append(1) or revoked.is_set())
    h.server=SimpleNamespace(owner=SimpleNamespace(stopping=stopped))
    h._next_peer_check=0
    h.probe_socket=lambda:probes.append(1) or False
    for _ in range(32):
        assert not h.cancelled()
    assert len(authorizations)==32 and len(probes)==1
    revoked.set()
    assert h.cancelled() and h.cancel_reason=='account_revoked' and len(probes)==1
    revoked.clear();stopped.set()
    assert h.cancelled() and h.cancel_reason=='service_stop' and len(probes)==1
    stopped.clear();now[0]+=.025
    assert not h.cancelled() and len(probes)==2


def test_existing_socket_failure_is_never_delayed(monkeypatch):
    h=stream.Handler.__new__(stream.Handler)
    h.server=SimpleNamespace(owner=SimpleNamespace(stopping=Event()))
    h._next_peer_check=float('inf')
    h.disconnected=True
    h.probe_socket=lambda: (_ for _ in ()).throw(AssertionError('known disconnect'))
    assert h.cancelled()
