"""Publish only the launcher and repository; cinema components remain one generation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

from build_ce_entry import build, ROOT
from build_release import archive, files
from bobbi_platform.offline_updates import SignedBundle, load_trust


def publish(bundle, output, tag):
    if not re.fullmatch(r'ce[1-9][0-9]{3,7}', tag):
        raise ValueError('Invalid release tag')
    output = Path(output)
    if output.exists():
        raise ValueError('Repository output must be new')
    bundle = Path(bundle)
    with SignedBundle(bundle, load_trust(), 'coreelec') as signed:
        manifest = signed.check_all()
        rows = {row['id']: row for row in manifest['components']}
        # Never index metadata from a different checkout than the signed source.
        for name in ('script.bobbi.start', 'repository.bobbi'):
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(signed.read(rows[name]['file'], rows[name]['size']))) as source:
                if source.read(name + '/addon.xml') != (ROOT / 'addons' / name / 'addon.xml').read_bytes():
                    raise ValueError('Repository metadata differs from signed generation')
    output.mkdir(parents=True)
    xml = ET.Element('addons')
    for name in ('repository.bobbi', 'script.bobbi.start'):
        root = ROOT / 'addons' / name
        meta = ET.parse(root / 'addon.xml').getroot()
        directory = output / name
        directory.mkdir()
        target = directory / (name + '-' + meta.get('version') + '.zip')
        if name == 'script.bobbi.start':
            build(bundle, target, online=True)
            target.with_suffix('.json').unlink()  # Build receipt is not a repository artifact.
        else:
            archive(root, files(root), target)
        target.with_suffix('.zip.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding='ascii')
        for asset in meta.findall('./extension/assets/*'):
            if asset.text and (root / asset.text).is_file():
                dest = directory / asset.text
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / asset.text, dest)
        xml.append(meta)
    raw = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(xml, encoding='utf-8') + b'\n'
    (output / 'addons.xml').write_bytes(raw)
    (output / 'addons.xml.sha256').write_text(hashlib.sha256(raw).hexdigest(), encoding='ascii')
    (output / 'addons.xml.md5').write_text(hashlib.md5(raw).hexdigest(), encoding='ascii')
    offer = dict(schema=1, tag=tag, sequence=manifest['sequence'], size=bundle.stat().st_size,
        sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        url='https://github.com/2223M1/bobbi-tv/releases/download/' + tag + '/BobbiTV-' + tag.upper() + '.bobbi-update.zip')
    (output / 'current.json').write_bytes((json.dumps(offer, indent=2) + '\n').encode('utf-8'))
    repo = rows['repository.bobbi']
    # Optional landing page. Raw GitHub URLs do not serve a directory index.
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>波比 TV 安装</title>'
            '<h1>波比 TV</h1><p>先安装仓库，再从程序插件安装“波比 TV · 开始使用”。</p>'
            '<a href="repository.bobbi/repository.bobbi-' + repo['version'] + '.zip">'
            'repository.bobbi-' + repo['version'] + '.zip</a></html>\n')
    (output / 'index.html').write_bytes(page.encode('utf-8'))
    return offer


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.bundle, args.output, args.tag), indent=2))
