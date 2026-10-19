"""Explicit short-lived same-device pairing, no LAN listener or URL secrets."""
import re
from urllib.request import Request, build_opener, ProxyHandler
from .runtime import NoRedirect
from .pairing import from_export


def exchange(code, opener=None):
    if not isinstance(code, str) or re.fullmatch('[0-9]{6}', code) is None:
        raise ValueError('Enter the six-digit code shown by the helper')
    request = Request('http://127.0.0.1:8091/pair', data=code.encode('ascii'),
                      headers={'Content-Type': 'text/plain'})
    with (opener or build_opener(ProxyHandler({}), NoRedirect())).open(request, timeout=3) as response:
        raw = response.read(4097)
    return from_export(raw)
