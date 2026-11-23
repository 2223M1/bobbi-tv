"""Completion host is a pinned successor with reversible existing maintenance."""
import json
from pathlib import Path
import sys

import pytest

from test_ce_native_reapply import tool,harness
from types import SimpleNamespace
from test_ce_native_handoff_profile import digest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))


@pytest.fixture
def candidate(tmp_path):
    binary = tmp_path/'candidate.bin'
    binary.write_bytes(b'new-completion-host')
    snapshot = tmp_path/'source-candidate'
    snapshot.mkdir()
    (snapshot/'header.h').write_text('fixed-layout')
    units = ['xbmc/cores/VideoPlayer/VideoPlayer.cpp','xbmc/application/ApplicationPlayer.cpp',
             'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp']
    objects = {}
    for unit in units:
        obj = tmp_path/(unit.rsplit('/',1)[1]+'.o')
        obj.write_bytes(unit.encode())
        dep = tmp_path/(obj.name+'.d')
        dep.write_text('fixed-layout dependencies')
        objects[unit] = dict(sha256=tool.sha_file(obj),depfile_sha256=tool.sha_file(dep))
    old = digest(b'schema-host')
    result = dict(state='BUILT_NOT_DEPLOYED',original_tree_unchanged=True,
        predecessor_sha256=old,**{'predecessor-relink_sha256':old},
        architecture_and_dependencies_unchanged=True,binary_bobicontrol_schema_unchanged=True,
        canonical_patch_sha256=digest(b'canonical-patch'),objects=objects,
        source_sha256={'header.h':tool.sha_file(snapshot/'header.h')},candidate_sha256=tool.sha_file(binary))
    path = tmp_path/'build-result.json'
    path.write_text(json.dumps(result))
    profile = dict(build_kind='completion',build_proof_sha256=tool.sha_file(path),
        canonical_patch_sha256=result['canonical_patch_sha256'],candidate=result['candidate_sha256'],
        predecessor=dict(binary=old))
    return path,profile,result


def test_completion_uses_exact_verified_schema_predecessor(candidate):
    path,profile,result = candidate
    assert tool.checked_build(path,profile)[0] == result


@pytest.mark.parametrize('damage',['proof','binary','object','depfile','source','source_extra'])
def test_completion_rejects_changed_build_artifacts(candidate,damage):
    path,profile,result = candidate
    targets = dict(proof=path,binary=path.parent/'candidate.bin',
        object=path.parent/'VideoPlayer.cpp.o',depfile=path.parent/'VideoPlayer.cpp.o.d',
        source=path.parent/'source-candidate/header.h',source_extra=path.parent/'source-candidate/other.h')
    targets[damage].write_bytes(b'changed')
    with pytest.raises(AssertionError): tool.checked_build(path,profile)


@pytest.mark.parametrize('damage',['unchanged','predecessor','relink','architecture','schema','patch','consumer'])
def test_completion_rejects_incomplete_proof_even_when_report_is_repinned(candidate,damage):
    path,profile,result = candidate
    fields = dict(unchanged='original_tree_unchanged',predecessor='predecessor_sha256',
        relink='predecessor-relink_sha256',architecture='architecture_and_dependencies_unchanged',
        schema='binary_bobicontrol_schema_unchanged',patch='canonical_patch_sha256')
    if damage=='consumer': result['objects'].pop('xbmc/application/ApplicationPlayer.cpp')
    else: result[fields[damage]] = False
    path.write_text(json.dumps(result))
    profile['build_proof_sha256'] = tool.sha_file(path)
    with pytest.raises(AssertionError): tool.checked_build(path,profile)


@pytest.mark.parametrize('valid',[True,False])
def test_optional_terminal_observation_does_not_downgrade_native_probe(valid):
    from bobbi_platform.capabilities import probe,NATIVE_METHODS,STANDARD_METHODS
    from bobbi_core.runtime_paths import known_ce_native
    assert known_ce_native('4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a')
    assert known_ce_native('ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991')
    observation = dict(schema=1,position_ms=99960 if valid else 0,duration_ms=100000 if valid else 0,
                       age_us=1000 if valid else 0,valid=valid)
    row = dict(protocol=1,native_instance='12345678-1234-1234-1234-123456789abc',request_id='a'*32,
        file_identity='file',url_sha256='b'*64,phase='TERMINAL',reason='NATURAL_EOF',sequence=2,
        user_intent=0,paused=False,completion_observation=observation)
    replies = {'Application.GetProperties':{'version':{'major':21}},
        'JSONRPC.Introspect':{'methods':dict.fromkeys(NATIVE_METHODS|STANDARD_METHODS,{})},
        'Player.BobiState':dict(protocol=1,selection_epoch=1,playback=row)}
    assert probe(lambda method,params:replies[method])['native_contract_available']


def private_fixture(tmp_path,monkeypatch):
    h = harness(tmp_path,monkeypatch)
    profile = tool.PROFILES['completion2114']
    versions = dict(profile['minimum_versions'])
    h.generation.write_text(json.dumps(dict(sequence=2026102114,versions=versions)))
    addons = tmp_path/'addons'
    for ident,version in versions.items():
        folder=addons/ident
        folder.mkdir(parents=True)
        (folder/'addon.xml').write_text('<addon id="'+ident+'" version="'+version+'"/>')
    entry=tmp_path/'installation.json'
    entry.write_text(json.dumps(dict(schema=1,sequence=2026102071,high_watermark=2026102071,
                                     phase='complete',tx='a'*32)))
    previous_path=h.ns['pathlib'].Path
    aliases={'/storage/.kodi/addons':addons,tool.ENTRY_GENERATION_PATH:entry}
    h.ns['pathlib']=SimpleNamespace(Path=lambda value:aliases.get(str(value),previous_path(value)))
    h.ns.update(MODE='apply',REQUIRED_SEQUENCE=2026102114,GENERATION_KIND='private_complete',
                GENERATION_PATH=tool.LEGACY_GENERATION_PATH,MINIMUM_VERSIONS=versions)
    h.receipt.unlink()
    (h.base/'previous.conf').unlink()
    return h,addons,entry


def test_private_generation_is_current_without_rewriting_historical_entry(tmp_path,monkeypatch):
    h,addons,entry=private_fixture(tmp_path,monkeypatch)
    before=(h.generation.read_bytes(),entry.read_bytes())
    h.run()
    assert h.ns['out']['generation']['source']=='private_complete'
    assert h.ns['out']['generation']['sequence']==2026102114
    assert (h.generation.read_bytes(),entry.read_bytes())==before
    assert json.loads(h.receipt.read_text())['state']=='applied'


@pytest.mark.parametrize('damage',['sequence','sequence_bool','missing_versions','version_low',
    'version_bad','manifest_version','manifest_id','pending','entry_pending','entry_host_pending'])
def test_private_incomplete_generation_never_stops_service(tmp_path,monkeypatch,damage):
    h,addons,entry=private_fixture(tmp_path,monkeypatch)
    state=json.loads(h.generation.read_text())
    ident='script.module.bobbi.core'
    if damage=='sequence': state['sequence']=2026102113
    if damage=='sequence_bool': state['sequence']=True
    if damage=='missing_versions': state.pop('versions')
    if damage=='version_low': state['versions'][ident]='0.1.57'
    if damage=='version_bad': state['versions'][ident]='0.1.999-preview'
    if damage=='manifest_version': (addons/ident/'addon.xml').write_text('<addon id="'+ident+'" version="0.1.57"/>')
    if damage=='manifest_id': (addons/ident/'addon.xml').write_text('<addon id="other" version="0.1.59"/>')
    if damage=='pending': (h.generation.parent/'journal.json').write_text('{}')
    if damage.startswith('entry_'):
        prior=json.loads(entry.read_text())
        if damage=='entry_pending': prior['phase']='switching'
        else: prior['host_pending']='update'
        entry.write_text(json.dumps(prior))
    h.generation.write_text(json.dumps(state))
    before=(h.generation.read_bytes(),entry.read_bytes())
    with pytest.raises(AssertionError): h.run()
    assert not h.calls and not h.receipt.exists()
    assert before==(h.generation.read_bytes(),entry.read_bytes())


@pytest.mark.parametrize('when',['stop','ready'])
@pytest.mark.parametrize('damage',['state','entry','manifest','pending'])
def test_private_concurrent_change_recovers_old_native_without_repairing_journal(tmp_path,monkeypatch,when,damage):
    h,addons,entry=private_fixture(tmp_path,monkeypatch)
    target={'state':h.generation,'entry':entry,'manifest':addons/'script.module.bobbi.core/addon.xml',
            'pending':h.generation.parent/'journal.json'}[damage]
    changed=[False]
    def change():
        if not changed[0]:
            target.write_bytes(b'concurrent update')
            changed[0]=True
    original=h.ns['command']
    def command(*args):
        if when=='stop' and args[:2]==('systemctl','stop'):change()
        return original(*args)
    h.ns['command']=command
    def ready(expected):
        if when=='ready':change()
        return True
    h.ns['ready']=ready
    with pytest.raises(AssertionError,match='PROGRAM_GENERATION_CHANGED|PROGRAM_UPDATE_PENDING'):h.run()
    assert target.read_bytes()==b'concurrent update'
    assert h.conf.read_bytes()==h.old_conf
    assert json.loads(h.receipt.read_text())['state']=='recovered_after_failure'


def test_private_candidate_profile_keeps_distinct_overlay_and_known_rollback():
    profile=tool.PROFILES['completion2114']
    assert profile['sequence']==2026102114 and profile['generation_kind']=='private_complete'
    assert profile['generation_path']==tool.LEGACY_GENERATION_PATH
    assert profile['predecessor']['binary']==tool.PROFILES['schema2043']['candidate']
    assert profile['base']!=tool.PROFILES['schema2043']['base']
