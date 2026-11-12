"""Pinned scoped successor verifies the changed schema and actual CE actor proof."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_ce_native_completion_profile import candidate, private_fixture
from test_ce_native_reapply import tool


CASES = ('seek_receipt', 'seek_failed', 'stale_cas', 'stream_key', 'duplicate', 'manual_subtitle_off',
    'audio_failed', 'audio_resync', 'resync_replacement', 'same_id_replacement', 'pending_manual',
    'gate_contention', 'decoder_intent_lock', 'resync_new_manual', 'ce_subtitle_resync',
    'ce_subtitle_replacement', 'ce_subtitle_new_manual', 'ce_subtitle_original_mode', 'ce_subtitle_non_demux')


@pytest.fixture
def scoped_candidate(candidate):
    path, previous, result = candidate
    profile=deepcopy(tool.PROFILES['scoped2122'])
    profile.update(candidate=previous['candidate'],predecessor=previous['predecessor'],
        canonical_patch_sha256=previous['canonical_patch_sha256'])
    snapshot=path.parent/'source-candidate'
    video='xbmc/cores/VideoPlayer/VideoPlayer.cpp'
    layout={video,'xbmc/application/ApplicationPlayer.cpp','xbmc/cores/playercorefactory/PlayerCoreConfig.cpp'}
    schema={'xbmc/interfaces/json-rpc/JSONRPC.cpp','xbmc/interfaces/json-rpc/JSONServiceDescription.cpp'}
    units=layout|schema|{'xbmc/interfaces/json-rpc/PlayerOperations.cpp'}
    method=dict(params=[dict(name='action',enum=['seek','audio_stream','manual_subtitle_stream','subtitle_visible']),
        dict(name='control_protocol',maximum=1)])
    for name in units|{'xbmc/cores/VideoPlayer/VideoPlayer.h','xbmc/cores/VideoPlayer/BobiScopedControl.h'}:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(name)
    methods=snapshot/'xbmc/interfaces/json-rpc/schema/methods.json'
    methods.parent.mkdir(parents=True);methods.write_text(json.dumps({'Player.BobiControl':method}))
    header=path.parent/'generated/ServiceDescription.h'
    header.parent.mkdir();header.write_text('actual generated schema')
    result['objects']={}
    for name in units:
        obj=path.parent/(Path(name).name+'.o');obj.write_bytes(name.encode())
        dep=Path(str(obj)+'.d')
        dep.write_text((snapshot/'xbmc/cores/VideoPlayer/VideoPlayer.h').as_posix() if name in layout else header.as_posix())
        result['objects'][name]=dict(sha256=tool.sha_file(obj),depfile_sha256=tool.sha_file(dep))
    result['source_sha256']={p.relative_to(snapshot).as_posix():tool.sha_file(p) for p in snapshot.rglob('*') if p.is_file()}
    result.update(build_kind='scoped_controls',predecessor_unchanged=True,
        predecessor_proof_sha256=profile['predecessor_proof_sha256'],recompiled_units=sorted(units),
        binary_bobicontrol_schema_unchanged=False,binary_bobicontrol_schema_matches_source=True,
        schema_changed_methods=['Player.BobiControl'],schema_include_sources=sorted(schema),
        schema_consumers=['build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/'+Path(p).name+'.o' for p in sorted(schema)],
        platform_variants=['preserve-ce-subtitle-switch-and-bluray'],
        ce_context_patch_sha256=profile['ce_context_patch_sha256'],platform_patch_sha256=profile['platform_patch_sha256'],
        binary_bobicontrol=method,generated_header_sha256=tool.sha_file(header),
        retained_archive_members={'build/guilib_listproviders/guilib_listproviders.a':{'DirectoryProvider.cpp.o':'retained'}})
    proof=path.parent/'actor/result.json';proof.parent.mkdir()
    artifacts={}
    for name,field in [('actual_scoped_actor.inc','extracted_sha256'),('scoped-actor-test','binary_sha256')]:
        target=proof.parent/name;target.write_bytes(name.encode());artifacts[field]=tool.sha_file(target)
    actor=dict(compiled=True,passed=True,tests=[dict(name=name,passed=True) for name in CASES],
        source=snapshot.as_posix(),source_sha256={p:result['source_sha256'][p] for p in
            (video,'xbmc/cores/VideoPlayer/BobiScopedControl.h')},**artifacts)
    proof.write_text(json.dumps(actor));profile.update(actor_proof=str(proof),actor_proof_sha256=tool.sha_file(proof))
    path.write_text(json.dumps(result));profile['build_proof_sha256']=tool.sha_file(path)
    return path,profile,result,proof,actor


def test_scoped_profile_accepts_changed_schema_and_bound_actual_actor(scoped_candidate):
    path,profile,result,_,_=scoped_candidate
    assert tool.checked_build(path,profile)[0]==result


@pytest.mark.parametrize('damage',['unchanged_schema','schema_match','schema_consumer','unit','patch','variant','generated',
    'actor_proof','actor_source','actor_binary','source_header','home_archive'])
def test_scoped_incomplete_or_tampered_artifacts_are_rejected(scoped_candidate,damage):
    path,profile,result,proof,actor=scoped_candidate
    if damage=='unchanged_schema':result['binary_bobicontrol_schema_unchanged']=True
    if damage=='schema_match':result['binary_bobicontrol_schema_matches_source']=False
    if damage=='schema_consumer':result['schema_consumers'].pop()
    if damage=='unit':result['recompiled_units'].pop()
    if damage=='patch':result['platform_patch_sha256']='0'*64
    if damage=='variant':result['platform_variants']=[]
    if damage=='generated':(path.parent/'generated/ServiceDescription.h').write_bytes(b'changed')
    if damage=='actor_proof':proof.write_bytes(b'changed')
    if damage=='actor_source':(proof.parent/'actual_scoped_actor.inc').write_bytes(b'changed')
    if damage=='actor_binary':(proof.parent/'scoped-actor-test').write_bytes(b'changed')
    if damage=='source_header':(path.parent/'source-candidate/xbmc/cores/VideoPlayer/BobiScopedControl.h').write_bytes(b'changed')
    if damage=='home_archive':result['retained_archive_members']={}
    path.write_text(json.dumps(result));profile['build_proof_sha256']=tool.sha_file(path)
    with pytest.raises(AssertionError):tool.checked_build(path,profile)


@pytest.mark.parametrize('damage',['missing_case','failed_case','false_positive','other_source','mismatched_source','header_dependency'])
def test_scoped_repinned_claims_do_not_replace_production_evidence(scoped_candidate,damage):
    path,profile,result,proof,actor=scoped_candidate
    if damage=='missing_case':actor['tests'].pop()
    if damage=='failed_case':actor['tests'][0]['passed']=False
    if damage=='false_positive':actor['passed']=False
    if damage=='other_source':actor['source']=str(path.parent/'foreign')
    if damage=='mismatched_source':actor['source_sha256']['xbmc/cores/VideoPlayer/VideoPlayer.cpp']='a'*64
    if damage=='header_dependency':
        dep=path.parent/'JSONRPC.cpp.o.d';dep.write_text('unrelated/generated/ServiceDescription.h')
        result['objects']['xbmc/interfaces/json-rpc/JSONRPC.cpp']['depfile_sha256']=tool.sha_file(dep)
    proof.write_text(json.dumps(actor));profile['actor_proof_sha256']=tool.sha_file(proof)
    path.write_text(json.dumps(result));profile['build_proof_sha256']=tool.sha_file(path)
    with pytest.raises(AssertionError):tool.checked_build(path,profile)


def test_scoped_profile_is_distinct_with_original_home_overlay_as_rollback():
    profile=tool.PROFILES['scoped2122'];old=tool.PROFILES['homefocus2116']
    assert profile['sequence']==2026102122 and profile['base']!=old['base']
    assert profile['predecessor']['binary']==old['candidate']
    assert profile['predecessor']['binary_path']==old['base']+'/kodi.bin'
    assert profile['minimum_versions']=={'plugin.video.bobbi':'0.1.64','script.module.bobbi.core':'0.1.64','script.module.bobbi.platform':'0.1.73'}
