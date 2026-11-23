import hashlib
import json
from pathlib import Path

import pytest

from test_ce_native_completion_profile import private_fixture
from test_ce_native_reapply import tool


def test_r18_lifecycle_uses_one_reviewed_ce_binary():
    from bobbi_core.runtime_paths import known_ce_native
    profile = tool.PROFILES['r18lifecycle2154']
    root = Path(__file__).resolve().parents[1]/'native/patches'
    series = json.loads((root/'ce-am6b-lifecycle-series.json').read_text())
    patch, = series['patches']
    assert series['predecessor_sha256'] == profile['predecessor']['binary'] == tool.PROFILES['pcmtempo2148']['candidate']
    assert hashlib.sha256((root/patch['file']).read_bytes()).hexdigest() == patch['sha256'] == profile['canonical_patch_sha256']
    assert patch['file'] not in {p['file'] for p in json.loads((root/'series.json').read_text())['patches']}
    assert known_ce_native(profile['candidate']) and not known_ce_native('0'+profile['candidate'][1:])


@pytest.mark.parametrize('change',[None,'missing_skin','newer_skin','wrong_profile',
                                   'reviewed_reapply','glass_reapply','unreviewed_reapply','wrong_new_plugin','initial_on_newer'])
def test_maintenance_requires_the_matching_product_and_skin(tmp_path, monkeypatch, change):
    profile = tool.PROFILES['r18lifecycle2154']
    h, addons, _ = private_fixture(tmp_path, monkeypatch)
    versions = dict(profile['minimum_versions'])
    required = dict(versions)
    sequence = profile['sequence']
    if change in ('reviewed_reapply','glass_reapply','unreviewed_reapply','wrong_new_plugin','initial_on_newer'):
        sequence = {'unreviewed_reapply': 2026102157, 'glass_reapply': 2026102156}.get(change,2026102155)
        versions.update(profile['reviewed_reapply_versions'][2026102156 if change=='glass_reapply' else 2026102155])
        if change!='initial_on_newer':
            h.ns['MODE']='reapply'
            h.receipt.write_text(json.dumps(dict(h.pins,state='rolled_back',recovered=True)))
            (h.base/'previous.conf').write_bytes(h.old_conf)
        if change=='wrong_new_plugin':
            versions['plugin.video.bobbi']='0.1.82'
    if change == 'missing_skin':
        required.pop('skin.bobbi.cinema')
    if change == 'newer_skin':
        versions['skin.bobbi.cinema'] = '0.1.25'
    h.ns.update(PROFILE_TAG='other' if change=='wrong_profile' else profile['tag'],
                MINIMUM_VERSIONS=required, REQUIRED_SEQUENCE=profile['sequence'],
                REVIEWED_REAPPLY_VERSIONS=profile['reviewed_reapply_versions'])
    h.generation.write_text(json.dumps(dict(sequence=sequence,versions=versions)))
    for ident, version in versions.items():
        path = addons/ident/'addon.xml'
        path.parent.mkdir(exist_ok=True)
        path.write_text(f'<addon id="{ident}" version="{version}"/>')
    if change not in (None,'reviewed_reapply','glass_reapply'):
        with pytest.raises(AssertionError, match='PRIVATE_COMPONENTS_INVALID|LIFECYCLE_COMPONENT_CHANGED|INITIAL_GENERATION_CHANGED'):
            h.run()
        assert h.conf.read_bytes()==h.old_conf
    else:
        h.run()
        assert json.loads(h.receipt.read_text())['state']=='applied'
