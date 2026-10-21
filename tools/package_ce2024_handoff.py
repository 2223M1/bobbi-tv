"""Create a local, commit-bound CE2024 handoff; never publish or overwrite it."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = 'd2fffa570fe59b90cd1d33499efcf7c6684b2647'
BASE = 'b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2'
SEQUENCE = 2026102024
PUBLIC_CA = 'third_party/addons/script.module.certifi/lib/certifi/cacert.pem'
CURATED_CATALOG = 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def validate_source_paths(names):
    """A Git snapshot, not an unexamined workspace/account backup."""
    folded = set()
    for name in names:
        parts = PurePosixPath(name).parts
        lower = name.lower()
        if (not parts or name.startswith('/') or '\\' in name or ':' in name
                or any(part in ('.', '..') for part in parts)
                or lower in folded):
            raise ValueError('INVALID_SOURCE_PATH')
        folded.add(lower)
        if any(part.lower() in ('.git', '.private', '.venv', '.venv-closure', '__pycache__') for part in parts):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if parts[0].lower() in ('profile', 'profiles', 'userdata', 'dist', 'staging'):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if (lower.endswith(('.keystore', '.jks', '/tmdb-project.json'))
                or lower.endswith(('.sqlite', '.sqlite3', '.db')) and name != CURATED_CATALOG
                or lower.endswith('.pem') and name != PUBLIC_CA):
            raise ValueError('LOCAL_SECRET_OR_DATABASE_IN_SOURCE')


def junit_counts(path):
    root = ET.parse(path).getroot()
    rows = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    if not rows:
        raise ValueError('MISSING_JUNIT_SUITE')
    result = {key: sum(int(row.get(key, '0')) for row in rows)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    result['passed'] = result['tests'] - result['failures'] - result['errors'] - result['skipped']
    return result


def local_gates():
    base = ROOT / 'review-evidence/ce2023'
    result = {'scope': 'local gates; remote CI recorded separately in GITHUB-STATUS.json', 'suites': {}, 'commands': {}}
    for name, expected in (('primary', 1823), ('baseline', 789), ('preparation', 177)):
        counts = junit_counts(base / ('clean24-' + name + '.xml'))
        if counts['passed'] != expected or counts['errors'] or counts['failures']:
            raise ValueError('TEST_RECEIPT_CHANGED')
        result['suites'][name] = counts
    for name in ('clean24-primary', 'clean24-baseline', 'clean24-preparation',
                 'clean24-source-a', 'clean24-source-b', 'clean24-repro', 'product24-final-audit'):
        value = json.loads((base / name / 'result.json').read_text(encoding='utf-8'))
        if value['exit_code'] != 0 or value['commit'] != PRODUCT:
            raise ValueError('GATE_IDENTITY_CHANGED')
        result['commands'][name] = {'exit_code': 0, 'source_commit': value['commit'],
                                   'receipt': 'review-evidence/ce2023/' + name + '/result.json'}
    result['not_passed'] = ['new_movie_startup', 'new_anime_audio_subtitle_buffering',
                          'historical_barakamon_metadata', 'warm_ui_smoke_timeout']
    result['not_certified'] = ['full_episode_continuation', 'full_ce2024_rollback',
                              'kodi_zip_browser_import', 'long_watch', 'seek',
                              'manual_subtitle_off', 'live_font_switch', 'subtitle_sync']
    return result


def inspect_source_archive(path, expected):
    with zipfile.ZipFile(path) as source:
        infos = [row for row in source.infolist() if not row.is_dir()]
        names = [row.filename for row in infos]
        validate_source_paths(names)
        if set(names) != set(expected) or len(names) != len(expected):
            raise ValueError('SOURCE_ARCHIVE_TREE_MISMATCH')
        evidence = []
        for row in infos:
            data = source.read(row.filename)  # Includes CRC verification.
            if row.filename.startswith('review-evidence/'):
                evidence.append(dict(path=row.filename, bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    acceptance='See the individual receipt and report; this index does not turn it into a pass'))
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--github-branch', help='Read-only verification after an explicitly authorized push')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists():
        raise ValueError('OUTPUT_EXISTS')
    # Protect the frozen candidate; staged/unstaged/untracked edits must be committed first.
    if git('status', '--porcelain').strip():
        raise ValueError('COMMIT_HANDOFF_FIRST')
    head = git('rev-parse', 'HEAD').decode().strip()
    if git('diff', PRODUCT, head, '--', 'addons', 'third_party', 'release').strip():
        raise ValueError('PRODUCT_CHANGED_SINCE_CERTIFIED_PACKAGE')
    names = git('ls-tree', '-r', '--name-only', '-z', head).decode('utf-8').rstrip('\x00').split('\x00')
    validate_source_paths(names)
    gates = local_gates()
    github = None
    if args.github_branch:
        repository = '2223M1/bobbi-tv'
        def gh(*parts):
            return json.loads(subprocess.check_output(['gh', *parts], cwd=ROOT, text=True, encoding='utf-8'))
        repo = gh('repo', 'view', repository, '--json', 'nameWithOwner,visibility,url')
        commit = gh('api', 'repos/' + repository + '/commits/' + args.github_branch)
        if repo['visibility'] != 'PRIVATE' or commit['sha'] != head:
            raise ValueError('REMOTE_IDENTITY_OR_VISIBILITY_CHANGED')
        runs = gh('run', 'list', '--repo', repository, '--branch', args.github_branch, '--limit', '10',
                  '--json', 'databaseId,headSha,status,conclusion,url,event,workflowName')
        github = dict(repository=repo, branch=args.github_branch, head_sha=commit['sha'],
                      commit_url=commit['html_url'], checked=time.time(),
                      runs=[row for row in runs if row['headSha'] == head],
                      merged=False, published=False, force_push=False)
    mapping = json.loads((ROOT/'review-evidence/ce2023/product24-source-package.json').read_text())
    if mapping['source_commit'] != PRODUCT or mapping['sequence'] != SEQUENCE:
        raise ValueError('PACKAGE_SOURCE_IDENTITY_CHANGED')
    artifacts = ROOT/'dist/ce2024-delivery'
    payload = artifacts/'bobbi-private-2026102024-coreelec.bobbi-update.zip'
    entry = artifacts/'script.bobbi.start-0.2.15-ce2024.zip'
    if sha(payload) != mapping['bundle_sha256'] or sha(entry) != mapping['entry_sha256']:
        raise ValueError('TESTED_PACKAGE_CHANGED')
    from audit_ce_entry import audit
    entry_audit = audit(entry)  # Real trust/signature/bootstrap, no signing key.
    with zipfile.ZipFile(entry) as archive:
        embedded = archive.read('script.bobbi.start/resources/complete.bobbi-update.zip')
    if hashlib.sha256(embedded).hexdigest() != sha(payload):
        raise ValueError('EMBEDDED_PAYLOAD_CHANGED')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-staging-', dir=destination.parent))
    # Failures intentionally leave only an explicitly named staging directory for diagnosis.
    source = stage/'BobbiTV-CE2024-Source-Evidence.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--output=' + str(source), head], cwd=ROOT, check=True)
    evidence = inspect_source_archive(source, names)
    write_json(stage/'EVIDENCE-INDEX.json', {'source_archive': source.name, 'entries': evidence})
    for artifact in (payload, entry):
        target = stage/artifact.name
        shutil.copyfile(artifact, target)
        if sha(target) != sha(artifact):
            raise ValueError('COPIED_ARTIFACT_CHANGED')
    shutil.copyfile(ROOT/'docs/CE2024-DELIVERY.md', stage/'REPORT.zh-CN.md')
    (stage/'PRODUCT-CHANGES.patch').write_bytes(git('diff', '--binary', BASE, PRODUCT, '--',
        'addons', 'third_party', 'release', 'tools', 'tests', '.github', '.gitignore', 'AGENTS.md'))
    (stage/'ALL-CHANGES.stat.txt').write_bytes(git('diff', '--stat', BASE, head))
    write_json(stage/'GATE-RESULTS.json', gates)
    if github is not None:
        write_json(stage/'GITHUB-STATUS.json', github)
    write_json(stage/'BUILD-ENVIRONMENT.json', {
        'python': sys.version, 'platform': platform.platform(),
        'dependencies': {name: importlib.metadata.version(name) for name in ('pytest', 'cryptography', 'requests')},
        'product_commit': PRODUCT, 'handoff_commit': head,
        'recipe': 'See source tools, requirements-test.txt, product24-*/result.json and clean24-*/result.json',
        'secrets_included': False, 'project_application_config': 'Only in signed private client payload, not source',
    })
    write_json(stage/'DELIVERY.json', {
        'schema': 1, 'created': time.time(), 'sequence': SEQUENCE,
        'product_commit': PRODUCT, 'product_tree': mapping['source_tree'],
        'handoff_commit': head, 'handoff_tree': git('rev-parse', head+'^{tree}').decode().strip(),
        'product_unchanged_in_handoff': True, 'local_only': github is None,
        'remote_ci_run': bool(github and github['runs']),
        'source_members': len(names), 'evidence_members': len(evidence),
        'bundle_sha256': sha(payload), 'entry_sha256': sha(entry), 'entry_audit': entry_audit,
        'playback_certification': 'Partial; unresolved failures are listed in REPORT.zh-CN.md',
    })
    members = sorted(stage.iterdir())
    write_json(stage/'FILES.json', {'files': [dict(name=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in members]})
    review = stage/'BobbiTV-CE2024-Review-20261021.zip'
    with zipfile.ZipFile(review, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for path in sorted(stage.iterdir()):
            if path == review:
                continue
            out.write(path, path.name, compress_type=zipfile.ZIP_STORED if path.suffix == '.zip' else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(review) as archive:
        if archive.testzip() is not None:
            raise ValueError('REVIEW_ZIP_CRC_FAILURE')
    write_json(stage/'REVIEW-ARCHIVE.json', dict(name=review.name, bytes=review.stat().st_size, sha256=sha(review),
                                               verified_crc=True, members=len(members)+1))
    if destination.exists():
        raise ValueError('OUTPUT_APPEARED_DURING_PACKAGING')
    stage.rename(destination)
    print(json.dumps(dict(output=str(destination), source_commit=PRODUCT, handoff_commit=head,
                          review_bytes=(destination/review.name).stat().st_size, local_only=github is None)))


if __name__ == '__main__':
    main()
