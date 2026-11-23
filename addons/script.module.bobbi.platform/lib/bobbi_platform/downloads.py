"""Bounded TLS-only release downloader for the coordinated update engine."""
import time
from urllib.error import HTTPError, URLError
from urllib.request import (Request, HTTPRedirectHandler, HTTPSHandler,
                            ProxyHandler, build_opener)
from .updates import allowed_release_url, allowed_release_redirect, MAX_REDIRECTS, UpdateError


class _Redirects(HTTPRedirectHandler):
    def __init__(self, deadline, clock):
        super().__init__()
        self.count, self.deadline, self.clock = 0, deadline, clock

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        remaining = self.deadline - self.clock()
        if (self.count > MAX_REDIRECTS or remaining <= 0
                or not allowed_release_redirect(newurl)):
            raise UpdateError('Rejected release redirect or expired download budget')
        req.timeout = min(getattr(req, 'timeout', 10), remaining)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, max_bytes, *, budget=90, clock=time.monotonic, opener_factory=build_opener):
    if not allowed_release_url(url):
        raise UpdateError('Invalid release download URL')
    if type(max_bytes) is not int or not 0 < max_bytes <= 128 * 1024 * 1024:
        raise UpdateError('Invalid release byte limit')
    if type(budget) not in (int, float) or not 0 < budget <= 180:
        raise UpdateError('Invalid download time budget')
    deadline = clock() + budget
    opener = opener_factory(ProxyHandler({}), HTTPSHandler(), _Redirects(deadline, clock))
    request = Request(url, headers={'User-Agent': 'bobbi-tv-updater/0.1', 'Accept-Encoding': 'identity'})
    try:
        with opener.open(request, timeout=min(10, budget)) as response:
            if response.status != 200 or not allowed_release_redirect(response.geturl()):
                raise UpdateError('Unexpected release response')
            length = response.headers.get('Content-Length')
            if length and (not length.isdigit() or int(length) > max_bytes):
                raise UpdateError('Release exceeds byte limit')
            encoding = response.headers.get('Content-Encoding', 'identity')
            if encoding not in ('', 'identity'):
                raise UpdateError('Unexpected release content encoding')
            result = bytearray()
            while len(result) <= max_bytes:
                if clock() >= deadline:
                    raise UpdateError('Download time budget exceeded')
                # read1 does at most one buffered socket read. Per-read timeout
                # is <=10s; wall budget can overshoot by at most that read.
                read = getattr(response, 'read1', response.read)
                chunk = read(min(65536, max_bytes + 1 - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
                if len(result) > max_bytes:
                    raise UpdateError('Release exceeds byte limit')
            if clock() >= deadline or length and len(result) != int(length):
                raise UpdateError('Truncated or over-budget release')
            return bytes(result)
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise UpdateError('Release transport failed: ' + type(error).__name__) from None
