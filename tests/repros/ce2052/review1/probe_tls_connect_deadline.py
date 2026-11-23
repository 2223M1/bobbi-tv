#!/usr/bin/env python3
"""Real first-localhost-address TCP stall, then second-address TLS stall.

This checks the original absolute request budget without a Back event. It
does not patch DNS, socket.connect, TLS, clocks, or production methods.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-seconds', type=float, default=2)
    parser.add_argument('--budget-tolerance', type=float, default=.4)
    args = parser.parse_args()
    root = args.repo.resolve()
    for name in ('script.module.requests', 'script.module.urllib3', 'script.module.idna',
                 'script.module.certifi', 'script.module.charset_normalizer'):
        sys.path.insert(0, str(root/'third_party/addons'/name/'lib'))
    for name in ('plugin.video.bobbi.torrent', 'script.module.bobbi.core'):
        sys.path.insert(0, str(root/'addons'/name/'lib'))
    from bobbi_torrent.backend import Backend, BackendError
    from urllib3.util.connection import allowed_gai_family
    import requests
    import urllib3
    sockets, fillers = [], []
    server = backend = None
    release = threading.Event()
    observed = {}
    try:
        ipv4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ipv4.bind(('127.0.0.1', 0))
        ipv4.listen(1)
        ipv4.settimeout(5)
        sockets.append(ipv4)
        port = ipv4.getsockname()[1]
        records = socket.getaddrinfo('localhost', port, allowed_gai_family(), socket.SOCK_STREAM)
        assert len(records) == 2, 'Fixture needs exactly two OS localhost addresses'
        assert records[0][0] == socket.AF_INET6 and records[1][0] == socket.AF_INET, 'Fixture requires actual IPv6-first ordering'
        assert records[1][4][0] == '127.0.0.1'
        assert all(ipaddress.ip_address(row[4][0]).is_loopback for row in records)
        ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        ipv6.bind(records[0][4])
        ipv6.listen(0)
        sockets.append(ipv6)
        for _ in range(16):
            filler = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            filler.settimeout(.03)
            try:
                filler.connect(records[0][4])
                fillers.append(filler)
            except socket.timeout:
                filler.close()
                break
        else:
            raise AssertionError('Could not saturate real IPv6 accept queue')
        started = time.monotonic()
        def serve():
            try:
                with ipv4.accept()[0] as connection:
                    connection.settimeout(5)
                    hello = connection.recv(4096)
                    observed['tls_record_type'] = hello[0] if hello else None
                    observed['client_hello_bytes'] = len(hello)
                    observed['client_hello_elapsed_seconds'] = time.monotonic()-started
                    release.wait(8)
            except Exception as error:
                observed['fixture_error'] = repr(error)
        server = threading.Thread(target=serve, name='ce2051-tls-budget-fixture')
        server.start()
        backend = Backend(dict(schema=1, endpoint='https://localhost:'+str(port), auth=None,
                               metadata_seconds=2, buffering_seconds=2))
        started = time.monotonic()
        try:
            backend.request('GET', '/echo', started+args.budget_seconds, lambda: None)
            outcome = 'UNEXPECTED_SUCCESS'
        except BackendError as error:
            outcome = error.code
        elapsed = time.monotonic()-started
        workers = [t.name for t in threading.enumerate()
                   if t.name in ('bobbi-control-io', 'bobbi-file-choice-status')]
        checks = dict(received_real_tls_client_hello=observed.get('tls_record_type') == 22,
                      original_deadline_wins=outcome == 'TORRENT_CONTROL_DEADLINE',
                      absolute_total_budget=elapsed <= args.budget_seconds+args.budget_tolerance,
                      zero_workers_at_return=not workers)
        report = dict(schema=1, status='PASS' if all(checks.values()) else 'FAIL',
                      scope='Real IPv6 localhost accept-queue saturation followed by real IPv4 TCP and TLS ClientHello stall',
                      real_device=False, simulated_dns=False, simulated_connect=False, simulated_ssl=False,
                      tls_verification_disabled=False, requests=requests.__version__, urllib3=urllib3.__version__,
                      address_order=[row[4][0] for row in records], request_budget_seconds=args.budget_seconds,
                      tolerance_seconds=args.budget_tolerance, elapsed_seconds=elapsed,
                      outcome=outcome, workers_at_return=workers, checks=checks, **observed)
        paths = ['addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/http_io.py',
                 'addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py',
                 'third_party/addons/script.module.urllib3/lib/urllib3/connection.py',
                 'third_party/addons/script.module.urllib3/lib/urllib3/util/ssl_.py']
        report['source'] = [dict(path=path, sha256=hashlib.sha256((root/path).read_bytes()).hexdigest()) for path in paths]
    except (AssertionError, OSError) as error:
        report = dict(schema=1, status='INCONCLUSIVE', reason=str(error), observations=observed)
    finally:
        if backend is not None:
            backend.close()
        release.set()
        for sock in fillers+sockets:
            sock.close()
        if server is not None:
            server.join(6)
            assert not server.is_alive(), 'Fixture did not close'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return {'PASS':0, 'FAIL':1, 'INCONCLUSIVE':2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
