"""Bounded catalogue-backed anime query and candidate identity helpers.

No release-group preference, remote lookup, filename mutation or file proof.
"""
import re
import unicodedata

from bobbi_core.candidate_titles import matches, normalized, chinese_episode_numbers
from bobbi_core.pack_parser import detect_pack_scope, release_season_markers


def first_season_episode(title, aliases, season, episode):
    """A bare local episode is eligible only for an already identified anime.

    Callers supply aliases ONLY with independently ID-bound animation metadata.
    Never infer subsequent seasons, packs, ranges, years, resolution or CRC.
    A candidate card remains subject to the existing exact file resolver.
    """
    if type(season) is not int or season != 1 or type(episode) is not int or not 1 <= episode <= 999:
        return False
    if not isinstance(title, str) or len(title) > 2048 or not aliases:
        return False
    chinese = chinese_episode_numbers(title, aliases)
    if chinese != ():
        return bool(chinese == (episode,) and not release_season_markers(title)
                    and detect_pack_scope(title, 1)['pack_type'] == 'none')
    if (release_season_markers(title) or detect_pack_scope(title, 1)['pack_type'] != 'none'
            or not matches(title, aliases, 'tv', release_season=1)):
        return False
    text = unicodedata.normalize('NFKC', title)
    for _ in range(3):
        stripped = re.sub(r'^\s*\[[^\[\]]{1,100}\][ ._-]*', '', text, count=1)
        if stripped == text:
            break
        text = stripped
    # Reject the whole ambiguous expression BEFORE collecting markers. Merely
    # skipping its left endpoint could promote the right endpoint to a single
    # episode (e.g. [03]-[04]). Decimal specials are not episode 03 either.
    continuation = (r'(?:\s-\s*|\[)[0-9]{1,3}(?:v\d+)?\]?\s*'
                    r'(?:[-–—−~_.至&/]|\b(?:to|through)\b)\s*\[?[0-9]')
    if re.search(continuation, text, re.I):
        return False
    pattern = (r'(?:\s-\s*([0-9]{1,3})(?:v\d+)?(?=\s*(?:\[|\(|$))'
               r'|\[([0-9]{1,3})(?:v\d+)?\])')
    numbered = set()
    for segment in re.split(r'[/|()]', text):
        for marker in re.finditer(pattern, segment, re.I):
            number = int(marker[1] or marker[2])
            numbered.add(number)
    # A bilingual release may place the trusted Chinese title in one segment
    # and the number after its romanised counterpart. The full catalogue gate
    # above binds the work; every recognised episode marker must agree.
    return numbered == {episode}


def catalog_anime_queries(details, requested_id):
    """At most one Simplified, Traditional, native and English title per ID.

    Translation country/language tags, not guessed script conversion, choose
    slots. Missing slots do not consume the fixed four-query ceiling.
    """
    if not isinstance(details, dict) or str(details.get('id')) != str(requested_id):
        return []
    genres = details.get('genres') or []
    if not isinstance(genres, list) or not any(isinstance(g, dict) and g.get('id') == 16 for g in genres):
        return []
    slots = {key: [] for key in ('zh-CN', 'zh-TW', 'native', 'en')}

    def add(slot, value):
        if isinstance(value, str) and 2 <= len(value.strip()) <= 512:
            slots[slot].append(value.strip())

    add('native', details.get('original_name'))
    translations = details.get('translations') or {}
    translations = translations.get('translations', []) if isinstance(translations, dict) else []
    for item in translations[:128] if isinstance(translations, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('data'), dict):
            continue
        language, country = item.get('iso_639_1'), item.get('iso_3166_1')
        value = item['data'].get('name')
        if language == 'zh' and country in ('CN', 'SG'):
            add('zh-CN', value)
        elif language == 'zh' and country in ('TW', 'HK', 'MO'):
            add('zh-TW', value)
        elif language == details.get('original_language'):
            add('native', value)
        elif language == 'en':
            add('en', value)
    alternate = details.get('alternative_titles') or {}
    alternate = alternate.get('results', []) if isinstance(alternate, dict) else []
    native_country = {'ja': 'JP', 'ko': 'KR', 'en': 'US'}.get(details.get('original_language'))
    for item in alternate[:128] if isinstance(alternate, list) else []:
        if not isinstance(item, dict):
            continue
        country, value = item.get('iso_3166_1'), item.get('title')
        if country in ('CN', 'SG'):
            add('zh-CN', value)
        elif country in ('TW', 'HK', 'MO'):
            add('zh-TW', value)
        elif country == native_country:
            add('native', value)
        elif country in ('US', 'GB'):
            add('en', value)
    # The requested detail's name is catalogue-bound but its locale is not
    # encoded in the payload. It is a last resort, never labelled Chinese.
    fallback = details.get('name')
    result, seen = [], set()
    for slot in ('zh-CN', 'zh-TW', 'native', 'en'):
        for title in slots[slot]:
            key = normalized(title)
            if key and key not in seen:
                result.append((slot, title))
                seen.add(key)
                break
    if not result and isinstance(fallback, str) and 2 <= len(fallback.strip()) <= 512:
        result.append(('unknown', fallback.strip()))
    return result[:4]


def provider_anime_titles(queries, language=''):
    """Prefer declared indexer language, with all other proven aliases retained."""
    language = str(language or '').lower().replace('_', '-')
    preferred = ('zh-TW', 'zh-CN') if language.startswith(('zh-tw', 'zh-hk', 'zh-hant')) else (
        ('zh-CN', 'zh-TW') if language.startswith('zh') else
        ('native',) if language.startswith(('ja', 'ko')) else
        ('en',) if language.startswith('en') else ())
    ordered = sorted(enumerate(queries[:4]), key=lambda pair: (
        preferred.index(pair[1][0]) if pair[1][0] in preferred else len(preferred), pair[0]))
    return list(dict.fromkeys(item[1] for _, item in ordered))
