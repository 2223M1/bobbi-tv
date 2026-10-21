"""Local CE2028 handoff, rejecting mismatched/dirty/unknown execution receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from closure_gate import require_clean_receipt
from package_ce2024_handoff import validate_source_paths

ROOT=Path(__file__).resolve().parents[1]
PRODUCT='0b4dad0454632d5d2eb31792444dd1456ab34a42'
TREE='2a5dc88063d60cc36ccb7c889a2765b237632a82'
BASE='c4e0baca6acefa58f031979bff71e7cd1028efdf'
SEQUENCE=2026102028
GATES=('primary','baseline','preparation','source-a','source-b','repro',
       'client-build','sign','entry','artifact-audit')


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if git('status','--porcelain').strip():raise ValueError('HANDOFF_CHECKOUT_DIRTY')
    if git('diff',PRODUCT,'HEAD','--','addons','third_party','release').strip():
        raise ValueError('PRODUCT_CHANGED_AFTER_FREEZE')
    evidence={}
    for gate in GATES:
        path=args.results/('clean28-'+gate)/'result.json'
        value=json.loads(path.read_text())
        require_clean_receipt(value,PRODUCT,TREE)
        evidence[gate]=dict(receipt='results/clean28-'+gate+'/result.json',exit_code=0,
                            commit=PRODUCT,tree=TREE)
    mapping=json.loads((args.results/'product28-source-package.json').read_text())
    if (mapping['source_commit'],mapping['source_tree'],mapping['sequence'])!=(PRODUCT,TREE,SEQUENCE):
        raise ValueError('PRODUCT_MAPPING_CHANGED')
    bundle=args.results/'delivery/bobbi-private-2026102028-coreelec.bobbi-update.zip'
    entry=args.results/'delivery/script.bobbi.start-0.2.19-ce2028.zip'
    if sha(bundle)!=mapping['bundle_sha256'] or sha(entry)!=mapping['entry_sha256']:
        raise ValueError('DELIVERY_ARTIFACT_CHANGED')
    counts={}
    for name in ('primary','baseline','preparation'):
        root=ET.parse(args.results/('clean28-'+name+'.xml')).getroot()
        suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
        total={key:sum(int(r.get(key,'0')) for r in suites) for key in ('tests','failures','errors','skipped')}
        if not suites or total['failures'] or total['errors']:raise ValueError('SUITE_NOT_PASSED')
        total['passed']=total['tests']-total['skipped']
        counts[name]=total
    head=git('rev-parse','HEAD').decode().strip()
    names=git('ls-tree','-r','--name-only',head).decode().splitlines()
    validate_source_paths(names)
    args.output.mkdir(parents=True,exist_ok=False)
    for artifact in (bundle,entry):shutil.copy2(artifact,args.output/artifact.name)
    shutil.copy2(ROOT/'docs/CE2028-DELIVERY.md',args.output/'交付报告.md')
    shutil.copy2(ROOT/'docs/CLAUDE-CE-UI-HANDOFF.md',args.output/'Claude联调说明.md')
    results=args.output/'results'
    results.mkdir()
    # Preserve failures alongside passes; never rewrite or promote them.
    directories=['before','after-1','keyboard','library','ui-preview','ui26-working-tests','full-primary-1']
    directories += ['clean'+str(version)+'-'+gate for version in (25,26,27,28) for gate in GATES]
    for name in directories:
        if (args.results/name).is_dir():shutil.copytree(args.results/name,results/name)
    for path in args.results.iterdir():
        if path.is_file() and path.suffix in ('.json','.xml'):
            shutil.copy2(path,results/path.name)
    subprocess.run(['git','archive','--format=zip','--output='+str(args.output/'BobbiTV-CE2028-Source-Evidence.zip'),head],cwd=ROOT,check=True)
    (args.output/'CE2024-to-CE2028.diff').write_bytes(git('diff','--binary',BASE,PRODUCT,'--','addons','tools','tests','release'))
    manifest=dict(product_commit=PRODUCT,product_tree=TREE,handoff_commit=head,sequence=SEQUENCE,
        gates=evidence,counts=counts,remote_ci='not run; no push authorized this round',
        acceptance='See report: clean local gates do not close unrelated historical viewing failures.',
        files={p.relative_to(args.output).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))
               for p in sorted(args.output.rglob('*')) if p.is_file()})
    (args.output/'DELIVERY.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(args.output),product_commit=PRODUCT,counts=counts),ensure_ascii=False))


if __name__=='__main__':main()
