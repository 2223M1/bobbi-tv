"""Application config is a separate bounded input, never account/profile data."""
import json
from pathlib import Path
import shutil
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
import build_release as builder


def test_local_application_input_is_not_required_by_git_inventory(tmp_path):
    root = tmp_path / 'script.module.bobbi.core'
    target = root / 'resources/tmdb-project.json'
    target.parent.mkdir(parents=True)
    (root / 'default.py').write_text('pass')
    before = builder.files(root)
    target.write_text('private configuration is separately validated')
    assert builder.files(root) == before == {'default.py': builder.hashlib.sha256(b'pass').hexdigest()}


def test_project_input_validates_then_packages_exact_application_fields(tmp_path):
    root = tmp_path / 'script.module.bobbi.core'
    module = root / 'lib/bobbi_core/project_metadata.py'
    module.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'addons/script.module.bobbi.core/lib/bobbi_core/project_metadata.py', module)
    target = root / 'resources/tmdb-project.json'
    target.parent.mkdir(parents=True)
    from bobbi_core.project_metadata import ATTRIBUTION
    value = dict(schema=1, application='Bobbi TV', api_key='a'*32,
                 use='personal-noncommercial', attribution=ATTRIBUTION)
    roots = {root.name: root}
    with pytest.raises(ValueError, match='project configuration required'):
        builder.project_resource(roots)
    target.write_text(json.dumps(value))
    raw = builder.project_resource(roots)
    target.write_text('changed-after-validation')
    output = tmp_path / 'core.zip'
    builder.archive(root, [], output, {builder.LOCAL_RESOURCE[1]: raw})
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read(root.name + '/' + builder.LOCAL_RESOURCE[1])) == value
    target.write_text(json.dumps(dict(value, session='must-not-package')))
    with pytest.raises(ValueError):
        builder.project_resource(roots)


def test_source_check_never_reads_local_key_and_cannot_be_signed(tmp_path, monkeypatch):
    root = tmp_path / 'source/script.module.bobbi.core'
    root.mkdir(parents=True)
    (root / 'addon.xml').write_text('<addon id="script.module.bobbi.core" version="0.1.12"/>')
    inventory = tmp_path / 'inventory.json'
    inventory.write_text(json.dumps({'components': {root.name: builder.files(root)}}))
    monkeypatch.setattr(builder, 'INVENTORY', inventory)
    monkeypatch.setattr(builder, 'sources', lambda: {root.name: root})
    def forbidden(*args):
        raise AssertionError('A source check must never read the local project key')
    monkeypatch.setattr(builder, 'project_resource', forbidden)
    first, second = tmp_path / 'one', tmp_path / 'two'
    manifest = builder.build(first, source_check=True)
    assert manifest == builder.build(second, source_check=True)
    assert manifest['channel'] == 'source-check' and manifest['installable'] is False
    from check_repository import compare
    assert compare(first, second) > 0
    with zipfile.ZipFile(first / manifest['components'][0]['file']) as archive:
        assert not any(name.endswith('tmdb-project.json') for name in archive.namelist())
    assert json.loads((first / 'application-input.json').read_text())['included'] is False
    from sign_private_bundle import checked_components
    with pytest.raises(ValueError, match='cannot be signed'):
        checked_components(first, manifest, {'components': [root.name]})
    # The default private build still requires its real application input.
    with pytest.raises(AssertionError, match='must never read'):
        builder.build(tmp_path / 'private')
