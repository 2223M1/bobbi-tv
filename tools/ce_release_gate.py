"""Freeze CE publication inputs; promote feeds only after actual remote readback.

Signing and upload stay in the maintainer's environment. This tool uses the
existing package/entry/transport contracts and never handles a private key.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust
from bobbi_platform.online_updates import _transfer, parse_offer, release_url
from bobbi_platform.updates import _safe_path


def identity(path):
    path = _safe_path(Path(path).resolve())
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def source_matches(signed):
    from build_release import sources, files, project_resource, LOCAL_RESOURCE
    roots = sources()
    inventory = json.loads((ROOT / 'release/source-inventory.json').read_text())['components']
    if set(roots) != {r['id'] for r in signed.manifest['components']}:
        raise ValueError('Source vector differs')
    for row in signed.manifest['components']:
        name = row['id']
        expected = files(roots[name])
        if expected != inventory[name]:
            raise ValueError('Source inventory changed')
        if name == LOCAL_RESOURCE[0]:
            expected[LOCAL_RESOURCE[1]] = hashlib.sha256(project_resource(roots)).hexdigest()
        with zipfile.ZipFile(BytesIO(signed.read(row['file'], row['size']))) as archive:
            actual = {p[len(name)+1:]: hashlib.sha256(archive.read(p)).hexdigest() for p in archive.namelist()}
        if actual != expected:
            raise ValueError('Signed component differs from frozen source: ' + name)


def prepare(bundle, entry, component_assets, feeds, output):
    from audit_ce_entry import audit
    output = Path(output)
    if output.exists():
        raise ValueError('Publication receipt must be new')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise ValueError('Commit tracked changes before freezing publication')
    with SignedBundle(bundle, load_trust(), 'coreelec') as signed:
        manifest = signed.check_all()
        source_matches(signed)
    if audit(entry)['sequence'] != manifest['sequence']:
        raise ValueError('Entry belongs to another generation')
    with zipfile.ZipFile(entry) as archive:
        raw = archive.read('script.bobbi.start/resources/complete.bobbi-update.zip')
        if hashlib.sha256(raw).hexdigest() != identity(bundle)['sha256']:
            raise ValueError('Embedded complete package differs')
    feed_rows, offers = {}, {}
    for channel, folder in feeds.items():
        offer = parse_offer((Path(folder) / 'current.json').read_bytes())
        if offer['url'] != release_url(offer['tag'], channel) or offer['sequence'] != manifest['sequence']:
            raise ValueError('Feed generation/channel differs')
        if any(offer[key] != identity(bundle)[other] for key, other in (('size', 'bytes'), ('sha256', 'sha256'))):
            raise ValueError('Feed package differs')
        offers[channel] = offer
        from build_online_repository import publish
        with tempfile.TemporaryDirectory(prefix='bobbi-release-feed-') as temporary:
            expected_feed = Path(temporary) / 'expected'
            publish(bundle, expected_feed, offer['tag'], channel)
            expected_files = {p.relative_to(expected_feed).as_posix(): identity(p)['sha256']
                              for p in expected_feed.rglob('*') if p.is_file()}
            actual_files = {p.relative_to(folder).as_posix(): identity(p)['sha256']
                            for p in Path(folder).rglob('*') if p.is_file()}
            if expected_files != actual_files:
                raise ValueError('Feed differs from signed generation')
        feed_rows[channel] = {p.relative_to(folder).as_posix(): identity(p)
                              for p in sorted(Path(folder).rglob('*')) if p.is_file()}
    if set(offers) != {'github', 'gitee'} or offers['github']['tag'] != offers['gitee']['tag']:
        raise ValueError('Both canonical feeds required')
    tag = offers['github']['tag']
    if Path(bundle).name != Path(release_url(tag)).name:
        raise ValueError('Canonical complete package filename required')
    assets = {Path(bundle).name: identity(bundle), Path(entry).name: identity(entry)}
    # Compare against the actual signed source, not a hand-edited asset listing.
    from build_component_assets import build
    with tempfile.TemporaryDirectory(prefix='bobbi-release-assets-') as temporary:
        rebuilt = Path(temporary) / 'expected'
        build(bundle, rebuilt, tag)
        if {p.name for p in Path(component_assets).iterdir()} != {p.name for p in rebuilt.iterdir()}:
            raise ValueError('Component asset vector differs')
        for path in rebuilt.iterdir():
            actual = identity(Path(component_assets) / path.name)
            if actual['sha256'] != identity(path)['sha256']:
                raise ValueError('Component asset changed')
            assets[path.name] = actual
    receipt = dict(schema=1, commit=commit, tree=tree, tag=tag, sequence=manifest['sequence'],
                   assets=assets, feeds=feed_rows, offers=offers, created_at=int(time.time()))
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def recheck_local(receipt):
    for row in list(receipt['assets'].values()) + [r for feed in receipt['feeds'].values() for r in feed.values()]:
        if identity(row['path']) != row:
            raise ValueError('Frozen publication input changed')


def readback(receipt, channel, report, transfer=_transfer):
    """Every byte, including the optional component route, before any promotion."""
    recheck_local(receipt)
    base = release_url(receipt['tag'], channel).rsplit('/', 1)[0] + '/'
    result = dict(commit=receipt['commit'], tree=receipt['tree'], tag=receipt['tag'],
                  channel=channel, started_at=int(time.time()), files=[], passed=False)
    try:
        for name, expected in receipt['assets'].items():
            digest, count = hashlib.sha256(), 0
            def consume(block):
                nonlocal count
                count += len(block)
                digest.update(block)
            transfer(base + name, expected['bytes'], consume, lambda: False, lambda _: None,
                     expected=expected['bytes'], deadline=time.monotonic() + 600)
            row = dict(file=name, bytes=count, matched=count == expected['bytes'] and digest.hexdigest() == expected['sha256'])
            result['files'].append(row)
            if not row['matched']:
                raise ValueError('Remote release asset differs')
        recheck_local(receipt)
        result['passed'] = True
        return result
    except Exception as error:
        result['error_class'] = type(error).__name__
        raise
    finally:
        result['finished_at'] = int(time.time())
        Path(report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


def promote(receipt, channel, target, report, transfer=_transfer):
    """Keep old ZIPs; publish data before discovery pointers. No network writes."""
    readback(receipt, channel, report, transfer)
    target = _safe_path(Path(target).absolute())
    target.mkdir(parents=True, exist_ok=True)
    feed = receipt['feeds'][channel]
    pointers = ('addons.xml.md5', 'addons.xml.sha256', 'addons.xml', 'index.html', 'current.json')
    names = sorted(set(feed) - set(pointers)) + [name for name in pointers if name in feed]
    # Validate the whole path vector before the first output mutation.
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid feed path')
        _safe_path(target / relative)
    for name in names:
        # The receipt is maintainer-local, but never let an edited path escape.
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid feed path')
        destination = _safe_path(target / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=str(destination.parent))
        try:
            with os.fdopen(fd, 'wb') as output, Path(feed[name]['path']).open('rb') as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            if identity(temporary)['sha256'] != feed[name]['sha256']:
                raise ValueError('Feed changed during promotion')
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation', required=True)
    stage = sub.add_parser('prepare')
    for name in ('bundle', 'entry', 'component-assets', 'github-feed', 'gitee-feed', 'output'):
        stage.add_argument('--' + name, required=True, type=Path)
    for operation in ('verify', 'promote'):
        step = sub.add_parser(operation)
        step.add_argument('--receipt', required=True, type=Path)
        step.add_argument('--channel', required=True, choices=('github', 'gitee'))
        step.add_argument('--report', required=True, type=Path)
        if operation == 'promote': step.add_argument('--target', required=True, type=Path)
    args = parser.parse_args()
    if args.operation == 'prepare':
        result = prepare(args.bundle, args.entry, args.component_assets,
                         dict(github=args.github_feed, gitee=args.gitee_feed), args.output)
        print(json.dumps({key: result[key] for key in ('commit', 'tree', 'tag', 'sequence')}))
    else:
        receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
        if args.operation == 'verify': readback(receipt, args.channel, args.report)
        else: promote(receipt, args.channel, args.target, args.report)
        print(json.dumps(dict(tag=receipt['tag'], channel=args.channel, operation=args.operation, passed=True)))
