"""Read-only release audit; extraction and negative fixtures stay in one temp root."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust, MAX_BUNDLE
from bobbi_platform.updates import (UpdateEngine, UpdateError, MAX_ARCHIVE,
                                    MAX_EXPANDED, MAX_FILES, MAX_RATIO)
from sign_private_bundle import checked_components


def rejected(path, trust, profile):
    try:
        with SignedBundle(path, trust, profile) as source:
            source.check_all()
    except UpdateError as error:
        return str(error)
    raise AssertionError('Invalid fixture was accepted')


def audit(components, releases, sequence, profiles=('windows', 'coreelec', 'android')):
    if (not profiles or len(set(profiles)) != len(profiles)
            or any(p not in ('windows', 'coreelec', 'android') for p in profiles)):
        raise ValueError('Select explicit unique release profiles')
    trust = load_trust()
    built = json.loads((components / 'manifest.json').read_text(encoding='utf-8'))
    checked = checked_components(components, built, trust)
    result = {'schema': 1, 'scope': 'actual private component ZIPs and signed offline bundles; not device certification',
              'profiles_audited': list(profiles),
              'limits': {'archive_bytes': MAX_ARCHIVE, 'expanded_bytes_per_component': MAX_EXPANDED,
                         'files_per_component': MAX_FILES, 'member_expansion_ratio': MAX_RATIO,
                         'signed_bundle_bytes': MAX_BUNDLE}, 'components': [], 'bundles': [], 'negative_checks': {}}
    with tempfile.TemporaryDirectory(prefix='bobbi-private-archive-audit-') as temporary:
        root = Path(temporary).resolve()
        assert root.name.startswith('bobbi-private-archive-audit-')
        engine = UpdateEngine(root/'addons', root/'work', trust['components'], 'private-candidate',
                              'windows', lambda *_: False, lambda *_: None, lambda: True,
                              nullcontext, offline=True)
        stage = root/'stage'
        stage.mkdir()
        for row, blob in checked:
            item = dict(id=row['id'], version=row['version'], size=row['bytes'], sha256=row['sha256'])
            engine._extract(blob, item, stage)
            with zipfile.ZipFile(components / row['file']) as archive:
                members = archive.infolist()
                worst = max(members, key=lambda r: r.file_size / max(1, r.compress_size))
                result['components'].append(dict(id=row['id'], file=row['file'], sha256=row['sha256'],
                    archive_bytes=len(blob), expanded_bytes=sum(r.file_size for r in members), files=len(members),
                    max_member_ratio=round(worst.file_size/max(1, worst.compress_size), 4),
                    max_ratio_member=worst.filename, updater_extraction='passed'))
        for profile in profiles:
            path = releases/('bobbi-private-%s-%s.bobbi-update.zip' % (sequence, profile))
            with SignedBundle(path, trust, profile) as source:
                manifest = source.check_all()
                assert manifest['sequence'] == sequence
                result['bundles'].append(dict(file=path.name, profile=profile, bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), components=len(manifest['components']),
                    signature='passed', all_component_hashes='passed'))
        selected = profiles[0]
        original = releases/('bobbi-private-%s-%s.bobbi-update.zip' % (sequence, selected))
        wrong = 'windows' if selected != 'windows' else 'coreelec'
        result['negative_checks']['wrong_profile'] = rejected(original, trust, wrong)
        with zipfile.ZipFile(original) as archive:
            content = [(member, archive.read(member.filename)) for member in archive.infolist()]
        for case in ('signature_tampered', 'component_tampered', 'missing_component'):
            path = root/(case + '.zip')
            with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_STORED) as archive:
                for index, (member, data) in enumerate(content):
                    if case == 'signature_tampered' and member.filename == 'release.sig':
                        data = (b'A' if data[:1] != b'A' else b'B') + data[1:]
                    if index == len(content)-1:
                        if case == 'missing_component':
                            continue
                        if case == 'component_tampered':
                            data = bytes([data[0] ^ 1]) + data[1:]
                    archive.writestr(member, data)
            result['negative_checks'][case] = rejected(path, trust, selected)
    result['total_component_archive_bytes'] = sum(row['archive_bytes'] for row in result['components'])
    result['total_component_expanded_bytes'] = sum(row['expanded_bytes'] for row in result['components'])
    result['total_files'] = sum(row['files'] for row in result['components'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--components', type=Path, default=ROOT/'dist/private-components')
    parser.add_argument('--releases', type=Path, default=ROOT/'dist/private-releases')
    parser.add_argument('--sequence', type=int, default=2026101901)
    parser.add_argument('--profiles', nargs='+', choices=('windows', 'coreelec', 'android'),
                        default=['windows', 'coreelec', 'android'])
    parser.add_argument('--report', type=Path, default=ROOT/'review-evidence/private-artifact-boundaries.json')
    args = parser.parse_args()
    report = audit(args.components, args.releases, args.sequence, args.profiles)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: report[name] for name in ('total_component_archive_bytes',
        'total_component_expanded_bytes', 'total_files', 'negative_checks')}, indent=2))
