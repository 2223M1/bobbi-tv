"""Real sockets and the shipped Requests/urllib3, isolated from pytest stubs."""
import json
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / 'third_party/addons').glob('*/lib'):
    sys.path.insert(0, str(path))
for name in ('plugin.video.bobbi.torrent', 'script.module.bobbi.core'):
    sys.path.insert(0, str(ROOT / 'addons' / name / 'lib'))
from bobbi_torrent.backend import Backend, BackendError
from bobbi_torrent import resolver
import requests
import urllib3


def probe(mode, choice):
    entered, done, cancelled = threading.Event(), threading.Event(), threading.Event()
    operations = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            operations.append(json.loads(self.rfile.read(int(self.headers['Content-Length'])))['action'])
            try:
                if mode == 'refused':
                    self.send_response(403); self.end_headers(); entered.set(); return
                if mode == 'header':
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                else:
                    self.send_response(200); self.end_headers()
                self.wfile.flush(); entered.set()
                while not done.wait(.02):
                    self.wfile.write(b' '); self.wfile.flush()
            except (OSError, ValueError):
                pass  # Request-local shutdown is the expected server-side EOF.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    thread.start()
    backend = Backend(dict(schema=1, endpoint='http://127.0.0.1:'+str(server.server_port),
        auth=None, metadata_seconds=30, buffering_seconds=90))
    def active():
        if cancelled.is_set():
            raise BackendError('TORRENT_'+choice.upper(), choice)
    owner = SimpleNamespace(active=active)
    runner = resolver.Resolver(backend, owner, SimpleNamespace())
    def choose(rows):
        assert entered.wait(3)
        time.sleep(.1)
        if choice in ('cancelled', 'superseded'): cancelled.set()
        if choice == 'exception': raise ValueError('choice failed')
        return None if choice == 'back' else rows[0]
    resolver.FILE_CHOICE_STATUS_SECONDS = .01
    started = time.monotonic()
    outcome = ''
    try:
        if choice == 'deadline':
            try: backend.status('a'*40, time.monotonic()+.3, active)
            except BackendError as error: outcome = error.code
            assert outcome == 'TORRENT_CONTROL_DEADLINE'
        else:
            try:
                result = runner.choose_with_status(choose, [dict(id=1)], 'a'*40)
                outcome = 'back' if result is None else 'confirmed'
            except BackendError as error: outcome = error.code
            except ValueError: outcome = 'choice_failed'
            expected = {'back':'back', 'confirm':'confirmed', 'exception':'choice_failed',
                'cancelled':'TORRENT_CANCELLED', 'superseded':'TORRENT_SUPERSEDED'}[choice]
            if mode == 'refused' and choice == 'confirm': expected = 'TORRENT_HTTP_REJECTED'
            assert outcome == expected, (mode, choice, outcome)
        elapsed = time.monotonic()-started
        assert elapsed < 3, elapsed
        assert operations == ['get']
        assert not any(t.name in ('bobbi-control-io', 'bobbi-file-choice-status') for t in threading.enumerate())
        return dict(mode=mode, choice=choice, outcome=outcome, seconds=round(elapsed,3),
                    operations=operations, workers_at_return=0)
    finally:
        done.set(); backend.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    results = [probe(mode, choice) for mode in ('header', 'body')
        for choice in ('back', 'confirm', 'exception', 'cancelled', 'superseded', 'deadline')]
    results += [probe('refused', choice) for choice in ('back', 'confirm')]
    print(json.dumps(dict(requests=requests.__version__, urllib3=urllib3.__version__, cases=results)))
