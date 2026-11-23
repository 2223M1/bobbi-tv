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
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust
from bobbi_platform.online_updates import _transfer, parse_offer, release_url, feed_url, check_offer_manifest
from bobbi_platform.updates import _safe_path, _json


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


def source_check_evidence(first, second):
    """Two reproducible source checks, both tied to the reviewed source vector."""
    from check_repository import compare
    from build_release import sources, files
    count = compare(first, second)
    built = json.loads((Path(first) / 'manifest.json').read_text(encoding='utf-8'))
    roots = sources()
    if (built.get('channel') != 'source-check' or built.get('installable') is not False
            or len(built.get('components', [])) != len(roots)
            or {row['id'] for row in built['components']} != set(roots)):
        raise ValueError('Source-check evidence required')
    for row in built['components']:
        if row['file'] != '{0}/{0}-{1}.zip'.format(row['id'], row['version']):
            raise ValueError('Invalid source-check component path')
        path = _safe_path(Path(first) / row['file'])
        checked = identity(path)
        if (checked['bytes'], checked['sha256']) != (row['bytes'], row['sha256']):
            raise ValueError('Source-check component changed')
        with zipfile.ZipFile(path) as archive:
            prefix = row['id'] + '/'
            if any(not name.startswith(prefix) for name in archive.namelist()):
                raise ValueError('Source-check component identity differs')
            actual = {name[len(prefix):]: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
            if len(actual) != len(archive.namelist()) or actual != files(roots[row['id']]):
                raise ValueError('Source-check differs from frozen source')
    return dict(reproducible_files=count, files=[identity(path) for folder in (first, second)
        for path in sorted(Path(folder).rglob('*')) if path.is_file()])


MIRRORS = {'dual': ('github', 'gitee'), 'github-only': ('github',)}


def prepare(bundle, entry, component_assets, feeds, output, *, track, github_release, source_checks,
            mirror_policy='dual'):
    from audit_ce_entry import audit
    if mirror_policy not in MIRRORS or set(feeds) != set(MIRRORS[mirror_policy]):
        raise ValueError('Feeds must match the explicitly selected mirror policy')
    output = Path(output)
    if output.exists():
        raise ValueError('Publication receipt must be new')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise ValueError('Commit tracked changes before freezing publication')
    metadata = json.loads(Path(github_release).read_text(encoding='utf-8'))
    if (track not in ('stable', 'preview') or metadata.get('prerelease') is not (track == 'preview')
            or metadata.get('draft') is not False or metadata.get('target_commitish') != commit):
        raise ValueError('GitHub release track/commit metadata differs')
    from vendor_licenses import require_distribution
    require_distribution()
    source_evidence = source_check_evidence(*source_checks)
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
        offer = parse_offer((Path(folder) / 'current.json').read_bytes(), track)
        check_offer_manifest(offer, manifest)
        if offer['schema'] != 2 or offer['tag'] != metadata.get('tag_name'):
            raise ValueError('Versioned feed/release metadata required')
        if offer['url'] != release_url(offer['tag'], channel) or offer['sequence'] != manifest['sequence']:
            raise ValueError('Feed generation/channel differs')
        if any(offer[key] != identity(bundle)[other] for key, other in (('size', 'bytes'), ('sha256', 'sha256'))):
            raise ValueError('Feed package differs')
        offers[channel] = offer
        from build_online_repository import publish
        with tempfile.TemporaryDirectory(prefix='bobbi-release-feed-') as temporary:
            expected_feed = Path(temporary) / 'expected'
            publish(bundle, expected_feed, offer['tag'], channel, track, metadata['prerelease'])
            expected_files = {p.relative_to(expected_feed).as_posix(): identity(p)['sha256']
                              for p in expected_feed.rglob('*') if p.is_file()}
            actual_files = {p.relative_to(folder).as_posix(): identity(p)['sha256']
                            for p in Path(folder).rglob('*') if p.is_file()}
            if expected_files != actual_files:
                raise ValueError('Feed differs from signed generation')
        feed_rows[channel] = {p.relative_to(folder).as_posix(): identity(p)
                              for p in sorted(Path(folder).rglob('*')) if p.is_file()}
    if len({o['tag'] for o in offers.values()}) != 1:
        raise ValueError('Canonical feeds must refer to the same tag')
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
    receipt = dict(schema=3, mirror_policy=mirror_policy, commit=commit, tree=tree, tag=tag, track=track, sequence=manifest['sequence'],
                   assets=assets, feeds=feed_rows, offers=offers, github_release=identity(github_release),
                   source_checks=source_evidence,
                   evidence=[identity(ROOT / 'licenses/THIRD-PARTY.json'), identity(ROOT / 'release/capability-matrix.json')],
                   created_at=int(time.time()))
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def recheck_local(receipt):
    extra = [receipt['github_release']] if 'github_release' in receipt else []
    extra += receipt.get('evidence', []) + receipt.get('source_checks', {}).get('files', [])
    for row in list(receipt['assets'].values()) + [r for feed in receipt['feeds'].values() for r in feed.values()] + extra:
        if identity(row['path']) != row:
            raise ValueError('Frozen publication input changed')


def _pointer_guard(raw, receipt, mirror):
    old = parse_offer(raw, receipt['track'])
    new = receipt['offers'][mirror]
    if old['sequence'] > new['sequence'] or (old['sequence'] == new['sequence'] and old != new):
        raise ValueError('Active pointer is newer or has conflicting package identity')
    return old['sequence']


def _mirrors(receipt):
    schema = receipt.get('schema')
    mirrors = ('github', 'gitee') if schema == 2 else (
        MIRRORS.get(receipt.get('mirror_policy'), ()) if schema == 3 else ())
    if (not mirrors or set(receipt['feeds']) != set(mirrors) or receipt.get('track') not in ('stable', 'preview')
            or (schema == 3 and set(receipt.get('offers', ())) != set(mirrors))):
        raise ValueError('Versioned dual-mirror or scoped publication receipt required')
    if schema == 3:
        for mirror in mirrors:
            row = receipt['feeds'][mirror]['current.json']
            if row['bytes'] > 32768:
                raise ValueError('Invalid frozen track pointer')
            offer = parse_offer(Path(row['path']).read_bytes(), receipt['track'])
            if (offer != receipt['offers'][mirror] or offer['tag'] != receipt['tag']
                    or offer['sequence'] != receipt['sequence'] or offer['url'] != release_url(receipt['tag'], mirror)):
                raise ValueError('Frozen offer identity differs')
    return mirrors


def readback(receipt, channel, report, transfer=_transfer, *, staged=False):
    """Before a feed commit check assets + old pointer; after push check every live byte."""
    recheck_local(receipt)
    mirrors = _mirrors(receipt)
    if channel not in mirrors or (staged and receipt['schema'] != 3):
        raise ValueError('Invalid mirror channel')
    result = dict(commit=receipt['commit'], tree=receipt['tree'], tag=receipt['tag'],
                  phase='before-feed-commit' if staged else 'live-feed-readback', mirrors=mirrors,
                  track=receipt['track'], channel=channel, started_at=int(time.time()), files=[], passed=False,
                  promotable=False)
    try:
        chunks = []
        transfer('https://api.github.com/repos/2223M1/bobbi-tv/releases/tags/' + receipt['tag'],
                 256 * 1024, chunks.append, lambda: False, lambda _: None,
                 deadline=time.monotonic() + 20)
        metadata = _json(b''.join(chunks))
        if (metadata.get('tag_name') != receipt['tag'] or metadata.get('draft') is not False
                or metadata.get('prerelease') is not (receipt['track'] == 'preview')
                or metadata.get('target_commitish') != receipt['commit']):
            raise ValueError('Remote GitHub release identity differs')
        result['github_release_identity'] = 'matched'
        targets = []
        for mirror in mirrors:
            base = release_url(receipt['tag'], mirror).rsplit('/', 1)[0] + '/'
            targets.extend((mirror, 'asset', base + name, name, expected) for name, expected in receipt['assets'].items())
            url = feed_url(receipt['track'], mirror)
            if staged:
                chunks = []
                try:
                    transfer(url, 32768, chunks.append, lambda: False, lambda _: None,
                             deadline=time.monotonic() + 20)
                except HTTPError as error:
                    if error.code != 404 or receipt['track'] != 'preview':
                        raise
                    previous = None  # A not-yet-created preview; never assume a stable feed is absent.
                else:
                    previous = _pointer_guard(b''.join(chunks), receipt, mirror)
                result.setdefault('previous_sequences', {})[mirror] = previous
                continue
            base = url.rsplit('/', 1)[0] + '/'
            for name, expected in receipt['feeds'][mirror].items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                    raise ValueError('Invalid feed path')
                targets.append((mirror, 'feed', base + name, name, expected))
        deadline = time.monotonic() + 1200
        for mirror, kind, url, name, expected in targets:
            digest, count = hashlib.sha256(), 0
            def consume(block):
                nonlocal count
                count += len(block)
                digest.update(block)
            transfer(url, expected['bytes'], consume, lambda: False, lambda _: None,
                     expected=expected['bytes'], deadline=deadline)
            row = dict(mirror=mirror, kind=kind, file=name, bytes=count, matched=count == expected['bytes'] and digest.hexdigest() == expected['sha256'])
            result['files'].append(row)
            if not row['matched']:
                raise ValueError('Remote release asset differs')
        recheck_local(receipt)
        result['passed'] = True
        result['promotable'] = True
        return result
    except Exception as error:
        result['error_class'] = type(error).__name__
        raise
    finally:
        result['finished_at'] = int(time.time())
        Path(report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


def promote(receipt, channel, target, report, transfer=_transfer):
    """Keep old ZIPs; publish data before discovery pointers. No network writes."""
    target = _safe_path(Path(target).absolute())
    if target.name != receipt.get('track'):
        raise ValueError('Promotion target must be the selected track directory; legacy current.json is immutable here')
    staged = receipt.get('schema') == 3
    if staged:
        if channel not in _mirrors(receipt):
            raise ValueError('Invalid mirror channel')
        live = _safe_path(target / 'current.json')
        if live.exists():
            if live.stat().st_size > 32768:
                raise ValueError('Invalid local track pointer')
            _pointer_guard(live.read_bytes(), receipt, channel)
    readback(receipt, channel, report, transfer, staged=staged)
    feed = receipt['feeds'][channel]
    pointers = ('addons.xml.md5', 'addons.xml.sha256', 'addons.xml', 'index.html', 'current.json')
    names = sorted(set(feed) - set(pointers)) + [name for name in pointers if name in feed]
    # Validate the whole path vector before the first output mutation.
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid feed path')
        destination = _safe_path(target / relative)
        if (staged and (name.endswith('.zip') or name.endswith('.zip.sha256')) and destination.exists()
                and identity(destination)['sha256'] != feed[name]['sha256']):
            raise ValueError('Published versioned file cannot change')
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
    for name in ('bundle', 'entry', 'component-assets', 'github-feed', 'output'):
        stage.add_argument('--' + name, required=True, type=Path)
    stage.add_argument('--gitee-feed', type=Path, help='Required for the default dual-mirror policy')
    stage.add_argument('--mirror-policy', choices=tuple(MIRRORS), default='dual')
    stage.add_argument('--track', choices=('stable', 'preview'), required=True)
    stage.add_argument('--github-release', type=Path, required=True, help='Frozen GitHub release JSON with resolved target commit')
    stage.add_argument('--source-first', type=Path, required=True)
    stage.add_argument('--source-second', type=Path, required=True)
    for operation in ('verify', 'promote'):
        step = sub.add_parser(operation)
        step.add_argument('--receipt', required=True, type=Path)
        step.add_argument('--channel', required=True, choices=('github', 'gitee'))
        step.add_argument('--report', required=True, type=Path)
        if operation == 'promote':
            step.add_argument('--target', required=True, type=Path, help='Local repository/stable or repository/preview directory')
    args = parser.parse_args()
    if args.operation == 'prepare':
        feeds = dict(github=args.github_feed)
        if args.gitee_feed is not None: feeds['gitee'] = args.gitee_feed
        result = prepare(args.bundle, args.entry, args.component_assets, feeds, args.output,
                         mirror_policy=args.mirror_policy,
                         track=args.track, github_release=args.github_release,
                         source_checks=(args.source_first, args.source_second))
        print(json.dumps({key: result[key] for key in ('commit', 'tree', 'tag', 'sequence')}))
    else:
        receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
        if args.operation == 'verify': readback(receipt, args.channel, args.report)
        else: promote(receipt, args.channel, args.target, args.report)
        print(json.dumps(dict(tag=receipt['tag'], channel=args.channel, operation=args.operation, passed=True)))
