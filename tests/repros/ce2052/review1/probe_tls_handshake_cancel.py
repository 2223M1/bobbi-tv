#!/usr/bin/env python3
"""Observe real chooser cancellation while localhost accepts TCP but stalls TLS.

No simulated DNS, connect, SSL, or timeout. The listener reads a real TLS
ClientHello and keeps the socket open without a ServerHello. An optional exact
old http_io.py can replace only that module for a clearly labeled baseline.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--http-io-baseline', type=Path)
    parser.add_argument('--max-back-seconds', type=float, default=.5)
    args = parser.parse_args()
    root = args.repo.resolve()
    for name in ('script.module.requests', 'script.module.urllib3', 'script.module.idna',
                 'script.module.certifi', 'script.module.charset_normalizer'):
        sys.path.insert(0, str(root/'third_party/addons'/name/'lib'))
    for name in ('plugin.video.bobbi.torrent', 'script.module.bobbi.core'):
        sys.path.insert(0, str(root/'addons'/name/'lib'))
    if args.http_io_baseline:
        import bobbi_torrent
        spec = importlib.util.spec_from_file_location('bobbi_torrent.http_io', args.http_io_baseline)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        bobbi_torrent.http_io = module
    from bobbi_torrent.backend import Backend
    from bobbi_torrent import http_io, resolver
    import requests
    import urllib3
    source_paths = [
        'addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/http_io.py',
        'addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py',
        'addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/resolver.py',
        'third_party/addons/script.module.urllib3/lib/urllib3/connection.py',
        'third_party/addons/script.module.urllib3/lib/urllib3/util/ssl_.py',
    ]
    binding = []
    for path in source_paths:
        actual = args.http_io_baseline if args.http_io_baseline and path.endswith('/http_io.py') else root/path
        binding.append(dict(path=path, sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),
                            provenance='baseline module override' if actual == args.http_io_baseline else 'reviewed source'))
    cases = []
    previous_interval = resolver.FILE_CHOICE_STATUS_SECONDS
    resolver.FILE_CHOICE_STATUS_SECONDS = .01  # Enter the actual 2 s request promptly.
    original_track = http_io.RequestIO.track
    try:
        for mode in ('back', 'confirm'):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(4)
            port = listener.getsockname()[1]
            client_hello, release = threading.Event(), threading.Event()
            observed, tracked = {}, []
            def serve():
                try:
                    with listener.accept()[0] as connection:
                        connection.settimeout(4)
                        header = connection.recv(4096)
                        observed['client_hello_bytes'] = len(header)
                        observed['tls_record_type'] = header[0] if header else None
                        observed['tcp_peer_loopback'] = connection.getpeername()[0] == '127.0.0.1'
                        client_hello.set()
                        release.wait(8)
                except Exception as error:
                    observed['fixture_error'] = repr(error)
                    client_hello.set()
            def track(guard, sock):
                tracked.append(sock)  # Observation only; preserve the production operation.
                return original_track(guard, sock)
            http_io.RequestIO.track = track
            server = threading.Thread(target=serve, name='ce2051-tls-fixture')
            server.start()
            backend = Backend(dict(schema=1, endpoint='https://localhost:'+str(port),
                                   auth=None, metadata_seconds=2, buffering_seconds=2))
            owner = SimpleNamespace(active=lambda: None)
            runner = resolver.Resolver(backend, owner, SimpleNamespace())
            selected = dict(id=1)
            decision = {}
            def choose(candidates):
                assert client_hello.wait(4), 'No TLS ClientHello arrived'
                assert observed.get('tls_record_type') == 22, observed
                time.sleep(.05)
                decision['at'] = time.monotonic()
                decision['tracked_sockets'] = [dict(type=type(sock).__name__, fileno=sock.fileno()) for sock in tracked]
                return None if mode == 'back' else selected
            started = time.monotonic()
            try:
                result = runner.choose_with_status(choose, [selected], 'f'*40)
                returned = time.monotonic()
                assert result == (None if mode == 'back' else selected)
                workers = [t.name for t in threading.enumerate()
                           if t.name in ('bobbi-control-io', 'bobbi-file-choice-status')]
                row = dict(case=mode, elapsed_seconds=round(returned-started, 6),
                           seconds_after_decision=round(returned-decision['at'], 6),
                           configured_request_budget_seconds=2,
                           tracked_at_decision=decision['tracked_sockets'],
                           track_calls=len(tracked), workers_at_return=workers, **observed)
                row['checks'] = dict(
                    real_tls_client_hello=row['tls_record_type'] == 22 and row['tcp_peer_loopback'],
                    bounded_user_exit=row['seconds_after_decision'] <= args.max_back_seconds,
                    zero_workers_at_return=not workers)
                row['status'] = 'PASS' if all(row['checks'].values()) else 'FAIL'
                cases.append(row)
            finally:
                backend.close()
                release.set()
                listener.close()
                server.join(5)
                assert not server.is_alive(), 'Fixture thread did not close'
                http_io.RequestIO.track = original_track
    finally:
        resolver.FILE_CHOICE_STATUS_SECONDS = previous_interval
        http_io.RequestIO.track = original_track
    report = dict(schema=1, scope='Real vendored Requests/urllib3 and OS localhost TCP/TLS ClientHello; no Kodi or external backend',
                  real_device=False, simulated_dns=False, simulated_connect=False, simulated_ssl=False,
                  baseline_module_override=bool(args.http_io_baseline), tls_verification_disabled=False,
                  requests=requests.__version__, urllib3=urllib3.__version__, source=binding, cases=cases,
                  max_back_seconds=args.max_back_seconds,
                  threshold_origin='Reviewer engineering acceptance target, not device certification',
                  status='PASS' if all(row['status'] == 'PASS' for row in cases) else 'FAIL')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
