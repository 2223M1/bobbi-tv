"""Stage 4B regression suite: R16 AV_START diagnostics proof, R17/REV-01 404 absence cache, and RB-05 release gate evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib', 'tests'):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from bobbi_platform import online_components as components, online_updates as online, optimization
from bobbi_platform.host import Host
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import signing
from test_online_components import assets, canonical, network
from test_online_updates import offer_for

GATE_SPEC = importlib.util.spec_from_file_location('ce_release_gate_s4b', ROOT / 'tools/ce_release_gate.py')
gate = importlib.util.module_from_spec(GATE_SPEC)
GATE_SPEC.loader.exec_module(gate)


def test_rev01_feed_schema_stays_strict_and_404_absence_skips_warm_reprobe(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path / 'one.zip', signing)
    _, blobs = assets(path)
    base_offer = offer_for(path.read_bytes())

    # REV-01: stable/preview current.json schema must NOT accept extra fields like transport_mode
    mutated_offer = dict(base_offer, transport_mode='bundle-only')
    with pytest.raises(UpdateError, match='ONLINE_OFFER_INVALID'):
        online.parse_offer(json.dumps(mutated_offer))

    # Seed warm component cache first
    calls = network(monkeypatch, blobs)
    work = tmp_path / 'work'
    components.download(base_offer, work, signing[1]).unlink()
    assert (work / 'components-v1').is_dir()

    # Remove .components-v1.zip to model a 2-asset GitHub release (404 on metadata)
    blobs.pop('BobbiTV-CE2054.components-v1.zip')
    calls.clear()

    # Warm attempt #1: probes .components-v1.zip once, gets 404, records absence, falls back to full
    r1 = {}
    out1 = components.download(base_offer, work, signing[1], report=r1)
    assert out1.read_bytes() == path.read_bytes()
    out1.unlink()
    assert calls == ['BobbiTV-CE2054.components-v1.zip', 'BobbiTV-CE2054.bobbi-update.zip']
    assert r1['mode'] == 'full-fallback'
    assert (work / components.ABSENCE_FILE).is_file()

    # Warm attempt #2 (same mirror, tag, sha256 within TTL): skips .components-v1.zip completely!
    calls.clear()
    r2 = {}
    out2 = components.download(base_offer, work, signing[1], report=r2)
    assert out2.read_bytes() == path.read_bytes()
    out2.unlink()
    assert calls == ['BobbiTV-CE2054.bobbi-update.zip']
    assert r2['mode'] == 'full'
    assert r2.get('components_absent_cached') is True

    # Changing sha256 or tag or expiring TTL invalidates the cached absence and probes again!
    assert components._is_known_absent(work, dict(base_offer, sha256='f' * 64)) is False
    assert components._is_known_absent(work, dict(base_offer, tag='ce2055')) is False
    future_now = components.time.time() + components.ABSENCE_TTL + 5
    assert components._is_known_absent(work, base_offer, clock=lambda: future_now) is False


@pytest.mark.parametrize('transient_code', [401, 403, 429, 500, 502, 503])
def test_non_404_http_errors_and_corrupt_metadata_are_never_cached_as_absent(
    tmp_path, signing, monkeypatch, transient_code
):
    path = canonical(tmp_path / 'one.zip', signing)
    _, blobs = assets(path)
    base_offer = offer_for(path.read_bytes())
    calls = network(monkeypatch, blobs)
    work = tmp_path / 'work'
    components.download(base_offer, work, signing[1]).unlink()

    blobs['BobbiTV-CE2054.components-v1.zip'] = HTTPError(
        'https://github.com/test/BobbiTV-CE2054.components-v1.zip',
        transient_code,
        'transient',
        {},
        None,
    )
    calls.clear()
    r1 = {}
    components.download(base_offer, work, signing[1], report=r1).unlink()
    assert r1['mode'] == 'full-fallback'
    assert components._is_known_absent(work, base_offer) is False

    # Next warm download still probes .components-v1.zip because transient errors are not cached
    calls.clear()
    components.download(base_offer, work, signing[1]).unlink()
    assert calls[0] == 'BobbiTV-CE2054.components-v1.zip'


def test_absence_cache_is_bounded_to_max_entries(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    for idx in range(25):
        fake_offer = {
            'url': f'https://mirror-{idx}.example/BobbiTV-CE2054.bobbi-update.zip',
            'tag': 'ce2054',
            'sha256': f'{idx:064x}',
        }
        components._record_absent_404(work, fake_offer, clock=lambda i=idx: 1000.0 + i)
    loaded = components._load_absence_records(work, 1000.0)
    assert len(loaded) == components.ABSENCE_MAX


def test_rb05_release_gate_freezes_recursive_license_skin_and_generated_evidence(tmp_path):
    ev = gate.collect_publication_evidence(ROOT)
    rel_paths = {Path(row['path']).resolve().relative_to(ROOT.resolve()).as_posix() for row in ev}
    assert 'licenses/THIRD-PARTY.json' in rel_paths
    assert 'licenses/skin-reference-evidence.json' in rel_paths
    assert 'licenses/vendor/segno-license.txt' in rel_paths
    assert 'licenses/vendor/script.module.requests.txt' in rel_paths
    assert 'addons/skin.bobbi.cinema/1080p/Includes_HomeRails.generated.xml' in rel_paths
    assert 'addons/skin.bobbi.cinema/1080p/Includes_HomeHero.generated.xml' in rel_paths
    assert len(ev) >= 60

    # Copy one nested license into tmp_path and verify recheck_local detects post-freeze mutation
    nested = tmp_path / 'licenses/vendor/segno-license.txt'
    nested.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'licenses/vendor/segno-license.txt', nested)
    fake_receipt = {
        'assets': {},
        'feeds': {},
        'evidence': [gate.identity(nested)],
    }
    gate.recheck_local(fake_receipt)
    nested.write_bytes(nested.read_bytes() + b'\ntampered')
    with pytest.raises(ValueError, match='input changed'):
        gate.recheck_local(fake_receipt)


def test_r16_emby_play_ok_requires_actual_av_start_and_deduplicates_per_request(tmp_path):
    host = Host(tmp_path)
    try:
        def read_outcomes():
            db_path = tmp_path / optimization.FILE
            if not db_path.is_file():
                return []
            with sqlite3.connect(str(db_path)) as db:
                return db.execute('SELECT stage, outcome FROM pending ORDER BY rowid').fetchall()

        # 1. Handoff alone records 'handoff', never 'ok'
        optimization.observe(tmp_path, 'emby_play', 'handoff', optimization.time.monotonic() - 0.4)
        assert read_outcomes() == [('emby_play', 'handoff')]

        # 2. Pre-AV TERMINAL (cancelled/failed before AV_START) never records 'ok'
        host.notify_playback_event({
            'event': 'TERMINAL',
            'request_id': 'req-cancelled',
            'source_meta': {'provider': 'emby', 'handoff_monotonic': '10.0'},
        })
        assert read_outcomes() == [('emby_play', 'handoff')]

        # 3. Real AV_START records 'ok' once, and duplicate AV_START for same request_id is ignored
        now_m = optimization.time.monotonic()
        for _ in range(3):
            host.notify_playback_event({
                'event': 'AV_START',
                'request_id': 'req-started-01',
                'source_meta': {'provider': 'emby', 'handoff_monotonic': f'{now_m - 1.2:.3f}'},
            })
        assert read_outcomes() == [('emby_play', 'handoff'), ('emby_play', 'ok')]
    finally:
        host.close()
