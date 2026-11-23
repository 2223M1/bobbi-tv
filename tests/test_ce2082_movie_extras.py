"""Observed extras-only release must not masquerade as a feature film."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.candidate_titles import matches
from bobbi_core.movie_release_kind import conflict


def test_dotted_extras_only_release_is_not_the_film():
    title = 'Source.Code.2011.EXTRAS.1080p.BluRay.H264-RMXTRAS'
    assert conflict(title, ['Source Code', '源代码']) == 'extras_only'
    assert not matches(title, ['Source Code'], 'movies')


def test_extras_title_and_mixed_or_unknown_contents_remain_candidates():
    for title, aliases in [
        ('Extras.2005.1080p.BluRay.H264-GROUP', ['Extras']),
        ('Source.Code.2011.Movie+Extras.1080p.BluRay.H264-GROUP', ['Source Code']),
        ('Source.Code.2011.EXTRAS.The.Other.Movie.1080p.BluRay', ['Source Code']),
        ('Source.Code.2011.1080p.BluRay.H264-GROUP', ['Source Code']),
        ('Source.Code.2011.EXTRAS.Unknown.Cut.1080p.BluRay', ['Source Code']),
    ]:
        assert conflict(title, aliases) == '', title
