"""One Host-owned adapter into ShareStream for authorized finite HTTP media."""
from hashlib import sha256
import json
import re
from threading import Lock
from urllib.parse import urlencode, urlsplit

from bobbi_core.library_contract import LibraryError, direct_url
from bobbi_core.share_stream import ShareStream
from .libraries import Registry
from .source_media_http import Session, evidence, probe


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def local_media_url(result):
    if (not isinstance(result, dict) or set(result) != {'size', 'url'} or type(result['size']) is not int or
            not 0 < result['size'] < 2**63 or type(result['url']) is not str or not re.fullmatch(
                r'http://127\.0\.0\.1:[0-9]{1,5}/stream/[0-9a-f]{32}/video\.[a-z0-9]+', result['url'])
            or not 0 < urlsplit(result['url']).port <= 65535):
        raise LibraryError('SOURCE_STREAM_INVALID')
    return result['url']


class SourceStreams:
    def __init__(self, root, current, session_factory=Session):
        self.path, self.current = root / 'libraries.sqlite3', current
        self.sessions, self.lock = session_factory, Lock()
        self.transport, self.closed = None, False

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
            return resolve_selected(source, selection, cancelled=lambda: self.closed or not self.current())
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
        if evidence(reply) != body['etag']:
            raise LibraryError('SOURCE_STREAM_CHANGED')

    def grant(self, body):
        self.check(body)
        url, headers = body['upstream'], body['headers']
        if digest(url) != body['target'] or not self.headers(body, url, headers):
            raise LibraryError('SOURCE_STREAM_CHANGED')
        return url + '|' + urlencode(headers)

    @staticmethod
    def headers(body, url, headers):
        return (digest(url) == body['target'] and set(headers) <= {'User-Agent', 'Referer', 'If-Match'}
                and headers.get('If-Match') == body['etag'])

    def open(self, request):
        if (set(request) != {'request_id', 'source_id', 'generation', 'selection'} or
                any(type(request[k]) is not str or not re.fullmatch(pattern, request[k]) for k, pattern in (
                    ('request_id', '[a-f0-9]{32}'), ('source_id', '[a-f0-9]{32}'), ('generation', '[a-f0-9]{64}'))) or
                not isinstance(request['selection'], dict)):
            raise LibraryError('SOURCE_STREAM_INVALID')
        # Resolve outside the admission lock. Never transmit credentials or a
        # target URL across the runtime control socket or the Kodi plugin route.
        url, headers, _ = self.resolve(request)
        size, tag = probe(url, {'User-Agent': 'BobbiTV', **headers}, self.sessions)
        key = digest([request['source_id'], request['generation'], request['selection']])
        ext = urlsplit(url).path.rsplit('.', 1)[-1].lower()
        name = 'video.' + ext if ext in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'iso') else 'video.bin'
        body = dict(request, locator='source:' + key, guid=key, media=key, title=name,
                    size=size, etag=tag, target=digest(url), upstream=url,
                    headers={'User-Agent': 'BobbiTV', **headers, 'If-Match': tag})
        self.check(body)
        with self.lock:
            if self.closed:
                raise LibraryError('SOURCE_STREAM_CHANGED')
            if self.transport is None:
                # Only open() can construct a body. The transport is private
                # and never accepts caller-provided stream registration fields.
                self.transport = ShareStream(lambda _: None, self.grant, direct_url,
                    body_check=lambda value: value, header_check=self.headers, session_factory=self.sessions,
                    observer=lambda _: None, binding_check=self.check, response_check=self.check_reply)
            result = self.transport.register(body)
        self.check(body)
        return dict(url=result['url'], size=size)

    def close(self):
        with self.lock:
            self.closed, transport = True, self.transport
        if transport is not None:
            transport.close()
