"""Bundle unchanged licensed cinema fonts; never subset or rename binaries."""
import argparse
import hashlib
from pathlib import Path
import shutil
from provenance_document import read_source

ROOT = Path(__file__).resolve().parents[1]
FONTS = {
    'HarmonyOS_SansSC_Regular.ttf': '984cf609545acee8ef060780fb70fc3099b058c0553416331b6e863fdf7c26fa',
    'HarmonyOS_SansSC_Bold.ttf': 'c215d8ab1cb6709fec2e063f8213e9af86d7587d345b56325e36b67d6b947d98',
    'LICENCE-HarmonyOS-Sans.txt': '327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102',
}


def prepare(source=None):
    public = ROOT / 'assets/fonts'
    source = Path(source) if source is not None else public
    android = ROOT / 'android/app/src/main/assets/fonts'
    payloads = {}
    for name, expected in FONTS.items():
        path = source / name
        raw = read_source(ROOT, 'assets/fonts/' + name) if source == public else path.read_bytes()
        if path.is_symlink() or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Licensed font input changed: ' + name)
        payloads[name] = raw
    for dest_root in (public, android):
        dest_root.mkdir(parents=True, exist_ok=True)
        for name in FONTS:
            if dest_root == public and name.startswith('LICENCE-'):
                continue  # Canonical source remains inside COPYRIGHT.zh-CN.md.
            source_file, dest = source / name, dest_root / name
            if source_file.resolve() != dest.resolve():
                if dest.is_symlink():
                    raise ValueError('Symlink font output')
                dest.write_bytes(payloads[name])
    return {'fonts': 2, 'license': True, 'modified_font_binaries': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    print(prepare(parser.parse_args().source))
