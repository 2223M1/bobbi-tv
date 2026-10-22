"""Retain container routing without granting a URL or reading remote media."""
import re
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core.share_stream import ShareStream


@pytest.mark.parametrize('suffix,expected', [
    ('iso', 'iso'), ('ISO', 'iso'), ('mkv', 'mkv'), ('mp4', 'mp4'),
    ('unknown', 'bin'), ('iso?redirect=1', 'bin'),
])
def test_registered_stream_retains_supported_container(suffix, expected):
    calls = []
    service = ShareStream(lambda body: calls.append('validate'),
                          lambda body: calls.append('resolve'), lambda url: True)
    body = dict(request_id='a'*32, locator='am6bjuku://'+'b'*64,
                guid='juku:'+'b'*64, title='Fixture.Movie.2024.'+suffix,
                size=95095816192, media='movies:655:0:0')
    try:
        ready = service.register(body)
        assert re.fullmatch('/stream/[a-f0-9]{32}/video\\.'+expected,
                            urlsplit(ready['url']).path)
        assert ready['bytes'] == body['size']
        assert calls == ['validate']  # Reservation cannot probe/download media.
        entry = service.records[body['request_id']]
        assert entry.body == body and entry.address is None
        assert service.register(body)['url'] == ready['url']
    finally:
        service.close()
