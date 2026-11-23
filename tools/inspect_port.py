"""Print structural portability evidence, not account values or private logs."""
import ast
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def inspect():
    xml = ET.parse(ROOT / 'addons/plugin.video.bobbi/resources/settings.xml')
    settings = []
    for setting in xml.iter('setting'):
        key = setting.get('id', '')
        if re.search('anime|garden|jackett|nyaa|rss|torrent|source|engine|tmdb|stremio', key, re.I):
            default = setting.findtext('default') or ''
            settings.append({'id': key, 'type': setting.get('type'),
                             'default': default if default in ('', 'true', 'false') or default.isdigit() else '[configured string]'})
    issues = []
    for path in (ROOT / 'addons').rglob('*.py'):
        if path.is_symlink():
            raise ValueError('Symlink source')
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.search(r'(?:https?://)?192\.168\.\d+\.\d+', node.value):
                    issues.append({'file': path.relative_to(ROOT).as_posix(), 'line': node.lineno, 'reason': 'private-endpoint'})
    print(json.dumps({'settings': settings, 'issues': issues}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    inspect()
