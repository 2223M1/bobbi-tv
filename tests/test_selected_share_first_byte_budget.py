"""Only a selected file may use the remaining resolution budget for response headers."""
import io
from types import SimpleNamespace

import pytest
from test_ce2012_share_failure import Client, ShareError
from bobbi_catalog import api


@pytest.mark.parametrize('path,limit,lag,expected', [
    ('/os_linux/2.0/share/downurl',8,5.5,'ok'),
    ('/os_linux/2.0/share/downurl',2,2.5,'deadline'),
    ('/os_linux/2.0/share/downurl',30,8.1,'network_timeout'),
    ('/share/search',8,5.5,'network_timeout'),
    ('/share/snap',8,5.5,'network_timeout'),
])
def test_first_headers_not_one_more_request_or_a_new_deadline(monkeypatch,path,limit,lag,expected):
    clock=[100.0]
    monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda:clock[0]))
    calls=[]
    def header(req, timeout):
        calls.append(timeout)
        clock[0] += min(timeout,lag)
        if timeout < lag:
            raise TimeoutError
        return io.BytesIO(b'{"state":true,"data":{"fixture":1}}')
    client=Client.__new__(Client)
    client.ua,client.cookie='fixture','test';client.opener=SimpleNamespace(open=header)
    args=(path,{'code':'dummy','password':'dummy'},{},100+limit)
    if expected=='ok':
        assert client.get(*args)=={'fixture':1}
    else:
        with pytest.raises(ShareError) as caught:client.get(*args)
        assert caught.value.code==expected
    assert calls == [min(limit,8 if path.endswith('/downurl') else 4)]
