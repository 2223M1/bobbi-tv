import pytest
from test_ce_trace_signal_diagnostics import functions


def test_trial_identity_is_verified_before_any_gui_command():
    ns=functions('checked_trial_metadata')
    test=dict(title='A Place Further Than the Universe',tmdb_id=76059,kind='tv',year=2018,animation=True)
    actual=dict(id=76059,name='A Place Further than the Universe',original_name='宇宙よりも遠い場所',
                original_language='ja',first_air_date='2018-01-02',genres=[{'id':16}])
    assert ns['checked_trial_metadata'](test,actual)['original_language']=='ja'
    for wrong in (dict(actual,id=76013),dict(actual,name='NFL Football Fanatic'),
                  dict(actual,first_air_date='2017-01-01'),dict(actual,genres=[])):
        with pytest.raises(AssertionError):ns['checked_trial_metadata'](test,wrong)
    # The historical incorrect ID is not rescued by an unrelated cached English name.
    with pytest.raises(AssertionError,match='TITLE_MISMATCH'):
        ns['checked_trial_metadata'](dict(test,tmdb_id=76013),dict(actual,id=76013,name='NFL Football Fanatic'))


def test_diacritics_are_display_variations_not_a_different_work():
    ns=functions('checked_trial_metadata')
    assert ns['checked_trial_metadata'](dict(title='Amelie',kind='movie',tmdb_id=194,year=2001),
        dict(title='Amélie',id=194,release_date='2001-04-25'))['id']==194
