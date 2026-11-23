"""One mechanical fix for an inherited addon-ID/package-name collision."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
count = 0
for path in (ROOT / 'addons/plugin.video.bobbi').rglob('*.py'):
    text = path.read_text(encoding='utf-8-sig')
    changed = text.replace('lib.bobbi.', 'lib.jacktook.')
    if text != changed:
        path.write_text(changed, encoding='utf-8')
        count += 1
print('Internal module references repaired:', count)
