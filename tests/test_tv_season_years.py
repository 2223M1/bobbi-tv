"""One checked season-date interpretation shared by the UI and preparation."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.catalog_identity import tv_season_years, prove_work
from bobbi_core.episode_identity import catalog_identity


def details(rows):
    return dict(id=42, name='Example Show', original_name='Example Show',
                first_air_date='2001-01-02', seasons=rows)


def test_cached_and_service_dates_share_one_checked_extractor():
    data = details([dict(season_number=1, air_date='2001-01-02'),
                    dict(season_number=2, air_date='2015-03-04')])
    assert tv_season_years(data, 42) == {1: 2001, 2: 2015}
    assert catalog_identity(data, 42)['season_years'] == tv_season_years(data, 42)
    assert tv_season_years(data, 99) == {}
    assert tv_season_years(dict(data, id=True), 1) == {}


@pytest.mark.parametrize('rows', [
    [dict(season_number=2, air_date='2015-99-99')],
    [dict(season_number=2, air_date='2015-02-29')],
    [dict(season_number=True, air_date='2015-03-04')],
    [dict(season_number=2, air_date='2015-03-04'), dict(season_number=2, air_date='2016-03-04')],
    [dict(season_number=2, air_date='2015-03-04')] * 101,
])
def test_malformed_or_ambiguous_season_dates_never_add_a_year(rows):
    assert tv_season_years(details(rows), 42) == {}


@pytest.mark.parametrize('year', [2001, 2015])
def test_same_work_show_and_target_season_years_are_both_valid(year):
    catalog = dict(provider='tmdb', id=42, kind='tv', aliases=['Example Show'], year=2001,
                   response_sha256='a' * 64, season_years={2: 2015, 3: 2018})
    media = dict(tmdb_id=42, kind='tv', season=2, episode=1)
    assert prove_work(media, 'Example.Show.%d.S02E01.mkv' % year, catalog)['release_year'] == year
    with pytest.raises(ValueError, match='year'):
        prove_work(media, 'Example.Show.2018.S02E01.mkv', catalog)
    with pytest.raises(ValueError, match='year'):
        prove_work(dict(media, kind='movie'), 'Example.Show.2015.mkv', dict(catalog, kind='movie'))
