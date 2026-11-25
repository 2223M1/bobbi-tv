"""Runtime-only UI localization helper for Bobbi platform & companion addons.

Strict invariants:
- Never imported by ``bobbi_core`` (``bobbi_core`` stays 100% pure Python).
- Never caches translated strings at module import time; active UI language is
  resolved at every call so live ``ZH -> EN -> ZH`` switching takes effect
  immediately without restarting Kodi or dropping in-memory state.
- Falls back cleanly to on-disk ``strings.po`` catalogs (cached only by file
  path + mtime, never pinned to one locale) when ``xbmcaddon`` is stubbed in
  headless tests or unavailable.
"""
import json
from pathlib import Path
import re

_PO_CACHE = {}
_ADDONS_ROOT = Path(__file__).resolve().parents[3]
_ENTRY_RE = re.compile(
    r'msgctxt\s+"#(\d+)"(?:\s*\n(?:#[^\n]*\n)*)\s*msgid\s+((?:"(?:[^"\\]|\\.)*"\s*\n?)+)(?:#[^\n]*\n)*\s*msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*\n?)+)',
    re.MULTILINE,
)
_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unquote(block):
    parts = _STR_RE.findall(block)
    raw = ''.join(parts)
    return (
        raw.replace('\\n', '\n')
        .replace('\\t', '\t')
        .replace('\\"', '"')
        .replace('\\\\', '\\')
    )


def parse_po_file(po_path):
    """Parse a Kodi ``strings.po`` file into ``{int_id: (msgid, msgstr)}``."""
    path = Path(po_path)
    try:
        stat = path.stat()
    except OSError:
        return {}
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _PO_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    entries = {}
    for match in _ENTRY_RE.finditer(text):
        code = int(match.group(1))
        if code not in entries:
            entries[code] = (_unquote(match.group(2)), _unquote(match.group(3)))
    _PO_CACHE[key] = entries
    return entries


def normalize_locale(raw_value):
    """Normalize a Kodi locale setting or language tag into ``'en_gb'`` or ``'zh_cn'``."""
    if not isinstance(raw_value, str):
        return ''
    lowered = raw_value.strip().lower().replace('-', '_')
    if not lowered:
        return ''
    if lowered.startswith(('resource.language.en', 'en_', 'english')) or lowered == 'en':
        return 'en_gb'
    if lowered.startswith(('resource.language.zh', 'zh_', 'chinese')) or lowered == 'zh':
        return 'zh_cn'
    return ''


def current_locale():
    """Return active Kodi UI locale (``'zh_cn'`` or ``'en_gb'``) at call time."""
    try:
        import xbmc
    except ImportError:
        return 'zh_cn'

    rpc = getattr(xbmc, 'executeJSONRPC', None)
    if callable(rpc):
        try:
            raw = rpc(
                '{"jsonrpc":"2.0","id":1,"method":"Settings.GetSettingValue",'
                '"params":{"setting":"locale.language"}}'
            )
            if isinstance(raw, str) and raw:
                payload = json.loads(raw)
                val = ((payload.get('result') or {}).get('value')) if isinstance(payload, dict) else None
                norm = normalize_locale(val)
                if norm:
                    return norm
        except Exception:
            pass

    get_info = getattr(xbmc, 'getInfoLabel', None)
    if callable(get_info):
        try:
            norm = normalize_locale(get_info('System.Language'))
            if norm:
                return norm
        except Exception:
            pass

    get_lang = getattr(xbmc, 'getLanguage', None)
    if callable(get_lang):
        try:
            iso_flag = getattr(xbmc, 'ISO_639_1', 0)
            norm = normalize_locale(get_lang(iso_flag) if isinstance(iso_flag, int) else get_lang())
            if norm:
                return norm
        except Exception:
            pass

    return 'zh_cn'


def is_english():
    return current_locale() == 'en_gb'


def addon_po_string(addon_id, msg_id, lang=None):
    """Lookup ``msg_id`` directly from shipped ``strings.po`` for ``addon_id``."""
    lang = lang or current_locale()
    base = _ADDONS_ROOT / addon_id / 'resources' / 'language'
    code = int(msg_id)
    if lang == 'zh_cn':
        for candidate in (
            base / 'resource.language.zh_cn' / 'strings.po',
            base / 'Chinese (Simple)' / 'strings.po',
        ):
            entries = parse_po_file(candidate)
            if code in entries:
                msgid, msgstr = entries[code]
                if msgstr:
                    return msgstr
                if msgid:
                    return msgid
    for candidate in (
        base / 'resource.language.en_gb' / 'strings.po',
        base / 'English' / 'strings.po',
    ):
        entries = parse_po_file(candidate)
        if code in entries:
            msgid, msgstr = entries[code]
            return msgstr or msgid
    return ''


def tr(msg_id, zh_text='', en_text='', addon_id='script.module.bobbi.platform'):
    """Resolve localized UI copy at call time with safe PO and inline fallbacks."""
    lang = current_locale()
    if msg_id is not None:
        try:
            import xbmcaddon
            addon = xbmcaddon.Addon(addon_id)
            localized = addon.getLocalizedString(int(msg_id))
            if isinstance(localized, str) and localized:
                return localized
        except Exception:
            pass
        from_po = addon_po_string(addon_id, msg_id, lang=lang)
        if from_po:
            return from_po
    return en_text if (lang == 'en_gb' and en_text) else zh_text
