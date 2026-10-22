"""Real BT adapter and framebuffer reader, with bounded transport/filesystem IO."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from threading import Event
import time

import pytest

from test_bobbi_torrent_adapter import (Backend, BackendError, Resolver, Response,
    Session, Clock, FakeOwner, HASH, RID, config, request, status, failure_log)
from test_ce_ui_preview import p


@pytest.mark.parametrize('http_status', [200, 401, 403, 404, 409, 429, 500, 503])
def test_manual_confirmation_http_retains_phase_without_repeating_commands(http_status):
    clock = Clock()
    owner = FakeOwner(clock)
    choices = []
    owner.choose_file = lambda rows: choices.append(rows) or rows[0]
    # Valid work/episode binding; a weak romanized file needs manual confirmation.
    file = dict(id=1, path='Example - 01 [1080p].mkv', length=1000000)
    info = status(file)
    replies = [Response(b'MatriX.147'), Response({'hash': HASH}), Response(info),
               Response(info, http_status)]
    if http_status == 200:
        replies += [Response(b''), Response(info)]
    session = Session(replies)
    resolver = Resolver(Backend(config(), session, clock), owner, Session([]), clock)
    from bobbi_core.episode_identity import bind_selected_episode
    proof = bind_selected_episode({'tmdb_id': 12345}, {'season': 1, 'episode': 1}, HASH,
        mappings={'tmdb_show:12345:s1': {'anidb:999:R': {'1-13': '1-13'}}})
    selected = request(episode_binding=json.dumps(proof))
    if http_status == 200:
        result = resolver.resolve(selected)
        assert result['file_evidence'] == 'USER_CONFIRMED_FILE' and result['file'] == file
    else:
        with pytest.raises(BackendError) as failed:
            resolver.resolve(selected)
        assert failed.value.code == 'TORRENT_HTTP_REJECTED'
        detail = json.loads(failure_log(failed.value, RID).split(' detail=')[1])
        assert detail['http_status'] == http_status
        assert detail['operation'] == 'status' and detail['method'] == 'POST'
        assert detail['stage'] == 'selector' and detail['substage'] == 'manual_recheck'
        assert detail['request_id'] == RID and 'elapsed_ms' in detail and 'stage_ms' in detail
        assert not any('/stream' in call[1] for call in session.calls)
    assert len(choices) == 1 and not owner.targets
    assert sum(call[2].get('json', {}).get('action') == 'add' for call in session.calls) == 1


@pytest.mark.parametrize('bad', ['https://secret.invalid/?token=secret', {}, [], True, -1, 600])
def test_failure_log_rejects_unbounded_http_fields(bad):
    diagnostic = dict(operation=bad, method=bad, substage=bad, http_status=bad,
                      initial_http_status=bad, url='secret', body='secret')
    assert json.loads(failure_log(BackendError('TORRENT_HTTP_REJECTED', diagnostic=diagnostic))
                      .split(' detail=')[1]) == {}


@pytest.fixture
def framebuffer(tmp_path):
    root = tmp_path / 'fb'
    root.mkdir()
    for name, content in dict(stride='32', virtual_size='8,8', bits_per_pixel='32', pan='0,0').items():
        (root/name).write_text(content)
    device = tmp_path/'pixels'
    device.write_bytes(bytes(range(256)))
    return root, device


def test_valid_patch_records_exact_geometry(framebuffer):
    root, device = framebuffer
    result = p.framebuffer_patch(root, device, (2, 1, 3, 2))
    assert result['valid'] and result['reason'] == 'OK'
    assert result['expected_bytes'] == result['actual_bytes'] == 64
    assert result['expected_patch_bytes'] == result['actual_patch_bytes'] == 24
    assert p.patch_stability(result, [result]*10)['status'] == 'PASS'


@pytest.mark.parametrize('size', [0, 33, 95])
def test_empty_or_short_read_is_not_a_pixel_hash(framebuffer, size):
    root, device = framebuffer
    device.write_bytes(bytes(size))
    result = p.framebuffer_patch(root, device, (2, 1, 3, 2))
    assert result['valid'] is False and result['sha256'] is None
    assert result['reason'] == 'SHORT_READ' and result['actual_bytes'] < 64
    verdict = p.patch_stability(result, [result]*50)
    assert verdict['status'] == 'INCONCLUSIVE' and verdict['valid_samples'] == 0
    assert verdict['changed_samples'] == 0


@pytest.mark.parametrize('name,value,reason', [
    ('bits_per_pixel','16','UNSUPPORTED_FORMAT'), ('stride','4','INVALID_GEOMETRY'),
    ('virtual_size','2,8','INVALID_GEOMETRY'), ('pan','0,-1','INVALID_OFFSET'),
    ('pan','0,7','INVALID_OFFSET'), ('pan','1,0','INVALID_OFFSET')])
def test_framebuffer_geometry_errors_are_not_visual_changes(framebuffer, name, value, reason):
    root, device = framebuffer
    (root/name).write_text(value)
    sample = p.framebuffer_patch(root, device, (2, 1, 3, 2))
    assert not sample['valid'] and sample['sha256'] is None and sample['reason'] == reason


def test_pan_change_exhaustion_retains_invalid_samples(framebuffer):
    root, original = framebuffer
    class Device:
        def open(self, *args, **kwargs):
            pan = int((root/'pan').read_text().split(',')[1])
            (root/'pan').write_text('0,' + str(1-pan))
            return io.BytesIO(original.read_bytes())
    result = p.framebuffer_patch(root, Device(), (2, 1, 3, 2))
    assert result['reason'] == 'MOVING' and result['sha256'] is None
    assert result['pan_before'] != result['pan_after']


def test_invalid_and_insufficient_samples_cannot_pass(framebuffer):
    valid = p.framebuffer_patch(*framebuffer, box=(2, 1, 3, 2))
    invalid = dict(valid, valid=False, reason='SHORT_READ', sha256=None)
    assert p.patch_stability(valid, [valid]*9)['status'] == 'INCONCLUSIVE'
    result = p.patch_stability(valid, [valid]*49 + [invalid])
    assert result['status'] == 'INCONCLUSIVE' and result['invalid_samples'] == 1
    assert result['changed_samples'] == 0 and not result['passed']
    changed = dict(valid, sha256='f'*64)
    assert p.patch_stability(valid, [valid]*10 + [changed])['status'] == 'CHANGED'


def test_manual_dialog_longer_than_engine_idle_lease_keeps_same_torrent(monkeypatch):
    from bobbi_torrent import resolver as production
    monkeypatch.setattr(production, 'FILE_CHOICE_STATUS_SECONDS', .005)
    clock, ready = Clock(), Event()
    owner = FakeOwner(clock)
    class ExpiringBackend:
        expires = 30
        reads = 0
        def status(self, info_hash, deadline, active):
            active()
            assert info_hash == HASH
            assert clock.now < self.expires
            self.expires = clock.now + 30
            self.reads += 1
            if self.reads >= 5: ready.set()
            else: clock.now += 10
            return status()
    backend = ExpiringBackend()
    resolver = Resolver(backend, owner, Session([]), clock)
    def choose(rows):
        assert ready.wait(1)
        clock.now = 45  # Original 30-second lease would already be gone.
        return rows[0]
    file = status()['file_stats'][0]
    assert resolver.choose_with_status(choose, [file], HASH) == file
    before = backend.reads
    time.sleep(.02)
    assert backend.reads == before  # No detached refresher after dialog closes.
    assert backend.status(HASH, 47, owner.active)['hash'] == HASH
    assert not owner.targets and not owner.bindings


@pytest.mark.parametrize('result', ['http', 'cancel', 'superseded', 'back'])
def test_manual_wait_error_or_cancel_never_admits_stale_choice(monkeypatch, result):
    from bobbi_torrent import resolver as production
    monkeypatch.setattr(production, 'FILE_CHOICE_STATUS_SECONDS', .005)
    clock, observed = Clock(), Event()
    owner = FakeOwner(clock)
    reads = []
    class BackendDouble:
        def status(self, info_hash, deadline, active):
            reads.append(info_hash)
            observed.set()
            if result == 'http':
                raise BackendError('TORRENT_HTTP_REJECTED', diagnostic=dict(http_status=404,operation='status',method='POST'))
            if result == 'cancel': owner.cancel = True
            if result == 'superseded':
                owner.active = lambda: (_ for _ in ()).throw(BackendError('TORRENT_SUPERSEDED','superseded'))
            active()
            return status()
    resolver = Resolver(BackendDouble(), owner, Session([]), clock)
    def choose(rows):
        assert observed.wait(1)
        time.sleep(.02)
        return None if result == 'back' else rows[0]
    file = status()['file_stats'][0]
    if result == 'back':
        assert resolver.choose_with_status(choose,[file],HASH) is None
    else:
        with pytest.raises(BackendError) as error:
            resolver.choose_with_status(choose,[file],HASH)
        if result == 'http':
            assert error.value.diagnostic['substage'] == 'manual_wait'
            assert error.value.diagnostic['http_status'] == 404
        else: assert error.value.category == ('cancelled' if result == 'cancel' else result)
    before = len(reads)
    time.sleep(.02)
    assert len(reads) == before and set(reads) == {HASH}
