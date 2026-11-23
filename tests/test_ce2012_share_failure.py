"""Actual API and stream error boundary: fixed categories, no signed URLs/body."""
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest
for name in ('script.module.bobbi.core','script.module.bobbi.catalog'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addons'/name/'lib'))
from bobbi_catalog.api import Client, ShareError
from bobbi_core.share_stream import observation_error, observation_fields


@pytest.mark.parametrize('raw,expected', [
    (b'{"state":false,"errno":4100010,"error":"private body"}', 'share_revoked'),
    (b'{"state":false,"errno":99}', 'login_required'),
    (b'{"state":false,"errno":12345}', 'share_unavailable'),
    (b'not-json-private-body', 'invalid_response'),
    (b'[]', 'invalid_response'),
])
def test_actual_api_rejection_categories(raw, expected):
    class Reply(io.BytesIO):
        headers = {'Content-Length': str(len(raw))}
        def read1(self,n): return self.read(n)
    client = Client.__new__(Client)
    client.ua, client.cookie = 'fixture', 'sensitive-cookie'
    client.opener = SimpleNamespace(open=lambda *a,**kw: Reply(raw))
    with pytest.raises(ShareError) as caught:
        client.get('/os_linux/2.0/share/downurl', {'code':'fixture','password':'private'}, {}, time.monotonic()+2)
    assert caught.value.code == expected
    reason, fields = observation_error(caught.value)
    receipt = json.dumps(observation_fields(dict(reason=reason,**fields)))
    assert expected in receipt
    assert not any(secret in receipt for secret in ('private','sensitive','Cookie','http://'))
    if expected == 'share_revoked': assert fields['api_code'] == 4100010


@pytest.mark.parametrize('error,expected', [
    (ShareError('identity_changed'),'share_identity_changed'),
    (ShareError('invalid_locator'),'share_invalid_locator'),
    (ShareError('network_timeout'),'share_network_timeout'),
    (ShareError('http_rejected',http_status=403),'share_http_rejected'),
    (KeyError('https://private.invalid/?token=secret'),'unexpected_exception'),
])
def test_stream_categories_keep_correlation_without_body(error,expected):
    reason, extra = observation_error(error)
    row = observation_fields(dict(reason=reason,request='a'*16,file='b'*64,stage='grant',**extra))
    assert row['reason'] == expected and row['request'] == 'a'*16 and row['file'] == 'b'*64
    assert 'secret' not in json.dumps(row)
