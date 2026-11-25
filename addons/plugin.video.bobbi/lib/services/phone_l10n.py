"""Authoritative PO-backed UI string projection for paired phone management.

Single source of truth: ``addons/plugin.video.bobbi/resources/language/`` PO
catalogs (``English/strings.po`` and ``resource.language.zh_cn/strings.po``).
Never reads browser ``Accept-Language`` headers; TV locale is authoritative.
"""
from pathlib import Path

from bobbi_platform.i18n import current_locale, parse_po_file

_LANG_ROOT = Path(__file__).resolve().parents[2] / 'resources' / 'language'

_SHARED_RANGES = (range(91300, 91383), range(91484, 91500))
_CATALOG_RANGE = range(91383, 91463)
_PLAYBACK_RANGE = range(91463, 91473)
_STREMIO_RANGE = range(91473, 91478)
_IMPORT_RANGE = range(91478, 91481)
_SUBTITLE_RANGE = range(91481, 91484)


def _wanted_ids(scopes=None):
    ids = set()
    for rng in _SHARED_RANGES:
        ids.update(rng)
    if not scopes or 'catalog_read' in scopes:
        ids.update(_CATALOG_RANGE)
    if not scopes or 'playback_read' in scopes:
        ids.update(_PLAYBACK_RANGE)
    if not scopes or 'stremio_addons' in scopes:
        ids.update(_STREMIO_RANGE)
    if not scopes or 'source_import' in scopes:
        ids.update(_IMPORT_RANGE)
    if not scopes or 'subtitle_upload' in scopes:
        ids.update(_SUBTITLE_RANGE)
    return sorted(ids)


def session_locale_payload(scopes=None):
    """Return ``{'locale': 'zh-CN'|'en-GB', 'ui_strings': {str_id: text}}``."""
    kodi_lang = current_locale()
    is_en = kodi_lang == 'en_gb'
    locale_tag = 'en-GB' if is_en else 'zh-CN'

    en_entries = parse_po_file(_LANG_ROOT / 'English' / 'strings.po')
    zh_entries = parse_po_file(_LANG_ROOT / 'resource.language.zh_cn' / 'strings.po')

    ui_strings = {}
    for code in _wanted_ids(scopes):
        if is_en:
            entry = en_entries.get(code)
            if entry:
                msgid, msgstr = entry
                text = msgstr or msgid
                if text:
                    ui_strings[str(code)] = text
        else:
            entry = zh_entries.get(code)
            if entry:
                msgid, msgstr = entry
                text = msgstr or msgid
                if text:
                    ui_strings[str(code)] = text
    return {'locale': locale_tag, 'ui_strings': ui_strings}
