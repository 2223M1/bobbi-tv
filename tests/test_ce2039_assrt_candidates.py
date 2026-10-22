"""Offline production API/traversal/bytes tests for two bounded ASSRT failures."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import subtitle_candidates as subtitles


CONTEXT = dict(mode='series', title='Audit Show', season=1, episode=1,
               duration=300, release='Audit.Show.S01E01.1080p.BluRay.GROUP')
INCOMPLETE = dict(id=100001, native_name='Audit Show', subtype='Subrip(srt)')
EXACT = dict(INCOMPLETE, native_name='Audit Show S01E01',
             lang={'langlist': {'langchs': True, 'langdou': True}})
RAW = '1\n00:00:01,000 --> 00:00:03,000\n中文对白\nEnglish dialogue\n'.encode('utf-8')


def ok(rows):
    return {'status': 0, 'sub': {'subs': rows}}


def detail(ident):
    return ok([dict(EXACT, id=ident, videoname=CONTEXT['release'], filelist=[
        {'f': 'Audit.Show.S01E01.chs.eng.srt', 'url': 'https://assrt.net/offline/{}.srt'.format(ident)}])])


@pytest.fixture
def probe(tmp_path):
    def make(searches, details=None, body=RAW, on_call=None):
        calls, now, cancelled = [], [0.0], [False]
        answers = iter(searches)
        def transport(url, deadline, cancel, limit, **kwargs):
            assert 0 < deadline <= 30
            parsed = urlsplit(url)
            if parsed.netloc == 'api.assrt.net':
                operation = parsed.path.rsplit('/', 1)[-1]
                params = parse_qs(parsed.query)
                if operation == 'search':
                    call = ('search', params['q'][0])
                    answer = next(answers)  # Any extra search is a failed test.
                elif operation == 'detail':
                    ident = int(params['id'][0])
                    call = ('detail', ident)
                    answer = (details or {}).get(ident, detail(ident))
                else:
                    pytest.fail('Unexpected API operation')
                calls.append(call)
                if on_call:
                    on_call(call, now, cancelled)
                return json.dumps(answer).encode('utf-8')
            assert parsed.netloc == 'assrt.net' and parsed.path.startswith('/offline/')
            calls.append(('download', None))
            return body
        provider = subtitles.AssrtCandidates(None, tmp_path/'state',
            clock=lambda: now[0], wall=lambda: 1000, transport=transport)
        # Synthetic in-memory placeholder: no credential file or network access.
        provider.token_file = SimpleNamespace(read_text=lambda: '0' * 32)
        return SimpleNamespace(provider=provider, calls=calls, now=now, cancelled=cancelled,
            run=lambda: provider.candidates(CONTEXT, 30, lambda: cancelled[0], tmp_path/'texts'))
    return make


def test_existing_incomplete_row_survives_later_search_unavailable(probe):
    p = probe([ok([INCOMPLETE]), {'status': 30002}])
    result = p.run()
    assert result['origin'] == 'assrt:100001' and result['bilingual'] is True
    assert result['state'] == 'candidate'
    assert [call[0] for call in p.calls] == ['search', 'search', 'detail', 'download']
    assert p.calls[2] == ('detail', 100001)
    assert p.provider.events == [dict(stage='search', reason='ASSRT_API_30002', candidate=None)]


def test_missing_detail_only_skips_that_id(probe):
    p = probe([ok([EXACT, dict(EXACT, id=100002)])], {100001: {'status': 20900}})
    result = p.run()
    assert result['origin'] == 'assrt:100002' and result['bilingual'] is True
    assert [call[0] for call in p.calls] == ['search', 'detail', 'detail', 'download']
    assert p.provider.events == [dict(stage='detail', reason='ASSRT_API_20900', candidate='100001')]


@pytest.mark.parametrize('first', [None, [], [dict(INCOMPLETE, native_name='Different Work')],
                                  [dict(INCOMPLETE, subtype='pgs')]])
def test_unavailable_search_without_admitted_rows_stays_unavailable(probe, first):
    p = probe(([] if first is None else [ok(first)]) + [{'status': 30002}])
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_API_30002$'):
        p.run()
    assert all(call[0] == 'search' for call in p.calls)
    assert len(p.calls) == (1 if first is None else 2)


@pytest.mark.parametrize('body', [b'<html>not a subtitle</html>',
    b'1\n00:00:01,000 --> 00:00:03,000\nEnglish only\n'])
def test_unavailable_search_is_not_relabelled_when_retained_row_body_fails(probe, body):
    p = probe([ok([INCOMPLETE]), {'status': 30002}], body=body)
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_API_30002$'):
        p.run()
    assert [call[0] for call in p.calls] == ['search', 'search', 'detail', 'download']
    assert p.provider.events[0]['reason'] == 'ASSRT_API_30002'


@pytest.mark.parametrize('stage', ['search', 'detail'])
@pytest.mark.parametrize('code', [20001, 30900])
def test_authentication_and_quota_still_stop_traversal(probe, stage, code):
    p = (probe([ok([INCOMPLETE]), {'status': code}]) if stage == 'search' else
         probe([ok([EXACT, dict(EXACT, id=100002)])], {100001: {'status': code}}))
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_API_{}$'.format(code)):
        p.run()
    assert len(p.calls) == 2
    assert not any(call == ('detail', 100002) or call[0] == 'download' for call in p.calls)


@pytest.mark.parametrize('stage', ['search', 'detail'])
@pytest.mark.parametrize('stop', ['cancel', 'deadline'])
def test_cancellation_and_deadline_win_over_recoverable_provider_errors(probe, stage, stop):
    def on_call(call, now, cancelled):
        target = call[0] == 'detail' if stage == 'detail' else call == ('search', 'Audit Show S01')
        if target:
            if stop == 'cancel':
                cancelled[0] = True
            else:
                now[0] = 30
    p = (probe([ok([INCOMPLETE]), {'status': 30002}], on_call=on_call) if stage == 'search' else
         probe([ok([EXACT, dict(EXACT, id=100002)])], {100001: {'status': 20900}}, on_call=on_call))
    with pytest.raises(subtitles.LookupStopped, match='^CANCELLED_OR_DEADLINE$'):
        p.run()
    assert len(p.calls) == 2
    assert all(call[0] != 'download' for call in p.calls)


def test_successful_empty_search_still_uses_only_three_queries(probe):
    p = probe([ok({}), ok({}), ok({})])
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run()
    assert len(p.calls) == 3 and p.provider.events == []


def test_missing_candidates_do_not_expand_six_detail_limit(probe):
    rows = [dict(EXACT, id=100001 + index) for index in range(12)]
    p = probe([ok(rows)], {row['id']: {'status': 20900} for row in rows})
    with pytest.raises(subtitles.LookupStopped, match='^MATCHED_SUBTITLE_UNAVAILABLE$'):
        p.run()
    assert len([call for call in p.calls if call[0] == 'detail']) == 6
    assert len(p.calls) == 7
    assert len(p.provider.load('quota.json', [])) == 7


def test_retained_metadata_does_not_bypass_final_episode_identity(probe):
    wrong = detail(100001)
    wrong['sub']['subs'][0]['filelist'][0]['f'] = 'Audit.Show.S01E02.chs.eng.srt'
    p = probe([ok([INCOMPLETE]), {'status': 30002}], {100001: wrong})
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_API_30002$'):
        p.run()
    assert [call[0] for call in p.calls] == ['search', 'search', 'detail']


@pytest.mark.parametrize('reason', ['ASSRT_API_20900', 'ASSRT_API_30002'])
def test_only_fixed_provider_reasons_are_public(reason):
    assert subtitles.public_failure_reason(subtitles.LookupStopped(reason)) == reason
    assert subtitles.public_failure_reason(subtitles.LookupStopped(reason + '_private')) == 'LookupStopped'
