"""Cloud gate recovery and real HTTP error classification, no cloud account IO."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json

import pytest
import requests

from test_ce2035_preparation_metadata import offline_session, intent, complete_intent
from bobbi_core.torrent_metadata import registered_metadata, MetadataUnavailable


def test_cloud_recovery_keeps_one_pending_task_and_does_not_reread_torrent(offline_session, monkeypatch):
    session, reads, provider_calls, _, _, _ = offline_session
    first = complete_intent(session, intent())
    assert first['state'] == 'accepted'
    calls = []
    monkeypatch.setattr(session.worker, 'next_action', lambda playing: calls.append('worker'))
    monkeypatch.setattr(session.direct_queue, 'next_action', lambda: calls.append('direct'))
    session.readiness.next_check = 0
    assert session.readiness.begin()
    session.readiness.complete(account=session.config['account'])
    session.next_work = 0
    session.tick()
    assert calls == ['direct', 'worker']
    assert reads == ['registered_metadata'] and provider_calls == []
    assert session.queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1
    assert session.dispatch('status', {'request_id': intent()['request_id']})['state'] == 'accepted'
    assert json.loads(session.snapshot_path.read_text())['titles'] == []


def test_due_cloud_health_failure_then_local_validation_is_not_starved(offline_session, monkeypatch):
    session, reads, _, _, _, _ = offline_session
    checks = []
    def still_offline():
        checks.append('account')
        raise ConnectionError('fixture')
    monkeypatch.setattr(session.provider, 'account_scope', still_offline)
    session.readiness.next_check = 0
    result = complete_intent(session, intent())
    assert result['state'] == 'accepted'
    assert checks == ['account'] and reads == ['registered_metadata']
    assert not session.readiness.ready


def test_publication_failure_is_distinguished_from_metadata(offline_session):
    session, _, _, _, _, reports = offline_session
    body = intent()
    session.dispatch('prepare', body)
    session.intake.take()
    session._failed('intent', body, ValueError('private-publication-token'))
    result = session.dispatch('status', {'request_id': body['request_id']})
    assert result['result'] == dict(error='ValueError', stage='publication', reason='publication_failed')
    assert 'private-publication-token' not in repr(result) + repr(reports)


@pytest.mark.parametrize('status,reason', [(401, 'torrent_authentication'),
    (403, 'torrent_authentication'), (404, 'torrent_missing'), (429, 'torrent_http_status'),
    (500, 'torrent_backend'), (503, 'torrent_backend')])
def test_metadata_http_error_is_classified_without_response_body(status, reason):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            assert self.path == '/echo'
            raw = b'MatriX.144.1'
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(value)
            raw = b'private-response?token=never-output'
            self.send_response(status)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with requests.Session() as session:
            session.trust_env = False
            with pytest.raises(MetadataUnavailable) as caught:
                registered_metadata(session, 'http://127.0.0.1:%d' % server.server_port, 'b' * 40)
        assert caught.value.reason == reason
        assert 'private' not in str(caught.value)
        assert calls == [dict(action='get', hash='b' * 40)]
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()
