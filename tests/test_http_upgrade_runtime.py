"""Supported Kodi floor is a consumer contract, not old-library equivalence."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from bobbi_platform import ce_install_ui
from bobbi_platform.upstream_addons import DECLARED_HTTP_RUNTIME_FLOORS, UPSTREAM_COMPONENTS, inspect_http_runtime
from bobbi_platform.updates import UpdateError

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'release/http-runtime-policy.json').read_text())


def test_actual_loaded_runtime_matches_the_matrix_process():
    actual = inspect_http_runtime()
    expected = json.loads(os.environ.get('BOBBI_HTTP_RUNTIME_EXPECTED', '{}'))
    for name in ('requests', 'urllib3'):
        assert Path(actual[name]['file']).is_file()
        if expected:
            assert actual[name]['version'] == expected['script.module.' + name]
    assert actual['python_version_info'][:2] >= [3, 11]


def test_declared_floors_and_bundled_versions_match_explicit_policy():
    assert DECLARED_HTTP_RUNTIME_FLOORS == POLICY['minimums']
    for addon in ('plugin.video.bobbi', 'script.module.bobbi.core', 'script.module.bobbi.platform'):
        meta = ET.parse(ROOT / 'addons' / addon / 'addon.xml').getroot()
        imports = {n.get('addon'): n.get('version') for n in meta.findall('./requires/import')}
        assert {k: imports[k] for k in POLICY['minimums']} == POLICY['minimums']
    for name, version in POLICY['bundled'].items():
        assert ET.parse(ROOT / 'third_party/addons' / name / 'addon.xml').getroot().get('version') == version


@pytest.mark.parametrize('outdated', [False, True])
def test_real_installer_dependency_stage_preserves_official_floor(tmp_path, outdated):
    staged = tmp_path / 'staged'
    versions = {'script.module.pycryptodome': '3.4.3'}
    for base in ('addons', 'third_party/addons'):
        for path in (ROOT / base).glob('*/addon.xml'):
            target = staged / path.parent.name / 'addon.xml'
            target.parent.mkdir(parents=True)
            target.write_bytes(path.read_bytes())
            versions[path.parent.name] = ET.parse(path).getroot().get('version')
    versions.update(POLICY['minimums'])
    if outdated:
        versions['script.module.requests'] = '2.30.0'
    installed = tmp_path / 'installed'
    installed.mkdir()
    for name in UPSTREAM_COMPONENTS:
        (installed / name).mkdir()
        (installed / name / 'addon.xml').write_text(f'<addon id="{name}" version="{versions[name]}"/>')
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in installed.rglob('*') if p.is_file()}
    commands = []
    host = ce_install_ui.KodiHost.__new__(ce_install_ui.KodiHost)
    host.details = lambda name: {'version': versions[name], 'enabled': True}
    host.xbmc = SimpleNamespace(executebuiltin=lambda *args: commands.append(args))
    host.monitor = SimpleNamespace(waitForAbort=lambda _: True)
    if outdated:
        with pytest.raises(UpdateError, match='DEPENDENCY_UNAVAILABLE:script.module.requests'):
            host.dependencies(staged)
        assert commands == [('InstallAddon(script.module.requests)', False)]
    else:
        host.dependencies(staged)
        assert commands == []
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in installed.rglob('*') if p.is_file()}
    assert after == before
