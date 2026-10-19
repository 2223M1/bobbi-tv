"""Local written/phonetic similarity; scores are heuristics, not probabilities."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from .command_rules import number

AUTO_SCORE = .90
AUTO_MARGIN = .08
CHOICE_SCORE = .55


def normalize(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = re.sub(r'[零〇一二两三四五六七八九十百千0-9]+',
                   lambda m: str(n) if (n := number(m[0])) is not None else m[0], value)
    return ''.join(char for char in value if char.isalnum() or char == '+')


@lru_cache(maxsize=1)
def pronunciations():
    path = Path(__file__).resolve().parents[2] / 'config/media-pronunciations.json'
    return json.loads(path.read_text(encoding='utf-8'))


def loose(phone):
    return re.sub(r'ng$', 'n', re.sub(r'^([zcs])h', r'\1', phone))


@lru_cache(maxsize=32768)
def evidence(char):
    return frozenset([char] + ['@' + loose(phone) for phone in pronunciations().get(char, [])])


@lru_cache(maxsize=16384)
def substitution(left, right):
    if left == right:
        return 0.
    a, b = pronunciations().get(left, []), pronunciations().get(right, [])
    if not a or not b:
        return 1.
    if a[0] == b[0]:
        return .10
    if set(a).intersection(b):
        return .28
    if {loose(x) for x in a}.intersection(loose(x) for x in b):
        return .35
    return 1.


def identity(value):
    # Numerals and CCTV's + suffix distinguish sequels/stations even when most
    # letters agree. A missing number can be offered, never inferred for autoplay.
    station = re.match(r'cctv(\d+)(\+?)', value)
    return tuple(re.findall(r'\d+', value)), station.groups() if station else None


def similarity(query, title, query_keys=None):
    if not query or not title:
        return 0.
    qids, tids = identity(query), identity(title)
    if qids[0] and tids[0] and qids[0] != tids[0] or qids[1] and tids[1] and qids[1] != tids[1]:
        return 0.
    if query == title:
        return 1.
    if min(len(query), len(title)) / max(len(query), len(title)) < CHOICE_SCORE:
        return .65 if len(query) >= 2 and query in title else 0.
    if query not in title:
        # An unmatched target character costs at least one edit. This optimistic
        # bound ignores order, repetition and phonetic penalties; it cannot drop
        # a candidate whose actual score reaches the selection threshold.
        keys = query_keys if query_keys is not None else frozenset().union(*(evidence(char) for char in query))
        missing = sum(evidence(char).isdisjoint(keys) for char in title)
        if missing > (1 - CHOICE_SCORE) * max(len(query), len(title)):
            return 0.
    previous = list(range(len(title) + 1))
    for i, left in enumerate(query, 1):
        current = [i]
        for j, right in enumerate(title, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + substitution(left, right)))
        previous = current
    score = 1 - previous[-1] / max(len(query), len(title))
    if len(query) >= 2 and query in title:
        score = max(score, .65 + .15 * len(query) / len(title))
    return score


def rank(query, rows, year=None, cancelled=lambda: False):
    from .live_tv import normalize as channel_name
    queries = {'channel': normalize(channel_name(query)), 'library': normalize(query)}
    keys = {kind: frozenset().union(*(evidence(char) for char in value)) for kind, value in queries.items()}
    if len(queries['library']) < 2:
        return [], False
    ranked = []
    for row in rows:
        if cancelled():
            raise InterruptedError('已取消查找。')
        if year is not None and row.get('year') != year:
            continue
        current = 'channel' if row['kind'] == 'channel' else 'library'
        query = queries[current]
        title = normalize(channel_name(row['title'])) if row['kind'] == 'channel' else normalize(row['title'])
        score = similarity(query, title, keys[current])
        if row['kind'] == 'channel':
            base = re.sub(r'(?:(?:高清|标清|超清|uhd|hd|sd|4k|8k))+$', '', title)
            score = max(score, similarity(query, base, keys[current]))
            station = re.fullmatch(r'cctv\d+\+?', query)
            if station and re.match(r'cctv\d+\+?', title) and identity(query) == identity(title):
                score = 1.
        if score >= CHOICE_SCORE:
            ranked.append(dict(row=row, score=score, identity=identity(query) == identity(title), length=len(query)))
    ranked.sort(key=lambda row: (-row['score'], row['row']['kind'], row['row']['id']))
    top = ranked[0] if ranked else None
    second = ranked[1]['score'] if len(ranked) > 1 else 0.
    automatic = bool(top and top['score'] >= AUTO_SCORE and top['score'] - second >= AUTO_MARGIN
                     and (top['length'] >= 3 or top['score'] == 1.) and top['identity'])
    return ranked[:12], automatic
