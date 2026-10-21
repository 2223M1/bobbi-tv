#!/usr/bin/env python3
"""Compare current cleanup and entry-audit contracts without any release key.

Runs actual clean_archive/check_nested and audit_ce_entry.audit. Fixture ZIPs
contain the actual candidate bootstrap modules. Only SignedBundle/load_trust
are replaced at the signature/payload fixture boundary; the actual isolated
bootstrap import subprocess still runs. This is not the downloaded 96 MB asset,
signature verification, a device test, or evidence of runtime startup failure.
"""
import argparse
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import zipfile


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(payload):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as target:
        for name, raw in sorted(payload.items()):
            target.writestr(name, raw)
    return stream.getvalue()


def checkout_commit(repo):
    """Return this checkout's HEAD, never an enclosing workspace repository."""
    try:
        top = subprocess.run(
            ['git', '-C', str(repo), 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=10)
        if top.returncode or Path(top.stdout.strip()).resolve() != repo:
            return None
        head = subprocess.run(
            ['git', '-C', str(repo), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=10)
        return head.stdout.strip() if head.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo/'tools'))
    sys.path.insert(0, str(repo/'addons/script.module.bobbi.platform/lib'))
    packager = load(repo/'tools/package_ce2021_github.py', 'ce2021_review_packager')
    audit = load(repo/'tools/audit_ce_entry.py', 'ce2021_review_audit')
    platform = repo/'addons/script.module.bobbi.platform/lib/bobbi_platform'
    bootstrap = {name:(platform/name).read_bytes() for name in audit.BOOTSTRAP}
    platform_blob = archive({'script.module.bobbi.platform/lib/bobbi_platform/'+name:raw
                             for name,raw in bootstrap.items()})
    embedded = archive({'review-fixture.txt':b'Payload fixture; signature boundary is explicit'})
    addon = (repo/'addons/script.bobbi.start/addon.xml').read_bytes()
    members = {'script.bobbi.start/addon.xml':addon,
               'script.bobbi.start/default.py':(repo/'addons/script.bobbi.start/default.py').read_bytes(),
               'script.bobbi.start/bootstrap/LICENSE':b'Review fixture notice\n',
               packager.EMBEDDED:embedded}
    for name,raw in bootstrap.items():
        members['script.bobbi.start/bootstrap/bobbi_platform/'+name] = raw
    original = archive(members)
    removed = []
    cleaned = packager.clean_archive(original, 'fixture-entry', removed,
                                    {packager.EMBEDDED:embedded})
    packager.check_nested(cleaned, 'fixture-clean-entry')

    class SignedFixture:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def check_all(self):
            return {'sequence':2026102022, 'components':[
                {'id':'script.module.bobbi.platform','file':'platform.zip','size':len(platform_blob)}]}
        def read(self, name, size):
            assert name=='platform.zip' and size==len(platform_blob)
            return platform_blob

    audit.SignedBundle, audit.load_trust = SignedFixture, lambda: {}
    results = []
    with tempfile.TemporaryDirectory(prefix='ce2021-entry-contract-') as tmp:
        for label,blob in [('CONTROL-ORIGINAL-ENTRY',original),('CLEAN-ENTRY-CURRENT-AUDIT',cleaned)]:
            path = Path(tmp)/(label+'.zip')
            path.write_bytes(blob)
            try:
                receipt = audit.audit(path)
                # The production audit labels its signature check "passed".
                # That boundary is a fixture here, so never expose that label
                # as independent signature evidence in this review result.
                receipt.pop('embedded_complete_signature', None)
                receipt['signature_boundary'] = 'fixture; cryptographic verification not executed'
                receipt['sequence_origin'] = 'fixture; no release manifest downloaded'
                receipt['scope'] = 'fixture ZIP; actual isolated bootstrap import; no release asset or device test'
                results.append({'id':label,'passed':True,'audit':receipt})
            except KeyError as error:
                results.append({'id':label,'passed':False,'exception':'KeyError','detail':str(error)})
            except Exception as error:
                results.append({'id':label,'passed':False,'harness_error':type(error).__name__,
                                'detail':str(error),'traceback':traceback.format_exc()})
    result = {'scope':'Actual cleanup and audit with real isolated bootstrap import; SignedBundle fixture replaces only signature/payload boundary; no release asset or device test',
              'review_reference_commit':'b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2',
              'actual_checkout_commit':checkout_commit(repo),
              'source_identity_authority':'sources[].sha256 records the actual files executed; review_reference_commit is only the fixed review baseline',
              'removed':removed,'non_document_bootstrap_unchanged':packager.inventory(original)==packager.inventory(cleaned),
              'clean_check_nested_passed':True,'tests':results,'count':len(results),
              'passed':sum(row['passed'] for row in results),
              'failed':sum(not row['passed'] and not row.get('harness_error') for row in results),
              'errors':sum(bool(row.get('harness_error')) for row in results),
              'sources':[{'path':p,'sha256':hashlib.sha256((repo/p).read_bytes()).hexdigest()} for p in [
                  'tools/package_ce2021_github.py','tools/audit_ce_entry.py','tools/build_ce_entry.py',
                  'addons/script.bobbi.start/default.py']]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['count','passed','failed','errors','removed','clean_check_nested_passed','non_document_bootstrap_unchanged']},ensure_ascii=False))
    return 2 if result['errors'] else 1 if result['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
