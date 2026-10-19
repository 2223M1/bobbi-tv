"""Content-first subtitles: no timeline/font admission or repeated auto apply."""
import json
from pathlib import Path

import pytest

from bobbi_core.subtitle_binding import binding
from bobbi_core.subtitle_candidates import identity, inspect_text
from test_subtitle_binding import video
from test_subtitle_preparation import subject, finish, receipt_for
from test_subtitle_pack import matcher
from test_subtitle_external_owner import setup


@pytest.mark.parametrize('duration', [None, 0, 60, 7200])
def test_sparse_shifted_chinese_is_valid_without_video_timeline(duration):
    raw = '1\r\n00:30:00,000 --> 00:30:03,000\r\n安静电影只有少量对白\r\n'.encode('gb18030')
    output, bilingual = inspect_text(raw, '.srt', duration)
    assert output == raw and bilingual is False


def test_unknown_video_duration_does_not_hide_exact_episode_subtitles():
    context = dict(title='Example Show', mode='series', season=2, episode=3)
    assert identity(context) == identity(dict(context, duration=0))
    with pytest.raises(ValueError, match='episode'):
        identity(dict(context, episode=None))


def test_ass_animated_font_keeps_original_styles_without_font_gate():
    raw = ('[Script Info]\n[V4+ Styles]\nFormat: Name,Fontname,Bold,Italic\n'
           'Style: Default,Absent Font,0,0\n[Events]\nFormat: Start,End,Style,Text\n'
           'Dialogue: 0:30:01.00,0:30:03.00,Default,{\\t(\\fnOther Font)}中文字幕\n').encode('utf-8')
    assert inspect_text(raw, '.ass', 60)[0] == raw
    record = binding(video(), raw, '.ass', 'zh', True, False,
                     dict(kind='provider', id='fixture:1'))
    assert record['state'] == 'READY_NOT_VISUAL_PROOF'
    assert record['fonts_ready'] is False and record['timing'] is None


def downgrade(subject):
    finish(subject)
    row = subject.queue.db.execute('SELECT seq,payload FROM subtitle_revisions').fetchone()
    old = json.loads(row['payload'])
    old.update(schema=1, state='CANDIDATE_NOT_READY', chinese_ready=False)
    old['content'].pop('chinese_cues', None)
    subject.queue.db.execute('UPDATE subtitle_revisions SET payload=? WHERE seq=?',
                            (json.dumps(old), row['seq']))
    subject.queue.db.execute("UPDATE subtitle_preparation SET state='CANDIDATE_NOT_READY'")
    return old


def test_old_immutable_subtitle_migrates_without_cloud_or_video_read(subject):
    downgrade(subject)
    before = len(subject.reads)
    subject.provider.offline_tasks = lambda _: pytest.fail('Migration must not read cloud')
    plan = subject.worker.next_action()
    assert plan['kind'] == 'content_policy_migration'
    assert subject.worker.complete(plan, subject.worker.perform(plan))
    record = subject.worker.store.records(plan['video'], 0, ready_only=True)[0]
    assert record['schema'] == 2 and record['state'] == 'READY_NOT_VISUAL_PROOF'
    assert len(subject.reads) == before
    assert subject.worker.for_playback(receipt_for(subject))['state'] == 'ready'
    assert subject.worker.next_action() is None


def test_manual_revision_during_migration_is_not_overwritten(subject):
    old = downgrade(subject)
    plan = subject.worker.next_action()
    result = subject.worker.perform(plan)
    subject.worker.store.put(old['video'], subject.raw, old['extension'], old['language'],
        old['full_dialogue'], old['forced'], old['origin'], timing=old['timing'], manual_intent=1)
    assert subject.worker.complete(plan, result)
    assert subject.worker.store.records(old['video'])[0]['manual_intent'] == 1


def test_failed_old_migration_cannot_schedule_retry_over_manual_revision(subject):
    old = downgrade(subject)
    plan = subject.worker.next_action()
    subject.worker.store.put(old['video'], subject.raw, old['extension'], old['language'],
        old['full_dialogue'], old['forced'], old['origin'], timing=old['timing'], manual_intent=1)
    before = tuple(subject.queue.db.execute('SELECT * FROM subtitle_preparation').fetchone())
    assert subject.worker.complete(plan, dict(state='RETRY', reason='OLD_READ_FAILED'))
    assert tuple(subject.queue.db.execute('SELECT * FROM subtitle_preparation').fetchone()) == before
    assert subject.worker.next_action() is None


def test_unqualified_video_during_migration_is_terminal_not_a_retry_loop(subject, monkeypatch):
    downgrade(subject)
    plan = subject.worker.next_action()
    result = subject.worker.perform(plan)
    def changed(*_):
        raise ValueError('qualified file changed')
    monkeypatch.setattr('bobbi_core.subtitle_preparation.prepared_video', changed)
    assert subject.worker.complete(plan, result)
    assert subject.queue.db.execute('SELECT state FROM subtitle_preparation').fetchone()[0] == 'REJECTED_IDENTITY'
    assert subject.worker.next_action() is None


@pytest.mark.parametrize('legacy', [False, True])
def test_failed_local_export_retries_without_cloud_read(subject, monkeypatch, legacy):
    if legacy:
        downgrade(subject)
    from bobbi_core import subtitle_export
    original = subtitle_export.export
    def unavailable(*_, **__):
        raise OSError('native directory temporarily unavailable')
    monkeypatch.setattr(subtitle_export, 'export', unavailable)
    plan = subject.worker.next_action()
    assert subject.worker.complete(plan, subject.worker.perform(plan))
    assert subject.queue.db.execute('SELECT state FROM subtitle_preparation').fetchone()[0] == 'EXPORT_RETRY'
    assert subject.worker.for_playback(receipt_for(subject))['state'] == 'pending'
    assert subject.worker.next_action() is None  # Backoff is enforced.
    subject.queue.db.execute('UPDATE subtitle_preparation SET next_attempt=0')
    subject.provider.offline_tasks = lambda _: pytest.fail('Export retry must not read cloud')
    monkeypatch.setattr(subtitle_export, 'export', original)
    retry = subject.worker.next_action()
    assert retry['record']['schema'] == 2
    assert subject.worker.complete(retry, subject.worker.perform(retry))
    assert subject.worker.for_playback(receipt_for(subject))['state'] == 'ready'
    assert subject.worker.next_action() is None


def test_local_export_failure_is_bounded_and_preserves_immutable_object(subject, monkeypatch):
    from bobbi_core import subtitle_export
    def unavailable(*_, **__):
        raise OSError('native directory unavailable')
    monkeypatch.setattr(subtitle_export, 'export', unavailable)
    for attempt in range(1, 4):
        subject.queue.db.execute('UPDATE subtitle_preparation SET next_attempt=0')
        plan = subject.worker.next_action()
        assert plan['attempts'] == attempt
        assert subject.worker.complete(plan, subject.worker.perform(plan))
    assert subject.queue.db.execute('SELECT state FROM subtitle_preparation').fetchone()[0] == 'READ_UNAVAILABLE'
    assert subject.worker.next_action() is None
    assert subject.worker.store._read(plan['record']) == subject.raw


def test_different_late_candidate_never_queues_second_automatic_load():
    owner, native, args, catalog, candidate, message = setup()
    assert owner.dispatch(message)['status'] == 'QUEUED'
    candidate['file'].update(sha256='c' * 64,
        path=str(Path(candidate['file']['path']).with_name('c' * 32 + '.srt')))
    assert owner.dispatch(message)['status'] == 'QUEUED'
    assert len(native.commands) == 1


def test_confirmed_embedded_chinese_never_starts_later_external_search():
    owner, native, args, catalog, candidate, message = setup()
    catalog.update(streams=[dict(index=1, language='zho', stream_key='c' * 64)],
                   current_index=1, visible=True)
    assert owner.dispatch(message)['status'] == 'CONFIRMED'
    catalog['streams'] = []
    native.external_subtitle = lambda _: pytest.fail('Do not replace confirmed Chinese')
    assert owner.dispatch(message)['status'] == 'CONFIRMED'
    native.current['subtitle_intent'] = catalog['receipt']['subtitle_intent'] = 1
    assert owner.dispatch(message)['status'] == 'MANUAL_PRESERVED'


@pytest.mark.parametrize('initial', ['pending', 'unavailable'])
def test_foreign_only_early_catalog_does_not_latch_missing_chinese(initial):
    owner, native, args, catalog, candidate, message = setup()
    native.external_subtitle = lambda _: dict(state=initial, reason='NO_MATCHED_CHINESE_TEXT')
    assert owner.dispatch(message)['status'] in ('SUBTITLE_PREPARING', 'NO_QUALIFIED_CHINESE_SUBTITLE')
    assert owner.subtitle_completed is None and owner.subtitle_pending is None
    cancelled = []
    native.cancel_external_subtitle_lookup = lambda: cancelled.append(True)
    catalog['streams'].append(dict(index=1, language='zho', stream_key='c' * 64))
    assert owner.dispatch(message)['status'] == 'QUEUED'
    assert len(native.commands) == 1 and native.commands[0]['index'] == 1
    assert cancelled == [True]


def test_manual_hide_while_external_lookup_pending_prevents_late_embedded_apply():
    owner, native, args, catalog, candidate, message = setup()
    native.external_subtitle = lambda _: dict(state='pending')
    assert owner.dispatch(message)['status'] == 'SUBTITLE_PREPARING'
    catalog['streams'].append(dict(index=1, language='zho', stream_key='c' * 64))
    native.current['subtitle_intent'] = catalog['receipt']['subtitle_intent'] = 1
    assert owner.dispatch(message)['status'] == 'MANUAL_PRESERVED'
    assert native.commands == []


def test_timing_observer_failure_cannot_fail_prepared_video():
    from bobbi_core.runtime_measurement import measured
    class Work:
        def observer(self, _):
            raise RuntimeError('optional log sink failed')
        @measured('resolve')
        def execute(self, value):
            return dict(state='ready')
    assert Work().execute(dict(request_id='a' * 32)) == dict(state='ready')


def test_production_preserves_cached_fonts_and_idle_extraction_without_hot_refresh():
    root = Path(__file__).resolve().parents[2]
    player = (root / 'addons/plugin.video.bobbi/lib/native_player.py').read_text(encoding='utf-8')
    service = (root / 'addons/script.module.bobbi.core/lib/bobbi_core/preparation_host.py').read_text(encoding='utf-8')
    assert 'prepare_fonts(' in player
    assert 'FontPreflightLane' in service and 'SubtitleFontPreparation' in service
    import ast
    tree = ast.parse(service)
    session = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Session')
    tick = next(n for n in session.body if isinstance(n, ast.FunctionDef) and n.name == 'tick')
    # Subtitle/font extraction is lexically inside the idle-only branch; the
    # local preflight lane remains available before creating the AV renderer.
    idle = [n for n in ast.walk(tick) if isinstance(n, ast.If)
            and ast.dump(n.test) == ast.dump(ast.UnaryOp(op=ast.Not(), operand=ast.Attribute(
                value=ast.Name(id='self', ctx=ast.Load()), attr='playing', ctx=ast.Load())))]
    assert any("subtitle_fonts" in ast.dump(n) and "font_work" in ast.dump(n) for n in idle)
    assert 'lambda: self.lease.valid() and not self.playing' in service
    assert 'ReloadSkin' not in service and 'Bobi.Fonts' not in service
