"""Exercise the production identity-encoding reader through real loopback HTTP."""
from types import SimpleNamespace
import ssl
from threading import Event
from collections import deque

import pytest

from test_ce_progressive_http import PAYLOAD, pipeline, wait_end
from test_online_transport import endpoint  # shared local HTTPS server with an ephemeral test CA
from bobbi_core import share_stream as stream


def test_backlogged_records_reach_one_owner_check_without_waiting_to_fill(monkeypatch):
    from bobbi_core import share_origin as wire
    one = b'a' * 4096
    packets = deque([one]*8 + [b'z', BlockingIOError(), b''])
    class Source:
        def recv_into(self, buf):
            item = packets.popleft()
            if isinstance(item, BaseException):
                raise item
            buf[:len(item)] = item
            return len(item)
    monkeypatch.setattr(wire.select, 'select', lambda *a: pytest.fail('must not wait after any prefix'))
    reader = wire.ReadyReader(Source(), 10, clock=lambda: 0.)
    buf = bytearray(32768)
    assert reader.readinto(buf) == len(buf) and bytes(buf) == one * 8
    assert reader.readinto(buf) == 1 and buf[0] == ord('z')
    assert reader.readinto(buf) == 0


def test_no_data_wait_uses_one_deadline_both_tls_directions(monkeypatch):
    from bobbi_core import share_origin as wire
    now, waits = [0.], []
    replies = iter([ssl.SSLWantReadError(), ssl.SSLWantWriteError(), BlockingIOError()])
    class Source:
        def recv_into(self, buf): raise next(replies)
    sock = Source()
    def ready(r, w, unused, timeout):
        waits.append((bool(r),bool(w),round(timeout,2))); now[0] += .4
        return (r, w, []) if len(waits)<3 else ([], [], [])
    monkeypatch.setattr(wire.select, 'select', ready)
    reader = wire.ReadyReader(sock, 1, clock=lambda:now[0])
    with pytest.raises(TimeoutError):
        reader.readinto(bytearray(8192))
    assert waits == [(True,False,1.),(False,True,.6),(True,False,.2)]


def test_io_error_after_a_valid_prefix_is_reported_on_next_read():
    from bobbi_core.share_origin import ReadyReader
    class Source:
        called = False
        def recv_into(self, buf):
            if self.called:
                raise ConnectionResetError()
            self.called = True
            buf[:1] = b'x'
            return 1
    reader=ReadyReader(Source(), 10)
    buf=bytearray(2)
    assert reader.readinto(buf)==1 and buf[:1]==b'x'
    with pytest.raises(ConnectionResetError):
        reader.readinto(buf)


def test_tls_framing_hostname_and_no_redirect_are_still_owned_by_one_origin(endpoint,monkeypatch):
    from bobbi_core import share_origin as wire
    origin=wire.RangeOrigin()
    endpoint.blob = bytes(range(256)) * 16
    def get(path):
        return origin.get(endpoint.url + path, headers={'User-Agent':'local range fixture',
            'Accept-Encoding':'identity','Range':'bytes=1-','Connection':'close'},
            stream=True,allow_redirects=False,timeout=(2,2))
    monkeypatch.setattr(wire,'tls_context',endpoint.trusted)
    with get('/resume') as reply:
        assert reply.status_code == 206 and b''.join(reply.iter_content(32768)) == endpoint.blob[1:]
    with get('/chunked') as reply:
        assert b''.join(reply.iter_content(32768)) == endpoint.blob
    with get('/redirect') as reply:
        assert reply.status_code == 302
    assert [r[0] for r in endpoint.requests] == ['/resume','/chunked','/redirect']
    assert set(endpoint.sni)=={'localhost'}
    monkeypatch.setattr(wire,'tls_context',endpoint.untrusted)
    with pytest.raises(ssl.SSLCertVerificationError), get('/resume'):
        pytest.fail('untrusted peer was accepted')


def test_only_selected_115_uses_the_cookie_free_one_origin_reader():
    from bobbi_core.share_origin import RangeOrigin, tls_context
    owner = SimpleNamespace(session_factory=None, origin_factory=None)
    for addr, diagnostic, eligible in (
        ('am6bsharelib://id', None, True), ('am6bqqdocs://id', None, True),
        ('pan://id', None, False), ('am6bsharelib://id', {'mode':'open_range'}, False)):
        entry = SimpleNamespace(body={'locator':addr}, diagnostic=diagnostic)
        with stream.ShareStream.session(owner, entry) as session:
            assert isinstance(session, RangeOrigin) is eligible
    ctx = tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert tls_context() is ctx


@pytest.mark.parametrize('progressive', [False, True])
@pytest.mark.parametrize('mode', ['normal', 'chunked', 'short_once', 'expired', 'wrong_range', 'wrong_length', 'encoding'])
def test_origin_keeps_shared_range_gate_and_recovery(progressive, mode, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    with pipeline(progressive, mode, real_origin=True) as (_, connect, calls, events, resolves, _):
        c, response = connect('bytes=117-524404')
        try:
            if mode in ('wrong_range','wrong_length','encoding'):
                assert response.status == 503
            else:
                assert response.status == 206 and response.read() == PAYLOAD[117:524405]
        finally:
            c.close()
        wait_end(events)
        if mode in ('wrong_range','wrong_length','encoding'):
            assert events[-1]['delivered'] == 0
        else:
            assert events[-1]['outcome'] == 'complete'
            if mode == 'expired':
                assert len(resolves) == 2
            elif mode == 'short_once':
                assert len(calls)>1 and calls[1][0]>117


def test_first_available_prefix_is_not_held_to_fill_a_tls_sized_buffer():
    body_waiting, release = Event(), Event()
    with pipeline(True, payload=PAYLOAD[:65536], body_pause=(16384, body_waiting, release),
                  real_origin=True) as (_, connect, *unused):
        c, response = connect()
        try:
            assert body_waiting.wait(2)
            assert response.status == 200 and response.read(256) == PAYLOAD[:256]
            release.set()
            assert response.read() == PAYLOAD[256:65536]
        finally:
            release.set()
            c.close()
