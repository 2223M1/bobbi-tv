"""Bounded, request-local observations; never a search/cache completion contract.

The owning interpreter records process IPC events. Snapshots/logging happen
after child termination/reaping; diagnostics do not perform network I/O.
Cancellation observability is explicit when the caller supplies its guard.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


_PROVIDERS = frozenset(('nyaasi', 'dmhy', 'mikan', 'mikanani', 'acgrip',
                       'bangumimoe', 'acgnx', 'tokyotosho', 'knaben'))
_QUERY_KINDS = frozenset(('search', 'tvsearch', 'movie'))
_LIMIT = 256
_QUERY_FIELDS = frozenset(('q', 't', 'season', 'ep', 'year', 'cat', 'tmdbid', 'imdbid'))
_CREDENTIAL_FIELDS = frozenset(('apikey', 'api_key', 'key', 'token', 'access_token',
    'password', 'passwd', 'pass', 'cookie', 'secret', 'username', 'user', 'authorization', 'auth'))


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _digest(domain, value):
    return hashlib.sha256((domain + '\n' + _canonical(value)).encode('utf-8')).hexdigest()


def _text_fp(value):
    if type(value) is not str or not 0 < len(value) <= 2048:
        return None
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError:
        return None
    return _digest('fanout-text-v2', value)


def _strict_url_query(url):
    # urlsplit strips some raw control characters; unquote normally replaces
    # invalid UTF-8. Reject both before they can collapse distinct requests.
    if re.search(r'[\x00-\x1f\x7f-\x9f]', url) or re.search(r'%(?![0-9A-Fa-f]{2})', url):
        raise ValueError('Unsupported diagnostic URL encoding')
    url.encode('utf-8', errors='strict')
    parsed = urlsplit(url)
    return parsed, parse_qs(parsed.query, keep_blank_values=True, max_num_fields=128,
                            encoding='utf-8', errors='strict')


def _checked_ref_values(invocation_id, scope_id, plan_id, fingerprint_coverage):
    values = dict(invocation_id=invocation_id, scope_id=scope_id, plan_id=plan_id,
                  fingerprint_coverage=fingerprint_coverage)
    for field, length in (('invocation_id', 32), ('scope_id', 64), ('plan_id', 64)):
        value = values[field]
        if type(value) is not str or not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
            raise ValueError('Invalid diagnostic reference')
    if (type(fingerprint_coverage) is not str or fingerprint_coverage not in
            ('allowlisted_fields_only', 'partial_or_unsupported')):
        raise ValueError('Invalid diagnostic reference coverage')
    return values


def _number(value, low, high):
    if value is None:
        return None, 'missing'
    if type(value) is int or (isinstance(value, str) and re.fullmatch(r'[0-9]{1,12}', value)):
        number = int(value)
        if low <= number <= high:
            return number, 'present'
    return None, 'invalid'


def _imdb(value):
    if value is None:
        return None, 'missing'
    return ((value, 'present') if isinstance(value, str) and re.fullmatch(r'tt[0-9]{7,12}', value)
            else (None, 'invalid'))


def _alias_fps(values, languages=False):
    if not isinstance(values, (list, tuple)):
        return dict(state='invalid', entries=[], omitted=None)
    entries = []
    invalid = False
    for value in values[:16]:
        if languages:
            language, text = value if isinstance(value, (list, tuple)) and len(value) == 2 else (None, None)
            language_fp = (_digest('fanout-language-v2', language) if isinstance(language, str)
                           and re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,15}', language) else None)
            title_fp = _text_fp(text)
            invalid = invalid or language_fp is None or title_fp is None
            entries.append(dict(language=language if language in ('en', 'ja', 'zh', 'zh-CN', 'zh-TW', 'unknown')
                                else 'other', language_fp=language_fp, title_fp=title_fp))
        else:
            entries.append(_text_fp(value))
            invalid = invalid or entries[-1] is None
    return dict(state='bounded' if len(values) > 16 else 'invalid' if invalid else 'observed',
                entries=entries, omitted=max(0, len(values) - 16))


@dataclass(frozen=True)
class SearchScope:
    scope_id: str
    # Canonical JSON contains only safe scalar/hashed fields, never raw titles.
    serialized: str


@dataclass(frozen=True)
class DiagnosticRef:
    invocation_id: str
    scope_id: str
    plan_id: str
    fingerprint_coverage: str

    def __post_init__(self):
        _checked_ref_values(self.invocation_id, self.scope_id, self.plan_id, self.fingerprint_coverage)


class FanoutPlan(list):
    """Internal list-compatible carrier, not a new transport call parameter."""
    def __init__(self, urls, scope):
        super().__init__(urls)
        self.scope = scope


def make_plan(urls, query, mode, season, episode, year, title_queries=(),
              anime_title_queries=(), anime_absolute_query='', anime_release_query='',
              movie_tmdb_id=None, movie_imdb_id=None):
    try:
        kind = mode if mode in ('tv', 'movies') else 'unknown'
        scope = dict(kind=kind, primary_query_fp=_text_fp(query),
            title_queries=_alias_fps(title_queries), anime_title_queries=_alias_fps(anime_title_queries, True),
            anime_absolute_query_fp=_text_fp(anime_absolute_query),
            anime_release_query_fp=_text_fp(anime_release_query),
            tv_tmdb_id=None, tv_identity_basis='not_received', caller_role='unavailable')
        for name, value, low, high in (('year', year, 1800, 3000),
                ('release_season', season, 0, 999), ('release_episode', episode, 0, 9999)):
            scope[name], scope[name + '_state'] = _number(value, low, high)
        if kind == 'movies':
            scope['movie_tmdb_id'], scope['movie_tmdb_id_state'] = _number(movie_tmdb_id, 1, 999999999999)
            scope['movie_imdb_id'], scope['movie_imdb_id_state'] = _imdb(movie_imdb_id)
        else:
            scope.update(movie_tmdb_id=None, movie_tmdb_id_state='not_applicable',
                         movie_imdb_id=None, movie_imdb_id_state='not_applicable')
        incomplete = (scope['primary_query_fp'] is None or kind == 'unknown'
            or scope['title_queries']['state'] != 'observed'
            or scope['anime_title_queries']['state'] != 'observed'
            or any(value == 'invalid' for key, value in scope.items() if key.endswith('_state'))
            or any(value is not None and (type(value) is not str or
                   (value != '' and scope[field] is None)) for value, field in (
                       (anime_absolute_query, 'anime_absolute_query_fp'),
                       (anime_release_query, 'anime_release_query_fp'))))
        scope['fingerprint_coverage'] = 'bounded_input_subset' if incomplete else 'observed_inputs'
        return FanoutPlan(urls, SearchScope(_digest('fanout-scope-v2', scope), _canonical(scope)))
    except Exception:
        return urls


def _query_identity(url):
    result = dict(provider_ref=None, query_fp=None, query_identity_state='unsupported',
                  unrepresented_fields=None)
    if type(url) is not str or len(url) > 8192:
        return result
    try:
        parsed, parameters = _strict_url_query(url)
        match = re.fullmatch(r'/api/v2[.]0/indexers/([a-zA-Z0-9_-]{1,128})/results/torznab/api/?', parsed.path)
        if not match:
            return result
        provider = match.group(1)
        result['provider_ref'] = provider if provider in _PROVIDERS else _digest('fanout-provider-v2', provider)
        selected = {key: values for key, values in parameters.items() if key in _QUERY_FIELDS}
        if not selected or any(len(values) > 8 or any(len(value) > 2048 for value in values)
                               for values in selected.values()):
            return result
        result.update(query_fp=_digest('fanout-query-v2', selected),
            query_identity_state='allowlisted_fields_only',
            unrepresented_fields=sum(len(values) for key, values in parameters.items()
                                     if key not in _QUERY_FIELDS and key.casefold() not in _CREDENTIAL_FIELDS))
    except (ValueError, UnicodeError):
        pass
    return result


def observe(receipt, method, *args, **kwargs):
    """Only diagnostic failures are suppressed; transport/parser calls stay outside."""
    try:
        if isinstance(receipt, FanoutReceipt):
            return getattr(receipt, method)(*args, **kwargs)
    except Exception:
        try:
            key = method if method in ('enqueue', 'start', 'terminal', 'bind_responses',
                'parse_start', 'parse_end', 'aborted', 'emit', 'reference') else 'other'
            receipt._diagnostic_errors[key] = receipt._diagnostic_errors.get(key, 0) + 1
        except Exception:
            pass
    return None


def new_receipt(urls):
    try:
        return FanoutReceipt(urls.scope if isinstance(urls, FanoutPlan) else None)
    except Exception:
        return None


def transport_tasks(urls, receipt):
    for ordinal, url in enumerate(urls):
        try:
            receipt._planned = ordinal + 1
        except Exception:
            pass
        yield ordinal, url, observe(receipt, 'enqueue', ordinal, url)


def observe_owner(result, query, ids, mode, year, requested_pair, release_pair):
    """Consume the exact returned reference before existing result rebuilds.

    Argument identity is not catalogue verification, GUI ownership, or playback.
    A result lacking a valid ref is left unclaimed, never matched to nearby logs.
    """
    try:
        ref = getattr(result, 'fanout_diagnostic_ref', None)
        if not isinstance(ref, DiagnosticRef):
            return
        # Validate a single scalar snapshot, then serialize only that snapshot.
        # Frozen dataclasses can still be corrupted through object.__setattr__.
        reference = _checked_ref_values(ref.invocation_id, ref.scope_id, ref.plan_id,
                                        ref.fingerprint_coverage)
        owner = dict(identity_basis='search_arguments', caller_role='unavailable',
                     kind=mode if mode in ('tv', 'movies') else 'unknown', query_fp=_text_fp(query))
        owner['tmdb_id'], owner['tmdb_id_state'] = _number(ids.get('tmdb_id') if isinstance(ids, dict) else None, 1, 999999999999)
        owner['imdb_id'], owner['imdb_id_state'] = _imdb(ids.get('imdb_id') if isinstance(ids, dict) else None)
        owner['year'], owner['year_state'] = _number(year, 1800, 3000)
        for prefix, pair in (('requested', requested_pair), ('release', release_pair)):
            for index, name, high in ((0, 'season', 999), (1, 'episode', 9999)):
                value = pair[index] if isinstance(pair, (list, tuple)) and len(pair) > index and mode == 'tv' else None
                field = prefix + '_' + name
                owner[field], owner[field + '_state'] = _number(value, 0, high)
        from lib.jacktook.utils import kodilog
        kodilog('FANOUT-OWNER ' + _canonical(dict(schema=2, owner=owner, **reference)))
    except Exception:
        pass


def _labels(url):
    provider, kind = 'configured_other', 'other'
    if type(url) is not str or len(url) > 8192:
        return provider, kind
    try:
        parsed, parameters = _strict_url_query(url)
        parts = parsed.path.split('/')
        if len(parts) == 9 and parts[1:4] == ['api', 'v2.0', 'indexers']:
            if parts[5:] == ['results', 'torznab', 'api', '']:
                provider = parts[4] if parts[4] in _PROVIDERS else provider
        elif len(parts) == 8 and parts[1:4] == ['api', 'v2.0', 'indexers']:
            if parts[5:] == ['results', 'torznab', 'api']:
                provider = parts[4] if parts[4] in _PROVIDERS else provider
        values = parameters.get('t', [])
        if len(values) == 1 and values[0] in _QUERY_KINDS:
            kind = values[0]
    except (ValueError, UnicodeError):
        pass
    return provider, kind


class FanoutReceipt:
    """Ordinal ownership avoids response-object reuse and timestamp guessing."""
    def __init__(self, scope=None):
        self.invocation_id = uuid4().hex
        self.scope = scope if isinstance(scope, SearchScope) else None
        self._origin = time.perf_counter()
        self._records = []
        self._planned = 0
        self._parse_rows = {}
        self._emitted = False
        self._diagnostic_errors = {}

    def _elapsed(self):
        return round(max(0.0, time.perf_counter() - self._origin) * 1000, 3)

    def tasks(self, urls):
        yield from transport_tasks(urls, self)

    def enqueue(self, ordinal, url):
        if ordinal >= _LIMIT:
            return None
        provider, kind = _labels(url)
        row = dict(ordinal=ordinal, provider=provider, query_kind=kind,
            enqueued_ms=self._elapsed(), started_ms=None, ended_ms=None,
            transport='not_started', reason='not_started', http_status=None,
            parse='not_attempted', parse_started_ms=None,
            parse_ended_ms=None, parsed_count=None)
        row.update(_query_identity(url))
        self._records.append(row)
        return row

    def start(self, row):
        if row is not None:
            row.update(started_ms=self._elapsed(), transport='running')

    def terminal(self, row, state, reason, status=None):
        if row is not None:
            row.update(ended_ms=self._elapsed(), transport=state, reason=reason,
                http_status=status if type(status) is int and 100 <= status <= 599 else None)

    def bind_responses(self, outcomes):
        rows = {row['ordinal']: row for row in self._records}
        index = 0
        for ordinal, (_, response) in enumerate(outcomes):
            if response is not None:
                if ordinal in rows:
                    self._parse_rows[index] = rows[ordinal]
                index += 1

    def parse_start(self, index):
        row = self._parse_rows.get(index)
        if row is not None:
            row.update(parse='running', parse_started_ms=self._elapsed())

    def parse_end(self, index, parsed=None, exception=False):
        row = self._parse_rows.get(index)
        if row is not None:
            row.update(parse_ended_ms=self._elapsed(),
                parse='exception' if exception else 'invalid' if parsed is None else 'succeeded',
                parsed_count=len(parsed) if isinstance(parsed, (list, tuple)) else None)

    def aborted(self):
        # map() may cancel unstarted futures on an exception. No UI-cancel
        # signal exists here, so do not call those tasks user-cancelled.
        for row in self._records:
            if row['transport'] == 'not_started':
                self.terminal(row, 'unobserved_after_abort', 'transport_aborted_before_start')

    def snapshot(self, stage):
        plan_id, coverage = self._plan_identity()
        return dict(schema=2, invocation_id=self.invocation_id,
            scope_id=self.scope.scope_id if self.scope is not None else None,
            scope=json.loads(self.scope.serialized) if self.scope is not None else None,
            plan_id=plan_id, fingerprint_coverage=coverage,
            diagnostic_errors=dict(self._diagnostic_errors),
            stage=stage if stage in ('transport_complete', 'parse_complete',
                'transport_exception', 'parse_exception') else 'unknown',
            user_cancel_observability=getattr(self, 'user_cancel_observability', 'unavailable'), planned=self._planned,
            omitted_records=max(0, self._planned - len(self._records)),
            elapsed_ms=self._elapsed(), records=[dict(row) for row in self._records])

    def _plan_identity(self):
        complete = (not self._diagnostic_errors and len(self._records) == self._planned and all(
            row['query_fp'] is not None and row['provider_ref'] is not None for row in self._records))
        values = [(row['ordinal'], row['provider_ref'], row['query_fp'], row['unrepresented_fields'])
                  for row in self._records]
        return (_digest('fanout-plan-v2', dict(planned=self._planned, records=values)),
                'allowlisted_fields_only' if complete else 'partial_or_unsupported')

    def reference(self):
        if self.scope is not None:
            plan_id, coverage = self._plan_identity()
            return DiagnosticRef(self.invocation_id, self.scope.scope_id, plan_id, coverage)

    def emit(self, stage):
        if self._emitted:
            return
        self._emitted = True
        try:
            from lib.jacktook.utils import kodilog
            kodilog('FANOUT-TERMINAL ' + json.dumps(self.snapshot(stage),
                ensure_ascii=True, separators=(',', ':')))
        except Exception:
            # An optional diagnostic must not replace a result or exception.
            pass
