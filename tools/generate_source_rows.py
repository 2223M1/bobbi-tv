"""Keep both Kodi source windows standalone, with one authored list-row layout."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = Path('addons/plugin.video.bobbi/resources/skins/Default/1080i')
BEGIN = b'        <!-- BEGIN source rows -->\n'
END = b'        <!-- END source rows -->'


def _parts(path):
    raw = path.read_bytes()
    if raw.count(BEGIN) != 1 or raw.count(END) != 1:
        raise ValueError(f'Missing or duplicate source-row markers in {path.name}')
    before, rows = raw.split(BEGIN)
    layout, after = rows.split(END)
    return before + BEGIN, layout, END + after


def sync_source_rows(root=ROOT, *, check=True):
    windows = root / WINDOWS
    _, layout, _ = _parts(windows / 'source_select.xml')
    direct = windows / 'source_select_direct.xml'
    before, old, after = _parts(direct)
    if old == layout:
        return
    if check:
        raise ValueError('Source rows are stale; run python tools/generate_source_rows.py')
    direct.write_bytes(before + layout + after)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail instead of writing the direct window')
    sync_source_rows(check=parser.parse_args().check)
