"""Transport-neutral validation for user-configured source and finite-media addresses."""
import ipaddress
import re
from urllib.parse import quote, urlsplit

from .library_contract import LibraryError, _text


def endpoint(url, code='SOURCE_HTTP_URL'):
    """Allow explicit household HTTP endpoints; never accept device-local service URLs."""
    try:
        _text(url, 8192)
        u = urlsplit(url)
        host = u.hostname or ''
        if (u.scheme not in ('https', 'http') or not host or u.username is not None or
                u.password is not None or u.fragment or u.netloc.endswith(':') or u.port == 0
                or re.search(r'[\s\\|]', url) or '%' in host or not host.isascii()):
            raise ValueError()
        host = host.rstrip('.').lower()
        ip = None
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', host):
                raise ValueError() from None
            if re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*', host):
                raise ValueError() from None
        if ip is not None:
            ip = getattr(ip, 'ipv4_mapped', None) or ip
            if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local or ip.is_reserved:
                raise ValueError()
        if (host == 'localhost' or host.endswith('.localhost') or u.scheme == 'http' and
                not (ip is not None and ip.is_private or host.endswith(('.local', '.lan', '.home.arpa')))):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise LibraryError(code) from None
    # Only percent-encode Unicode octets. Preserve existing % escapes, signatures
    # and separators in paths or queries; never unquote opaque provider IDs.
    return ''.join(ch if ch.isascii() else quote(ch, safe='') for ch in url)
