"""Kodi-independent adapter of the installed Stremio subtitle protocol.

Runs only in the preparation worker. Responses are candidates, never proof of
episode identity, dialogue completeness, timeline alignment or font readiness.
URLs stay in memory; callers persist only origin, bytes and separate evidence.
"""
import hashlib
import json
import re
import time

from bobbi_core.http_policy import build_resource_url, is_safe_http_url, request_with_safe_redirects
from bobbi_core.subtitle_language import CHINESE_CODES
from bobbi_core.subtitle_binding import MAX_SUBTITLE_BYTES, content_summary

LOOKUP_SECONDS = 5.0
MAX_RECORDS = 1000
MAX_CANDIDATES = 3
JSON_BYTES = 1024 * 1024


class SubtitleFetchStopped(RuntimeError):
    pass


class StremioSubtitleProvider:
    def __init__(self, session, base_url, cancelled=lambda: False,
                 clock=time.monotonic, validator=is_safe_http_url):
        if not validator(base_url):
            raise ValueError('Configured subtitle provider must be public HTTP(S)')
        self.session, self.base = session, base_url.rstrip('/')
        self.cancelled, self.clock, self.validator = cancelled, clock, validator
        self.provider_key = hashlib.sha256(self.base.encode()).hexdigest()

    def _guard(self, deadline):
        if self.cancelled():
            raise SubtitleFetchStopped('CANCELLED')
        if self.clock() >= deadline:
            raise SubtitleFetchStopped('DEADLINE')

    def _bytes(self, url, limit, deadline):
        responses = []
        def get(target, **kwargs):
            self._guard(deadline)
            if responses:
                responses[-1].close()
            remaining = deadline - self.clock()
            response = self.session.get(target, timeout=(min(3.05, remaining), min(2.0, remaining)),
                                        stream=True, headers={'Accept-Encoding': 'identity'}, **kwargs)
            responses.append(response)
            self._guard(deadline)
            return response
        try:
            self._guard(deadline)
            response = request_with_safe_redirects(get, url, validator=self.validator)
            if response.status_code != 200:
                raise ValueError('SUBTITLE_HTTP_' + str(response.status_code))
            headers = response.headers
            if headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                raise ValueError('Unexpected compressed subtitle response')
            size = headers.get('Content-Length')
            if size is not None and (not str(size).isdigit() or not 1 <= int(size) <= limit):
                raise ValueError('Subtitle response length budget')
            raw = bytearray()
            for chunk in response.iter_content(8192):
                self._guard(deadline)
                if not chunk:
                    continue
                if not isinstance(chunk, bytes) or len(chunk) > 8192 or len(raw) + len(chunk) > limit:
                    raise ValueError('Subtitle response byte budget')
                raw.extend(chunk)
            self._guard(deadline)
            if not raw or (size is not None and len(raw) != int(size)):
                raise ValueError('Truncated or empty subtitle response')
            return bytes(raw)
        finally:
            for response in responses:
                response.close()

    def candidates(self, imdb_id, media_type, season=None, episode=None):
        if not isinstance(imdb_id, str) or not re.fullmatch(r'tt[0-9]{5,12}', imdb_id):
            raise ValueError('Authoritative IMDb identity required')
        if media_type == 'series':
            if type(season) is not int or type(episode) is not int or not 0 <= season <= 999 or not 1 <= episode <= 10000:
                raise ValueError('Explicit mapped season and episode required')
            identity = '{}:{}:{}'.format(imdb_id, season, episode)
        elif media_type == 'movie' and season is None and episode is None:
            identity = imdb_id
        else:
            raise ValueError('Explicit movie/series identity required')
        deadline = self.clock() + LOOKUP_SECONDS
        url = build_resource_url(self.base, 'subtitles', media_type, identity)
        data = json.loads(self._bytes(url, JSON_BYTES, deadline))
        if not isinstance(data, dict) or not isinstance(data.get('subtitles'), list) or len(data['subtitles']) > MAX_RECORDS:
            raise ValueError('Bounded subtitle provider records required')
        result, seen = [], set()
        for row in data['subtitles']:
            self._guard(deadline)
            if not isinstance(row, dict):
                continue
            language, target = row.get('lang'), row.get('url')
            if not isinstance(language, str) or language.lower().replace('_', '-') not in CHINESE_CODES:
                continue
            ident = row.get('id') or row.get('subId')
            if (type(ident) not in (str, int) or not 1 <= len(str(ident)) <= 256
                    or not isinstance(target, str) or len(target) > 8192 or not self.validator(target)):
                continue
            origin_id = hashlib.sha256((self.provider_key + ':' + str(ident)).encode()).hexdigest()
            if origin_id in seen:
                continue
            seen.add(origin_id)
            result.append(dict(url=target, language=language,
                               origin=dict(kind='provider', id=origin_id),
                               state='CANDIDATE_NOT_READY'))
            if len(result) == MAX_CANDIDATES:
                break
        return result

    def download(self, candidate, deadline=None):
        if (not isinstance(candidate, dict) or candidate.get('state') != 'CANDIDATE_NOT_READY'
                or candidate.get('origin', {}).get('kind') != 'provider'):
            raise ValueError('Provider candidate required')
        deadline = self.clock() + LOOKUP_SECONDS if deadline is None else min(deadline, self.clock() + LOOKUP_SECONDS)
        raw = self._bytes(candidate['url'], MAX_SUBTITLE_BYTES, deadline)
        # Reuse the installed text decoder/ASS parser, not URL extensions (many
        # providers use opaque routes). Archives/HTML cannot enter the cache.
        from bobbi_core.fonts import subtitle_text
        text = subtitle_text(raw).lstrip()
        if re.search(r'(?im)^\[Events\]\s*$', text):
            extension = '.ass' if '[V4+ Styles]' in text else '.ssa'
        elif text.startswith('WEBVTT'):
            extension = '.vtt'
        else:
            extension = '.srt'
        if text.startswith('<') or not content_summary(raw, extension)['verified']:
            raise ValueError('Unsupported subtitle body')
        return dict(raw=raw, extension=extension, language=candidate['language'],
                    origin=dict(candidate['origin']), subtitle_sha256=hashlib.sha256(raw).hexdigest(),
                    state='CANDIDATE_NOT_READY')
