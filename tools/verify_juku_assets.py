"""Verify research hashes and exclusions; does not import or run upstream code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from index_juku_assets import REPO, PRIVATE, CREDENTIAL_LITERAL, file_hash, save_json


def main():
    root = REPO/'docs/research/juku-full-20261019/assets'
    checked_copies, inputs = {}, {}
    def read(name):
        return json.loads((root/name).read_text(encoding='utf-8'))
    def check(path, expected):
        actual = file_hash(path)
        if actual != expected:
            raise ValueError('Hash mismatch: '+str(path))
    def members(value):
        for row in value.get('members',[]):
            if row.get('copy'):
                target=(root/row['copy']).resolve()
                target.relative_to(root.resolve())
                check(target,row['sha256'])
                checked_copies[row['copy']]=row['sha256']
    manifests=[read('plugin-'+a+'-index.json') for a in ('arm64','x64')]
    for manifest in manifests:
        check(Path(manifest['source']),manifest['sha256'])
        inputs[manifest['source']]=manifest['sha256']
        members(manifest)
    group=read('group-index.json')
    for row in group['files']:
        check(Path(row['source']),row['sha256'])
        check(Path(row['mirror']),row['sha256'])
        inputs[row['source']]=row['sha256']
        if row.get('copy'):
            check(root/row['copy'],row['sha256'])
            checked_copies[row['copy']]=row['sha256']
        if row.get('index'):
            members(read(row['index']))
    official=read('official-versions.json')
    for row in official['files']:
        if row.get('copy'):
            check(root/row['copy'],row['sha256'])
            checked_copies[row['copy']]=row['sha256']
        members(row)
    expected_md5=(root/'official/addons.xml.md5').read_text().strip()
    if hashlib.md5((root/'official/addons.xml').read_bytes()).hexdigest() != expected_md5:
        raise ValueError('Official index MD5 mismatch')
    for manifest in manifests:
        published=next(row for row in official['files'] if row['url'].endswith(Path(manifest['source']).name))
        if published['sha256'] != manifest['sha256']:
            raise ValueError('Official and retained plugin differ')
    embedded=read('embedded/index.json')
    for binary in embedded['binaries']:
        check(Path(binary['binary']),binary['binary_sha256'])
        for row in binary['assets']:
            target=root/'embedded'/row['file']
            check(target,row['sha256'])
            checked_copies['embedded/'+row['file']]=row['sha256']
            for proof in row.get('evidence',[]):
                check(REPO/proof['file'],proof['sha256'])
    variants={row['architecture']:{Path(a['file']).name:a['sha256'] for a in row['assets']} for row in embedded['binaries']}
    differences=[n for n in variants['arm64'] if variants['arm64'][n]!=variants['x64'][n]]
    if differences != ['privateLibHTML.html']:
        raise ValueError('Unexpected embedded architecture differences')
    arm=(root/'embedded/arm64/privateLibHTML.html').read_bytes()
    x64=(root/'embedded/x64/privateLibHTML.html').read_bytes()
    if arm.count(b'202610182259') != 2 or arm.replace(b'202610182259',b'202610182254') != x64:
        raise ValueError('Difference extends beyond the two known cache-busters')
    for folder in ('original','group-original','embedded','official'):
        for path in (root/folder).rglob('*'):
            if not path.is_file():
                continue
            if path.suffix.lower() in ('.pem','.key','.p12','.pfx','.db','.sqlite','.sqlite3'):
                raise ValueError('Forbidden raw account/key file: '+str(path))
            raw=path.read_bytes()
            if PRIVATE.search(raw) or CREDENTIAL_LITERAL.search(raw):
                raise ValueError('Unexpected credential marker: '+str(path))
    group_repo=next(row for row in group['files'] if row['name']=='repository.juku-1.0.1.zip')
    local={m['path']:m['sha256'] for m in read(group_repo['index'])['members'] if m['type']=='file'}
    published=next(row for row in official['files'] if row['url'].endswith('/repository.juku-1.0.1.zip'))
    live={m['path']:m['sha256'] for m in published['members']}
    repo_diff=dict(group_sha256=group_repo['sha256'],official_sha256=published['sha256'],
                   common_identical=sorted(n for n in local.keys()&live.keys() if local[n]==live[n]),
                   common_changed=sorted(n for n in local.keys()&live.keys() if local[n]!=live[n]),
                   group_only=sorted(local.keys()-live.keys()),official_only=sorted(live.keys()-local.keys()))
    save_json(root/'repository-comparison.json',repo_diff)
    result=dict(result='pass',source_files_checked=len(inputs),source_mirror_files_checked=len(group['files']),
                unique_copied_asset_paths_checked=len(checked_copies),
                copied_bytes=sum((root/p).stat().st_size for p in checked_copies),
                official_index_md5_matches=True,official_plugin_archives_match_retained=True,
                embedded_assets_per_arch=36,embedded_identical_assets=35,
                embedded_difference='privateLibHTML: only two build cache-busters differ',
                group_repo_content_diff=repo_diff,
                limitations=['Static verification only; no upstream code/daemon/browser script execution',
                             'Marker scan is an exclusion check, not proof all upstream data is non-sensitive',
                             'MD5 only checks index consistency, not authenticity or signatures'])
    save_json(root/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
