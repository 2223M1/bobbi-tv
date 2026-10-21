"""Audit the actual user ZIP, its embedded signed payload and bootstrap imports."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from build_ce_entry import BOOTSTRAP, ROOT
from bobbi_platform.offline_updates import SignedBundle, load_trust


def audit(path):
    with tempfile.TemporaryDirectory(prefix='bobbi-entry-audit-') as name:
        temporary = Path(name)
        with zipfile.ZipFile(path) as entry:
            names = entry.namelist()
            assert len(set(names)) == len(names)
            assert all(n.startswith('script.bobbi.start/') and '..' not in n.split('/') for n in names)
            addon = ET.fromstring(entry.read('script.bobbi.start/addon.xml'))
            assert addon.get('id') == 'script.bobbi.start'
            assert addon.find('./extension[@point="xbmc.python.script"]').get('library') == 'default.py'
            requires = {n.get('addon') for n in addon.findall('./requires/import')}
            assert requires == {'xbmc.python', 'script.module.pycryptodome'}
            bundle = temporary / 'bundle.zip'
            bundle.write_bytes(entry.read('script.bobbi.start/resources/complete.bobbi-update.zip'))
            with SignedBundle(bundle, load_trust(), 'coreelec') as signed:
                manifest = signed.check_all()
                platform = next(row for row in manifest['components'] if row['id'] == 'script.module.bobbi.platform')
                with zipfile.ZipFile(BytesIO(signed.read(platform['file'], platform['size']))) as source:
                    for filename in BOOTSTRAP:
                        raw = entry.read('script.bobbi.start/bootstrap/bobbi_platform/' + filename)
                        assert raw == source.read('script.module.bobbi.platform/lib/bobbi_platform/' + filename)
                        target = temporary / 'bootstrap/bobbi_platform' / filename
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw)
            # No installed platform/core or account state in this interpreter.
            script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                'from bobbi_platform.ce_install_ui import KodiHost;'
                'from bobbi_platform.ce_installer import Installer;'
                'from bobbi_platform.runtime import call;'
                'from bobbi_platform.instance_lock import InstanceLock;'
                'assert "bobbi_core" not in sys.modules')
            subprocess.run([sys.executable, '-I', '-B', '-c', script, str(temporary/'bootstrap')],
                           check=True, timeout=15, cwd=temporary)
            # Legacy entries can contain a document; current clean builds do
            # not. Neither presence nor absence is a runtime trust primitive.
            # Signature, same-generation code and isolated import stay required.
    return dict(schema=1, sequence=manifest['sequence'], user_entry=Path(path).name,
        kodi_addon_xml='passed', embedded_complete_signature='passed', same_generation_bootstrap='passed',
        isolated_bootstrap_import='passed', account_state_copied=False,
        scope='actual ZIP and fresh interpreter; not clean-device installation certification')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('entry', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.entry)
    args.report.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
