"""Check a candidate against a frozen, freshly retrieved published generation.

Read-only preflight. It allocates no sequence, creates no tag, and never changes
the published feed. The operator must fetch the current selected track first.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.online_updates import parse_offer
from bobbi_platform.upstream_addons import OWNED_COMPONENTS, compare_versions
from build_ce_entry import BOOTSTRAP


def check_versions(offer, versions, changed_paths):
    """Changed owned components and the assembled launcher need fresh versions."""
    changed = set()
    bootstrap = {'addons/script.module.bobbi.platform/lib/bobbi_platform/' + name
                 for name in BOOTSTRAP}
    for path in changed_paths:
        parts = path.split('/')
        if len(parts) >= 3 and parts[0] == 'addons' and parts[1] in OWNED_COMPONENTS:
            changed.add(parts[1])
    assembly = {'tools/build_ce_entry.py', 'tools/build_online_repository.py'}
    if (bootstrap | assembly).intersection(changed_paths):
        changed.add('script.bobbi.start')
    prior = offer['versions']
    failures = []
    advances = {}
    for name in sorted(changed):
        new, old = versions.get(name), prior.get(name)
        if not new:
            failures.append(name + ': candidate component missing')
        elif old is not None and compare_versions(new, old) <= 0:
            failures.append(name + ': changed bytes require version > ' + old + ' (got ' + new + ')')
        else:
            advances[name] = {'published': old, 'candidate': new}
    if failures:
        raise ValueError('RELEASE_VERSION_REUSE: ' + '; '.join(failures))
    return {'changed_owned_components': sorted(changed), 'version_advances': advances,
            'published_tag': offer['tag'], 'published_sequence': offer['sequence'],
            'sequence_allocated': False, 'publication_verified': False}


def preflight(feed, commit=None, root=ROOT):
    root = Path(root).resolve()
    raw = Path(feed).read_bytes()
    if len(raw) > 32768:
        raise ValueError('Published feed too large')
    data = json.loads(raw)
    offer = parse_offer(raw, data.get('track', 'stable'))
    if offer['schema'] != 2:
        raise ValueError('Versioned published feed required')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    if commit is None:
        commit = git('rev-parse', 'refs/tags/' + offer['tag'] + '^{commit}')
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Full published source commit SHA required')
    if git('rev-parse', commit + '^{commit}') != commit:
        raise ValueError('Published commit object differs')
    # A baseline outside candidate ancestry is not a meaningful release diff,
    # unless a rebased/cherry-picked ancestor on HEAD carries the exact published tree SHA.
    anc = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, 'HEAD'])
    if anc.returncode != 0:
        published_tree = git('rev-parse', commit + '^{tree}')
        matched_anc = None
        for line in git('log', '--format=%H:%T', 'HEAD').splitlines():
            cand_sha, cand_tree = line.split(':', 1)
            if cand_tree == published_tree:
                matched_anc = cand_sha
                break
        if matched_anc is None:
            raise subprocess.CalledProcessError(anc.returncode, anc.args)
    versions = {}
    for addon in OWNED_COMPONENTS:
        path = root / 'addons' / addon / 'addon.xml'
        if path.is_file():
            meta = ET.parse(path).getroot()
            if meta.get('id') != addon:
                raise ValueError('Candidate component identity differs')
            versions[addon] = meta.get('version')
    # Include working-tree edits: running before the final commit cannot hide a
    # changed addon. Publication still separately requires a clean frozen tree.
    changed = git('diff', '--name-only', commit, '--', 'addons',
                  'tools/build_ce_entry.py', 'tools/build_online_repository.py').splitlines()
    result = check_versions(offer, versions, changed)
    result.update(published_commit=commit, candidate_commit=git('rev-parse', 'HEAD'))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--published-feed', type=Path, required=True)
    parser.add_argument('--published-commit', help='Full source commit; defaults to the fetched feed tag')
    args = parser.parse_args()
    print(json.dumps(preflight(args.published_feed, args.published_commit), indent=2))
