"""One Host-owned adapter into ShareStream for authorized finite HTTP media."""
from functools import partial
from hashlib import sha256
import json
import re
from threading import Lock
from urllib.parse import urlencode, urlsplit

from bobbi_core.library_contract import LibraryError, direct_url
from bobbi_core.share_stream import ShareStream
from bobbi_core.t4 import ALLOWED_HEADERS
from .libraries import Registry
from .source_media_http import Session, evidence, probe_stream
from .t4_tokens import T4TokenStore

ALLOWED_STREAM_HEADER_NAMES = frozenset(ALLOWED_HEADERS.values()) | {'If-Match'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def local_media_url(result):
    if (
        not isinstance(result, dict)
        or not ({'size', 'url'} <= set(result) <= {'size', 'url', 'identity_mode'})
        or type(result['size']) is not int
        or not 0 < result['size'] < 2**63
        or type(result['url']) is not str
        or not re.fullmatch(
            r'http://127\.0\.0\.1:[0-9]{1,5}/stream/[0-9a-f]{32}/video\.[a-z0-9]+',
            result['url'],
        )
        or not 0 < urlsplit(result['url']).port <= 65535
    ):
        raise LibraryError('SOURCE_STREAM_INVALID')
    return result['url']


class SourceStreams:
    def __init__(self, root, current, session_factory=Session):
        self.root = root
        self.path, self.current = root / 'libraries.sqlite3', current
        self.token_db_path = root / 't4-tokens.sqlite3'
        self.sessions, self.lock = session_factory, Lock()
        self.transport, self.closed = None, False

    def _transport_sessions(self):
        if self.sessions is Session:
            return partial(Session, max_redirects=3)
        return self.sessions

    def source(self, body):
        if self.closed or not self.current():
            raise LibraryError('SOURCE_STREAM_CHANGED')
        store = Registry(self.path, read_only=True)
        try:
            source, version = store.source_snapshot(body['source_id'])
        finally:
            store.close()
        if version != body['generation']:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return source

    def resolve(self, body):
        source = self.source(body)
        selection = body['selection']
        if source.kind == 't4' and selection.get('kind') == 't4':
            from .t4_http import resolve_selected
            with T4TokenStore(self.token_db_path, read_only=True) as tstore:
                return resolve_selected(
                    source,
                    selection,
                    generation=body['generation'],
                    token_store=tstore,
                    cancelled=lambda: self.closed or not self.current(),
                )
        if source.kind == 'vfs' and set(selection) == {'kind', 'relative', 'observation'} and selection['kind'] == 'strm':
            from .source_pointers import read
            url, observation = read(source, selection['relative'])
            if observation != selection['observation']:
                raise LibraryError('SOURCE_STREAM_CHANGED')
            return url, {}, selection['relative'].rsplit('/', 1)[-1][:-5]
        raise LibraryError('SOURCE_STREAM_INVALID')

    def check(self, body):
        if body['selection']['kind'] == 'strm':
            self.resolve(body)  # Never follow a replaced pointer on a later seek.
        else:
            self.source(body)

    @staticmethod
    def check_reply(body, reply):
        mode = body.get('identity_mode', 'strong_etag')
        if mode == 'strong_etag':
            if evidence(reply, require_etag=True) != body['etag']:
                raise LibraryError('SOURCE_STREAM_CHANGED')
        else:
            evidence(reply, require_etag=False)
        actual_mime = reply.headers.get('Content-Type', '').partition(';')[0].strip().lower()
        if body.get('mime') and actual_mime != body['mime']:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        cr = reply.headers.get('Content-Range', '')
        match = re.fullmatch(r'bytes \d+-\d+/([1-9][0-9]{0,18})', cr)
        if not match or int(match[1]) != body['size']:
            raise LibraryError('SOURCE_STREAM_CHANGED')

    def grant(self, body):
        self.check(body)
        url, headers = body['upstream'], body['headers']
        if digest(url) != body['target'] or not self.headers(body, url, headers):
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return url + '|' + urlencode(headers)

    @staticmethod
    def headers(body, url, headers):
        if digest(url) != body['target'] or not (set(headers) <= ALLOWED_STREAM_HEADER_NAMES):
            return False
        mode = body.get('identity_mode', 'strong_etag')
        if mode == 'strong_etag':
            return headers.get('If-Match') == body['etag']
        # weak_session NEVER sends If-Match or If-Range (REV-10).
        return 'If-Match' not in headers and 'If-Range' not in headers

    def open(self, request):
        if (set(request) != {'request_id', 'source_id', 'generation', 'selection'} or
                any(type(request[k]) is not str or not re.fullmatch(pattern, request[k]) for k, pattern in (
                    ('request_id', '[a-f0-9]{32}'), ('source_id', '[a-f0-9]{32}'), ('generation', '[a-f0-9]{64}'))) or
                not isinstance(request['selection'], dict)):
            raise LibraryError('SOURCE_STREAM_INVALID')
        # Resolve outside the admission lock. Never transmit credentials or a
        # target URL across the runtime control socket or the Kodi plugin route.
        url, headers, _ = self.resolve(request)
        probed = probe_stream(
            url,
            {'User-Agent': 'BobbiTV', **headers},
            self.sessions,
            max_redirects=3,
            cancelled=lambda: self.closed or not self.current(),
        )
        size = probed['size']
        tag = probed['etag']
        identity_mode = probed['identity_mode']
        mime = probed['mime']
        key = digest([request['source_id'], request['generation'], request['selection']])
        ext = urlsplit(probed['final_url']).path.rsplit('.', 1)[-1].lower()
        if ext not in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'iso'):
            ext = urlsplit(url).path.rsplit('.', 1)[-1].lower()
        name = 'video.' + ext if ext in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'iso') else 'video.bin'
        stream_headers = {'User-Agent': 'BobbiTV', **headers}
        if identity_mode == 'strong_etag':
            stream_headers['If-Match'] = tag
        body = dict(
            request,
            locator='source:' + key,
            guid=key,
            media=key,
            title=name,
            size=size,
            etag=tag,
            mime=mime,
            identity_mode=identity_mode,
            target=digest(url),
            upstream=url,
            headers=stream_headers,
        )
        self.check(body)
        with self.lock:
            if self.closed:
                raise LibraryError('SOURCE_STREAM_CHANGED')
            if self.transport is None:
                # Only open() can construct a body. The transport is private
                # and never accepts caller-provided stream registration fields.
                self.transport = ShareStream(
                    lambda _: None,
                    self.grant,
                    direct_url,
                    body_check=lambda value: value,
                    header_check=self.headers,
                    session_factory=self._transport_sessions(),
                    observer=lambda _: None,
                    binding_check=self.check,
                    response_check=self.check_reply,
                )
            result = self.transport.register(body)
        self.check(body)
        return dict(url=result['url'], size=size, identity_mode=identity_mode)

    def close(self):
        with self.lock:
            self.closed, transport = True, self.transport
        if transport is not None:
            transport.close()
