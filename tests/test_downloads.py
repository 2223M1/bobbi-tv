import io
import pytest
from bobbi_platform.downloads import fetch, _Redirects
from bobbi_platform.updates import UpdateError

URL = 'https://github.com/2223M1/bobbi-tv/releases/download/v0.1.0/package.zip'
CDN = 'https://release-assets.githubusercontent.com/example/package.zip?signature=example'


class Response(io.BytesIO):
    status = 200
    def __init__(self, data, headers=None, url=CDN):
        super().__init__(data)
        self.headers = headers or {}
        self.url = url
    def geturl(self):
        return self.url


def factory(response):
    class Opener:
        def open(self, req, timeout):
            assert timeout <= 10
            assert req.get_header('Accept-encoding') == 'identity'
            return response
    return lambda *handlers: Opener()


def test_actual_github_cdn_shape_and_byte_budget():
    assert fetch(URL, 3, opener_factory=factory(Response(b'zip'))) == b'zip'


@pytest.mark.parametrize('response', [
    Response(b'toolong'), Response(b'zip', {'Content-Length': '9'}),
    Response(b'zip', {'Content-Length': '2'}), Response(b'zip', {'Content-Encoding': 'gzip'}),
    Response(b'zip', url='https://example.com/x'),
])
def test_bad_responses_fail_closed(response):
    with pytest.raises(UpdateError):
        fetch(URL, 3, opener_factory=factory(response))


def test_initial_url_not_allowed_to_use_arbitrary_cdn():
    with pytest.raises(UpdateError):
        fetch(CDN, 3, opener_factory=lambda *x: pytest.fail('must not open'))


def test_http_redirect_cannot_escape_tls_or_repository():
    from urllib.request import Request
    handler = _Redirects(100, lambda: 0)
    req = Request(URL)
    req.timeout = 10
    with pytest.raises(UpdateError):
        handler.redirect_request(req, None, 302, 'Found', {}, 'http://example.com/file.zip')


def test_time_budget_expires():
    ticks = iter([0, 100])
    with pytest.raises(UpdateError):
        fetch(URL, 3, budget=90, clock=lambda: next(ticks), opener_factory=factory(Response(b'zip')))
