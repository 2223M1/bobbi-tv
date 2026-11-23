"""History order must not depend on the embedded host's locale/_strptime."""
from datetime import datetime
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


def subject(unavailable=True):
    spec=importlib.util.spec_from_file_location('clock_contract', ROOT/'addons/plugin.video.bobbi/lib/cinema/frontend_contract.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class EmbeddedDateTime(datetime):
        @classmethod
        def strptime(cls,*args):
            if unavailable:raise ValueError('embedded locale unavailable')
            return datetime.strptime(*args)
    module.datetime=EmbeddedDateTime
    return lambda value:module.parse_time(('',{'timestamp':value}))


@pytest.mark.parametrize('unavailable',[False,True])
@pytest.mark.parametrize('time,hour',[('07:43 PM',19),('07:43 AM',7),('12:43 PM',12),('12:43 AM',0)])
def test_legacy_ampm_preserved_without_locale(unavailable,time,hour):
    assert subject(unavailable)('Wed, 21 Oct 2026 '+time)==datetime(2026,10,21,hour,43)


def test_real_evening_trials_sort_after_morning_record_without_mutation():
    parse=subject()
    rows=['Wed, 21 Oct 2026 11:05 AM','Wed, 21 Oct 2026 07:33 PM','Wed, 21 Oct 2026 07:43 PM']
    original=list(rows)
    assert sorted(rows,key=parse,reverse=True)==list(reversed(rows))
    assert rows==original


def test_spanish_nfkc_legacy_and_rfc_remain_supported():
    parse=subject()
    assert parse('mié, 21 oct 2026 07:43 p. m.')==datetime(2026,10,21,19,43)
    assert parse('Wed, 21 Oct 2026 19:43:00 +0800')==datetime(2026,10,21,19,43)


@pytest.mark.parametrize('value',[None,'','not a date','Wed, 31 Feb 2026 07:43 PM',
                                  'Wed, 21 Oct 2026 13:43 PM'])
def test_invalid_dates_fail_closed_not_misordered(value):
    assert subject()(value)==datetime.min
