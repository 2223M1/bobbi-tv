"""Actual ledger/store/cache/preflight chain; partial is never full style proof."""
import json

import pytest

from bobbi_core.font_cache import FontCache
from bobbi_core.font_playback_preflight import FontPlaybackPreflight
from test_cinema_fonts import font
from test_subtitle_preparation import subject, finish, receipt_for
from test_subtitle_pack import matcher


@pytest.mark.parametrize('cancel', [False, True])
def test_partial_font_preflight_preserves_completeness_and_owner(subject, tmp_path, cancel):
    original, _ = finish(subject)
    receipt = receipt_for(subject)
    current = original['video']
    cache = FontCache(subject.queue.ledger, tmp_path/'font-cache', tmp_path/'native-fonts')
    subject.worker.store.font_cache = cache
    row = cache.import_font(font(), 'same_release_pack', current['release_key'])
    raw = ('[Script Info]\n[V4+ Styles]\nFormat: Name,Fontname,Bold,Italic\n'
           'Style: Default,Test Font,0,0\nStyle: Missing,Absent Family,0,0\n'
           '[Events]\nFormat: Start,End,Style,Text\n'
           'Dialogue: 0:00:01.00,0:00:04.00,Default,真实中文对白\n').encode()
    fonts = cache.bind(current['release_key'], raw, [row['sha256']])
    record = subject.worker.store.put(current, raw, '.ass', 'zh', True, False,
        dict(kind='provider', id='fixture:partial'), font_result=fonts)
    assert not record['fonts_ready']
    subject.worker._record(subject.rid, current['key'], record['state'], 1,
        dict(binding_key=record['key'], subtitle_sha256=record['subtitle_sha256']))
    body = dict(request_id=receipt['request_id'], resource_id=subject.rid,
        source_info_hash=current['selected']['source_info_hash'], file_identity=receipt['file_identity'],
        boot_id='e'*32, epoch=1)
    live = [True]
    def export(store, binding):
        assert store._read(binding) == raw
        return dict(path='/fixture/caption.ass', sha256=binding['subtitle_sha256'], bytes=len(raw))
    preflight = FontPlaybackPreflight(subject.worker, cache, lambda _: live[0], exporter=export)
    plan = preflight.plan(body)
    assert plan['state'] == 'planned'
    result = preflight.perform(plan)
    live[0] = not cancel
    applied = preflight.complete(plan, result)
    if cancel:
        assert applied['state'] == 'stale'
        assert not list(cache.native.iterdir())
        return
    assert applied['state'] == 'ready' and applied['font_inputs_complete'] is False
    assert applied['missing_font_count'] == 1
    assert cache.owns_activation(current['release_key'], record['subtitle_sha256'], body['request_id'], applied['font_hashes'])
    detail = json.loads(subject.queue.db.execute('SELECT detail FROM subtitle_preparation').fetchone()[0])
    assert detail['font_activation']['inputs_complete'] is False
    assert detail['font_activation']['missing_count'] == 1
    assert subject.worker.for_playback(receipt)['state'] == 'ready'
