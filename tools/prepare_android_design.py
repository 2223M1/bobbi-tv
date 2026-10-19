"""Bundle unchanged licensed cinema fonts; never subset or rename binaries."""
import argparse
import hashlib
from pathlib import Path
import shutil

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
    for name, expected in FONTS.items():
        path = source / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Licensed font input changed: ' + name)
    for dest_root in (public, android):
        dest_root.mkdir(parents=True, exist_ok=True)
        for name in FONTS:
            source_file, dest = source / name, dest_root / name
            if source_file.resolve() != dest.resolve():
                if dest.is_symlink():
                    raise ValueError('Symlink font output')
                shutil.copyfile(source_file, dest)
    return {'fonts': 2, 'license': True, 'modified_font_binaries': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    print(prepare(parser.parse_args().source))
