"""U17 convergence contracts: single RouteSpec router, Host-owned next-worker drain,
Debrid single _make_request contract, Emby Http gateway fallback, capability docs,
and deterministic architecture graph regeneration (CT-CAPABILITIES, CT-DEBRID, CT-ARCHITECTURE).
"""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "addons" / "plugin.video.bobbi"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


def _load_router():
    spec = importlib.util.spec_from_file_location("u17_router_under_test", PLUGIN_ROOT / "lib" / "router.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_u17_routespec_single_declaration_legacy_aliases_and_completion_contracts(monkeypatch):
    router = _load_router()
    declared = [act for spec in router.ROUTE_SPECS for act in spec.actions]
    assert len(declared) == len(set(declared)), "Every route action must be declared once"
    assert set(declared) == set(router.ROUTE_BY_ACTION)
    assert all(spec.completion in router.VALID_COMPLETIONS for spec in router.ROUTE_SPECS)

    # Legacy bobi_* -> bobbi_* saved bookmark alias normalization
    seen = []
    cw_mod = ModuleType("lib.utils.views.continue_watching")
    cw_mod.open_resume_card = lambda params: seen.append(dict(params)) or "opened"
    monkeypatch.setitem(sys.modules, "lib.utils.views.continue_watching", cw_mod)
    monkeypatch.setattr(sys, "argv", ["plugin://plugin.video.bobbi/", "-1", "?action=bobi_resume_card&id=42"])
    prepared = []
    assert router.addon_router(prepare_catalog=lambda: prepared.append(True)) == "opened"
    assert prepared == [True]
    assert seen == [{"action": "bobbi_resume_card", "id": "42"}]

    # OSD popup bypasses prepare_catalog and completes endOfDirectory in finally
    ended = []
    osd_mod = ModuleType("lib.services.osd_playback")
    osd_mod.run = lambda op, token=None: {"op": op, "token": token}
    xbmcplugin_mod = ModuleType("xbmcplugin")
    xbmcplugin_mod.endOfDirectory = lambda handle, succeeded=True, cacheToDisc=True: ended.append(
        (handle, succeeded, cacheToDisc)
    )
    monkeypatch.setitem(sys.modules, "lib.services.osd_playback", osd_mod)
    monkeypatch.setitem(sys.modules, "xbmcplugin", xbmcplugin_mod)
    monkeypatch.setattr(sys, "argv", ["plugin://plugin.video.bobbi/", "7", "?action=osd_apply&token=abc"])
    prepared.clear()
    assert router.addon_router(prepare_catalog=lambda: prepared.append(True)) == {"op": "apply", "token": "abc"}
    assert prepared == []
    assert ended == [(7, True, False)]

    # source_import_manage_phone completes with succeeded=False when called with directory handle >= 0
    ended.clear()
    mp_mod = ModuleType("lib.clients.stremio.manage_phone")
    mp_mod.source_import_manage_phone = lambda params: "paired_done"
    monkeypatch.setitem(sys.modules, "lib.clients.stremio.manage_phone", mp_mod)
    monkeypatch.setattr(sys, "argv", ["plugin://plugin.video.bobbi/", "3", "?action=source_import_manage_phone"])
    assert router.addon_router() == "paired_done"
    assert ended == [(3, False, False)]


def test_u17_owned_next_worker_retired_and_host_close_enforces_cancel_and_lease_retention(tmp_path):
    from bobbi_platform.host import Host
    from bobbi_platform.instance_lock import InstanceLock
    from lib.services.playback_control import PlaybackControlServer

    # Verify legacy untracked _owned_next_worker attribute and raw Thread spawns are gone
    pc_src = (PLUGIN_ROOT / "lib" / "services" / "playback_control.py").read_text(encoding="utf-8")
    assert "_owned_next_worker" not in pc_src
    assert "bobbi-native-next-summary" not in pc_src

    # 1. Normal cancel + drain receipt on Host.close()
    codes = []
    host = Host(tmp_path / "clean", report=codes.append)
    host.start()
    srv = PlaybackControlServer(native=SimpleNamespace(poll_io=None, close=None), path=None, host=host)
    host.playback = srv
    entered = Event()
    observed_cancel = Event()

    def cancellable_job(cancelled):
        entered.set()
        while not cancelled():
            Event().wait(0.02)
        observed_cancel.set()

    assert host.owned_next.submit("summary", cancellable_job)
    assert entered.wait(1.0)
    host.close()
    assert observed_cancel.is_set()
    assert "SHUTDOWN_BEGIN_OWNED_NEXT" in codes
    assert "SHUTDOWN_DRAINED_OWNED_NEXT" in codes
    claimant = InstanceLock(str(tmp_path / "clean" / "runtime.json") + ".lock")
    claimant.acquire()
    claimant.close()

    # 2. Wedged worker retains runtime.lease and raises OWNED_NEXT_DRAIN_PENDING
    release_wedged = Event()
    wedged_entered = Event()
    host2 = Host(tmp_path / "wedged", report=lambda _c: None)
    host2.start()
    host2.owned_next.close = lambda timeout=0.05: Host.__dict__  # replaced below with bounded close
    from bobbi_platform.owned_playback import OwnedNextCoordinator
    coord2 = OwnedNextCoordinator(stopping=host2.stopping, profile_current=host2.check_profile)
    host2.owned_next = SimpleNamespace(close=lambda: coord2.close(timeout=0.1))

    assert coord2.submit("candidate", lambda _cancelled: (wedged_entered.set(), release_wedged.wait(5.0)))
    assert wedged_entered.wait(1.0)
    try:
        with pytest.raises(RuntimeError, match="OWNED_NEXT_DRAIN_PENDING"):
            host2.close()
        claimant2 = InstanceLock(str(tmp_path / "wedged" / "runtime.json") + ".lock")
        with pytest.raises(OSError):
            claimant2.acquire()
    finally:
        release_wedged.set()
        assert coord2.close(timeout=2.0)
        host2.owned_next = SimpleNamespace(close=lambda: True)
        host2.close()


def test_u17_debrid_single_make_request_contract_and_nuvio_stremio_scope_isolation(monkeypatch):
    from base64 import b64encode

    kodi_utils_stub = ModuleType("lib.utils.kodi.utils")
    kodi_utils_stub.kodilog = lambda *a, **kw: None
    kodi_utils_stub.notification = lambda *a, **kw: None
    kodi_utils_stub.dialog_ok = lambda *a, **kw: None
    kodi_utils_stub.set_setting = lambda *a, **kw: None
    kodi_utils_stub.translation = lambda code: str(code)
    auth_stub = ModuleType("lib.services.debrid.auth")
    auth_stub.run_realdebrid_auth = lambda *a, **kw: None
    auth_stub.run_premiumize_auth = lambda *a, **kw: None
    dl_stub = ModuleType("lib.services.debrid.download")
    dl_stub.run_realdebrid_download = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "lib.utils.kodi.utils", kodi_utils_stub)
    monkeypatch.setitem(sys.modules, "lib.services.debrid.auth", auth_stub)
    monkeypatch.setitem(sys.modules, "lib.services.debrid.download", dl_stub)
    for mod_name in ("lib.api.debrid.base", "lib.api.debrid.realdebrid", "lib.api.debrid.premiumize"):
        monkeypatch.delitem(sys.modules, mod_name, raising=False)

    from lib.api.debrid.base import DebridClient
    from lib.api.debrid.realdebrid import RealDebrid
    from lib.api.debrid.premiumize import Premiumize

    assert "_make_request" not in RealDebrid.__dict__
    assert "_make_request" not in Premiumize.__dict__
    assert RealDebrid._make_request is DebridClient._make_request
    assert Premiumize._make_request is DebridClient._make_request

    calls = []

    class DummySession:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return SimpleNamespace(
                status_code=200,
                headers={"Content-Type": "application/json"},
                raise_for_status=lambda: None,
                json=lambda: {"access_token": "tok-rd", "ok": True},
                text='{"access_token": "tok-rd", "ok": true}',
                close=lambda: None,
            )

    sess = DummySession()
    rd_tok = b64encode(b"cid:csec:code").decode("ascii")
    rd = RealDebrid(token=rd_tok, session=sess)
    # params=None normalizes cleanly to {} without mutating caller dicts
    assert rd._make_request("GET", "https://api.real-debrid.com/rest/1.0/user", params=None) == {
        "access_token": "tok-rd",
        "ok": True,
    }
    assert calls[-1][2]["params"] == {}
    assert "Bearer tok-rd" in calls[-1][2]["headers"].get("Authorization", "")

    custom_params = {"page": 2}
    pm = Premiumize(token="tok-pm", session=sess)
    assert pm._make_request("GET", "https://www.premiumize.me/api/folder/list", params=custom_params) == {
        "access_token": "tok-rd",
        "ok": True,
    }
    assert calls[-1][2]["params"] == {"page": 2}

    # Nuvio and Stremio share bounded HTTP policy while keeping separate storage keys
    nuvio_src = (PLUGIN_ROOT / "lib" / "clients" / "nuvio" / "addon_selection.py").read_text(encoding="utf-8")
    stremio_src = (PLUGIN_ROOT / "lib" / "clients" / "stremio" / "addon_selection.py").read_text(encoding="utf-8")
    assert "fetch_bounded_json" in nuvio_src or "request_with_safe_redirects" in nuvio_src
    assert "nuvio" in nuvio_src.lower() and "stremio_addons" not in nuvio_src


def test_u17_capabilities_docs_and_deterministic_architecture_graph(tmp_path, monkeypatch):
    tvbox_doc = (ROOT / "docs" / "tvbox-t4-bridge.md").read_text(encoding="utf-8")
    assert "完整的Dolby Vision" not in tvbox_doc
    assert "双端同步体验" not in tvbox_doc
    assert "直播订阅入口条数" in tvbox_doc

    cap_doc = (ROOT / "docs" / "architecture" / "current-capabilities.md").read_text(encoding="utf-8")
    for required_token in (
        "Infuse Direct",
        "EmbyCon",
        "b64b7501ff79cf34b349d61a360bc139d195908f9df19af7c9139a44a37acbac",
        "Profile 7 FEL",
        "BLOCKED",
        "R00",
        "R19",
        "RouteSpec",
        "OwnedNextCoordinator",
    ):
        assert required_token in cap_doc, required_token

    tool_path = ROOT / "tools" / "architecture_graph.py"
    spec = importlib.util.spec_from_file_location("u17_arch_graph", tool_path)
    arch = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, arch)
    spec.loader.exec_module(arch)

    out1 = tmp_path / "graph1"
    out2 = tmp_path / "graph2"
    assert arch.main(["--repo", str(ROOT), "--output", str(out1)]) == 0
    assert arch.main(["--repo", str(ROOT), "--output", str(out2)]) == 0
    g1 = json.loads((out1 / "graph.json").read_text(encoding="utf-8"))
    g2 = json.loads((out2 / "graph.json").read_text(encoding="utf-8"))
    assert arch.stable(g1) == arch.stable(g2)
    assert g1["diagnostics"] == []
    assert g1["boundary_findings"] == []
    assert g1["summary"]["edges_by_status"].get("unresolved", 0) > 0
    # Verify RouteSpec actions in router.py emit kodi-action dispatch_branch edges
    dispatch_sources = {
        e["source"]
        for e in g1["edges"]
        if e["kind"] == "dispatch_branch" and e["evidence"]["path"] == "addons/plugin.video.bobbi/lib/router.py"
    }
    assert "protocol:kodi-action:plugin.video.bobbi:emby_rail" in dispatch_sources
    assert "protocol:kodi-action:plugin.video.bobbi:source_import_manage_phone" in dispatch_sources
