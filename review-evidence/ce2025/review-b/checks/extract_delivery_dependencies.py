"""Extract only the five original Python dependencies from the reviewed entry.

No product installation, account data, native binaries, network or signing key.
The exact CE2024 outer/payload hashes are required; this is a review helper.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ENTRY_SHA256 = 'cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c'
PAYLOAD_SHA256 = 'd53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096'
MODULES = ('script.module.certifi', 'script.module.chardet', 'script.module.idna',
           'script.module.requests', 'script.module.urllib3')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.entry.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ENTRY_SHA256:
        raise SystemExit('ENTRY_SHA256_MISMATCH')
    with ZipFile(BytesIO(raw)) as entry:
        payload = entry.read('script.bobbi.start/resources/complete.bobbi-update.zip')
    if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256:
        raise SystemExit('PAYLOAD_SHA256_MISMATCH')
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ZipFile(BytesIO(payload)) as bundle:
        for module in MODULES:
            names = [name for name in bundle.namelist()
                     if name.startswith(module + '/') and name.endswith('.zip')]
            if len(names) != 1:
                raise SystemExit('COMPONENT_NOT_UNIQUE:' + module)
            component = bundle.read(names[0])
            count = 0
            with ZipFile(BytesIO(component)) as archive:
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    if (path.is_absolute() or '..' in path.parts or '\\' in member.filename
                            or not path.parts or path.parts[0] != module):
                        raise SystemExit('UNSAFE_COMPONENT_MEMBER')
                    if member.is_dir() or '/lib/' not in member.filename:
                        continue
                    target = args.out.joinpath(*path.parts)
                    if any(p.is_symlink() for p in (target, *target.parents)):
                        raise SystemExit('UNSAFE_OUTPUT_SYMLINK')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))
                    count += 1
            rows.append(dict(member=names[0], sha256=hashlib.sha256(component).hexdigest(),
                             extracted_files=count))
    record = dict(entry_sha256=ENTRY_SHA256, payload_sha256=PAYLOAD_SHA256,
                  components=rows)
    (args.out / 'PROVENANCE.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
