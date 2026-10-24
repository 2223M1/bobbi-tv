"""Explicit, locator-free receipts for list-compatible provider results."""
from dataclasses import dataclass
import re


def provider_failed(record):
    """A limited/stale snapshot is not itself a failed network query."""
    if record.get('state') in ('FAILED', 'TIMEOUT'):
        return True
    if record.get('state') != 'PARTIAL':
        return False
    completion = record.get('completion')
    if isinstance(completion, dict):
        return any(type(completion.get(key)) is int and completion[key] > 0
                   for key in ('failed', 'timed_out'))
    # Older in-process adapters supplied the summary before structured receipts.
    return any(int(value) for value in re.findall(
        r'\b(?:failed|timed_out)=(\d+)\b', str(record.get('error') or '')))


def provider_diagnostics(providers):
    """Shared allowlisted projection for picker logs and opt-in user reports."""
    names = {'setup', 'coordinator', 'preferred', 'local-entry', '115-local-index',
             '漫迪 mdsub', 'qqdocs', 'juku', 'jackett', 'animegarden'}
    states = {'COMPLETE', 'PARTIAL', 'FAILED', 'TIMEOUT', 'CANCELLED', 'PENDING', 'RUNNING'}
    errors = {'ValueError', 'TypeError', 'KeyError', 'AttributeError', 'RuntimeError',
              'ImportError', 'ModuleNotFoundError', 'JukuError', 'ShareError', 'TimeoutError',
              'OperationalError', 'OSError', 'ConnectionError', 'ReadTimeout', 'ConnectTimeout',
              'HTTPError', 'CANDIDATE_CAPACITY_EXCEEDED', 'SEARCH_DEADLINE', 'PREVIOUS_SEARCH_IO_BUSY',
              'RETRY_PROVIDER_UNAVAILABLE'}
    result = []
    for provider, record in list(providers.items())[:40]:
        provider = provider if isinstance(provider, str) else ''
        record = record if isinstance(record, dict) else {}
        name, _, ordinal = provider.rpartition(':')
        if not name or not ordinal.isdecimal():
            name, ordinal = provider, ''
        name = name.casefold()
        state, error = record.get('state'), record.get('error')
        row = dict(provider=name if name in names else 'other',
                   ordinal=int(ordinal) if ordinal and len(ordinal) < 4 else 0,
                   state=state if isinstance(state, str) and state in states else 'UNKNOWN',
                   error=error if isinstance(error, str) and error in errors else '')
        count = record.get('count')
        row['count'] = count if type(count) is int and 0 <= count <= 4096 else 0
        completion = record.get('completion') or {}
        completion = completion if isinstance(completion, dict) else {}
        row['completion'] = {key:value for key,value in completion.items()
                             if key in ('planned','succeeded','failed','timed_out','skipped','stale','truncated')
                             and type(value) is int and 0 <= value <= 65536}
        age = completion.get('snapshot_age')
        if type(age) is int and 0 <= age <= 2147483647:
            row['completion']['snapshot_age'] = age
        result.append(row)
    return result


@dataclass(frozen=True)
class SearchCompletion:
    planned: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    timed_out: int = 0
    stale: int = 0
    truncated: int = 0
    snapshot_age: int = 0

    def __post_init__(self):
        counts = (self.planned, self.succeeded, self.failed, self.skipped, self.timed_out,
                  self.stale, self.truncated, self.snapshot_age)
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError('Nonnegative integer query counts required')
        if self.planned != self.succeeded + self.failed + self.skipped + self.timed_out:
            raise ValueError('Every planned query requires a terminal outcome')

    @property
    def complete(self):
        return not (self.failed or self.skipped or self.timed_out or self.stale or self.truncated)

    @property
    def state(self):
        if self.complete:
            return 'COMPLETE'
        if self.succeeded:
            return 'PARTIAL'
        return 'FAILED' if self.failed else 'TIMEOUT'

    def combine(self, other):
        return SearchCompletion(self.planned + other.planned,
            self.succeeded + other.succeeded, self.failed + other.failed,
            self.skipped + other.skipped, self.timed_out + other.timed_out,
            self.stale + other.stale, self.truncated + other.truncated,
            max(self.snapshot_age, other.snapshot_age))

    def with_parse_failures(self, count):
        if type(count) is not int or not 0 <= count <= self.succeeded:
            raise ValueError('Parse failures must be an integer within successful query count')
        return SearchCompletion(self.planned, self.succeeded - count,
                                self.failed + count, self.skipped, self.timed_out,
                                self.stale, self.truncated, self.snapshot_age)

    def summary(self):
        return 'queries={}/{} failed={} skipped={} timed_out={} stale={} truncated={} snapshot_age={}'.format(
            self.succeeded, self.planned, self.failed, self.skipped, self.timed_out,
            self.stale, self.truncated, self.snapshot_age)


class SearchResults(list):
    """Legacy iteration/truthiness stay unchanged; never infer receipt from rows."""
    def __init__(self, rows=(), completion=None):
        super().__init__(rows)
        if not isinstance(completion, SearchCompletion):
            raise ValueError('Explicit completion receipt required')
        self.completion = completion


def replace_rows(original, rows):
    return (SearchResults(rows, original.completion)
            if isinstance(original, SearchResults) else rows)
