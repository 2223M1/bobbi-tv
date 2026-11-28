"""One Kodi profile's picker preferences. Values hold no file or account locators."""
import json
import os
import re
from tempfile import NamedTemporaryFile

from bobbi_core.library_labels import visible_name

AXIS = {'library':'source', 'station':'source', 'indexer':'source', 'quality':'quality', 'quality_tab':'quality',
        'provider':'group', 'release_group':'group', 'type':'type', 'only_torrents':'type',
        'only_debrid':'type', 'chinese_subtitles':'subtitle', 'language':'language'}
FLAGS = {'only_torrents':'仅 BT', 'only_debrid':'仅解限服务', 'chinese_subtitles':'标注中文字幕'}
TITLES = {'library':'源库', 'station':'BT 站点', 'indexer':'来源站点', 'quality':'清晰度', 'quality_tab':'清晰度',
          'provider':'压制组', 'release_group':'压制组', 'type':'片源类型', 'language':'语言'}


def choice(kind, value=None, label=None):
    if kind not in AXIS:
        return None
    if kind in FLAGS:
        return (kind, None, FLAGS[kind]) if value is None else None
    if kind in ('library', 'station') and not (isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value)):
        return None
    # n/a is a defined local quality-tab key, not a private path.
    if kind not in ('library', 'station') and value not in ('n/a', 'N/A') and not visible_name(value):
        return None
    text = visible_name(label or value) or ('未知清晰度' if value in ('n/a', 'N/A') else '')
    return (kind, value, text) if text else None


def summary(rules):
    return '、'.join(TITLES[k]+ '：'+ label if k in TITLES else label for k, _, label in rules.values())


class Preferences:
    def __init__(self, binding):
        self.binding = binding
        self.path = binding.root('plugin.video.bobbi') / 'source-filters.json'

    def read(self):
        try:
            self.binding.require_current()
            with self.path.open('rb') as f:
                raw = f.read(8193)
            if len(raw) > 8192:
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('rules'), list):
                return {}
            result = {}
            for item in data['rules'][:len(AXIS)]:
                rule = choice(*item) if isinstance(item, list) and len(item) == 3 else None
                if rule:
                    result[AXIS[rule[0]]] = rule
            self.binding.require_current()
            return result
        except (OSError, ValueError, TypeError, RuntimeError):
            return {}

    def write(self, rules):
        self.binding.require_current()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf8', dir=self.path.parent,
                                    prefix='.source-filters-', delete=False) as f:
                temp = f.name
                json.dump(dict(schema=1, rules=list(rules.values())), f, ensure_ascii=False)
            self.binding.require_current()
            os.replace(temp, self.path)
            temp = None
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except FileNotFoundError:
                    pass


def catalog_options(source):
    """Read local public directory only when the user opens the source filter."""
    if not source or not (source.root / 'catalog.sqlite3').is_file() or source.owner.current() != source:
        return {}
    import sqlite3
    from bobbi_core.library_labels import directory, memberships
    from bobbi_core.sharelib_catalog import _cache
    try:
        with _cache(source.root, readonly=True, cancelled=lambda: source.owner.current() != source) as cache:
            lookup = directory(cache)
            revoked = {'shared:'+row[0] for row in cache.db.execute('SELECT code FROM library_visibility WHERE revoked=1')}
            result = memberships(['main:', *(key for key in lookup[1] if key not in revoked)], lookup)
        return result if source.owner.current() == source else {}
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        return {}
