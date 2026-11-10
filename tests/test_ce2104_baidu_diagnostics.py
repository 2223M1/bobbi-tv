"""Baidu failure evidence stays credential-free; no external services used."""
import json
import io
import logging
from types import SimpleNamespace

import pytest

from bobbi_platform import pan_baidu
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session, WEBKIT_USER_AGENT, USER_AGENT
from test_ce2096_pan_adapters import Transport, baidu_saved


@pytest.fixture(autouse=True)
def capture_protocol_facts(caplog):
    caplog.set_level(logging.INFO, logger=pan_baidu.__name__)


@pytest.mark.parametrize('url,agent', [
    ('https://passport.baidu.com/v2/api/getqrcode', WEBKIT_USER_AGENT),
    ('https://passport.baidu.com/channel/unicast', WEBKIT_USER_AGENT),
    ('https://passport.baidu.com/v3/login/main/qrbdusslogin', WEBKIT_USER_AGENT),
    (pan_baidu.IDENTITY_URL, 'Mozilla/5.0 (Linux; Android 12; SM-X800) AppleWebKit/537.36'),
    ('https://pan.baidu.com/api/list', 'pan.baidu.com'),
    ('https://pan.baidu.com/api/filemetas', USER_AGENT),
])
def test_login_user_agent_does_not_change_file_requests(url, agent):
    class Reply(io.BytesIO):
        status = 200
        headers = {'Content-Length': '2'}
    def opened(request, timeout):
        assert request.get_header('User-agent') == agent
        return Reply(b'{}')
    Session('baidu', opener=SimpleNamespace(open=opened)).request(url)


def test_optional_identity_still_rejects_explicit_upstream_failure(caplog):
    wire = Transport(dict(errno=-6, result=[]))
    wire.saved = baidu_saved()
    with pytest.raises(PanError, match='^PAN_API_REJECTED$'):
        pan_baidu.Client(session=wire).subject()
    assert wire.calls[0][0] == pan_baidu.IDENTITY_URL
    assert wire.calls[0][1]['appname'] == 'baiduboxapp'
    assert '"errno": -6' in caplog.text
    assert '"result_type": "list"' in caplog.text
    assert 'fixture-' not in caplog.text


@pytest.mark.parametrize('wrapped', [False, True])
def test_probe_records_only_bounded_shape_and_numeric_error(caplog, wrapped):
    secret = 'private-account-ticket-and-credential'
    value = dict(errno=-6, result={'uk': secret}, errInfo={'no': '400021', 'msg': secret},
                 cookie=secret, redirect_url='https://example.test/' + secret)
    raw = json.dumps(value).encode()
    if wrapped:
        raw = (pan_baidu.QR_CALLBACK + '(').encode() + raw + b');'
    wire = Transport()
    wire.saved = baidu_saved()
    pan_baidu._login_probe('exchange', wire, raw)
    assert '"exchange_code": 400021' in caplog.text
    assert '"errno": -6' in caplog.text
    assert '"envelope": "%s"' % ('jsonp' if wrapped else 'json') in caplog.text
    assert secret not in caplog.text and 'fixture-' not in caplog.text and 'https://' not in caplog.text


@pytest.mark.parametrize('value', [True, 'private-ticket', 2**100, None, [], {}])
def test_probe_never_logs_unbounded_or_nonnumeric_error_values(caplog, value):
    pan_baidu._login_probe('identity', Transport(), dict(errno=value, errInfo={'no': value}))
    assert 'private-ticket' not in caplog.text
    assert str(2**100) not in caplog.text
    assert '"errno":' not in caplog.text
    assert '"exchange_code":' not in caplog.text


@pytest.mark.parametrize('raw', [b'<script>private-ticket</script>',
    b'other_callback({"errno":0,"secret":"private-ticket"});',
    b'bd__cbs__cupstt({});evil("private-ticket")', b'\xffprivate-ticket', b'x'*65537,
    b'['*8000+b']'*8000],
    ids=['html', 'foreign-callback', 'extra-script', 'invalid-utf8', 'oversize', 'deep-json'])
def test_probe_never_executes_or_logs_other_response_text(caplog, raw):
    pan_baidu._login_probe('exchange', Transport(), raw)
    assert '"envelope": "other"' in caplog.text
    assert 'private-ticket' not in caplog.text
    assert '"errno":' not in caplog.text


def test_probe_rejects_arbitrary_stage_before_accessing_session(caplog):
    pan_baidu._login_probe('private-ticket', None, {})
    assert not caplog.records
