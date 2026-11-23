"""Bounded ordinary header qualification, not decoded/media-profile proof."""
import hashlib
from pathlib import Path
import struct
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core import matroska_qualification as mkv, media_probe as media


def vint(value):
    width=next(n for n in range(1,9) if value<(1<<(7*n))-1)
    return ((1<<(7*width))|value).to_bytes(width,'big')


def head(ident,size):
    return ident.to_bytes((ident.bit_length()+7)//8,'big')+vint(size)


def elem(ident,data=b''):
    return head(ident,len(data))+data


def integer(ident,value):
    return elem(ident,value.to_bytes(max(1,(value.bit_length()+7)//8),'big'))


def info(duration=1500.0,scale=1000000):
    return elem(mkv.INFO,integer(0x2ad7b1,scale)+elem(0x4489,struct.pack('>d',duration*1000)))


def track(codec=b'V_MPEG4/ISO/AVC',width=1920,height=1080,extra=b'',video_extra=b''):
    return elem(0xae,integer(0xd7,1)+integer(0x83,1)+elem(0x86,codec)
        +elem(0xe0,integer(0xb0,width)+integer(0xba,height)+video_extra)+extra)


def chapters(ordered=None,extra=b'',atom_extra=b'',start=0,end=None,nested=b''):
    atom=integer(0x73c4,1)+integer(0x91,start)+atom_extra+nested
    if end is not None:atom+=integer(0x92,end)
    edition=integer(0x45bc,1)+(integer(0x45dd,ordered) if ordered is not None else b'')+extra+elem(0xb6,atom)
    return elem(mkv.CHAPTERS,elem(0x45b9,edition))


class Sparse:
    def __init__(self,metadata=None,chapters_data=None,attachments=15*1024*1024,tail=b'',unknown=False,cluster_bytes=2*1024*1024):
        ebml=elem(mkv.EBML,elem(0x4282,b'matroska')+integer(0x4285,4))
        metadata=info()+elem(mkv.TRACKS,track()) if metadata is None else metadata
        after=(chapters() if chapters_data is None else chapters_data)+tail+head(mkv.CLUSTER,cluster_bytes)
        payload=len(metadata)+len(head(mkv.ATTACHMENTS,attachments))+attachments+len(after)+cluster_bytes
        segment=(mkv.SEGMENT.to_bytes(4,'big')+b'\xff') if unknown else head(mkv.SEGMENT,payload)
        prefix=ebml+segment+metadata+head(mkv.ATTACHMENTS,attachments)
        self.font=(len(prefix),len(prefix)+attachments)
        self.pieces=[(0,prefix),(self.font[1],after)]
        self.size=self.font[1]+len(after)+cluster_bytes
        self.calls=[]
    def read(self,start,end):
        self.calls.append((start,end))
        for offset,data in self.pieces:
            if offset<=start<=end<offset+len(data):
                yield data[start-offset:end-offset+1]
                return
        pytest.fail('Attachment or Cluster payload was read')
    def budget(self,cancelled=lambda:False):
        return media.RangeBudget(self.size,self.read,cancelled)


@pytest.mark.parametrize('unknown',[False,True])
def test_complete_prefix_actual_chapters_skips_large_attachment_and_emits_only_real_facts(unknown):
    source=Sparse(unknown=unknown)
    result=media.qualification_probe('not-invoked',source.size,source.read)
    assert result['duration']==1500 and result['streams']==[dict(codec_type='video',codec_name='h264',width=1920,height=1080)]
    assert result['method']=='matroska_container_header' and result['chapters_checked']
    assert result['attachments_bytes']==15*1024*1024 and result['read_bytes']<1024
    assert result['requests']<=32 and len(result['probe_sha256'])==64
    assert all(end<source.font[0] or start>=source.font[1] for start,end in source.calls)
    assert all(key not in result['streams'][0] for key in ('index','pix_fmt','avg_frame_rate','channel_layout'))


@pytest.mark.parametrize('metadata',[info()+elem(mkv.TRACKS,track(codec=b'V_UNKNOWN')),
    info()+elem(mkv.TRACKS,track(width=0)),info()+elem(mkv.TRACKS,track(height=16385)),
    info(float('nan'))+elem(mkv.TRACKS,track()),info(float('inf'))+elem(mkv.TRACKS,track()),
    info(-1)+elem(mkv.TRACKS,track()),info(scale=0)+elem(mkv.TRACKS,track()),
    elem(mkv.INFO,b'')+elem(mkv.TRACKS,track()),info()+info()+elem(mkv.TRACKS,track()),
    info()+elem(mkv.TRACKS,track())+elem(mkv.TRACKS,track()),
    info()+elem(mkv.TRACKS,track()+track()),info()+elem(mkv.TRACKS,track(extra=elem(0x6d80))),
    info()+elem(mkv.TRACKS,track(extra=integer(0x23314f,1))),
    elem(mkv.INFO,elem(0x4489,struct.pack('>d',1500))+elem(0x3cb923,b'external'))+elem(mkv.TRACKS,track())])
def test_missing_ambiguous_external_encoded_or_unsupported_facts_never_qualify(metadata):
    source=Sparse(metadata=metadata)
    with pytest.raises(mkv.UnsupportedLayout):mkv.inspect_headers(source.budget(),media.BYTE_BUDGET-media.ANALYSIS_BYTES)


@pytest.mark.parametrize('chapters_data',[chapters(ordered=1),chapters(ordered=2),
    chapters(extra=integer(0x45dd,0)+integer(0x45dd,0)),chapters(atom_extra=elem(0x6e67,b'external')),
    chapters(atom_extra=integer(0x6ebc,1)),chapters(atom_extra=elem(0x6944,b'')),
    chapters(atom_extra=elem(0x8f,b'')),chapters(start=2,end=1),
    chapters(atom_extra=integer(0x91,0)),chapters(atom_extra=elem(0x99,b'unknown'))])
def test_ordered_external_process_conflicting_or_unknown_chapters_are_unsupported(chapters_data):
    source=Sparse(chapters_data=chapters_data)
    with pytest.raises(mkv.UnsupportedLayout):mkv.inspect_headers(source.budget(),1)


def test_known_nondefault_nested_display_chapters_are_safe_without_duration_guess():
    display=elem(0x80,elem(0x85,b'private chapter title')+elem(0x437c,b'eng'))
    nested=elem(0xb6,integer(0x91,2000000000000)+display)
    source=Sparse(chapters_data=chapters(ordered=0,extra=integer(0x45db,0),nested=nested))
    result=mkv.inspect_headers(source.budget(),1)
    assert result['duration']==1500 and result['chapters_checked']  # Do not invent timeline from chapter labels.


def test_unsupported_fallback_reuses_same_budget_and_single_lane(monkeypatch):
    source=Sparse(attachments=1,cluster_bytes=17*1024*1024)
    observed=[]
    def fallback(binary,size,read,cancelled,transferred,**kwargs):
        budget=kwargs['budget']
        assert budget.count>0 and budget.requests>0
        assert not media._LANE.acquire(blocking=False)
        observed.append((budget.count,budget.requests,budget.started))
        return {'fallback':True}
    monkeypatch.setattr(media,'_probe',fallback)
    assert media.qualification_probe('binary',source.size,source.read)=={'fallback':True}
    assert len(observed)==1 and media._LANE.acquire(blocking=False)
    media._LANE.release()


def test_many_small_voids_use_soft_scan_cap_then_same_remaining_budget(monkeypatch):
    source=Sparse(metadata=info()+elem(mkv.TRACKS,track())+elem(0xec)*60,attachments=1,cluster_bytes=17*1024*1024)
    seen=[]
    def fallback(*args,**kwargs):
        budget=kwargs['budget'];seen.append(budget.requests)
        assert budget.requests==24 and budget.count<128*1024
        return {'fallback':True}
    monkeypatch.setattr(media,'_probe',fallback)
    assert media.qualification_probe('binary',source.size,source.read)=={'fallback':True}
    assert seen==[24]


def test_soft_time_cap_reserves_same_total_budget_without_sleep(monkeypatch):
    clock=[0.0]
    source=Sparse(metadata=info()+elem(mkv.TRACKS,track())+elem(0xec)*20,attachments=1,cluster_bytes=17*1024*1024)
    def slow_read(start,end):
        clock[0]+=1.0
        yield from source.read(start,end)
    original=media.RangeBudget
    monkeypatch.setattr(media,'RangeBudget',lambda size,read,cancelled:original(size,read,cancelled,clock=lambda:clock[0]))
    def fallback(*args,**kwargs):
        budget=kwargs['budget']
        assert 8<=clock[0]<10 and budget.started==0 and budget.requests<24
        return {'fallback':True}
    monkeypatch.setattr(media,'_probe',fallback)
    assert media.qualification_probe('binary',source.size,slow_read)=={'fallback':True}


@pytest.mark.parametrize('size',[1024,14*1024*1024,15*1024*1024,16*1024*1024])
def test_small_file_bypasses_prefix_entirely_and_keeps_original_byte_accounting(monkeypatch,size):
    source=Sparse(attachments=1)
    source.size=size
    def fallback(*args,**kwargs):
        budget=kwargs['budget']
        assert budget.count==0 and budget.requests==0 and source.calls==[]
        return {'original':True}
    monkeypatch.setattr(media,'_probe',fallback)
    assert media.qualification_probe('binary',source.size,source.read)=={'original':True}


def test_ordinary_large_file_never_reads_tracks_or_chapters_bodies_before_fallback(monkeypatch):
    metadata=info()+elem(mkv.TRACKS,track(extra=elem(0x63a2,b'private codec data'*2000)))
    source=Sparse(metadata=metadata,attachments=1,cluster_bytes=17*1024*1024)
    def fallback(*args,**kwargs):
        assert kwargs['budget'].count<256 and all(end-start+1<100 for start,end in source.calls)
        return {'fallback':True}
    monkeypatch.setattr(media,'_probe',fallback)
    assert media.qualification_probe('binary',source.size,source.read)=={'fallback':True}


@pytest.mark.parametrize('explicit',[False,True])
def test_only_plain_subtitle_packet_zlib_is_supported_without_decoding(explicit):
    encoding=(integer(0x5031,0)+integer(0x5032,1)+integer(0x5033,0) if explicit else b'')
    encoding+=elem(0x5034,integer(0x4254,0)+elem(0x4255) if explicit else b'')
    subtitle=elem(0xae,integer(0xd7,2)+elem(0x6d80,elem(0x6240,encoding))+integer(0x83,17)+elem(0x86,b'S_TEXT/ASS'))
    source=Sparse(metadata=info()+elem(mkv.TRACKS,track()+subtitle))
    result=media.qualification_probe('unused',source.size,source.read)
    assert result['method']=='matroska_container_header' and len(result['streams'])==1
    assert result['streams'][0]['codec_type']=='video'


@pytest.mark.parametrize('kind,encoding',[(1,elem(0x5034)),(2,elem(0x5034)),
    (17,integer(0x5032,0)+elem(0x5034)),(17,integer(0x5032,2)+elem(0x5034)),
    (17,integer(0x5032,4)+elem(0x5034)),(17,integer(0x5033,1)+elem(0x5034)),
    (17,elem(0x5034,integer(0x4254,3))),(17,elem(0x5034,integer(0x4254,1))),
    (17,elem(0x5034,elem(0x4255,b'x'))),(17,elem(0x5034)+elem(0x5035)),
    (17,b''),(17,elem(0x5034)+integer(0x5031,0)+integer(0x5031,0)),
    (17,elem(0x5034,elem(0x4256)))])
def test_other_content_encoding_combinations_remain_unsupported(kind,encoding):
    encoded=elem(0xae,integer(0xd7,2)+integer(0x83,kind)+elem(0x6d80,elem(0x6240,encoding)))
    source=Sparse(metadata=info()+elem(mkv.TRACKS,track()+encoded))
    with pytest.raises(mkv.UnsupportedLayout) as raised:mkv.inspect_headers(source.budget(),1)
    assert raised.value.element_id==0x6d80


@pytest.mark.parametrize('fault',['cancel','io','deadline','bytes','requests'])
def test_terminal_failures_never_fallback_or_leave_lane_owned(monkeypatch,fault):
    source=Sparse()
    def forbidden(*args,**kwargs):pytest.fail('Terminal failure attempted ffprobe fallback')
    monkeypatch.setattr(media,'_probe',forbidden)
    cancelled=lambda: fault=='cancel'
    if fault=='io':
        def read(*args):raise media.ProbeError('EXACT_RANGE_UNAVAILABLE')
    else:read=source.read
    original=media.RangeBudget
    if fault in ('deadline','bytes','requests'):
        def budget(*args):
            value=original(*args)
            if fault=='deadline':value.started-=21
            if fault=='bytes':value.count=media.BYTE_BUDGET
            if fault=='requests':value.requests=32
            return value
        monkeypatch.setattr(media,'RangeBudget',budget)
    with pytest.raises(media.ProbeError):media.qualification_probe('binary',source.size,read,cancelled)
    assert media._LANE.acquire(blocking=False)
    media._LANE.release()


def test_advertised_uncovered_chapters_or_conflicting_info_never_qualify():
    for identifier in (mkv.INFO,mkv.TRACKS,mkv.CHAPTERS):
        seek=elem(mkv.SEEKHEAD,elem(0x4dbb,elem(0x53ab,identifier.to_bytes(4,'big'))+integer(0x53ac,999)))
        source=Sparse(metadata=seek+info()+elem(mkv.TRACKS,track()))
        with pytest.raises(mkv.UnsupportedLayout):mkv.inspect_headers(source.budget(),1)


def test_real_large_attachment_fixture_header_facts_match_actual_ffprobe(monkeypatch):
    import json,shutil,subprocess
    path=Path('D:/AM6B-Project/ce2029-results-20261021/independent-mkv-probe-budget-20261022/large_font.mkv')
    binary=shutil.which('ffprobe')
    if not path.is_file() or not binary:pytest.skip('Optional real local fixture/ffprobe unavailable')
    called=[]
    with path.open('rb') as stream:
        def read(start,end):
            called.append((start,end));stream.seek(start)
            remaining=end-start+1
            while remaining:
                chunk=stream.read(min(remaining,65536))
                if not chunk:return
                remaining-=len(chunk)
                yield chunk
        result=media.qualification_probe(binary,path.stat().st_size,read)
    actual=json.loads(subprocess.check_output([binary,'-v','error','-show_entries',
        'format=duration:stream=codec_type,codec_name,width,height','-of','json',str(path)],timeout=20))
    video=next(row for row in actual['streams'] if row['codec_type']=='video')
    assert result['method']=='matroska_container_header' and result['duration']==pytest.approx(float(actual['format']['duration']))
    assert result['streams'][0]==video and result['read_bytes']<65536
    assert all(end<520 or start>=19704872 for start,end in called)


def test_worker_injection_preserves_profile_and_direct_subtitle_paths():
    text=(ROOT/'addons/script.module.bobbi.core/lib/bobbi_core/preparation_host.py').read_text(encoding='utf-8')
    assert 'inspect=qualification_probe' in text
    assert "profile_qualifier = CloudQualifier(c['ffprobe'], c['cd2_endpoint'], c['download_capability'],\n                                          lambda: cancelled() or self.playing)" in text
    from bobbi_core.cloud_qualifier import CloudQualifier
    assert CloudQualifier.__init__.__defaults__[-1] is media.probe
    direct=(ROOT/'addons/script.module.bobbi.core/lib/bobbi_core/direct_cloud_io.py').read_text(encoding='utf-8')
    assert 'result = probe(self.qualifier.binary' in direct and 'qualification_probe' not in direct
