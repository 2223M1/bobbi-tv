"""Candidate failure state is traversal-local, not inferred from diagnostics."""
from copy import deepcopy

import pytest

from test_ce2039_assrt_candidates import probe, ok, EXACT, INCOMPLETE, detail, subtitles


@pytest.mark.parametrize('stage,reason,ident', [
    ('inspect', 'NO_EXACT_TORRENT_CHINESE_SIDECAR', None),
    ('inspect', 'TORRENT_SUBTITLE_INCOMPLETE', None),
    ('search', 'ASSRT_API_30002', None),
    ('detail', 'ASSRT_API_20900', 100001),
    ('download', 'ASSRT_HTTP_404', 100001),
    ('inspect', 'SUBTITLE_NOT_TEXT', 100001),
])
def test_prior_diagnostic_does_not_create_a_current_matched_candidate(probe, stage, reason, ident):
    p = probe([ok({}), ok({}), ok({})])
    p.provider.note(stage, reason, ident)
    before = deepcopy(p.provider.events)
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run()
    assert len(p.calls) == 3 and all(call[0] == 'search' for call in p.calls)
    assert p.provider.events == before


@pytest.mark.parametrize('shape', ['empty', 'unrelated', 'image_only', 'empty_detail',
                                  'wrong_detail', 'wrong_episode_file'])
def test_inspect_note_does_not_turn_rejected_metadata_into_download_failure(probe, shape):
    searches, details = [ok([EXACT])], None
    if shape == 'empty':
        searches = [ok({})]*3
    elif shape == 'unrelated':
        searches = [ok([dict(EXACT, native_name='Different Work S01E01')])]*3
    elif shape == 'image_only':
        searches = [ok([dict(EXACT, subtype='pgs')])]
    elif shape == 'empty_detail':
        details = {EXACT['id']: ok([])}
    else:
        answer = detail(EXACT['id'])
        if shape == 'wrong_detail':
            answer['sub']['subs'][0].update(native_name='Different Work S02E02', videoname='')
        else:
            answer['sub']['subs'][0]['filelist'][0]['f'] = 'Audit.Show.S01E02.chs.eng.srt'
        details = {EXACT['id']: answer}
    p = probe(searches, details)
    p.provider.note('inspect', 'NO_EXACT_TORRENT_CHINESE_SIDECAR')
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run()
    assert not any(call[0] == 'download' for call in p.calls)


@pytest.mark.parametrize('failure', ['missing_detail', 'invalid_detail', 'invalid_filelist', 'invalid_body', 'download'])
def test_current_admitted_candidate_failure_is_unavailable_even_without_event_storage(probe, monkeypatch, failure):
    details, body = None, b'<html>not text</html>'
    if failure == 'missing_detail':
        details = {EXACT['id']: {'status': 20900}}
    elif failure == 'invalid_detail':
        details = {EXACT['id']: ok({})}  # {} is accepted only for successful search, not detail.
    elif failure == 'invalid_filelist':
        answer = detail(EXACT['id'])
        answer['sub']['subs'][0]['filelist'] = {'not': 'a file list'}
        details = {EXACT['id']: answer}
    p = probe([ok([EXACT])], details, body=body)
    # Diagnostics can be redirected or truncated without becoming authority.
    monkeypatch.setattr(p.provider, 'note', lambda *args: None)
    if failure == 'download':
        original = p.provider.read
        def broken(url, *args, **kwargs):
            if url.startswith('https://assrt.net/offline/'):
                raise subtitles.LookupStopped('ASSRT_HTTP_404')
            return original(url, *args, **kwargs)
        monkeypatch.setattr(p.provider, 'read', broken)
    with pytest.raises(subtitles.LookupStopped, match='^MATCHED_SUBTITLE_UNAVAILABLE$'):
        p.run()
    assert p.provider.events == []


def test_reused_provider_does_not_reuse_previous_candidate_failure(probe, monkeypatch):
    p = probe([ok([EXACT])], body=b'<html>not text</html>')
    with pytest.raises(subtitles.LookupStopped, match='^MATCHED_SUBTITLE_UNAVAILABLE$'):
        p.run()
    before, calls = deepcopy(p.provider.events), []
    def empty_search(query, deadline, cancelled):
        calls.append(query)
        assert deadline == 30
        return []
    monkeypatch.setattr(p.provider, 'search', empty_search)
    with pytest.raises(subtitles.LookupStopped, match='^NO_MATCHED_CHINESE_TEXT$'):
        p.run()
    assert len(calls) == 3 and p.provider.events == before


@pytest.mark.parametrize('stop', ['provider', 'cancel', 'deadline'])
def test_original_provider_and_cancellation_failures_take_priority(probe, stop):
    def on_call(call, now, cancelled):
        if call == ('search', 'Audit Show S01'):
            if stop == 'cancel':
                cancelled[0] = True
            elif stop == 'deadline':
                now[0] = 30
    p = probe([ok([INCOMPLETE]), {'status': 30002}], body=b'<html>not text</html>', on_call=on_call)
    p.provider.note('inspect', 'NO_EXACT_TORRENT_CHINESE_SIDECAR')
    reason = 'ASSRT_API_30002' if stop == 'provider' else 'CANCELLED_OR_DEADLINE'
    with pytest.raises(subtitles.LookupStopped, match='^'+reason+'$'):
        p.run()
    assert len(p.calls) == (4 if stop == 'provider' else 2)


def test_successful_candidate_after_inspect_note_remains_usable(probe):
    p = probe([ok([EXACT])])
    p.provider.note('inspect', 'NO_EXACT_TORRENT_CHINESE_SIDECAR')
    assert p.run()['origin'] == 'assrt:100001'
    assert [call[0] for call in p.calls] == ['search', 'detail', 'download']
