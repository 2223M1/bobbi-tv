"""Read-only candidate projection and exact installed-policy binding tests."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ce_cloud_qualification_candidate as candidate
from test_ce_cloud_ebml_directory import scene,SCOPE,EXPECTED,DATA


def facts(**changes):
    value=dict(duration=1500.0,streams=[dict(codec_type='video',codec_name='hevc',width=1920,height=1080,
        tags={'filename':'private-name','title':'private-title'},index=0,pix_fmt='yuv420p')],
        method='matroska_container_header',coverage='prefix_to_first_cluster',read_bytes=5,requests=1,
        seconds=.01,probe_sha256='a'*64,attachments_bytes=15*1024*1024,chapters_checked=True)
    value.update(changes)
    return value


def test_candidate_reads_exact_mapping_but_never_publishes_ready_or_private_demux_fields(scene):
    before=scene.path.read_bytes()
    def probe(binary,size,read,cancelled):
        assert size==len(DATA) and not cancelled()
        assert b''.join(read(0,4))==DATA[:5]
        return facts()
    result=candidate.diagnose(scene.root,EXPECTED,account_read=lambda:deepcopy(SCOPE),
        provider_factory=lambda:scene.provider,probe=probe)
    assert result['ok'] and result['qualification']['ordinary_candidate']
    assert result['qualification']['state']=='READONLY_NOT_PUBLISHED' and result['qualification']['media_profile'] is False
    assert result['media_reads']['requests']==1 and result['media_reads']['bytes']==5
    assert scene.path.read_bytes()==before and scene.provider.maps==2 and scene.provider.session.closed
    raw=json.dumps(result)
    for secret in ('private','filename','pix_fmt','115open','http://',SCOPE['account_id']):assert secret not in raw


@pytest.mark.parametrize('changes',[{'duration':float('nan')},{'duration':0},{'coverage':'full_file'},
    {'duration':10**1000},{'seconds':10**1000},
    {'method':'unknown'},{'requests':33},{'read_bytes':16*1024*1024+1},{'seconds':21},
    {'probe_sha256':'private-url'},{'chapters_checked':'yes'},
    {'streams':[dict(codec_type='video',codec_name='private url',width=1920,height=1080)]}])
def test_candidate_projection_has_closed_truthful_evidence(changes):
    with pytest.raises(ValueError):candidate.safe_result(facts(**changes))


def test_candidate_account_drift_withholds_entire_qualification(scene):
    scopes=iter([SCOPE,SCOPE,dict(SCOPE,epoch=99)])
    result=candidate.diagnose(scene.root,EXPECTED,account_read=lambda:next(scopes),
        provider_factory=lambda:scene.provider,probe=lambda *args:facts())
    assert not result['ok'] and result['error']=='ACCOUNT_CHANGED' and 'qualification' not in result


def test_candidate_hard_media_timeout_does_not_start_postchecks(scene):
    def expired(*args):raise candidate.binding._HardDeadline()
    result=candidate.diagnose(scene.root,EXPECTED,account_read=lambda:deepcopy(SCOPE),
        provider_factory=lambda:scene.provider,probe=expired)
    assert not result['ok'] and result['error']=='TIME_BUDGET'
    assert scene.provider.maps==1 and scene.provider.session.closed


def test_narrow_method_cannot_generate_strong_profile_even_if_future_stream_fields_added(scene,monkeypatch):
    from bobbi_core.cloud_qualifier import CloudQualifier
    from bobbi_core import release_media_profile
    def forbidden(*args):pytest.fail('Narrow facts attempted media_profile')
    monkeypatch.setattr(release_media_profile,'media_profile',forbidden)
    request=candidate.binding.load_bound_task(scene.path,EXPECTED,scene.config['account'],scene.config['destination'],lambda:True)
    qualifier=CloudQualifier('binary',scene.config['cd2_endpoint'],scene.config['download_capability'],inspect=lambda *args:facts())
    result=qualifier(scene.provider,request)
    assert result and result['qualification']['video_codec']=='hevc'
    assert 'media_profile' not in result['qualification']
    assert (result['qualification']['probe_method'],result['qualification']['probe_coverage'])==('matroska_container_header','prefix_to_first_cluster')
    qualifier.inspect=lambda *args:facts(coverage='unknown')
    assert qualifier(scene.provider,request) is None


def test_full_demux_path_can_still_produce_strong_profile(scene,monkeypatch):
    from bobbi_core.cloud_qualifier import CloudQualifier
    from bobbi_core import release_media_profile
    result=facts();result.pop('method');result.pop('coverage')
    profile={'sentinel':'original-full-profile'}
    monkeypatch.setattr(release_media_profile,'media_profile',lambda streams:profile)
    request=candidate.binding.load_bound_task(scene.path,EXPECTED,scene.config['account'],scene.config['destination'],lambda:True)
    qualifier=CloudQualifier('binary',scene.config['cd2_endpoint'],scene.config['download_capability'],inspect=lambda *args:result)
    assert qualifier(scene.provider,request)['qualification']['media_profile'] is profile
    assert qualifier(scene.provider,request)['qualification']['probe_method']=='ffprobe'


@pytest.mark.parametrize('pair',[{'method':None,'coverage':None},{'method':'ffprobe'},
    {'coverage':'bounded_demux'},{'method':'other','coverage':'bounded_demux'},
    {'method':'matroska_container_header','coverage':'bounded_demux'}])
def test_explicit_null_partial_or_unknown_method_pair_is_not_legacy(scene,pair):
    from bobbi_core.cloud_qualifier import CloudQualifier
    value=facts();value.pop('method');value.pop('coverage');value.update(pair)
    request=candidate.binding.load_bound_task(scene.path,EXPECTED,scene.config['account'],scene.config['destination'],lambda:True)
    qualifier=CloudQualifier('binary',scene.config['cd2_endpoint'],scene.config['download_capability'],inspect=lambda *args:value)
    assert qualifier(scene.provider,request) is None


def evidence(method=None):
    value=dict(file_id='file',bytes=1000000,version_key='release',source_binding=True,
        read_bytes=1024,probe_sha256='a'*64,duration=600.0,video_codec='hevc')
    if method:
        value.update(probe_method=method,probe_coverage='prefix_to_first_cluster' if method=='matroska_container_header' else 'bounded_demux')
    return value


@pytest.mark.parametrize('method',[None,'ffprobe','matroska_container_header'])
def test_ledger_persists_fixed_method_pair_in_same_ready_transaction_and_audit(tmp_path,method):
    from bobbi_core.ledger import Ledger
    with Ledger(tmp_path/'ledger.sqlite') as ledger:
        resource=ledger.register(dict(provider='115',account='account',file_id='file',cloud_path='/115open/inbox/file.mkv',
            bytes=1000000,kind='video',media_id='tmdb:tv:1:s1:e1',version_key='release'),managed=True,identity_verified=True)
        value=evidence(method)
        ledger.mark_ready(resource,value)
        saved=ledger.get(resource)['qualification']
        detail=json.loads(ledger.db.execute("SELECT detail FROM audit WHERE action='ready' AND resource=? ORDER BY seq DESC LIMIT 1",(resource,)).fetchone()[0])
        for key in ('probe_method','probe_coverage'):
            assert saved.get(key)==value.get(key)==detail.get(key)
        assert 'media_profile' not in saved


@pytest.mark.parametrize('extra',[{'probe_method':'ffprobe'}, {'probe_coverage':'bounded_demux'},
    {'probe_method':None,'probe_coverage':None}, {'probe_method':'unknown','probe_coverage':'bounded_demux'},
    {'probe_method':'matroska_container_header','probe_coverage':'prefix_to_first_cluster','media_profile':{}},
    {'probe_method':{},'probe_coverage':'bounded_demux'}])
def test_ledger_rejects_bad_pair_and_header_profile_without_ready_mutation(tmp_path,extra):
    from bobbi_core.ledger import Ledger
    with Ledger(tmp_path/'ledger.sqlite') as ledger:
        resource=ledger.register(dict(provider='115',account='account',file_id='file',cloud_path='/115open/inbox/file.mkv',
            bytes=1000000,kind='video',media_id='tmdb:tv:1:s1:e1',version_key='release'),managed=True,identity_verified=True)
        with pytest.raises(ValueError):ledger.mark_ready(resource,dict(evidence(),**extra))
        assert ledger.get(resource)['state']=='observed'
        assert not ledger.db.execute("SELECT 1 FROM audit WHERE action='ready'").fetchone()


def test_bundle_injects_only_candidate_probe_modules_without_device_install():
    source=candidate.remote_source(EXPECTED)
    compile(source,'candidate','exec')
    assert "'bobbi_core.matroska_qualification'" in source and "'bobbi_core.media_probe'" in source
    assert "namespace['remote_main']" in source and 'injected_source_sha256' in source
    own=Path(candidate.__file__).read_text(encoding='utf-8')
    for forbidden in ('.add_offline(','.mark_ready(','.register(','.publish(','.control(','.write_text('):
        assert forbidden not in own


def test_header_only_diagnostic_stops_at_fixed_numeric_unsupported_field_without_fallback(monkeypatch):
    from test_matroska_qualification import Sparse,info,elem,track
    from bobbi_core import matroska_qualification as mkv,media_probe as media
    source=Sparse(metadata=info()+elem(mkv.TRACKS,track(extra=elem(0x6d80,b''))))
    monkeypatch.setattr(media,'_probe',lambda *a,**kw:pytest.fail('diagnostic retried via ffprobe'))
    with pytest.raises(mkv.UnsupportedLayout) as raised:
        candidate.header_diagnose('never-executed',source.size,source.read,lambda:False)
    diagnostic=candidate.safe_unsupported(raised.value)
    assert {k:diagnostic[k] for k in ('stage','reason','element_id')}==dict(stage='tracks',reason='TRACK_FIELD_UNSUPPORTED',element_id=0x6d80)
    assert diagnostic['encoding']['complete'] is False and diagnostic['encoding']['track_type']==1
    assert raised.value.metrics['read_bytes']<1024 and raised.value.metrics['requests']<24
    assert media._LANE.acquire(blocking=False)
    media._LANE.release()
    assert 'True)' in candidate.remote_source(EXPECTED,header_only=True)


@pytest.mark.parametrize('kind',[1,2,17])
@pytest.mark.parametrize('algorithm',[0,3])
def test_encoding_diagnostic_is_order_independent_numeric_only_and_never_adds_http(kind,algorithm):
    from test_matroska_qualification import Sparse,info,elem,integer
    from bobbi_core import matroska_qualification as mkv
    compression=elem(0x5034,integer(0x4254,algorithm)+elem(0x4255,b'private-settings'))
    encoding=elem(0x6d80,elem(0x6240,compression))
    entry=elem(0xae,encoding+integer(0x83,kind)+integer(0xd7,1))
    source=Sparse(metadata=info()+elem(mkv.TRACKS,entry))
    with pytest.raises(mkv.UnsupportedLayout) as raised:
        candidate.header_diagnose('never',source.size,source.read,lambda:False)
    diagnostic=candidate.safe_unsupported(raised.value)
    summary=diagnostic['encoding']
    assert summary['complete'] and summary['track_type']==kind
    row=summary['encodings'][0]
    assert (row['order'],row['scope'],row['type'],row['algorithm'])==(0,1,0,algorithm)
    assert row['settings_bytes']==len(b'private-settings') and row['encryption_present'] is False
    assert row['defaulted']==['order','scope','type']
    assert 'private' not in json.dumps(diagnostic) and raised.value.metrics['requests']==len(source.calls)
    # Directly summarizing the already cached bytes cannot invoke the reader.
    budget=source.budget();budget.read=lambda *a:pytest.fail('diagnostic added HTTP')
    again=mkv.Headers(budget,1).encoding_diagnostic(bytes([kind]),elem(0x6240,compression))
    assert again==summary


@pytest.mark.parametrize('content',[b'',
    bytes.fromhex('624080')*5,
    bytes.fromhex('6240855031820100'),
    bytes.fromhex('6240885031810050318100')])
def test_incomplete_or_excessive_encoding_diagnostic_is_fail_closed(content):
    from test_matroska_qualification import Sparse
    from bobbi_core import matroska_qualification as mkv
    summary=mkv.Headers(Sparse().budget(),1).encoding_diagnostic(b'\x11',content)
    assert summary['complete'] is False


def test_encryption_is_reported_even_when_type_defaults_to_compression():
    from test_matroska_qualification import Sparse,elem
    from bobbi_core import matroska_qualification as mkv
    summary=mkv.Headers(Sparse().budget(),1).encoding_diagnostic(b'\x11',elem(0x6240,elem(0x5035,b'private-encryption')))
    assert summary['complete'] and summary['encodings'][0]['type']==0
    assert summary['encodings'][0]['encryption_present'] is True and 'private' not in json.dumps(candidate.safe_encoding(summary))
