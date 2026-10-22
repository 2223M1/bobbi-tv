"""Negative-only movie label screening; never media identity or readiness proof.

Bare -NN/[NN] is unknown: an unlabelled split movie is indistinguishable from
an anime episode by that syntax alone. This module does not resolve files.
"""
import re
import unicodedata


def _outside_aliases(title, aliases):
    from bobbi_core.candidate_titles import normalized
    text = unicodedata.normalize('NFKC', title).casefold()
    names = [unicodedata.normalize('NFKC', name).casefold() for name in aliases
             if isinstance(name, str) and 2 <= len(name.strip()) <= 512]
    trusted = {normalized(name).replace(' ', '') for name in names}
    # A leading release group is not a type assertion. Conservatively ignore
    # at most three such tags, even if their text contains episode-like words.
    for _ in range(3):
        group = re.match(r'^\s*(?:\[([^\[\]]{1,100})\]|【([^【】]{1,100})】)\s*', text)
        if not group or normalized(group[1] or group[2]).replace(' ', '') in trusted:
            break
        text = text[group.end():]
    # Protect complete aliases, not arbitrary interior substrings. Masking is
    # not positive admission; it only prevents a title such as "Episode 50"
    # or "Extras" from being mistaken for release metadata.
    for name in sorted(names, key=len, reverse=True):
        words = re.findall(r'[^\W_]+', name)
        if words:
            pattern = r'(?<!\w)' + r"[ ._'’:\-]*".join(map(re.escape, words)) + r'(?!\w)'
            text = re.sub(pattern, ' ', text)
    return re.sub(r'\[\s*\]|【\s*】|\(\s*\)', ' ', text)


def _technical(text):
    from bobbi_core.candidate_titles import _technical_tail
    # The marker may have appeared inside a metadata bracket. Unknown words
    # after it are deliberately not consumed as if they were technical tags.
    text = text.lstrip(' ._-])】')
    return not text or _technical_tail(text)


def conflict(title, aliases):
    """Return a narrow conflict reason, or '' for unknown/nonconflicting.

    Callers retain their existing positive alias check. This predicate never
    accepts a row, fetches data, changes a title, or relaxes an exact file gate.
    """
    if not isinstance(title, str) or not title or len(title) > 2048 or not aliases:
        return ''
    # Explicit bracketed format/category evidence, not words occurring in a
    # film title. Missing category remains unknown. A '+' in an uploader name
    # must not turn a manga-only row into a mixed movie collection.
    from bobbi_core.candidate_titles import normalized
    trusted = {normalized(alias) for alias in aliases if isinstance(alias, str)}
    for tag in re.findall(r'\[([^\[\]]+)\]|【([^【】]+)】', unicodedata.normalize('NFKC', title).casefold()):
        label = next(part for part in tag if part)
        if normalized(label) not in trusted and re.fullmatch(r'\s*(?:manga|comics?|e[ -]?books?|漫画|漫畫)(?:[ _-]+(?:[a-z]{2,3}|digital|pdf|epub|cbz|cbr))*\s*', label):
            return 'non_video'
    text = _outside_aliases(title, aliases)
    text = re.sub(r'\([^()\r\n]{1,160}[?？]\)', ' ', text)
    # Explicit mixed contents are not an extras-only or TV-only assertion.
    # Preserve ambiguous Movie + TV/Extras collections for exact file checks.
    if re.search(r'\+|&|\b(?:and|with|plus|movies?|films?)\b|正片|本篇|剧场版|劇場版|含', text):
        return ''
    # Do not reinterpret the right endpoint of an unsupported range as an
    # isolated episode. Ranges remain unknown in this deliberately narrow gate.
    if re.search(r'第\s*[0-9]{1,3}\s*[话話集]\s*(?:至|[-~～–—/])\s*第?\s*[0-9]{1,3}', text):
        return ''
    markers = (
        ('tv_episode', r'(?<![a-z0-9])s[0-9]{1,2}[ ._-]*e[0-9]{1,3}(?![a-z0-9])'),
        ('tv_episode', r'(?<![a-z0-9])(?:episode|ep)[ ._-]*0*[1-9][0-9]{0,2}(?![a-z0-9])'),
        ('tv_episode', r'第\s*0*[1-9][0-9]{0,2}\s*[话話集]'),
        ('tv_season', r'(?<![a-z0-9])(?:season[ ._-]*|s)0*[1-9][0-9]?[ ._-]+(?:complete|全)(?![a-z0-9])'),
    )
    for reason, pattern in markers:
        for marker in re.finditer(pattern, text):
            if _technical(text[marker.end():]):
                return reason
    for marker in re.finditer(r'(?<![a-z0-9])extras(?![a-z0-9])', text):
        prefix = re.sub(r'(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])', ' ', text[:marker.start()])
        prefix = re.sub(r'(?<![a-z0-9])(?:dvd|dvdiso)(?![a-z0-9])', ' ', prefix)
        prefix = re.sub(r'[\[\]()【】. _-]', '', prefix)
        if prefix:
            continue
        suffix = re.sub(r'\[r[0-9](?:us|uk|jp|eu)?\]', ' ', text[marker.end():])
        # A bounded question in parentheses describes the extras, not a movie
        # payload. Bare (Movie)/(TV) labels or unknown prose remain unknown.
        suffix = re.sub(r'\([^()\r\n]{1,160}[?？]\)', ' ', suffix)
        if _technical(suffix):
            return 'extras_only'
    return ''
