"""Verify the single canonical Segno QR vendor copy in script.module.bobbi.platform."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILES = ('__init__.py', 'consts.py', 'encoder.py', 'utils.py', 'writers.py')


def verify():
    duplicate = ROOT / 'addons/plugin.video.bobbi/lib/vendor/segno'
    if duplicate.exists():
        raise ValueError('Duplicate Segno vendor directory must not exist in plugin.video.bobbi')
    target = ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/_vendor/segno'
    actual = tuple(sorted(p.name for p in target.glob('*.py')))
    if actual != EXPECTED_FILES:
        raise ValueError(f'Unexpected Segno file set: {actual}')
    notice = ROOT / 'addons/script.module.bobbi.platform/licenses/segno.txt'
    if not notice.is_file():
        raise ValueError('Missing Segno license notice in script.module.bobbi.platform')
    print('Canonical Segno QR vendor verified.')


if __name__ == '__main__':
    verify()
