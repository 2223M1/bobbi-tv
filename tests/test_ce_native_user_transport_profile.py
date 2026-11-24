"""The 2128 bridge consumes a separately pinned offline user-transport proof."""
from copy import deepcopy
import json

import pytest

from test_ce_native_reapply import tool
from test_ce_native_completion_profile import candidate


def test_user_transport_profile_preserves_scoped_predecessor_and_minimums():
    current=tool.PROFILES['usertransport2128'];old=tool.PROFILES['scoped2122']
    assert current['sequence']==2026102128 and current['base']!=old['base']
    assert current['predecessor']['binary']==old['candidate']
    assert current['predecessor']['binary_path']==old['base']+'/kodi.bin'
    assert current['minimum_versions']=={'plugin.video.bobbi':'0.1.69','script.module.bobbi.core':'0.1.69','script.module.bobbi.platform':'0.1.78'}
    assert old['build_kind']=='scoped_controls' and old['sequence']==2026102122
    assert old['canonical_patch_sha256']=='e2dc7818da99ee2db8d7dcbee7b0f1f21ac8bde3ecacf0e826c44df6febbed1a'


def test_offline_profile_requires_all_old_cases_and_full_transport_controls():
    profile=json.loads((tool.ROOT/'native/tests/user_transport_profile.json').read_text())
    assert profile['deployment_authority'] is False
    assert len(profile['required_actor_cases'])==63
    assert len([name for name in profile['required_actor_cases'] if not name.startswith('user_')])==19
    assert {'user_retire_many','user_retire_replay','user_retirement_real_state','user_state_read','user_full_result_fields'} <= set(profile['required_actor_cases'])
    assert {'user_tempo_150','user_tempo_200','user_tempo_pause','user_tempo_legacy_rebound',
            'user_tempo_legacy_reset','user_tempo_projection','user_tempo_applied_guard'} <= set(profile['required_actor_cases'])
    assert len(profile['required_negative_controls'])==15
    assert {'resume_tempo_retained','speed_only_projection','speed_only_applied'} <= set(profile['required_negative_controls'])


def test_completion_or_old_scoped_proof_is_not_a_transport_proof(candidate):
    path,_,_=candidate
    with pytest.raises(AssertionError,match='BUILD_PROOF_CHANGED'):
        tool.checked_build(path,tool.PROFILES['usertransport2128'])


def test_repinned_summary_cannot_bypass_separate_offline_binding(candidate):
    path,base,result=candidate
    profile=deepcopy(tool.PROFILES['usertransport2128'])
    profile.update(build_proof_sha256=tool.sha_file(path),candidate=base['candidate'],
        canonical_patch_sha256=base['canonical_patch_sha256'],predecessor=base['predecessor'])
    result['binary_bobicontrol_schema_unchanged']=False
    path.write_text(json.dumps(result));profile['build_proof_sha256']=tool.sha_file(path)
    with pytest.raises(AssertionError,match='TRANSPORT_PROFILE_BINDING'):
        tool.checked_build(path,profile)


@pytest.mark.parametrize('damage',['offline_profile_sha256','verification_proof_sha256'])
def test_user_transport_offline_binding_hashes_fail_closed(candidate,damage,monkeypatch,tmp_path):
    path,_,_=candidate
    profile=deepcopy(tool.PROFILES['usertransport2128'])
    # This negative control reaches the real verifier without a maintainer's /opt tree.
    # The synthetic verification record is not a candidate build attestation.
    offline=json.loads((tool.ROOT/'native/tests/user_transport_profile.json').read_text())
    proof=tmp_path/'verification.json'
    proof.write_text(json.dumps(dict(state='VERIFIED_OFFLINE_NOT_DEVICE_CERTIFIED',
        deployment_authority=False, candidate_sha256=profile['candidate'],
        build_proof_sha256=profile['build_proof_sha256'], profile_sha256=profile['offline_profile_sha256'],
        verifier_sha256=tool.sha_file(tool.ROOT/'native/tests/verify_ce_user_transport_candidate.py'),
        actor_cases=len(offline['required_actor_cases']), negative_controls=len(offline['required_negative_controls'])+1,
        real_translation_units=6)))
    monkeypatch.setattr(tool, 'local_artifact_path', lambda reference: {profile['verification_proof']:proof}[reference])
    profile['verification_proof_sha256']=tool.sha_file(proof)
    profile[damage]='0'*64
    expected={'offline_profile_sha256':'TRANSPORT_PROFILE_CHANGED',
              'verification_proof_sha256':'TRANSPORT_VERIFICATION_CHANGED'}
    with pytest.raises(AssertionError,match=expected[damage]):tool.checked_user_transport_build(path,{},profile)
