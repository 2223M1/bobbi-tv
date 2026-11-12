"""Display labels preserve scan claims without changing resolution ranking."""
from types import SimpleNamespace

import pytest

from lib.gui.source_select import SourceSelect, _quality_key, _quality_tabs, _source_quality
from lib.utils.general import source_resolution as resolution
from lib.utils.general.cinema_source_rank import source_preference
from bobbi_core.ledger import encode


def source(title, quality=''):
    return SimpleNamespace(title=title,quality=quality,type='Direct',size=1024,indexer='115 · CD2',
        url='/storage/file.mkv',guid='bobi:test',preparedResourceId='resource',preparedVersionKey='version',
        preparedInfoHash='hash',catalogIdentity=None)


@pytest.mark.parametrize('title,label', [
    ('Galactic.Heroes.S01E01.1080i.mkv','1080i'),('Film.1080p.mkv','1080p'),
    ('Film.[1080I].mkv','1080i'),('Film.1920x1080.mkv','1080'),
    ('Film.1440×1080.mkv','1080'),('Film.3840x2160.mkv','4K'),
    ('Film.1080i.1080p.mkv','1080'),('Film.1080i.720p.mkv','未知'),
    ('Film.1080i.1280x720.mkv','未知'),('Film.x1080i2.mkv','未知')])
def test_reason_and_picker_share_scan_preserving_display(title,label):
    item=source(title)
    assert resolution.source_resolution_label(item)==label
    assert _source_quality(item)==label
    reason=source_preference(item)['reason']
    if label!='未知':assert label in reason
    if label!='1080p':assert '1080p' not in reason


@pytest.mark.parametrize('title,label', [('Film.1080i.mkv','1080i'),('Film.1920x1080.mkv','1080'),
    ('Film.1080i.1080p.mkv','1080'),('Film.1080i.720p.mkv','未知'),('opaque.mkv','未知')])
def test_precomputed_progressive_quality_does_not_override_filename_or_unknown_scan(title,label):
    assert _source_quality(source(title,'[B][COLOR blue]1080p[/COLOR][/B]'))==label


def prepared(title,width=1920,height=1080):
    item=source(title)
    item.catalogIdentity={'mode':'movies','tmdb_id':1}
    profile=dict(schema=1,video=dict(codec='h264',width=width,height=height,pixel_format='yuv420p',
        transfer='not_reported',primaries='not_reported',frame_rate=[25,1]),
        main_audio=dict(codec='aac',sample_rate=48000,channels=2,layout='stereo',bits=0,language='ja'),
        commentary_count=0,streams_sha256='a'*64)
    item.preparedMediaProfile=resolution._PreparedMediaProfile(resolution._source_binding(item),encode(profile))
    return item


@pytest.mark.parametrize('title,label', [('Film.mkv','1080'),('Film.1080i.mkv','1080i'),
    ('Film.1080p.mkv','1080p'),('Film.720p.mkv','1080'),('Film.1080p.1080i.mkv','1080')])
def test_exact_prepared_dimensions_do_not_prove_progressive_scan(title,label):
    item=prepared(title)
    facts=resolution.source_resolution(item)
    assert facts.resolution==1080 and facts.measured=='已备探测1920×1080'
    assert resolution.source_resolution_label(item,facts)==_source_quality(item)==label
    if title=='Film.720p.mkv':assert facts.caution=='分辨率标记冲突'


def test_scan_labels_do_not_modify_the_numeric_sort_key_or_source_metadata():
    keys=[]
    for title in ('Film.1080i.mkv','Film.1080p.mkv','Film.1920x1080.mkv'):
        item=source(title);before=dict(vars(item))
        result=source_preference(item);_source_quality(item)
        keys.append(result['key'])
        assert vars(item)==before
    assert keys[0]==keys[1]==keys[2]
    assert keys[0][4]==1080


@pytest.mark.parametrize('label,key', [
    ('1080i','1080p'),('1080p','1080p'),('1080','1080p'),
    ('[B]1080I[/B]','1080p'),('720i','720p'),('720p','720p'),('720','720p'),
    ('2160i','4k'),('2160p','4k'),('2160','4k'),('4K','4k'),
    ('未知','n/a'),('1080i 1080p','n/a'),('x1080i2','n/a')])
def test_resolution_buckets_keep_stable_keys_independent_of_scan_display(label,key):
    assert _quality_key(label)==key


def test_neutral_bucket_labels_counts_and_filter_preserve_source_order():
    sources=[source('Film.'+title+'.mkv','1080p') for title in (
        '1080i','1080p','1920x1080','1080i.1080p','720p','1280x720','3840x2160','opaque')]
    assert _quality_tabs(sources)==[
        ('全部','__all__',8),('4K','4k',1),('1080','1080p',4),('720','720p',2),('其他','n/a',1)]
    window=SourceSelect.__new__(SourceSelect)
    window.sources=sources
    assert window._apply_source_filter('quality_tab','1080p')==sources[:4]
    assert window._apply_source_filter('quality_tab','720p')==sources[4:6]
    assert window._apply_source_filter('quality_tab','4k')==sources[6:7]
    assert window._apply_source_filter('quality_tab','n/a')==sources[7:]
