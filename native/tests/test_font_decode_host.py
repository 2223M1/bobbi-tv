"""Actual host decoder/limiter integration, separate from Android ABI verification."""
import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.android_font_decoder import decoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='bobbi-font-decoder-') as directory:
        root = Path(directory)
        source = args.font.read_bytes()
        archive = root/'fonts.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
            row = zipfile.ZipInfo('Fonts/fixture.ttf')
            row.create_system = 0
            row.external_attr = 0x20
            zipped.writestr(row, source)
        decode = decoder(args.tools/'libbobbi_7zip.so', args.tools/'libbobbi_font_limiter.so')
        fonts = decode(archive, hashlib.sha256(archive.read_bytes()).hexdigest(), root/'output', lambda: True)
        assert len(fonts) == 1
        assert Path(fonts[0]['path']).read_bytes() == source
        assert fonts[0]['sha256'] == hashlib.sha256(source).hexdigest()
    print('PASS actual font archive -> bounded native child -> inspected font bytes (Linux host, not Android runtime)')


if __name__ == '__main__':
    main()
