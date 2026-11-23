"""Verify actual signed delivery against checkout; retain real tamper controls."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from audit_ce_entry import audit
from build_release import ROOT, sources, files, LOCAL_RESOURCE, project_resource
from bobbi_platform.offline_updates import SignedBundle, load_trust
from bobbi_platform.updates import UpdateError


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    roots, rows = sources(), []
    with SignedBundle(args.bundle, load_trust(), 'coreelec') as bundle:
        manifest = bundle.check_all()
        for component in manifest['components']:
            identifier = component['id']
            expected = files(roots[identifier])
            if identifier == LOCAL_RESOURCE[0]:
                expected[LOCAL_RESOURCE[1]] = digest(project_resource(roots))
            with zipfile.ZipFile(BytesIO(bundle.read(component['file'], component['size']))) as archive:
                actual = {name.split('/', 1)[1]: digest(archive.read(name)) for name in archive.namelist()}
            if expected != actual:
                raise ValueError('SOURCE_COMPONENT_MISMATCH:' + identifier)
            rows.extend(dict(component=identifier, path=name, sha256=sha,
                build_input=(identifier, name) == LOCAL_RESOURCE) for name, sha in sorted(actual.items()))
    entry_audit = audit(args.entry)
    with zipfile.ZipFile(args.entry) as entry:
        assert entry.read('script.bobbi.start/resources/complete.bobbi-update.zip') == args.bundle.read_bytes()
    controls = []
    with tempfile.TemporaryDirectory(prefix='bobbi-delivery-negative-') as temporary:
        for mode in ('signature', 'component'):
            target = Path(temporary) / (mode + '.zip')
            with zipfile.ZipFile(args.bundle) as archive, zipfile.ZipFile(target, 'w') as out:
                for item in archive.infolist():
                    data = archive.read(item)
                    if (mode == 'signature' and item.filename == 'release.sig'
                            or mode == 'component' and item.filename == manifest['components'][0]['file']):
                        data = bytes([data[0] ^ 1]) + data[1:]
                    out.writestr(item, data)
            try:
                with SignedBundle(target, load_trust(), 'coreelec') as bundle:
                    bundle.check_all()
            except UpdateError as error:
                controls.append(dict(control=mode, rejected=True, reason=str(error)))
            else:
                raise AssertionError('TAMPER_ACCEPTED:' + mode)
    value = dict(sequence=manifest['sequence'], source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), source_tree=subprocess.check_output(
        ['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),
        bundle_sha256=digest(args.bundle.read_bytes()), entry_sha256=digest(args.entry.read_bytes()),
        entry_audit=entry_audit, controls=controls, files=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(sequence=manifest['sequence'], files=len(rows), controls=controls, output=str(args.output))))


if __name__ == '__main__':
    main()
