"""Chinese startup policy. Unknown language or release identity is not proof."""

import re


CHINESE_CODES = {'zh', 'chi', 'zho', 'zh-cn', 'zh-tw', 'zh-hans', 'zh-hant',
                 'zh-sg', 'zh-hk', 'chs', 'cht'}
_CHINESE_NAME = re.compile(r'(?i)(?:\b(?:chinese|mandarin|chs|cht|jpsc|jptc|zh-hans|zh-hant)\b|简体|繁体|繁體|简中|繁中|中文)')


def chinese_track(streams):
    """Prefer a full Chinese track, then simplified; never choose English by index."""
    candidates = []
    if not isinstance(streams, (list, tuple)):
        return None
    for stream in streams:
        if not isinstance(stream, dict) or type(stream.get('index')) is not int:
            continue
        language = str(stream.get('language') or '').casefold().replace('_', '-')
        name = str(stream.get('name') or '')
        # Explicit foreign language beats an ambiguous translated track name.
        known_chinese = language in CHINESE_CODES
        if not known_chinese and not (language in ('', 'und', 'unknown') and _CHINESE_NAME.search(name)):
            continue
        simplified = language in ('zh-cn', 'zh-sg', 'zh-hans', 'chs') or bool(re.search(r'(?i)(?:\b(?:chs|hans|jpsc)\b|简)', name))
        forced = stream.get('isforced') is True or bool(re.search(r'(?i)\b(?:forced|commentary|signs(?:\s*&\s*songs)?)\b|仅标识|僅標識|评论|評論', name))
        # Signs/forced-only tracks do not satisfy automatic full-dialogue
        # Chinese selection. They remain available through Kodi's manual UI.
        if forced:
            continue
        bilingual = bool(re.search(r'(?i)双语|雙語|中英|bilingual|chs[&+ /]+eng|eng[&+ /]+chs', name))
        candidates.append(((not bilingual, not simplified, stream['index']), stream))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None
