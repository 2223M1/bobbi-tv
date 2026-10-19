"""HTTP transport is loaded only by consumers that make HTTP requests."""
import base64
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, proxy_bypass


class AuthenticatedProxyHandler(ProxyHandler):
    def proxy_open(self, req, proxy, type):
        if req.host and proxy_bypass(req.host):
            return None
        parsed = urlsplit(proxy)
        if parsed.username is not None:
            # HTTPSHandler moves this header into CONNECT, including empty passwords.
            credentials = unquote(parsed.username) + ':' + unquote(parsed.password or '')
            token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
            req.add_unredirected_header('Proxy-Authorization', 'Basic ' + token)
            proxy = parsed._replace(netloc=parsed.netloc.rsplit('@', 1)[1]).geturl()
        return super().proxy_open(req, proxy, type)
