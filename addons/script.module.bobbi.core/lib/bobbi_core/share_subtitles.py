"""Selected-share text sidecars; no second daemon, cloud tasks or video reads."""
from pathlib import PurePosixPath
import re
import time
from urllib.parse import parse_qs

PAGE = 100
MAX_FILES = 1000
MAX_CANDIDATES = 3
MAX_BYTES = 2 * 1024 * 1024
TEXT = {'.ass', '.ssa', '.srt', '.vtt'}
EXCLUDE = re.compile(r'(?i)commentary|\bforced\b|signs.?and.?songs|导演评论|僅標識|仅标识')


class Stopped(RuntimeError):
    pass


def matches(video, subtitle, explicit=False, context=None):
    if (not isinstance(subtitle, str) or len(subtitle) > 1024 or
            re.search(r'[\\/\x00-\x1f\x7f]', subtitle) or EXCLUDE.search(subtitle)):
        return False
    path = PurePosixPath(subtitle)
    if path.suffix.casefold() not in TEXT:
        return False
    # Explicit same-share file references still may not contradict the episode.
    from bobbi_core.subtitle_candidates import episode_tags, EDITION
    context = context or {}
    video_episodes, subtitle_episodes = episode_tags(video), episode_tags(subtitle)
    if (subtitle_episodes and subtitle_episodes != video_episodes
            and (video_episodes or context.get('mode') != 'series')):
        return False
    if set(m.group().casefold() for m in EDITION.finditer(subtitle)) - set(
            m.group().casefold() for m in EDITION.finditer(video)):
        return False
    if context.get('mode') == 'series' or video_episodes:
        # Explicit author links may use generic Chinese filenames, but an
        # actual anime/season/episode declaration must not contradict the video.
        from bobbi_core.juku_catalog import _filename_episode
        try:
            vs, ve = _filename_episode(video)
            ss, se = _filename_episode(subtitle)
        except ValueError:
            return False
        wanted_season = vs if vs is not None else context.get('season')
        wanted_episode = ve if ve is not None else context.get('episode')
        if (se is not None and se != wanted_episode or ss is not None and ss != wanted_season):
            return False
        # Explicit author links are useful, not permission to contradict the
        # requested season/special scope. Reuse the subtitle-only title-aware
        # parser (Chinese/ordinal seasons, OVA/specials) rather than a second
        # incomplete regex list. Generic Chinese filenames remain eligible.
        from bobbi_core.subtitle_episode import declarations
        seasons = declarations(subtitle, str(context.get('title') or ''))
        if seasons and seasons != {wanted_season}:
            return False
    if context.get('mode') == 'movie':
        from bobbi_core.movie_identity import declared_years
        from bobbi_core.movie_years import accepted_years
        years = declared_years(subtitle, [context.get('title', '')])
        allowed = set(accepted_years(context.get('_movie_years'), context.get('tmdb'), context.get('year')))
        if years and not years <= allowed:
            return False
    if explicit:
        return True
    stem, candidate = PurePosixPath(video).stem.casefold(), path.stem.casefold()
    return candidate == stem or (candidate.startswith(stem) and candidate[len(stem):len(stem) + 1] in '. _[(')


def fetch_candidate(body, context, deadline, cancelled, client, account_guard,
                    selected=None, transport=None, root=None, report=lambda **_: None,
                    account_scope=None):
    """Use only the current selected tuple and captured account credentials."""
    from bobbi_core.subtitle_candidates import inspect_text, publish, ROOT
    from bobbi_core.subtitle_io import read_http
    if account_scope is not None:
        from bobbi_platform.account_manager import validate_snapshot
        account_scope = validate_snapshot(account_scope, authenticated=True)
    if selected is None:
        from bobbi_core.share_catalog import selected
    value = selected(body)
    if isinstance(value, tuple):
        share, row = value
    else:
        row, share = value, value['share']
    if row.get('name') != body['title'] or row.get('size') != body['size']:
        raise ValueError('SHARE_SUBTITLE_SELECTION_CHANGED')
    # Reserve most of the original 30-second total for other existing providers.
    deadline = min(deadline, time.monotonic() + 10)
    def guard():
        if cancelled() or time.monotonic() >= deadline:
            raise Stopped('SHARE_SUBTITLE_CANCELLED_OR_TIMEOUT')
        if account_guard() is False:
            raise Stopped('SHARE_SUBTITLE_ACCOUNT_CHANGED')
    class Cancellation:
        def is_set(self):
            return cancelled() or time.monotonic() >= deadline
    def priority(entry):
        name = entry['name'].casefold()
        return (not entry['explicit'], not bool(re.search(r'双语|雙語|bilingual|chs.?eng|cht.?eng', name)),
                not bool(re.search(r'chs|zh.hans|简', name)), name)
    def acceptable(entry, explicit=False):
        return (isinstance(entry, dict) and not entry.get('is_dir')
            and re.fullmatch(r'[0-9]{1,32}', str(entry.get('fid', '')))
            and type(entry.get('size')) is int and 0 < entry['size'] <= MAX_BYTES
            and matches(row['name'], entry.get('name'), explicit, context))
    inspected, attempted = [], set()
    def inspect(candidates):
        for entry in sorted(candidates, key=priority):
            if entry['fid'] in attempted or len(attempted) >= MAX_CANDIDATES:
                continue
            guard()
            attempted.add(entry['fid'])
            try:
                resolved = entry.get('resolved') or client.resolve(share, entry, deadline)
                guard()
                url, _, options = resolved.partition('|')
                # Official resolver validates CDN; only UA, never the account
                # cookie or API credentials, goes to the subtitle download.
                ua = parse_qs(options, max_num_fields=2).get('User-Agent', [''])[0]
                raw = (transport or read_http)(url, deadline, lambda: Cancellation().is_set(), MAX_BYTES,
                    headers={'User-Agent': ua} if ua else {}, mode='share_cdn')
                if len(raw) != entry['size']:
                    raise ValueError('SHARE_SUBTITLE_SHORT_READ')
                extension = PurePosixPath(entry['name']).suffix.casefold()
                raw, bilingual = inspect_text(raw, extension, context.get('duration'))
                guard()
                inspected.append((bilingual, priority(entry), raw, extension))
            except (ValueError, OSError, RuntimeError):
                guard()  # Never turn a cancellation/account switch into success.
    references = row.get('subtitle_fids') or []
    references = references[:16] if isinstance(references, (tuple, list)) else []
    explicit = list(dict.fromkeys(str(item) for item in references
                    if re.fullmatch(r'[0-9]{1,32}', str(item))))
    candidates = []
    for fid in explicit[:MAX_CANDIDATES]:
        guard()
        try:
            entry = client.resolve_reference(share, fid, deadline, Cancellation())
            guard()
            if acceptable(entry, True) and entry['fid'] == fid:
                candidates.append(dict(entry, explicit=True))
        except (ValueError, OSError, RuntimeError):
            guard()
    report(stage='references', examined=min(len(explicit), MAX_CANDIDATES),
           truncated=len(explicit) > MAX_CANDIDATES)
    inspect(candidates)
    # A usable explicit same-share reference does not depend on knowing or
    # listing the video's parent. Directory scans are only the fallback.
    parent = str(row.get('parent') or '')
    truncated, examined, seen, candidates = False, 0, set(), []
    if not inspected and len(attempted) < MAX_CANDIDATES and re.fullmatch(r'[0-9]{1,32}', parent):
        for offset in range(0, MAX_FILES, PAGE):
            guard()
            try:
                result = client.list_directory(share, parent, offset, PAGE, deadline, Cancellation())
                rows = result['rows']
                if not isinstance(rows, list) or len(rows) > PAGE:
                    raise ValueError('SHARE_SUBTITLE_DIRECTORY_INVALID')
                for entry in rows:
                    guard()
                    fid = str(entry.get('fid', '')) if isinstance(entry, dict) else ''
                    if fid in seen:
                        continue
                    seen.add(fid)
                    examined += 1
                    if acceptable(entry, fid in explicit):
                        candidates.append(dict(entry, explicit=fid in explicit))
                total = result.get('total')
                if len(rows) < PAGE or type(total) is int and offset + len(rows) >= total:
                    break
                if offset + PAGE >= MAX_FILES:
                    truncated = True
            except (ValueError, OSError, RuntimeError):
                guard()
                truncated = True
                break
        report(stage='directory', examined=examined, truncated=truncated)
        inspect(candidates)
    if not inspected:
        raise Stopped('SHARE_SUBTITLE_NOT_FOUND')
    bilingual, _, raw, extension = min(inspected, key=lambda item: (not item[0], item[1]))
    guard()
    result = dict(file=publish(raw, extension, root or ROOT), bilingual=bilingual,
                  origin='same-share', state='candidate', directory_truncated=truncated)
    guard()  # Publication IO does not renew account or cancellation authority.
    if account_scope is not None:
        result['account_scope'] = dict(account_scope)
    return result
