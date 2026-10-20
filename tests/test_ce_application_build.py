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
    (root / 'LICENSE').write_text('license')
    before = builder.files(root)
    target.write_text('private configuration is separately validated')
    assert builder.files(root) == before == {'LICENSE': builder.hashlib.sha256(b'license').hexdigest()}


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
