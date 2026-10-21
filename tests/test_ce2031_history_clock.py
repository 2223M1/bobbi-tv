"""History order must not depend on the embedded host's locale/_strptime."""
import ast
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
import unicodedata
import pytest

ROOT=Path(__file__).resolve().parents[1]


def subject(unavailable=True):
    tree=ast.parse((ROOT/'addons/plugin.video.bobbi/lib/utils/general/utils.py').read_text(encoding='utf-8'))
    node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='parse_time')
    class EmbeddedDateTime(datetime):
        @classmethod
        def strptime(cls,*args):
            if unavailable:raise ValueError('embedded locale unavailable')
            return datetime.strptime(*args)
    env=dict(datetime=EmbeddedDateTime,parsedate_to_datetime=parsedate_to_datetime,
        re=re,unicodedata=unicodedata,kodilog=lambda _:None)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'production-history-time','exec'),env)
    return lambda value:env['parse_time'](('',{'timestamp':value}))


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
