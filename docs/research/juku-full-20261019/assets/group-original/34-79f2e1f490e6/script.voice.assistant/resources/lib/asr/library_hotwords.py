"""Chinese Kodi library titles tokenized for native Transducer hotwords."""
import fcntl
import hashlib
import json
from pathlib import Path
from ..data_paths import data_path
import re
import time
import unicodedata

from ..storage import atomic_write, read_json, write_json
from .text import vocabulary

CACHE_SECONDS = 3600
PAGE_SIZE = 1000
VERSION = 1
DIGITS = '零一二三四五六七八九'


def number(value):
    """A spoken cardinal form; preserve leading-zero identifiers digit by digit."""
    n = int(value)
    if n == 0:
        return DIGITS[0]
    if len(value) > 4 or len(value) > 1 and value.startswith('0'):
        return ''.join(DIGITS[int(c)] for c in value)
    result, zero = '', False
    for divisor, unit in ((1000, '千'), (100, '百'), (10, '十'), (1, '')):
        digit, n = divmod(n, divisor)
        if digit:
            if zero:
                result += '零'
            result += ('' if divisor == 10 and digit == 1 and not result else DIGITS[digit]) + unit
            zero = False
        elif result and n:
            zero = True
    return result


def compile_titles(titles, symbols, cancelled=lambda: False):
    paths, skipped, included, partial = set(), [], 0, 0
    for title in sorted(set(titles)):
        if cancelled():
            raise InterruptedError('已取消影视热词准备。')
        text = unicodedata.normalize('NFKC', title).strip()
        text = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', text)
        has_english = bool(re.search(r'[A-Za-z]', text))
        found = set()
        # English breaks a title into Chinese portions, never join across it:
        # 阿Q正传 can bias 正传, but must not create the fictitious 阿正传.
        for segment in re.split(r'[A-Za-z]+', text):
            if not re.search(r'[\u3400-\u9fff0-9]', segment):
                continue
            if has_english and len(re.findall(r'[\u3400-\u9fff]', segment)) < 2:
                continue
            if any(c.isalpha() and not '\u3400' <= c <= '\u9fff' for c in segment):
                continue
            clean = ''.join(re.findall(r'[\u3400-\u9fff0-9]', segment))
            forms = {clean,
                     re.sub(r'[0-9]+', lambda m: number(m.group()), clean),
                     re.sub(r'[0-9]+', lambda m: ''.join(DIGITS[int(c)] for c in m.group()), clean)}
            for form in forms:
                pieces = tuple(re.findall(r'[\u3400-\u9fff]|[0-9]+', form))
                if pieces and all(piece in symbols for piece in pieces):
                    found.add(pieces)
        if found:
            paths.update(found)
            included += 1
            partial += int(has_english)
        else:
            skipped.append(title)
    return sorted(paths), {'included_titles': included, 'partial_titles': partial,
                           'skipped_titles': len(skipped), 'skipped': skipped,
                           'token_paths': len(paths)}


def fetch_titles(rpc, cancelled):
    titles, counts = set(), {}
    for method, key in (('VideoLibrary.GetMovies', 'movies'), ('VideoLibrary.GetTVShows', 'tvshows')):
        start = 0
        while True:
            if cancelled():
                raise InterruptedError('已取消影视热词读取。')
            result = rpc(method, {'properties': ['title'], 'limits': {'start': start, 'end': start + PAGE_SIZE},
                                 'sort': {'method': 'title', 'order': 'ascending'}})
            if not isinstance(result, dict) or not isinstance(result.get(key), list):
                raise ValueError('Kodi 未返回完整的影视名称，未更新热词。')
            rows = result[key]
            total = int(result.get('limits', {}).get('total', start + len(rows)))
            if result.get('limits', {}).get('start', start) != start or total < start + len(rows):
                raise ValueError('Kodi 影视库分页不完整，未更新热词。')
            for row in rows:
                title = row.get('title') or row.get('label')
                if isinstance(title, str) and title.strip():
                    titles.add(title.strip())
            counts[key] = total
            start += len(rows)
            if start >= total:
                break
            if not rows:
                raise ValueError('Kodi 影视库分页提前结束，未更新热词。')
    return dict(counts, titles=sorted(titles), updated_at=time.time())


def prepare(profile, tokens_path, rpc, cancelled=lambda: False, force=False):
    directory = data_path(profile, 'asr-library-hotwords')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'prepare.lock').open('a') as lock:
        while True:
            if cancelled():
                raise InterruptedError('已取消影视热词准备。')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(.05)
        cache_path = directory / 'library.json'
        library = read_json(cache_path, {})
        if force or not library or time.time() - library.get('updated_at', 0) > CACHE_SECONDS:
            library = fetch_titles(rpc, cancelled)
            write_json(cache_path, library)
        fingerprint = hashlib.sha256(Path(tokens_path).read_bytes() +
            json.dumps([VERSION, library['titles']], ensure_ascii=False).encode()).hexdigest()[:24]
        path = directory / (fingerprint + '.txt')
        report_path = directory / (fingerprint + '.json')
        report = read_json(report_path)
        if report is None or not path.is_file():
            paths, report = compile_titles(library['titles'], vocabulary(tokens_path), cancelled)
            if cancelled():
                raise InterruptedError('已取消影视热词准备。')
            atomic_write(path, ''.join(' '.join(pieces) + '\n' for pieces in paths))
            write_json(report_path, report)
        return (str(path) if report['token_paths'] else ''), dict(report,
            movies=library['movies'], tvshows=library['tvshows'], unique_titles=len(library['titles']))
