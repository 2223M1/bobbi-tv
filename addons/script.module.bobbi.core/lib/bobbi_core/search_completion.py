"""Explicit, locator-free receipts for list-compatible provider results."""
from dataclasses import dataclass


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
