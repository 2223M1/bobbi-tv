"""Observed 4:3 BDRip must remain HD without weakening exact edition checks."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core.resolution import resolution_class
from bobbi_core.catalog_release import release_envelope


@pytest.mark.parametrize('geometry,quality', [('1440X1080',1080),('960x720',720),
    ('1920x1080',1080),('3840x2160',2160)])
def test_standard_landscape_geometries(geometry,quality):
    assert resolution_class('['+geometry+']') == quality


@pytest.mark.parametrize('geometry', ['1080x1440','720x960','1440x900','1080x1080',
    '1080p 960x720','2160p 1440x1080'])
def test_portrait_arbitrary_or_conflicting_dimensions_are_not_promoted(geometry):
    assert resolution_class('['+geometry+']') == 0


def test_observed_release_continues_only_with_same_full_edition():
    first='[philosophy-raws][Cowboy Bebop][01][BDRIP][Hi10P FLAC][1440X1080].mkv'
    following=first.replace('[01]','[02]')
    envelope=release_envelope(first,1,1)
    assert envelope is not None
    assert release_envelope(following,1,2)==envelope
    assert release_envelope(following,1,3) is None
    # Bare [02] gets its season from the independently bound catalog; the
    # resulting season-2 envelope must not equal season 1. Explicit S/E
    # conflicts are rejected rather than inferred from the filename.
    assert release_envelope(following,2,2) != envelope
    assert release_envelope(following.replace('[02]','[S02E02]'),1,2) is None
    for old,new in [('philosophy-raws','Other'),('1440X1080','960x720'),
                    ('FLAC','AAC'),('Hi10P','HEVC'),('.mkv','.mp4'),
                    ('BDRIP','BDRIP Extended')]:
        assert release_envelope(following.replace(old,new),1,2)!=envelope
