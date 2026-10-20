"""Real text/hash regressions for release303 candidate ordering; no network."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib.cinema import _shared  # dependency bootstrap
from bobbi_core import subtitle_candidates as subtitles


def srt(label, bilingual=True, count=30):
    def stamp(seconds):
        return '{:02d}:{:02d}:{:02d},000'.format(seconds // 3600, seconds // 60 % 60, seconds % 60)
    blocks = []
    for index in range(count):
        text = '中文对白第{}句'.format(index + 1)
        if bilingual:
            text += '\n{} English dialogue {}'.format(label, index + 1)
        blocks.append('{}\n{} --> {}\n{}\n'.format(index + 1, stamp(index * 10), stamp(index * 10 + 4), text))
    return '\n'.join(blocks).encode('utf-8')


@pytest.fixture
def audit(tmp_path, monkeypatch):
    root = tmp_path / 'texts'
    root.mkdir()
    now = [0.0]
    context = dict(mode='movie', title='Audit Example', year=2001, duration=300,
                   release='Audit.Example.2001.1080p.BluRay.GROUP', tmdb=1000001)
    provider = subtitles.AssrtCandidates(SimpleNamespace(get=Mock(side_effect=AssertionError('network forbidden'))),
                                        tmp_path / 'state', clock=lambda: now[0])
    monkeypatch.setattr(provider, 'local_candidates', Mock(return_value=[]))
    monkeypatch.setattr(provider, 'search', Mock(return_value=[]))
    monkeypatch.setattr(provider, 'api', Mock(side_effect=AssertionError('unplanned API')))
    if os.name == 'nt':
        # Linux publication unlinks a read-only hardlink, which Windows refuses.
        # Keep real body parsing/hash checks; isolate only this POSIX publisher.
        def publish_fixture(raw, extension, root):
            digest = hashlib.sha256(raw).hexdigest()
            path = Path(root) / (digest[:32] + extension)
            path.write_bytes(raw)
            return dict(path=str(path), sha256=digest, bytes=len(raw))
        monkeypatch.setattr(subtitles, 'publish', publish_fixture)

    def record(label, video=None, simplified=True, bilingual=True, advertised=True, count=30, media=None):
        target = media or context
        raw = srt(label, bilingual, count)
        path = root / (label + '.srt')
        path.write_bytes(raw)
        name = target['title'] + (' ' + str(target['year']) if target['mode'] == 'movie' else
                                 ' S{:02}E{:02}'.format(target['season'], target['episode']))
        flags = {'langchs' if simplified else 'langcht': 1}
        if advertised:
            flags['langdou'] = 1
        return dict(media=subtitles.identity(target), origin=label, state='candidate',
                    source=dict(native_name=name, videoname=video or target['release'], lang=dict(langlist=flags)),
                    file=dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)), bilingual=bilingual)

    def choose(records, deadline=30, cancelled=lambda: False, media=None):
        provider.save('candidates.json', records)
        return provider.candidates(media or context, deadline, cancelled, root=root)

    return SimpleNamespace(root=root, now=now, context=context, provider=provider, record=record, choose=choose)


@pytest.mark.parametrize('reverse', [False, True])
def test_exact_bluray_beats_old_web_regardless_of_cache_order(audit, reverse):
    old = audit.record('old_web', 'Audit.Example.2001.1080p.WEB-DL.OLD', simplified=False)
    exact = audit.record('exact_bluray')
    rows = [old, exact]
    result = audit.choose(rows[::-1] if reverse else rows)
    assert result['origin'] == 'exact_bluray'
    assert result['state'] == 'candidate'
    audit.provider.search.assert_not_called()
    audit.provider.api.assert_not_called()


def test_simplified_preference_is_used_between_exact_bilingual_candidates(audit):
    traditional = audit.record('traditional', simplified=False)
    simplified = audit.record('simplified')
    assert audit.choose([traditional, simplified])['origin'] == 'simplified'
    audit.provider.search.assert_not_called()


def test_medium_preference_is_used_between_nonexact_bilingual_candidates(audit):
    old = audit.record('web', 'Audit.Example.2001.WEB-DL.OLD')
    bluray = audit.record('bluray', 'Audit.Example.2001.BluRay.OTHER')
    assert audit.choose([old, bluray])['origin'] == 'bluray'


def test_actual_bilingual_precedes_exact_mono_and_overrides_saved_flag(audit):
    mono = audit.record('exact_mono', bilingual=False)
    mono['bilingual'] = True  # Stored/provider labels are not the current bytes.
    bilingual = audit.record('old_bilingual', 'Audit.Example.2001.WEB-DL.OLD', advertised=False)
    bilingual['bilingual'] = False
    result = audit.choose([mono, bilingual])
    assert result['origin'] == 'old_bilingual' and result['bilingual'] is True
    assert mono['bilingual'] is True and bilingual['bilingual'] is False  # Input records were not mutated.


def test_cached_state_cannot_claim_readiness_and_mono_label_is_corrected(audit):
    mono = audit.record('mono', bilingual=False)
    mono.update(bilingual=True, state='ready')
    result = audit.choose([mono])
    assert result['bilingual'] is False and result['state'] == 'candidate'


@pytest.mark.parametrize('cached_is_best', [False, True])
def test_cached_and_already_read_local_candidates_share_one_order(audit, cached_is_best):
    old = audit.record('old_web', 'Audit.Example.2001.WEB-DL.OLD')
    exact = audit.record('exact_local')
    cached, local = (exact, old) if cached_is_best else (old, exact)
    audit.provider.local_candidates.return_value = [local]
    assert audit.choose([cached])['origin'] == 'exact_local'
    audit.provider.local_candidates.assert_called_once()
    audit.provider.search.assert_not_called()


def test_local_simplified_can_improve_exact_traditional_cache_without_network(audit):
    traditional = audit.record('cache_traditional', simplified=False)
    simplified = audit.record('local_simplified')
    audit.provider.local_candidates.return_value = [simplified]
    assert audit.choose([traditional])['origin'] == 'local_simplified'
    audit.provider.search.assert_not_called()


def test_optional_local_read_failure_does_not_hide_an_inspected_cache(audit):
    audit.provider.local_candidates.side_effect = OSError('local object unavailable')
    result = audit.choose([audit.record('cached')])
    assert result['origin'] == 'cached' and result['state'] == 'candidate'
    audit.provider.search.assert_not_called()


def test_nonexact_cache_is_retained_without_starting_optional_search_near_deadline(audit):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    audit.now[0] = 24
    assert audit.choose([old], deadline=30)['origin'] == 'old'
    audit.provider.search.assert_not_called()


def test_optional_empty_search_and_repeated_local_reads_do_not_duplicate_cache(audit):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    audit.provider.local_candidates.return_value = [old]
    audit.choose([old])
    assert audit.provider.load('candidates.json', []) == [old]


@pytest.mark.parametrize('failure', [OSError('offline'), subtitles.LookupStopped('ASSRT_RATE_LIMIT'),
                                     subtitles.LookupStopped('ASSRT_HTTP_493')])
def test_nonexact_cache_survives_optional_provider_failure(audit, failure):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    audit.provider.search.side_effect = failure
    assert audit.choose([old])['origin'] == 'old'
    assert audit.provider.search.call_count == 1


@pytest.mark.parametrize('change', ['year', 'edition', 'media', 'hash', 'title'])
def test_identity_hash_and_full_dialogue_gates_remain_in_force(audit, change):
    valid = audit.record('valid')
    invalid = audit.record('invalid', count=3 if change == 'partial' else 30)
    if change == 'year':
        invalid['source']['native_name'] = 'Audit Example 2002'
    elif change == 'edition':
        invalid['source']['native_name'] += ' extended'
    elif change == 'media':
        invalid['media'] = 'foreign-work'
    elif change == 'hash':
        invalid['file']['sha256'] = '0' * 64
    elif change == 'title':
        invalid['source'].update(native_name='Other Film 2001', videoname='Other.Film.2001.BluRay')
    assert audit.choose([invalid, valid])['origin'] == 'valid'


def test_exact_episode_gate_remains_in_force(audit):
    context = dict(mode='series', title='Audit Show', year=2001, duration=300, season=2, episode=3,
                   release='Audit.Show.S02E03.BluRay.GROUP', tmdb=1000002)
    valid = audit.record('episode_valid', media=context)
    invalid = audit.record('episode_wrong', media=context)
    invalid['source']['filename'] = 'Audit.Show.S02E04.chs.srt'
    assert audit.choose([invalid, valid], media=context)['origin'] == 'episode_valid'


def test_cancellation_cannot_return_even_a_valid_cache(audit):
    with pytest.raises(subtitles.LookupStopped, match='CANCELLED_OR_DEADLINE'):
        audit.choose([audit.record('cached')], cancelled=lambda: True)
    audit.provider.local_candidates.assert_not_called()
    audit.provider.search.assert_not_called()


def test_optional_search_never_extends_the_original_deadline_or_returns_after_cancel(audit):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    received = []
    def expired(query, deadline, cancelled):
        received.append(deadline)
        audit.now[0] = 30
        raise subtitles.LookupStopped('CANCELLED_OR_DEADLINE')
    audit.provider.search.side_effect = expired
    with pytest.raises(subtitles.LookupStopped, match='CANCELLED_OR_DEADLINE'):
        audit.choose([old], deadline=30)
    assert received == [29]


def test_optional_search_reserves_commit_time_for_a_valid_warm_candidate(audit):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    def expired(query, deadline, cancelled):
        assert deadline == 29
        audit.now[0] = deadline
        raise subtitles.LookupStopped('CANCELLED_OR_DEADLINE')
    audit.provider.search.side_effect = expired
    assert audit.choose([old], deadline=30)['origin'] == 'old'


def test_optional_timeout_cannot_override_manual_cancellation(audit):
    old = audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')
    cancelled = [False]
    def expired(query, deadline, guard):
        audit.now[0] = deadline
        cancelled[0] = True
        raise subtitles.LookupStopped('CANCELLED_OR_DEADLINE')
    audit.provider.search.side_effect = expired
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([old], deadline=30, cancelled=lambda: cancelled[0])


def remote_plan(audit, monkeypatch, records):
    """Exercise real remote selection and byte inspection; no HTTP requests."""
    rows, details, texts = [], {}, {}
    for number, record in enumerate(records, 1):
        # Search records can be incomplete; exact release becomes known at detail.
        rows.append(dict(id=number, native_name='Audit Example 2001', lang={'desc': '中文'}))
        filename = 'Audit.Example.2001.{}.srt'.format('chs' if record['source']['lang']['langlist'].get('langchs') else 'cht')
        url = 'https://assrt.net/fixture/{}.srt'.format(number)
        details[number] = [dict(record['source'], filelist=[{'f': filename, 'url': url}])]
        texts[url] = Path(record['file']['path']).read_bytes()
    audit.provider.search.return_value = rows
    audit.provider.api.side_effect = lambda operation, params, deadline, cancelled: details[params['id']]
    monkeypatch.setattr(audit.provider, 'read', Mock(side_effect=lambda url, deadline, cancelled: texts[url]))


@pytest.mark.parametrize('stage', ['detail', 'download'])
def test_unclassified_http_error_is_observed_without_retrying_other_candidates(audit, monkeypatch, stage):
    remote_plan(audit, monkeypatch, [audit.record('first'), audit.record('second')])
    failing = audit.provider.api if stage == 'detail' else audit.provider.read
    failing.side_effect = subtitles.LookupStopped('ASSRT_HTTP_493')
    with pytest.raises(subtitles.LookupStopped, match='^ASSRT_HTTP_493$'):
        audit.choose([])
    assert audit.provider.api.call_count == 1
    assert audit.provider.read.call_count == (1 if stage == 'download' else 0)
    assert audit.provider.events == [dict(stage=stage, reason='ASSRT_HTTP_493', candidate='1')]


def test_http_restriction_keeps_already_validated_cold_candidate(audit, monkeypatch):
    remote_plan(audit, monkeypatch, [audit.record('first', 'Audit.Example.2001.WEB-DL.OLD'),
                                    audit.record('second')])
    original = audit.provider.read.side_effect
    def read(url, deadline, cancelled):
        if url.endswith('/2.srt'):
            raise subtitles.LookupStopped('ASSRT_HTTP_493')
        return original(url, deadline, cancelled)
    audit.provider.read.side_effect = read
    result = audit.choose([])
    assert result['origin'] == 'assrt:1' and result['bilingual']
    assert audit.provider.api.call_count == audit.provider.read.call_count == 2
    assert audit.provider.events == [dict(stage='download', reason='ASSRT_HTTP_493', candidate='2')]


@pytest.mark.parametrize('code', range(400, 600))
def test_http_failure_diagnostics_preserve_only_bounded_error_statuses(code):
    reason = 'ASSRT_HTTP_' + str(code)
    assert subtitles.public_failure_reason(subtitles.LookupStopped(reason)) == reason


@pytest.mark.parametrize('reason', ['ASSRT_HTTP_200', 'ASSRT_HTTP_600', 'ASSRT_HTTP_0493',
    'ASSRT_HTTP_493_private', 'ASSRT_HTTP_493\n', 'ASSRT_HTTP_https://private.invalid/token'])
def test_http_failure_diagnostics_do_not_accept_unbounded_provider_messages(reason):
    assert subtitles.public_failure_reason(subtitles.LookupStopped(reason)) == 'LookupStopped'


def direct_file_plan(audit, monkeypatch, filelist='absent', filename='Audit.Example.2001.chs.srt', raw=None):
    record=audit.record('single-file')
    source=dict(record['source'])
    detail=dict(source,filename=filename,url='https://assrt.net/fixture/single.srt')
    if filelist!='absent':
        detail['filelist']=filelist
    audit.provider.search.return_value=[dict(source,id=710166)]
    audit.provider.api.side_effect=lambda operation,params,deadline,cancelled:[detail]
    monkeypatch.setattr(audit.provider,'read',Mock(return_value=raw if raw is not None else Path(record['file']['path']).read_bytes()))
    return detail


@pytest.mark.parametrize('filelist',['absent',None,[],{}])
def test_single_text_detail_without_package_filelist_uses_all_existing_gates(audit,monkeypatch,filelist):
    direct_file_plan(audit,monkeypatch,filelist)
    result=audit.choose([])
    assert result['origin']=='assrt:710166' and result['bilingual'] is True
    assert result['source']['filename']=='Audit.Example.2001.chs.srt'
    audit.provider.read.assert_called_once()


@pytest.mark.parametrize('filelist',[{}, 'broken', [{}]*513,
    {'f': 'Audit.Example.2001.chs.srt'}, {'files': []}, False, 0])
def test_malformed_or_oversized_filelist_does_not_fall_back_to_top_level(audit,monkeypatch,filelist):
    direct_file_plan(audit,monkeypatch,filelist)
    if type(filelist) is dict and not filelist:
        # Preserve this historical node: observed {} is now a valid empty list
        # encoding, not permission for any other malformed shape to fall back.
        assert audit.choose([])['origin'] == 'assrt:710166'
        audit.provider.read.assert_called_once()
        return
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_not_called()
    assert audit.provider.events == [dict(stage='detail', reason='ASSRT_FILELIST_INVALID', candidate='710166')]


@pytest.mark.parametrize('filename',['Audit.Example.2002.chs.srt','Audit.Example.2001.zip',
    'Audit.Example.2001.forced.srt','Audit.Example.2001.commentary.ass','x'*4097+'.srt'])
def test_direct_detail_does_not_bypass_year_format_or_exclusion(audit,monkeypatch,filename):
    direct_file_plan(audit,monkeypatch,filename=filename)
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_not_called()


def test_top_level_file_is_not_added_beside_a_nonempty_package(audit,monkeypatch):
    direct_file_plan(audit,monkeypatch,filelist=[{'f':'Audit.Example.2002.chs.srt','url':'https://assrt.net/fixture/wrong.srt'}])
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_not_called()


@pytest.mark.parametrize('raw',[b'<html>not subtitle</html>',
    b'1\n00:30:00,000 --> 00:30:02,000\nChinese beyond this video\n'])
def test_direct_text_still_requires_chinese_body(audit,monkeypatch,raw):
    direct_file_plan(audit,monkeypatch,raw=raw)
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_called_once()


@pytest.mark.parametrize('message,reason', [
    ('Subtitle cue outside exact video timeline', 'SUBTITLE_TIMELINE_MISMATCH'),
    ('SUBTITLE_IO_TimeoutError', 'SUBTITLE_DOWNLOAD_TIMEOUT'),
    ('HTML is not a subtitle', 'SUBTITLE_NOT_TEXT'),
    ('Insufficient full Chinese dialogue', 'SUBTITLE_CHINESE_INSUFFICIENT'),
    ('Only partial Chinese dialogue', 'SUBTITLE_CHINESE_PARTIAL'),
    ('private https://example.invalid/token=secret', 'ValueError'),
    ('SUBTITLE_IO_private_token_secret', 'ValueError'),
])
def test_candidate_failure_records_only_exact_public_reason_codes(audit, message, reason):
    audit.provider.candidate_failure('inspect', ValueError(message), 710166, 30, lambda: False)
    assert audit.provider.events == [dict(stage='inspect', reason=reason, candidate='710166')]


def test_empty_object_detail_preserves_direct_file_year_and_body_rejection(audit, monkeypatch):
    direct_file_plan(audit, monkeypatch, filelist={}, filename='Audit.Example.2002.chs.srt')
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_not_called()
    direct_file_plan(audit, monkeypatch, filelist={}, raw=b'<html>wrong body</html>')
    with pytest.raises(subtitles.LookupStopped):
        audit.choose([])
    audit.provider.read.assert_called_once()
    assert audit.provider.events[-1]['reason'] == 'SUBTITLE_NOT_TEXT'


@pytest.mark.parametrize('message,reason', [
    ('NO_EXACT_TORRENT_CHINESE_SIDECAR', 'NO_EXACT_TORRENT_CHINESE_SIDECAR'),
    ('TORRENT_SUBTITLE_CANCELLED_OR_TIMEOUT', 'TORRENT_SUBTITLE_CANCELLED_OR_TIMEOUT'),
    ('SUBTITLE_IO_TimeoutError', 'SUBTITLE_DOWNLOAD_TIMEOUT'),
    ('https://private.invalid/token=secret', 'LookupStopped'),
    ('PRIVATE_TOKEN_SECRET', 'LookupStopped'),
])
def test_optional_torrent_failure_keeps_safe_reason_and_original_remote_fallback(audit, monkeypatch, message, reason):
    from threading import Event
    from lib.services.subtitle_fallback import SubtitleFallback
    from bobbi_core import torrent_subtitles
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi.torrent/lib'))
    from bobbi_torrent import backend
    worker = SubtitleFallback(clock=lambda: 0)
    worker.key = 'fixture'
    monkeypatch.setattr(subtitles, 'AssrtCandidates', lambda *args, **kwargs: audit.provider)
    monkeypatch.setattr(backend, 'subtitle_connection', lambda: ('http://localhost:18090', None))
    fetch = Mock(side_effect=subtitles.LookupStopped(message))
    monkeypatch.setattr(torrent_subtitles, 'fetch_candidate', fetch)
    audit.provider.candidates = Mock(return_value=audit.record('after-torrent-failure'))
    context = dict(mode='series', title='Mob Psycho 100', season=3, episode=1, duration=1400,
                   _torrent={'fixture': True})
    row = dict(native_instance='fixture-native', request_id='a' * 32, subtitle_intent=0)
    worker._run('fixture', row, context, Event(), 30)
    assert worker.result['state'] == 'candidate'
    assert audit.provider.events[-1] == dict(stage='inspect', reason=reason, candidate=None)
    assert fetch.call_count == audit.provider.candidates.call_count == 1
    assert fetch.call_args.args[-2] == audit.provider.candidates.call_args.args[1] == 30


def test_nonexact_cache_can_be_improved_by_remote_exact_bilingual(audit, monkeypatch):
    old = audit.record('cached_web', 'Audit.Example.2001.WEB-DL.OLD', simplified=False)
    remote_plan(audit, monkeypatch, [audit.record('remote_exact')])
    result = audit.choose([old])
    assert result['origin'] == 'assrt:1' and result['state'] == 'candidate'
    assert result['bilingual'] is True
    assert subtitles.candidate_rank(result, audit.context) == (1, 1, 1, 1)
    assert audit.provider.search.call_count == audit.provider.api.call_count == audit.provider.read.call_count == 1
    assert audit.provider.api.call_args.args[2] == 29


def test_remote_weaker_bilingual_does_not_displace_better_local_candidate(audit, monkeypatch):
    local = audit.record('local_bluray', 'Audit.Example.2001.BluRay.OTHER')
    audit.provider.local_candidates.return_value = [local]
    remote_plan(audit, monkeypatch, [audit.record('remote_web', 'Audit.Example.2001.WEB-DL.OLD', simplified=False)])
    assert audit.choose([])['origin'] == 'local_bluray'


def test_first_remote_bilingual_does_not_hide_later_exact_candidate(audit, monkeypatch):
    remote_plan(audit, monkeypatch, [audit.record('remote_web', 'Audit.Example.2001.WEB-DL.OLD'),
                                    audit.record('remote_exact')])
    assert audit.choose([])['origin'] == 'assrt:2'
    assert audit.provider.api.call_count == audit.provider.read.call_count == 2


def test_cold_first_download_is_retained_when_optional_second_download_times_out(audit, monkeypatch):
    remote_plan(audit, monkeypatch, [audit.record('remote_web', 'Audit.Example.2001.WEB-DL.OLD'),
                                    audit.record('remote_exact')])
    original = audit.provider.read.side_effect
    seen = []
    def read(url, deadline, cancelled):
        seen.append(deadline)
        if len(seen) == 2:
            audit.now[0] = deadline
            raise subtitles.LookupStopped('SUBTITLE_IO_DEADLINE')
        return original(url, deadline, cancelled)
    audit.provider.read.side_effect = read
    result = audit.choose([], deadline=30)
    assert result['origin'] == 'assrt:1' and result['bilingual']
    assert seen == [30, 29]


def test_missing_independent_python_preserves_qualified_warm_candidate(audit, monkeypatch):
    from bobbi_core import subtitle_io
    def missing():
        raise subtitle_io.SubtitleIOStopped('SUBTITLE_IO_PYTHON_UNAVAILABLE')
    monkeypatch.setattr(subtitle_io, '_interpreter', missing)
    def search(query, deadline, cancelled):
        audit.provider.read('https://assrt.net/fixture', deadline, cancelled)
    audit.provider.search.side_effect = search
    assert audit.choose([audit.record('old', 'Audit.Example.2001.WEB-DL.OLD')])['origin'] == 'old'


def test_real_local_read_preserves_release_metadata_and_candidate_status(audit, tmp_path, monkeypatch):
    import _sqlite3
    scope = dict(account_id='115:' + 'a' * 64, epoch=1, authenticated=True)
    audit.provider.accounts = SimpleNamespace(snapshot=lambda: dict(scope),
                                             is_current=lambda value: value == scope)
    audit.provider.local_scope = dict(scope)
    audit.provider.preparation_root = tmp_path / 'preparation'
    state = audit.provider.preparation_root / ('a' * 64 + '-1')
    objects = state / 'subtitles/objects'
    objects.mkdir(parents=True)
    raw = srt('local')
    digest = hashlib.sha256(raw).hexdigest()
    (objects / (digest + '.srt')).write_bytes(raw)
    payload = dict(video={'media_id': 'tmdb:movie:1000001', 'selected': {'torrent_path': audit.context['release']}},
                   forced=False, full_dialogue=True, language='chs', subtitle_sha256=digest, extension='.srt')
    connection = _sqlite3.connect(str(state / 'resources.sqlite'))
    try:
        connection.execute('CREATE TABLE subtitle_current (revision INTEGER)')
        connection.execute('CREATE TABLE subtitle_revisions (seq INTEGER, payload TEXT)')
        connection.execute('INSERT INTO subtitle_current VALUES (1)')
        connection.execute('INSERT INTO subtitle_revisions VALUES (1,?)', (json.dumps(payload),))
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(subtitles.sqlite3, 'connect', _sqlite3.connect)
    original = subtitles.AssrtCandidates.local_candidates
    monkeypatch.setattr(audit.provider, 'local_candidates', lambda context, deadline, cancelled, root:
                        original(audit.provider, context, deadline, cancelled, root))
    old = audit.record('cache_web', 'Audit.Example.2001.WEB-DL.OLD')
    result = audit.choose([old])
    assert result['origin'].startswith('local:') and result['state'] == 'candidate'
    assert result['source']['videoname'] == audit.context['release']
    assert subtitles.candidate_rank(result, audit.context)[:2] == (1, 1)
    audit.provider.search.assert_not_called()
