"""Fixed ownership and Kodi (not SemVer) dependency checks; no installation."""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from bobbi_platform.updates import UpdateError
from bobbi_platform.upstream_addons import (FULL_COMPONENTS, OWNED_COMPONENTS,
    UPSTREAM_COMPONENTS, check_dependencies, compare_versions, kodi_version,
    managed_components, project_state)


def addon_xml(name, version='3.0.0', requires=(), xml_id=None):
    node = ET.Element('addon', id=xml_id or name, version=version)
    if requires:
        imports = ET.SubElement(node, 'requires')
        for attrs in requires:
            ET.SubElement(imports, 'import', attrs)
    return ET.tostring(node, encoding='utf-8')


def install(root, name, version='3.0.0', requires=(), xml_id=None):
    target = Path(root) / name
    target.mkdir(parents=True, exist_ok=True)
    (target / 'addon.xml').write_bytes(addon_xml(name, version, requires, xml_id))
    return target


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in Path(root).rglob('*') if p.is_file()}


@pytest.mark.parametrize('left,right,order', [
    ('1.00', '1.0', 0), ('1.0', '1.0.0', -1),
    ('2.9.10', '2.10.1', -1), ('1.0~beta1', '1.0', -1),
    ('1.0~beta2', '1.0~beta10', -1), ('1.0~~', '1.0~', -1),
    ('1.0', '1.0+matrix.1', -1), ('1.0+matrix.9', '1.0+matrix.10', -1),
    ('1.0+MATRIX.01', '1.0+matrix.1', 0), ('2:0.1', '1:9.9', 1),
    ('0:1.0', '1.0', 0), ('1.0-1', '1.0-2', -1),
    ('1.0-1~rc', '1.0-1', -1), ('1.0-a', '1.0-1', 1),
    ('1.0-a', '1.0-~a', 1), ('1.0', '1.0-0', -1),
    ('1.', '1.+0', 0), ('1.', '1.+1', -1),
    ('1.0+', '1.0+0', 0), ('1.0_1', '1.0@1', 1),
    ('2147483647:1.0', '2147483646:1.0', 1),
])
def test_kodi_addonversion_order(left, right, order):
    assert compare_versions(left, right) == order
    assert compare_versions(right, left) == -order


@pytest.mark.parametrize('value', [None, True, '', ' ', '1/2', 'v1:2', '1:-2',
    '1.0-', '1.0-a-b', '1.0\n', '1.0:2.0', '2147483648.0',
    '2147483648:1.0', '1.0+2147483648', 'a' * 129, '00000000000.0',
    '\u0661:1.0.0', '\uff11:1.0.0'])
def test_unsupported_or_overflowing_versions_fail_closed(value):
    with pytest.raises(UpdateError, match='Unsupported'):
        kodi_version(value)


def test_only_exact_reviewed_inventory_changes_ownership():
    assert len(FULL_COMPONENTS) == 22
    assert len(OWNED_COMPONENTS) == 13
    assert len(UPSTREAM_COMPONENTS) == 9
    assert not OWNED_COMPONENTS & UPSTREAM_COMPONENTS
    assert managed_components(FULL_COMPONENTS) == OWNED_COMPONENTS
    for expected in (OWNED_COMPONENTS, FULL_COMPONENTS | {'plugin.video.other'},
                     FULL_COMPONENTS - {'script.module.certifi'},
                     {'plugin.video.bobbi', 'script.module.requests'}):
        assert managed_components(expected) == expected
    state = dict(sequence=42, versions=dict.fromkeys(FULL_COMPONENTS, '1.0.0'))
    assert project_state(state) == dict(sequence=42, versions=dict.fromkeys(OWNED_COMPONENTS, '1.0.0'))
    assert len(state['versions']) == 22


@pytest.fixture
def dependencies(tmp_path):
    addons, stage = tmp_path / 'addons', tmp_path / 'stage'
    stage.mkdir()
    for name in UPSTREAM_COMPONENTS:
        install(addons, name, '3.0.0+matrix.2')
    return addons, stage


def test_direct_transitive_and_optional_dependencies_are_read_only(dependencies):
    addons, stage = dependencies
    install(stage, 'plugin.video.bobbi', requires=(
        dict(addon='script.module.requests', version='2.0.0'),
        dict(addon='script.module.routing', version='3.0.0'),
        dict(addon='script.module.certifi', version='999.0.0', optional='true'),
        dict(addon='xbmc.python', version='99.0.0'),
        dict(addon='third.party.virtual', version='bad-unexamined'),
    ))
    install(stage, 'skin.bobbi.cinema', requires=(
        dict(addon='script.skinvariables', version='2.0.0'),))
    install(addons, 'script.module.requests', requires=(
        dict(addon='script.module.urllib3', version='3.0.0+matrix.1'),))
    install(addons, 'script.skinvariables', requires=(
        dict(addon='script.module.jurialmunkey', version='2.0.0'),))
    install(addons, 'script.module.jurialmunkey', requires=(
        dict(addon='script.module.infotagger', version='2.1.0'),
        dict(addon='script.module.requests', version='2.1.0'),))
    before = snapshot(addons), snapshot(stage)
    minimum = check_dependencies(addons, stage)
    assert set(minimum) == UPSTREAM_COMPONENTS
    assert minimum['script.module.requests'] == '2.1.0'
    assert minimum['script.module.urllib3'] == '3.0.0+matrix.1'
    assert minimum['script.module.infotagger'] == '2.1.0'
    assert minimum['script.module.certifi'] == '0.0.0'
    assert (snapshot(addons), snapshot(stage)) == before


@pytest.mark.parametrize('installed,required', [
    ('1.26.16+matrix.1', '1.26.16+matrix.2'),
    ('3.0.0~beta1', '3.0.0'), ('3.0.0-1', '3.0.0-2'),
])
def test_actual_kodi_suffix_order_controls_minimum(dependencies, installed, required):
    addons, stage = dependencies
    install(addons, 'script.module.urllib3', installed)
    install(stage, 'plugin.video.bobbi', requires=(
        dict(addon='script.module.urllib3', version=required),))
    before = snapshot(addons)
    with pytest.raises(UpdateError, match='script.module.urllib3.*install/update.*Kodi'):
        check_dependencies(addons, stage)
    assert snapshot(addons) == before


@pytest.mark.parametrize('fault', ['missing', 'wrong_id', 'invalid_xml', 'entity', 'huge', 'version'])
def test_missing_or_invalid_upstream_not_seeded_from_candidate(dependencies, fault):
    addons, stage = dependencies
    name = 'script.module.requests'
    path = addons / name / 'addon.xml'
    install(stage, name)
    if fault == 'missing':
        path.unlink()
    elif fault == 'wrong_id':
        install(addons, name, xml_id='script.module.other')
    else:
        path.write_bytes({'invalid_xml': b'not xml', 'entity': b'<!DOCTYPE addon><addon/>',
                          'huge': b'x' * (1024 * 1024 + 1),
                          'version': addon_xml(name, 'invalid/version')}[fault])
    before = snapshot(addons), snapshot(stage)
    with pytest.raises(UpdateError, match=name):
        check_dependencies(addons, stage)
    assert (snapshot(addons), snapshot(stage)) == before


def test_invalid_required_version_is_actionable(dependencies):
    addons, stage = dependencies
    install(stage, 'plugin.video.bobbi', requires=(
        dict(addon='script.module.requests', version='invalid/version'),))
    with pytest.raises(UpdateError, match='script.module.requests.*plugin.video.bobbi.*Kodi'):
        check_dependencies(addons, stage)


def test_unreviewed_partial_inventory_is_rejected(dependencies):
    with pytest.raises(UpdateError, match='ownership'):
        check_dependencies(*dependencies, managed={'plugin.video.bobbi'})


def test_linked_upstream_path_is_rejected(dependencies, tmp_path):
    addons, stage = dependencies
    path = addons / 'script.module.requests' / 'addon.xml'
    outside = tmp_path / 'other.xml'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip('Host does not permit symlink fixture')
    with pytest.raises(UpdateError, match='Symlink'):
        check_dependencies(addons, stage)
