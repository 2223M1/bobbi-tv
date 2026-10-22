"""Mutate disposable copies of an actual complete entry; never execute them."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import tempfile
import zipfile

from audit_ce_entry import audit


def probe(entry):
    control=audit(entry)
    raw=Path(entry).read_bytes()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        original={name:archive.read(name) for name in archive.namelist()}
    results=[]
    for case in ('default','addon_xml','extra','missing','bootstrap'):
        members=dict(original)
        if case=='default':members['script.bobbi.start/default.py']=b'raise RuntimeError("never execute")\n'
        elif case=='addon_xml':members['script.bobbi.start/addon.xml']=members['script.bobbi.start/addon.xml'].replace(b'version="0.',b'version="9.',1)
        elif case=='extra':members['script.bobbi.start/extra.py']=b'EXTRA=True\n'
        elif case=='missing':del members['script.bobbi.start/default.py']
        else:members['script.bobbi.start/bootstrap/bobbi_platform/ce_installer.py']=b'EXTRA=True\n'
        with tempfile.TemporaryDirectory(prefix='bobbi-entry-mutation-') as name:
            target=Path(name)/'never-install.zip'
            with zipfile.ZipFile(target,'w') as archive:
                for key,value in members.items():archive.writestr(key,value)
            try:audit(target)
            except (AssertionError,KeyError,ValueError):rejected=True
            else:rejected=False
            results.append(dict(case=case,rejected=rejected,executed=False))
    assert all(row['rejected'] for row in results),results
    assert Path(entry).read_bytes()==raw
    return dict(control=control,mutations=results,original_unchanged=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('entry',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();value=probe(args.entry)
    args.output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value))
