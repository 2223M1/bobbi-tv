import hashlib
import sqlite3

import pytest

from lib.cinema.font_cache import FontCache, FONT_SCHEMA_KEY, install_schema
from lib.cinema.ledger import Ledger
from test_cinema_fonts import font


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "connect", sqlite3.dbapi2.connect)
    clock = [1000]
    with Ledger(tmp_path / "ledger.sqlite", now=lambda: clock[0]) as ledger:
        yield FontCache(ledger, tmp_path / "cache", tmp_path / "Fonts"), clock


def subtitle(family="Test Font"):
    return ("[Script Info]\n[V4+ Styles]\nFormat: Name,Fontname,Bold,Italic\n"
            "Style: Default," + family + ",0,0\n[Events]\n").encode()


def bound(cache, version="release1", family="Test Font", origin="same_release_pack"):
    row = cache.import_font(font((family,)), origin, version)
    result = cache.bind(version, subtitle(family), [row["sha256"]])
    return row, result["subtitle_sha256"]


def test_exact_binding_and_activation_share_ledger_and_hardlink(cache):
    store, _ = cache
    row, sub = bound(store)
    result = store.activate("release1", sub, "request1", lambda: True)
    assert result["font_count"] == 1
    native = store._path(row, native=True)
    assert native.samefile(store._path(row))
    assert hashlib.sha256(native.read_bytes()).hexdigest() == row["sha256"]
    assert store.ledger.db.execute("SELECT action FROM audit ORDER BY seq DESC LIMIT 1").fetchone()[0] == "font_activate"


def partial_binding(store):
    row = store.import_font(font(), 'same_release_pack', 'partial')
    raw = subtitle().replace(b'[Events]', b'Style: Missing,Absent Family,0,0\n[Events]')
    result = store.bind('partial', raw, [row['sha256']])
    assert result['missing'] and result['selected']
    return row, result['subtitle_sha256']


def test_partial_fonts_activate_without_claiming_complete_coverage(cache):
    store, _ = cache
    row, sub = partial_binding(store)
    user = store.native/'user.ttf'; user.write_bytes(font(('User Font',)))
    plan = store.activation_plan('partial', sub)
    proof = store.verify_plan(plan)
    result = store.activate('partial', sub, 'request', lambda: True, verified=proof)
    assert result['font_count'] == 1 and result['inputs_complete'] is False
    assert result['missing_count'] == 1
    assert store._path(row, True).samefile(store._path(row)) and user.exists()
    assert store.owns_activation('partial', sub, 'request', result['hashes'])
    assert not store.owns_activation('partial', sub, 'other', result['hashes'])
    assert store.binding('partial', sub)['status'] == 'MISSING_FONTS'
    store.reserve('partial', sub, 'next')
    assert store.prune(lambda: True, limit=1)['removed'] == []


def test_partial_font_switch_keeps_owner_guard_and_rollback(cache):
    store, _ = cache
    old, oldsub = bound(store)
    store.activate('release1', oldsub, 'old', lambda: True)
    new, sub = partial_binding(store)
    guards = iter([True, False])
    with pytest.raises(RuntimeError):
        store.activate('partial', sub, 'new', lambda: next(guards))
    assert store._path(old, True).exists()
    assert not store._path(new, True).exists()


def test_extracted_font_file_uses_same_content_cache_and_binding(cache, tmp_path):
    store, _ = cache
    raw = font()
    path = tmp_path/'extracted.ttf'
    path.write_bytes(raw)
    row = store.import_file(path, 'same_release_pack', 'release1', hashlib.sha256(raw).hexdigest())
    assert store._verify(row).read_bytes() == raw
    result = store.bind('release1', subtitle(), [row['sha256']])
    assert result['status'] == 'EXACT_FONTS_READY_NOT_VISUAL_PROOF'
    assert store.import_font(raw, 'same_release_pack', 'release1') == row
    assert store.ledger.db.execute('SELECT COUNT(*) FROM font_objects').fetchone()[0] == 1


def test_extracted_font_hash_mismatch_never_published(cache, tmp_path):
    store, _ = cache
    path = tmp_path/'extracted.ttf'
    path.write_bytes(font())
    with pytest.raises(ValueError, match='differs'):
        store.import_file(path, 'same_release_pack', 'release1', '0'*64)
    assert not list(store.objects.iterdir())
    assert store.ledger.db.execute('SELECT COUNT(*) FROM font_objects').fetchone()[0] == 0


def test_change_between_font_inspection_and_copy_never_enters_ledger(cache, tmp_path, monkeypatch):
    from lib.cinema import font_cache
    store, _ = cache
    path = tmp_path/'extracted.ttf'
    raw = font()
    path.write_bytes(raw)
    original = font_cache.inspect_font_file
    def change(file):
        record = original(file)
        path.write_bytes(raw[:-1]+b'x')
        return record
    monkeypatch.setattr(font_cache, 'inspect_font_file', change)
    with pytest.raises(ValueError, match='publication'):
        store.import_file(path, 'same_release_pack', 'release1', hashlib.sha256(raw).hexdigest())
    assert store.ledger.db.execute('SELECT COUNT(*) FROM font_objects').fetchone()[0] == 0
    assert all(p.suffix == '.pending' for p in store.objects.iterdir())


def test_release_fonts_cannot_bind_to_a_different_release(cache):
    store, _ = cache
    row, _ = bound(store)
    result = store.bind("otherrelease", subtitle(), [row["sha256"]])
    assert result["missing"] and not result["selected"]
    with pytest.raises(ValueError):
        store.activate("otherrelease", result["subtitle_sha256"], "request", lambda: True)


def test_exact_local_fonts_are_valid_fallback_across_versions(cache):
    store, _ = cache
    row, _ = bound(store, origin="local_exact")
    result = store.bind("anotherrelease", subtitle(), [row["sha256"]])
    assert not result["missing"]


def test_playing_guard_does_not_change_native_fonts(cache):
    store, _ = cache
    _, sub = bound(store)
    with pytest.raises(RuntimeError):
        store.activate("release1", sub, "request1", lambda: False)
    assert list(store.native.iterdir()) == []


def test_cancel_during_switch_preserves_old_fonts_and_removes_new_links(cache):
    store, _ = cache
    old, sub = bound(store)
    store.activate("release1", sub, "oldrequest", lambda: True)
    new, sub2 = bound(store, "release2", "Other Font")
    guards = iter([True, False])
    with pytest.raises(RuntimeError):
        store.activate("release2", sub2, "newrequest", lambda: next(guards))
    assert store._path(old, True).is_file()
    assert not store._path(new, True).exists()
    assert [row[0] for row in store.ledger.db.execute("SELECT sha256 FROM font_native_links")] == [old["sha256"]]


def test_user_fonts_are_never_removed_and_only_old_managed_link_is_switched(cache):
    store, _ = cache
    user = store.native / "user.ttf"
    user.write_bytes(font(("User Font",)))
    old, sub = bound(store)
    store.activate("release1", sub, "old", lambda: True)
    new, sub2 = bound(store, "release2", "Other Font")
    store.activate("release2", sub2, "new", lambda: True)
    assert user.read_bytes() == font(("User Font",))
    assert store._path(old).exists() and not store._path(old, True).exists()
    assert store._path(new, True).exists()


def test_same_named_unknown_native_font_is_preserved(cache):
    store, _ = cache
    row, sub = bound(store)
    native = store._path(row, True)
    native.write_bytes(b"user-owned")
    with pytest.raises(ValueError):
        store.activate("release1", sub, "request", lambda: True)
    assert native.read_bytes() == b"user-owned"


def test_corrupt_cached_font_is_not_overwritten(cache):
    store, _ = cache
    row, sub = bound(store)
    store._path(row).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        store.import_font(font(("Test Font",)), "same_release_pack", "release1")
    with pytest.raises(ValueError):
        store.activate("release1", sub, "request", lambda: True)
    assert store._path(row).read_bytes() == b"corrupt"


def test_current_and_next_fonts_protected_even_when_soft_cap_exceeded(cache):
    store, clock = cache
    row, sub = bound(store)
    store.activate("release1", sub, "current", lambda: True)
    next_row, next_sub = bound(store, "nextrelease", "Next Font")
    store.reserve("nextrelease", next_sub, "next-owner", seconds=20)
    assert store.prune(lambda: True, limit=1)["removed"] == []
    clock[0] += 21
    result = store.prune(lambda: True, limit=1)
    assert result["removed"] == [next_row["sha256"]]
    assert store._path(row).is_file()
    assert store.binding("nextrelease", next_sub)["status"] == "FONT_CACHE_MISS"


def test_prune_during_playback_does_not_read_or_delete_files(cache):
    store, _ = cache
    row, _ = bound(store)
    result = store.prune(lambda: False, limit=0)
    assert not result["removed"]
    assert store._path(row).is_file()


def test_unmanaged_file_in_private_cache_is_not_a_prune_target(cache):
    store, _ = cache
    user = store.objects / "unrecognized-font.ttf"
    user.write_bytes(b"preserve")
    row, _ = bound(store)
    assert store.prune(lambda: True, limit=0)["removed"] == [row["sha256"]]
    assert user.read_bytes() == b"preserve"


def test_font_schema_retains_verified_preimage_and_does_not_replay(cache):
    store, _ = cache
    with sqlite3.connect(store.migration_backup) as original:
        assert original.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert original.execute("SELECT 1 FROM sqlite_master WHERE name='font_objects'").fetchone() is None
    assert install_schema(store.ledger) is None
    assert store.ledger.db.execute('PRAGMA user_version').fetchone()[0] == 2


@pytest.mark.parametrize('drift', ['missing_table', 'unknown_version', 'unversioned', 'changed_columns'])
def test_unknown_font_schema_stops_without_repair(cache, drift):
    store, _ = cache
    db = store.ledger.db
    if drift == 'missing_table': db.execute('DROP TABLE font_bindings')
    if drift == 'unknown_version': db.execute('UPDATE settings SET value=? WHERE key=?', ('2', FONT_SCHEMA_KEY))
    if drift == 'unversioned': db.execute('DELETE FROM settings WHERE key=?', (FONT_SCHEMA_KEY,))
    if drift == 'changed_columns': db.execute('ALTER TABLE font_bindings ADD COLUMN unknown TEXT')
    before = db.total_changes
    with pytest.raises(ValueError): install_schema(store.ledger)
    assert db.total_changes == before
