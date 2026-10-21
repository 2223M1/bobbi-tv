"""Retain original probes; adapt only new signature pins and snapshot IO seam."""
import argparse
import difflib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def changed(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Frozen fixture seam changed')
    return source.replace(old,new)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    original=ROOT/'review-evidence/ce2023/review-a/checks'
    receipts=[]
    for name in ('native_monitor','input_generation'):
        before=(original/('reproduce_'+name+'.py')).read_text(encoding='utf-8')
        if name=='native_monitor':
            after=(ROOT/'review-evidence/ce2014-monitor-adapter.py').read_text(encoding='utf-8')
            reason='Accept transport timeout keyword; inject EOF at the single authoritative snapshot; provide real tick seam. Assertions remain unchanged.'
        else:
            after=changed(before,"    outer = zipped({module.BUNDLE: bundle, module.ENTRY: entry,\n                    module.REPORT: b'Fixture input report; replaced by repository report.\\n',\n                    'README.md': b'Fixture input.\\n'})",
                "    members = {module.BUNDLE: bundle, module.ENTRY: entry,\n                    module.REPORT: b'Fixture input report; replaced by repository report.\\n',\n                    'README.md': b'Fixture input.\\n'}\n    members['MANIFEST.json'] = json.dumps(dict(schema=1,files=[dict(path=n,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in members.items()])).encode()\n    outer = zipped(members)")
            after=changed(after,"                    sys.argv = [str(module_path), '--key', str(pem), '--input', str(input_path), '--output', str(out)]",
                "                    with zipfile.ZipFile(BytesIO(bundle)) as z:\n                        expected_components = json.loads(z.read('release.json'))['components']\n                    with zipfile.ZipFile(BytesIO(outer)) as z:\n                        entry_raw = z.read(module.ENTRY)\n                    identity = case_root/'identity.json'\n                    identity.write_text(json.dumps(dict(sequence=2026102021, components=expected_components, outer_sha256=hashlib.sha256(outer).hexdigest(),payload_sha256=hashlib.sha256(bundle).hexdigest(),entry_sha256=hashlib.sha256(entry_raw).hexdigest())))\n                    registry = case_root/'registry.json'\n                    registry.write_text(json.dumps(dict(allocated=[2026102022])))\n                    sys.argv = [str(module_path), '--key', str(pem), '--input', str(input_path), '--output', str(out), '--identity',str(identity),'--registry',str(registry),'--sequence','2026102023']")
            after=after.replace("out / 'bobbi-private-2026102022-coreelec.bobbi-update.zip'", "out / 'bobbi-private-2026102023-coreelec.bobbi-update.zip'")
            after=after.replace("out / 'ce2021-clean-delivery-20261021.zip'", "out / 'ce2021-clean-2026102023.zip'")
            reason='Temporary fixture must supply exact caller pins, complete outer membership and explicit unallocated output sequence. Input acceptance expectations unchanged.'
        path=args.output/(name+'.py');path.write_text(after,encoding='utf-8')
        (args.output/(name+'.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='frozen-original',tofile='adapted-fixture')),encoding='utf-8')
        result=args.output/(name+'.json')
        run=subprocess.run([sys.executable,'-B',str(path),'--repo',str(ROOT),'--output',str(result)],capture_output=True)
        (args.output/(name+'.stdout')).write_bytes(run.stdout);(args.output/(name+'.stderr')).write_bytes(run.stderr)
        receipts.append(dict(name=name,exit_code=run.returncode,adaptation_reason=reason))
    source=ROOT/'review-evidence/ce2023/review-b/probes/probe_entry_builder.py'
    before=source.read_text(encoding='utf-8')
    after=changed(before,"                'tools/build_release.py',", "                'tools/build_release.py',\n                'tools/delivery_policy.py',")
    path=args.output/'b-entry.py';path.write_text(after,encoding='utf-8')
    (args.output/'b-entry.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original',tofile='complete-builder-dependencies')),encoding='utf-8')
    run=subprocess.run([sys.executable,'-B',str(path),'--repo',str(ROOT)],capture_output=True)
    (args.output/'b-entry.json').write_bytes(run.stdout);(args.output/'b-entry.stderr').write_bytes(run.stderr)
    receipts.append(dict(name='b-entry',exit_code=run.returncode,adaptation_reason='Copy the new policy dependency verbatim into the isolated builder. Assertions and real signatures unchanged.'))
    (args.output/'RESULT.json').write_text(json.dumps(receipts,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipts))
    return int(any(r['exit_code'] for r in receipts))


if __name__=='__main__':raise SystemExit(main())
