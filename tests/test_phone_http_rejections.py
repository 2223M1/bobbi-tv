"""Real loopback transport checks; no phone, account or device claims."""
from http.client import HTTPResponse
import socket
import time

import pytest

from test_ce2097_phone_management import phone, http_server


def raw_request(phone, headers, body=b'', method='POST', path='/manage/api'):
    host, port = phone.manager.host.split(':')
    connection = socket.create_connection((host, int(port)), timeout=5)
    lines = ['%s %s HTTP/1.1' % (method, path), 'Host: ' + phone.manager.host,
             'Origin: ' + phone.manager.origin] + headers
    connection.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii') + body)
    return connection


def receive(connection):
    reply = HTTPResponse(connection)
    reply.begin()
    result = reply.status, reply.read()
    reply.close()
    return result


@pytest.mark.parametrize('method,path,status', [
    ('GET', '/manage', 200), ('GET', '/api/addons', 404),
    ('POST', '/api/addons', 404), ('PUT', '/api/addons', 404),
    ('DELETE', '/api/addons', 404), ('OPTIONS', '/manage/api', 403),
])
def test_known_small_unread_body_does_not_reset_chosen_response(http_server, method, path, status):
    _, phone = http_server
    for _ in range(10):
        with raw_request(phone, ['Content-Length: 8192'], b'x' * 8192, method, path) as connection:
            assert receive(connection)[0] == status
    assert phone.calls == []


@pytest.mark.parametrize('headers,status', [
    (['Content-Length: 8193'], 413),
    (['Content-Length: -1'], 413),
    (['Content-Length: invalid'], 413),
    (['Content-Length: 99999999999999999999999999999999999'], 413),
    (['Content-Length: 2', 'Content-Length: 2'], 413),
    ([], 413),
    (['Transfer-Encoding: chunked'], 400),
    (['Transfer-Encoding: chunked', 'Content-Length: 2'], 400),
])
def test_ambiguous_unknown_or_oversize_body_is_not_waited_for(http_server, headers, status):
    _, phone = http_server
    started = time.monotonic()
    with raw_request(phone, ['Content-Type: application/json'] + headers) as connection:
        assert receive(connection)[0] == status
    assert time.monotonic() - started < 1.5  # The body-read timeout remains 3 seconds.
    assert phone.calls == []


@pytest.mark.parametrize('cross_site,status', [(True, 403), (False, 400)])
def test_short_body_eof_preserves_rejection_and_cannot_call_business(http_server, cross_site, status):
    _, phone = http_server
    headers = ['Content-Type: application/json', 'Content-Length: 2']
    if cross_site:
        headers.append('Sec-Fetch-Site: cross-site')
    with raw_request(phone, headers, b'{') as connection:
        connection.shutdown(socket.SHUT_WR)
        assert receive(connection)[0] == status
    assert phone.calls == []


@pytest.mark.parametrize('cross_site,status', [(True, 403), (False, 503)])
def test_stalled_small_body_uses_one_total_deadline_without_second_read(http_server, cross_site, status):
    request, phone = http_server
    headers = ['Content-Type: application/json', 'Content-Length: 2']
    if cross_site:
        headers.append('Sec-Fetch-Site: cross-site')
    started = time.monotonic()
    with raw_request(phone, headers, b'{') as connection:
        assert receive(connection)[0] == status
    assert 2 <= time.monotonic() - started < 4.5
    assert phone.calls == []
    assert request('/manage', method='GET')[0] == 200


def test_disconnected_partial_request_does_not_block_next_request_or_call_business(http_server):
    request, phone = http_server
    connection = raw_request(phone, ['Content-Type: application/json', 'Content-Length: 64'], b'{')
    connection.close()
    assert request('/manage', method='GET')[0] == 200
    assert phone.calls == []
