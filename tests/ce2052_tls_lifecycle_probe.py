"""Real stalled TLS through shipped HTTP stack; no TLS/DNS/connect mocks."""
import json
from pathlib import Path
import socket
import sys
from threading import Event, Thread, enumerate as threads
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT/'third_party/addons').glob('*/lib'):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(ROOT/'addons/plugin.video.bobbi.torrent/lib'))
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_torrent.backend import Backend, BackendError
from bobbi_torrent.resolver import Resolver
from bobbi_torrent import resolver


def trial(kind):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(4)
    hello, release = Event(), Event()
    def serve():
        with listener.accept()[0] as connection:
            connection.settimeout(4)
            assert connection.recv(4096)[0] == 22
            hello.set()
            release.wait(4)
    worker = Thread(target=serve, name='tls-fixture')
    worker.start()
    backend = Backend(dict(schema=1, endpoint='https://127.0.0.1:'+str(listener.getsockname()[1]),
                           auth=None, metadata_seconds=2, buffering_seconds=2))
    began = time.monotonic()
    decision = []
    try:
        if kind == 'chooser_exception':
            def choose(rows):
                assert hello.wait(3)
                decision.append(time.monotonic())
                raise ValueError('CHOOSER_FIXTURE')
            runner = Resolver(backend, SimpleNamespace(active=lambda:None), SimpleNamespace())
            try:
                runner.choose_with_status(choose, [dict(id=1)], 'a'*40)
            except ValueError as error:
                assert str(error) == 'CHOOSER_FIXTURE'
            else: raise AssertionError('Exception lost')
        else:
            expected = 'TORRENT_CONTROL_DEADLINE' if kind == 'deadline' else 'TORRENT_'+kind.upper()
            def active():
                if kind != 'deadline' and hello.is_set():
                    if not decision: decision.append(time.monotonic())
                    raise BackendError(expected)
            try:
                backend.request('GET', '/echo', began+(.4 if kind=='deadline' else 2), active)
            except BackendError as error:
                assert error.code == expected, error.code
            else: raise AssertionError('Stall accepted')
        ended = time.monotonic()
        assert hello.is_set()
        delay = ended-(decision[0] if decision else began)
        assert delay < (.8 if kind=='deadline' else .5), delay
        assert not [t.name for t in threads() if t.name in ('bobbi-control-io', 'bobbi-file-choice-status')]
        return dict(case=kind, seconds=delay, real_client_hello=True, workers=0)
    finally:
        backend.close()
        release.set()
        listener.close()
        worker.join(5)
        assert not worker.is_alive()


if __name__ == '__main__':
    resolver.FILE_CHOICE_STATUS_SECONDS = .02
    print(json.dumps(dict(cases=[trial(kind) for kind in (
        'cancelled', 'superseded', 'deadline', 'chooser_exception', 'cancelled', 'superseded')])) )
