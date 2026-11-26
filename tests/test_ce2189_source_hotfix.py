"""Post-CE2188 source hotfix & UX enhancement regressions (CE2189).

Covers:
1. HF-SRC-01: Custom Torznab streaming cancellation, deadline enforcement, and SearchAdmission lease release.
2. HF-SRC-02: Restore All Default Sources re-enables removed default sources in settings.xml while preserving
   API keys and pre-existing disabled-but-not-removed sources.
3. HF-ENH-01: Jackett Web UI copied URLs ending in '/results/torznab/' normalize cleanly to '/results/torznab/api'
   without requiring HTTP redirects.
4. HF-ENH-02: Custom Torznab honors bilingual/multi-alias `title_queries` (capped at 3 distinct queries) and
   deduplicates identical torrents across aliases.
5. HF-ENH-03: Custom Torznab edit menu offers one-click 'Test Custom Source Connection' in ZH and EN (zero CJK in EN).
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import inspect
import os
from pathlib import Path
import sys
from threading import Event, Lock, Thread
import time
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

import pytest
import requests

REPO = Path(os.environ.get("BOBBI_REVIEW_REPO") or Path(__file__).resolve().parents[1]).resolve()
for part in ["tests", "addons/script.module.bobbi.platform/lib", "addons/script.module.bobbi.core/lib"]:
    p_str = str(REPO / part)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
from test_u06_u11_sources_http_phone_contracts import _setup_plugin_test_env


@pytest.fixture
def modules(tmp_path, monkeypatch):
    _setup_plugin_test_env(monkeypatch, tmp_path=tmp_path)
    return (
        importlib.import_module("lib.gui.source_manager_dialog"),
        importlib.import_module("lib.utils.user_sources"),
        importlib.import_module("lib.clients.jackett"),
    )


def admission_options(jackett, tmp_path):
    if "slot_factory" not in inspect.signature(jackett.Jackett.search_custom_torznab).parameters:
        return {}
    from lib.clients.portable_http import _slot

    return {"slot_factory": lambda key=None: _slot(key, directory=tmp_path / "http-slots")}


def test_restore_defaults_reenables_source_removed_by_same_menu(modules, tmp_path):
    hub, prefs, _ = modules
    profile = tmp_path / "profile"
    profile.mkdir()
    settings = profile / "settings.xml"
    settings.write_text(
        '<settings><setting id="jackett_enabled">true</setting>'
        '<setting id="jackett_apikey">fixture-key</setting>'
        '<setting id="nuvio_enabled">false</setting></settings>',
        encoding="utf-8",
    )
    jackett_index = next(i for i, row in enumerate(prefs.DEFAULT_SOURCE_SPECS) if row[0] == "jackett")

    class Dialog:
        def __init__(self):
            self.choices = iter([jackett_index, len(prefs.DEFAULT_SOURCE_SPECS), -1])

        def select(self, title, choices, *args, **kwargs):
            return next(self.choices)

    assert hub._manage_default_sources(Dialog(), profile_root=profile) == hub.CHANGED
    assert prefs.load_user_sources(profile)["removed_defaults"] == []
    assert hub._read_setting_bool("jackett_enabled", profile_root=profile) is True
    values = {e.get("id"): e.text for e in ET.parse(settings).getroot().iter("setting")}
    assert values["jackett_apikey"] == "fixture-key"
    assert values["nuvio_enabled"] == "false"


@contextmanager
def origin(slow=False, *, custom_responder=None):
    entered, release = Event(), Event()
    seen_requests = []
    req_lock = Lock()
    default_body = b'<rss version="2.0"><channel><title>test</title></channel></rss>'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            with req_lock:
                seen_requests.append(self.path)
            try:
                if custom_responder is not None:
                    status, body = custom_responder(self.path)
                else:
                    status, body = 200, default_body
                self.send_response(status)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                if not slow:
                    self.wfile.write(body)
                    self.wfile.flush()
                    entered.set()
                    return
                self.wfile.write(body[:1])
                self.wfile.flush()
                entered.set()
                for byte in body[1:]:
                    if release.wait(0.04):
                        return
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", entered, release, seen_requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize("mode", ["deadline", "cancel"])
def test_custom_torznab_stops_during_slow_body(modules, tmp_path, mode):
    _, _, jackett = modules
    cancelled, done = Event(), Event()
    result, errors = [], []
    with origin(slow=True) as (base, entered, release, _), requests.Session() as session:
        url = f"{base}/api"
        session.trust_env = False
        deadline = time.monotonic() + (0.45 if mode == "deadline" else 4.0)

        def run():
            try:
                result.append(
                    jackett.Jackett.search_custom_torznab(
                        {"name": "loopback", "url": url},
                        "fixture",
                        "movies",
                        timeout=1.0,
                        deadline=deadline,
                        cancelled=cancelled.is_set,
                        session=session,
                        **admission_options(jackett, tmp_path),
                    )
                )
            except BaseException as error:
                errors.append(type(error).__name__)
            finally:
                done.set()

        thread = Thread(target=run, daemon=True)
        thread.start()
        try:
            assert entered.wait(2)
            if mode == "cancel":
                cancelled.set()
            assert done.wait(0.9)
            assert not errors
            assert result and not result[0].completion.complete
        finally:
            release.set()
            thread.join(3)
            assert not thread.is_alive()


def test_custom_torznab_fast_real_http_empty_rss_is_success(modules, tmp_path):
    _, _, jackett = modules
    with origin(slow=False) as (base, entered, _, _), requests.Session() as session:
        session.trust_env = False
        rows = jackett.Jackett.search_custom_torznab(
            {"name": "loopback", "url": f"{base}/api"},
            "fixture",
            "movies",
            timeout=1.0,
            deadline=time.monotonic() + 2,
            cancelled=lambda: False,
            session=session,
            **admission_options(jackett, tmp_path),
        )
        assert entered.wait(0.5)
        assert list(rows) == [] and rows.completion.complete


def test_cancelled_custom_search_releases_search_admission_for_next_search(modules, tmp_path):
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_core.search_admission import try_acquire
    from bobbi_core.source_list_session import SourceListSession

    _, _, jackett = modules
    search_session = SourceListSession({}, lambda rows: rows)
    with origin(slow=True) as (base, entered, release, _), requests.Session() as transport:
        url = f"{base}/api"
        transport.trust_env = False

        def setup(manager):
            manager.submit_task(
                "loopback",
                "custom",
                jackett.Jackett.search_custom_torznab,
                {"name": "loopback", "url": url},
                "fixture",
                "movies",
                deadline=manager.deadline,
                cancelled=manager.scope_cancelled,
                session=transport,
                **admission_options(jackett, tmp_path),
            )

        pump = ProgressiveSearch(
            search_session, setup, lambda rows: rows, admission=lambda: try_acquire(tmp_path / "search-lease"), budget=4
        )
        acquired = None
        pump.start()
        try:
            assert entered.wait(2)
            pump.cancel()
            pump.thread.join(1)
            expires = time.monotonic() + 0.9
            while time.monotonic() < expires:
                acquired = try_acquire(tmp_path / "search-lease")
                if acquired is not None:
                    break
                time.sleep(0.02)
            assert acquired is not None
        finally:
            if acquired is not None:
                acquired.release()
            release.set()
            pump.cancel()
            pump.thread.join(3)
            for future in pump._futures:
                future.result(timeout=3)


def test_jackett_copied_url_normalization_and_multi_alias_dedup_and_test_dialog(modules, tmp_path, monkeypatch):
    hub, prefs, jackett = modules
    rss_hit = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">'
        b'<channel><item>'
        b'<title>Sousou no Frieren S01E01 1080p</title>'
        b'<guid>magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01</guid>'
        b'<link>magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01</link>'
        b'<size>209715200</size>'
        b'<torznab:attr name="seeders" value="42"/>'
        b'<torznab:attr name="infohash" value="abcdef0123456789abcdef0123456789abcdef01"/>'
        b'</item></channel></rss>'
    )
    rss_empty = b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>empty</title></channel></rss>'

    def responder(path: str):
        parsed = urlsplit(path)
        if parsed.path != "/api/v2.0/indexers/mikan/results/torznab/api":
            return 301, b""
        qs = parse_qs(parsed.query)
        q_val = (qs.get("q") or [""])[0]
        if q_val in ("Sousou no Frieren", "Frieren", "test"):
            return 200, rss_hit
        return 200, rss_empty

    with origin(slow=False, custom_responder=responder) as (base, _, _, seen_reqs), requests.Session() as session:
        session.trust_env = False
        # User pasted Jackett's "Copy Torznab Feed" URL WITH trailing '/results/torznab/' (no '/api')
        copied_url = f"{base}/api/v2.0/indexers/mikan/results/torznab/"
        src_entry = {"id": "mikan", "name": "Mikan", "url": copied_url, "apikey": "k1", "enabled": True}

        res = jackett.Jackett.search_custom_torznab(
            src_entry,
            "葬送的芙莉莲",
            "tv",
            1,
            1,
            None,
            title_queries=("葬送的芙莉莲", "Sousou no Frieren", "Frieren", "Extra Ignored Alias"),
            timeout=2.0,
            deadline=time.monotonic() + 3.0,
            session=session,
            **admission_options(jackett, tmp_path),
        )
        assert res.completion.planned == 3 and res.completion.complete is True
        # Deduplicated across both matching aliases ("Sousou no Frieren" and "Frieren")
        assert len(res) == 1
        assert res[0].provider == "Mikan"
        assert all(p.startswith("/api/v2.0/indexers/mikan/results/torznab/api?") for p in seen_reqs)

        # Test interactive "Test Custom Source Connection" (index 3) in English with zero CJK
        monkeypatch.setattr(hub, "_is_en", lambda: True)
        monkeypatch.setattr(hub, "_t", lambda po_id, zh, en: en)
        ok_calls = []

        class _TestDlg:
            def select(self, title, opts, *a, **kw):
                assert len(opts) == 4
                assert not any("\u4e00" <= ch <= "\u9fff" for o in opts for ch in o)
                return 3

            def ok(self, title, body):
                ok_calls.append((title, body))

        changed = hub._edit_existing_custom_torznab(_TestDlg(), src_entry, profile_root=tmp_path / "prof")
        assert changed is False
        assert len(ok_calls) == 1
        assert "Custom Source Connected" in ok_calls[0][0]
        assert "1 item(s)" in ok_calls[0][1]
        assert not any("\u4e00" <= ch <= "\u9fff" for part in ok_calls[0] for ch in part)
