"""Setup first paint and the opt-in search report use real product entrypoints."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from test_onboarding import setup_ui
from bobbi_core import search_trace
from bobbi_core.search_completion import SearchCompletion
from bobbi_core.source_list_session import SourceListSession


def test_settings_first_menu_does_not_wait_for_optional_backend(setup_ui, monkeypatch):
    module = setup_ui.module
    monkeypatch.setattr(module, 'helper_status', lambda path: pytest.fail('network before first menu'))
    monkeypatch.setattr(module, 'probe', lambda *args: {'standard_playback': True})
    monkeypatch.setattr(module.xbmcgui, 'Dialog', lambda: setup_ui.dialog, raising=False)
    monkeypatch.setattr(sys, 'argv', ['default.py'])
    monkeypatch.setitem(sys.modules, 'bobbi_platform.library_ui', SimpleNamespace(
        registry=lambda *args: SimpleNamespace(sources=lambda: [], close=lambda: None)))
    setup_ui.choice = -1
    module.main()
    assert len(setup_ui.selections) == 1
    assert setup_ui.called == [] and setup_ui.builtins == []


def test_user_can_record_search_without_knowing_a_torrent_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(search_trace, '_sink', None)
    (tmp_path/'search-trace.json').write_text(json.dumps(dict(expires=time.time()+60, hashes=[])))
    search_trace.configure(tmp_path, 'a'*32)
    assert search_trace._sink is not None
    search_trace.observe('provider_return', [SimpleNamespace(title='PRIVATE', infoHash='f'*40)])
    row = json.loads(search_trace._sink.path.read_text())
    assert row['count'] == 1 and row['selected'] == []
    assert 'PRIVATE' not in search_trace._sink.path.read_text()


def test_disabling_recording_stops_an_already_running_search(tmp_path, monkeypatch):
    monkeypatch.setattr(search_trace, '_sink', None)
    marker = tmp_path/'search-trace.json'
    marker.write_text(json.dumps(dict(expires=time.time()+60, hashes=['f'*40])))
    search_trace.configure(tmp_path, 'a'*32)
    search_trace.observe('provider_return', [])
    before = search_trace._sink.path.read_bytes()
    marker.unlink()
    search_trace.observe('visible', [])
    assert search_trace._sink.path.read_bytes() == before


@pytest.fixture
def recording(tmp_path, monkeypatch):
    monkeypatch.setattr(search_trace, '_sink', None)
    search_trace.set_enabled(tmp_path, True)
    search_trace.configure(tmp_path, 'a'*32)
    return search_trace._sink


def test_existing_session_reports_receipts_without_changing_ownership(recording):
    session = SourceListSession({'id': 123}, lambda rows: rows)
    session.epoch = recording.invocation
    completion = SearchCompletion(planned=3, succeeded=1, timed_out=1, skipped=1,
                                  stale=1, truncated=1, snapshot_age=7200)
    assert session.publish(session.epoch, 'juku:1', [], state=completion.state, completion=completion)
    before = session.status()
    session.snapshot()
    report = search_trace.read_report(recording.path)
    assert session.status() == before and session.confirmed is None
    row = next(event for event in report['events'] if event['stage'] == 'providers')['providers'][0]
    assert row['completion']['timed_out'] == 1 and row['completion']['snapshot_age'] == 7200
    assert row['completion']['truncated'] == 1
    assert [event['stage'] for event in report['events']] == ['providers', 'session_pool', 'ranked', 'visible']


def test_late_session_cannot_append_to_another_report(recording):
    before = recording.path.read_bytes()
    search_trace.observe_providers('b'*32, {'juku': {'state': 'FAILED'}})
    search_trace.observe('processed', [], invocation='b'*32)
    assert recording.path.read_bytes() == before


def test_reenable_does_not_reactivate_previous_recorder(recording):
    search_trace.observe('processed', [])
    before = recording.path.read_bytes()
    search_trace.set_enabled(recording.path.parent, False)
    search_trace.set_enabled(recording.path.parent, True)
    recording.record('visible', [None])
    assert recording.path.read_bytes() == before


def test_cleanup_removes_only_owned_reports_and_never_recreates_them(recording):
    directory = recording.path.parent
    unrelated = directory/'account.json'
    unrelated.write_text('KEEP')
    search_trace.clear(directory)
    recording.record('visible', [])
    assert not recording.path.exists() and not search_trace.enabled(directory)
    assert unrelated.read_text() == 'KEEP'


def test_events_and_storage_are_bounded_and_report_incompleteness(recording):
    for count in range(150):
        search_trace.observe('processed', [None]*count)
    assert len(recording.path.read_text().splitlines()) == search_trace.MAX_EVENTS
    assert recording.path.stat().st_size <= search_trace.MAX_BYTES
    assert search_trace.read_report(recording.path)['incomplete']


def test_byte_limit_leaves_an_explicit_limit_event(recording):
    for count in range(125):
        search_trace.observe_providers(recording.invocation, {'juku:'+str(i): {
            'state': 'PARTIAL', 'count': count, 'completion': dict(planned=99, succeeded=22,
            failed=11, timed_out=33, skipped=33, stale=1, truncated=1, snapshot_age=7200)} for i in range(40)})
    assert recording.path.stat().st_size <= search_trace.MAX_BYTES
    assert len(recording.path.read_text().splitlines()) < search_trace.MAX_EVENTS
    assert search_trace.read_report(recording.path)['incomplete']


def test_report_slots_are_bounded_without_overwriting_old_records(tmp_path, monkeypatch):
    monkeypatch.setattr(search_trace, '_sink', None)
    search_trace.set_enabled(tmp_path, True)
    for index in range(12):
        search_trace.configure(tmp_path, format(index, '032x'))
    assert len(search_trace.reports(tmp_path)) == search_trace.MAX_REPORTS
    assert search_trace._sink is None
    with pytest.raises(ValueError, match='report limit'):
        search_trace.set_enabled(tmp_path, True)


def test_export_projection_ignores_injected_private_fields(tmp_path):
    secret = 'https://private.invalid/?token=SECRET'
    path = tmp_path/('search-trace-'+'a'*32+'.jsonl')
    events = [dict(stage='providers', url=secret, providers=[dict(provider=secret, ordinal=1,
        state='FAILED', error=secret, count=2, completion={'planned':1, 'url':secret})]),
        dict(stage='visible', state='', count=3, omitted=0, title=secret,
             selected=[dict(info_hash='f'*40, title=secret)]),
        dict(stage='invalid', data=secret), dict(stage='visible', state=[], count=0)]
    path.write_text('\n'.join(json.dumps(row) for row in events))
    report = search_trace.read_report(path)
    assert secret not in json.dumps(report) and 'f'*40 not in json.dumps(report)
    assert report['incomplete']
    assert report['events'][0]['providers'][0]['provider'] == 'other'


@pytest.mark.parametrize('expires', [float('inf'), float('nan'), -1, True, 10**400])
def test_invalid_or_expired_marker_never_records(tmp_path, monkeypatch, expires):
    monkeypatch.setattr(search_trace, '_sink', None)
    (tmp_path/'search-trace.json').write_text(json.dumps(dict(expires=expires, hashes=[])))
    search_trace.configure(tmp_path, 'a'*32)
    assert search_trace._sink is None and search_trace.reports(tmp_path) == []


def test_oversize_report_is_rejected_without_exporting_a_prefix(tmp_path):
    path = tmp_path/('search-trace-'+'a'*32+'.jsonl')
    path.write_bytes(b' '*(search_trace.MAX_BYTES+1))
    with pytest.raises(ValueError):
        search_trace.read_report(path)


def test_external_growth_cannot_append_beyond_byte_budget(recording):
    recording.path.write_bytes(b' ' * search_trace.MAX_BYTES)
    recording.record('processed', [])
    assert recording.path.stat().st_size == search_trace.MAX_BYTES
    assert recording.limited


def test_report_allocation_is_nonblocking_when_other_interpreter_owns_slot(tmp_path, monkeypatch):
    from bobbi_core.search_admission import try_acquire
    monkeypatch.setattr(search_trace, '_sink', None)
    search_trace.set_enabled(tmp_path, True)
    lease = try_acquire(tmp_path/'search-trace-lock')
    try:
        search_trace.configure(tmp_path, 'a'*32)
        assert search_trace._sink is None and search_trace.reports(tmp_path) == []
    finally:
        lease.release()


def test_recording_failure_never_changes_search_result(tmp_path, monkeypatch):
    monkeypatch.setattr(search_trace, '_sink', SimpleNamespace(invocation='a'*32,
        providers=lambda records: (_ for _ in ()).throw(OSError('private detail'))))
    session = SourceListSession({}, lambda rows: rows)
    session.epoch = 'a'*32
    assert session.publish(session.epoch, 'juku', state='FAILED', error='JukuError')
    assert session.status()['providers']['juku']['state'] == 'FAILED'


def test_direct_diagnostics_entry_survives_unreadable_general_configuration(setup_ui, monkeypatch):
    seen = []
    monkeypatch.setattr(setup_ui.module.xbmcgui, 'Dialog', lambda: setup_ui.dialog, raising=False)
    monkeypatch.setattr(setup_ui.module, 'load_config', lambda *args: pytest.fail('unrelated configuration loaded'))
    monkeypatch.setattr(sys, 'argv', ['default.py', 'diagnostics'])
    monkeypatch.setitem(sys.modules, 'bobbi_platform.diagnostics_ui', SimpleNamespace(show=seen.append))
    setup_ui.module.main()
    assert seen == [setup_ui.dialog] and setup_ui.called == []
