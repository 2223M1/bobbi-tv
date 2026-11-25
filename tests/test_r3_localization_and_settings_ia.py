"""R3 verification suite for Localization, Plugin Settings IA, Phone Web & Native Surfaces."""
import ast
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOBBI = ROOT / "addons" / "plugin.video.bobbi"
PLATFORM = ROOT / "addons" / "script.module.bobbi.platform"
CORE = ROOT / "addons" / "script.module.bobbi.core"

for _p in (str(BOBBI), str(PLATFORM / "lib"), str(CORE / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


PO_ENTRY_RE = re.compile(
    r'msgctxt\s+"#(\d+)"(?:\s*\r?\n(?:#[^\n]*\n)*)\s*'
    r'msgid\s+((?:"(?:[^"\\]|\\.)*"\s*\r?\n?)+)'
    r'(?:(?:#[^\n]*\n)*\s*msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*\r?\n?)+))?',
    re.MULTILINE,
)
PO_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unquote_po(block):
    if not block:
        return ""
    raw = "".join(PO_STR_RE.findall(block))
    return raw.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")


def _parse_po_strict(path: Path):
    text = path.read_text(encoding="utf-8")
    all_contexts = [int(m.group(1)) for m in re.finditer(r'msgctxt\s+"#(\d+)"', text)]
    duplicates = sorted({c for c in all_contexts if all_contexts.count(c) > 1})
    assert not duplicates, f"Duplicate msgctxt IDs in {path}: {duplicates}"

    entries = {}
    for m in PO_ENTRY_RE.finditer(text):
        assert m.group(3) is not None, f"Missing msgstr line for #{m.group(1)} in {path}"
        code = int(m.group(1))
        entries[code] = (_unquote_po(m.group(2)), _unquote_po(m.group(3)))
    assert len(entries) == len(all_contexts), f"Unparsed msgctxt blocks in {path}"
    return entries


def _placeholders(text: str):
    cleaned = re.sub(r"%%", "", text)
    pct = re.findall(r"%(?:\(\w+\))?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[diouxXeEfFgGcrs]", cleaned)
    braces = sorted(re.findall(r"\{[^{}]*\}", text))
    return pct, braces


def _kodi_tags(text: str):
    return re.findall(r"\[/?(?:B|I|CR|UPPERCASE|LOWERCASE|CAPITALIZE|LIGHT|COLOR(?:\s+[^\]]+)?)\]", text)


def test_all_po_catalogs_deduplicated_and_placeholder_tag_matched():
    # 1. Main plugin POs
    en_po = _parse_po_strict(BOBBI / "resources/language/English/strings.po")
    ro_po = _parse_po_strict(BOBBI / "resources/language/Romanian/strings.po")
    es_po = _parse_po_strict(BOBBI / "resources/language/Spanish/strings.po")
    zh_po = _parse_po_strict(BOBBI / "resources/language/resource.language.zh_cn/strings.po")

    assert 90512 in en_po and 90512 in ro_po and 90512 in es_po and 90512 in zh_po
    assert set(en_po) == set(zh_po), f"EN/ZH ID mismatch: {set(en_po) ^ set(zh_po)}"
    assert len(en_po) >= 1700

    # Verify cleared upstream Spanish overrides in English/strings.po
    for code in (30866, 30867, 30868, 30869, 30870, 30871, 30872, 90002):
        en_msgid, en_msgstr = en_po[code]
        assert en_msgstr == "", f"Unexpected override in English/strings.po #{code}: {en_msgstr!r}"
        assert en_msgid

    for code, (en_msgid, _) in en_po.items():
        zh_msgid, zh_msgstr = zh_po[code]
        assert zh_msgid == en_msgid
        assert zh_msgstr.strip(), f"Empty Chinese translation for #{code}"
        assert _placeholders(en_msgid) == _placeholders(zh_msgstr), f"Placeholder mismatch at #{code}"
        assert _kodi_tags(en_msgid) == _kodi_tags(zh_msgstr), f"Tag mismatch at #{code}"

    # 2. Platform & 8 companion addons
    companion_addons = (
        "script.module.bobbi.platform",
        "script.bobbi.setup",
        "script.bobbi.opensubtitles",
        "plugin.video.bobbi.library",
        "plugin.video.bobbi.torrent",
        "script.module.bobbi.catalog",
        "script.module.bobbi.mdsub",
        "repository.bobbi",
        "script.bobbi.start",
    )
    for addon_id in companion_addons:
        addon_dir = ROOT / "addons" / addon_id
        addon_xml = ET.parse(addon_dir / "addon.xml").getroot()
        meta = addon_xml.find("extension[@point='xbmc.addon.metadata']")
        assert meta is not None
        langs_sum = {n.get("lang") for n in meta.findall("summary")}
        langs_desc = {n.get("lang") for n in meta.findall("description")}
        assert {"en_GB", "zh_CN"} <= langs_sum, f"{addon_id} missing summary lang: {langs_sum}"
        assert {"en_GB", "zh_CN"} <= langs_desc, f"{addon_id} missing description lang: {langs_desc}"

        c_en = _parse_po_strict(addon_dir / "resources/language/resource.language.en_gb/strings.po")
        c_zh = _parse_po_strict(addon_dir / "resources/language/resource.language.zh_cn/strings.po")
        assert c_en and set(c_en) == set(c_zh)
        for code, (en_id, _) in c_en.items():
            zh_id, zh_str = c_zh[code]
            assert zh_id == en_id and zh_str.strip()
            assert _placeholders(en_id) == _placeholders(zh_str)
            assert _kodi_tags(en_id) == _kodi_tags(zh_str)


def test_bobbi_core_stays_kodi_free():
    forbidden = {"xbmc", "xbmcaddon", "xbmcgui", "xbmcplugin", "xbmcvfs", "bobbi_platform"}
    for py_file in (CORE / "lib/bobbi_core").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"{py_file} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"{py_file} imports {node.module}"


def test_cinema_context_labels_removed_and_live_zh_en_zh_roundtrip(monkeypatch, tmp_path):
    utils_src = (BOBBI / "lib/utils/kodi/utils.py").read_text(encoding="utf-8")
    assert "_CINEMA_CONTEXT_LABELS" not in utils_src

    active = {"locale": "resource.language.zh_cn", "skin": "skin.bobbi.cinema"}

    xbmc_stub = types.ModuleType("xbmc")
    xbmc_stub.LOGDEBUG = 0
    xbmc_stub.LOGINFO = 1
    xbmc_stub.LOGWARNING = 2
    xbmc_stub.LOGERROR = 3
    xbmc_stub.PLAYLIST_VIDEO = 1
    xbmc_stub.ISO_639_1 = 0
    xbmc_stub.getSkinDir = lambda: active["skin"]
    xbmc_stub.executeJSONRPC = lambda raw: json.dumps({"result": {"value": active["locale"]}})
    xbmc_stub.getInfoLabel = lambda key: ""
    xbmc_stub.getLanguage = lambda *a: ""
    xbmc_stub.getCondVisibility = lambda expr: False
    xbmc_stub.PlayList = lambda *a: object()
    xbmc_stub.Monitor = lambda: types.SimpleNamespace(abortRequested=lambda: False)
    xbmc_stub.log = lambda *a, **kw: None

    class _AddonStub:
        def __init__(self, addon_id="plugin.video.bobbi"):
            self.addon_id = addon_id

        def getAddonInfo(self, key):
            if key == "path":
                return str(ROOT / "addons" / self.addon_id)
            if key == "profile":
                return f"special://profile/addon_data/{self.addon_id}"
            if key == "id":
                return self.addon_id
            return "bobbi TV"

        def getLocalizedString(self, code):
            return ""

        def getSetting(self, key):
            return ""

        def setSetting(self, key, val):
            pass

    xbmcaddon_stub = types.ModuleType("xbmcaddon")
    xbmcaddon_stub.Addon = _AddonStub

    class _WinStub:
        _props = {}

        def __init__(self, *a):
            pass

        def getProperty(self, k):
            return self._props.get(k, "")

        def setProperty(self, k, v):
            self._props[k] = str(v)

        def clearProperty(self, k):
            self._props.pop(k, None)

    class _WinXmlStub:
        def __init__(self, *a, **kw):
            pass

        def close(self):
            pass

    xbmcgui_stub = types.ModuleType("xbmcgui")
    xbmcgui_stub.Window = _WinStub
    xbmcgui_stub.Dialog = lambda: types.SimpleNamespace()
    xbmcgui_stub.DialogProgress = lambda: types.SimpleNamespace()
    xbmcgui_stub.ListItem = lambda *a, **kw: types.SimpleNamespace()
    xbmcgui_stub.WindowXMLDialog = _WinXmlStub

    xbmcplugin_stub = types.ModuleType("xbmcplugin")
    xbmcplugin_stub.addDirectoryItems = lambda *a, **kw: None
    xbmcplugin_stub.endOfDirectory = lambda *a, **kw: None
    xbmcplugin_stub.setResolvedUrl = lambda *a, **kw: None

    xbmcvfs_stub = types.ModuleType("xbmcvfs")
    xbmcvfs_stub.File = open
    xbmcvfs_stub.delete = lambda p: None
    xbmcvfs_stub.listdir = lambda p: ([], [])
    xbmcvfs_stub.translatePath = lambda p: str(tmp_path / p.replace("special://", "").replace("/", "_"))

    for mod_name, mod_obj in (
        ("xbmc", xbmc_stub),
        ("xbmcaddon", xbmcaddon_stub),
        ("xbmcgui", xbmcgui_stub),
        ("xbmcplugin", xbmcplugin_stub),
        ("xbmcvfs", xbmcvfs_stub),
    ):
        monkeypatch.setitem(sys.modules, mod_name, mod_obj)
    monkeypatch.setitem(sys.modules, "lib.db.cached", types.SimpleNamespace(cache=types.SimpleNamespace(get=lambda k: None, set=lambda *a: None, delete=lambda k: None)))

    spec = importlib.util.spec_from_file_location("r3_kodi_utils_test", BOBBI / "lib/utils/kodi/utils.py")
    kodi_utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kodi_utils)

    from bobbi_platform import account_dialog, i18n, onboarding
    from lib.services.phone_management import MAX_REPLY, PhoneManagement, SCOPES, PLAYBACK_SCOPES, encode

    # Verify all 10 former _CINEMA_CONTEXT_LABELS IDs under skin.bobbi.cinema in ZH -> EN -> ZH
    ten_ids = (90049, 90115, 90755, 90733, 90050, 90051, 90081, 90116, 90205, 90672)
    zh_ten = {cid: kodi_utils.translation(cid) for cid in ten_ids}
    assert zh_ten[90049] == "重新查找片源"
    assert zh_ten[90115] == "选择片源"
    assert i18n.current_locale() == "zh_cn"
    zh_steps = dict(onboarding.steps({"standard_playback": True}, helper_state="ready", library_count=3))
    assert "检查播放器" in zh_steps["check"]
    assert all(len(v) <= 32 for v in zh_steps.values())
    win_zh = account_dialog.create(tmp_path / "qr.png")
    assert "扫码后在手机确认" in win_zh.message

    # Pair a live PhoneManagement session while TV is in ZH
    account_scope = {"provider": "115", "authenticated": True, "account_id": "115:" + "a" * 64, "epoch": 4}
    host_calls = []

    def fake_rpc(action, args, timeout=3):
        host_calls.append((action, args))
        if action == "pan_status":
            return {"providers": [{"provider": "115", "account": dict(account_scope)}]}
        if action == "catalog_preview":
            return {"items": [{"status": "ready", "before": None, "after": {"kind": "custom"}}]}
        return {"items": []}

    manager = PhoneManagement(
        account_scope,
        "http://192.168.1.50:8081",
        rpc=fake_rpc,
        scopes=SCOPES | PLAYBACK_SCOPES,
    )
    pair_code = manager.pairing_url.split("#", 1)[1]
    base_headers = {"Host": "192.168.1.50:8081", "Origin": "http://192.168.1.50:8081"}
    pair_res, cookie_hdr = manager.handle(
        "/manage/api/pair",
        {**base_headers, "Accept-Language": "en-US,en;q=0.9"},
        json.dumps({"code": pair_code}).encode("utf-8"),
    )
    # Browser Accept-Language: en-US MUST NOT switch TV locale from zh-CN!
    assert pair_res["locale"] == "zh-CN"
    assert pair_res["ui_strings"]["91303"] == "作品整理"
    assert len(encode(pair_res)) <= MAX_REPLY

    cookie_kv = cookie_hdr.split(";", 1)[0]
    csrf = pair_res["csrf"]
    auth_headers = {**base_headers, "Cookie": cookie_kv, "X-Bobbi-CSRF": csrf}

    # Record a preview digest before switching language
    cmd = [{"file_id": "a" * 64, "expected_revision": 1, "action": "ignore", "mapping": None}]
    manager.handle("/manage/api", auth_headers, json.dumps({"action": "catalog_preview", "params": {"commands": cmd}}).encode("utf-8"))
    assert len(manager.previews) == 1
    saved_previews = dict(manager.previews)

    # Switch TV language live to English (en_gb) WITHOUT reloading any Python module or restarting PhoneManagement!
    en_po = _parse_po_strict(BOBBI / "resources/language/English/strings.po")
    active["locale"] = "resource.language.en_gb"
    assert i18n.current_locale() == "en_gb"
    en_ten = {cid: kodi_utils.translation(cid) for cid in ten_ids}
    assert en_ten[90049] == "Scrape again"
    for cid in ten_ids:
        assert en_ten[cid] == (en_po[cid][1] or en_po[cid][0])
        assert en_ten[cid] != zh_ten[cid]

    en_steps = dict(onboarding.steps({"standard_playback": True}, helper_state="ready", library_count=3))
    assert "1. Player · OK" == en_steps["check"]
    assert all(len(v) <= 32 for v in en_steps.values())
    win_en = account_dialog.create(tmp_path / "qr.png")
    assert "Confirm on your phone" in win_en.message

    sess_en, _ = manager.handle(
        "/manage/api/session",
        {**base_headers, "Cookie": cookie_kv, "Accept-Language": "zh-CN,zh;q=0.9"},
        b"{}",
    )
    # Browser Accept-Language: zh-CN MUST NOT override English TV locale!
    assert sess_en["locale"] == "en-GB"
    assert sess_en["ui_strings"]["91303"] == "Organize Works"
    assert sess_en["csrf"] == csrf
    assert manager.previews == saved_previews
    assert len(encode(sess_en)) <= MAX_REPLY

    # Round-trip back to Chinese (zh_cn)
    active["locale"] = "resource.language.zh_cn"
    assert kodi_utils.translation(90049) == "重新查找片源"
    sess_zh2, _ = manager.handle("/manage/api/session", {**base_headers, "Cookie": cookie_kv}, b"{}")
    assert sess_zh2["locale"] == "zh-CN"
    assert sess_zh2["ui_strings"]["91303"] == "作品整理"
    assert sess_zh2["csrf"] == csrf
    assert manager.previews == saved_previews


def test_manage_js_uses_single_authoritative_po_source():
    zh_po = _parse_po_strict(BOBBI / "resources/language/resource.language.zh_cn/strings.po")
    en_po = _parse_po_strict(BOBBI / "resources/language/English/strings.po")
    js = (BOBBI / "resources/web/manage.js").read_text(encoding="utf-8")
    matches = list(re.finditer(r"\bt\(\s*(91\d{3})\s*,\s*'((?:[^'\\]|\\.)*)'", js))
    matches += list(re.finditer(r"\[\s*'[^']*'\s*,\s*(91\d{3})\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]", js))
    assert len(matches) >= 120
    for m in matches:
        code = int(m.group(1))
        js_zh = m.group(2).replace("\\n", "\n").replace("\\'", "'")
        assert code in en_po and code in zh_po, f"manage.js references missing PO #{code}"
        assert zh_po[code][1] == js_zh, f"Divergent fallback in manage.js for #{code}: {js_zh!r} != {zh_po[code][1]!r}"


def test_settings_ia_preserves_all_233_ids_45_hidden_and_53_action_routes():
    en_po = _parse_po_strict(BOBBI / "resources/language/English/strings.po")
    zh_po = _parse_po_strict(BOBBI / "resources/language/resource.language.zh_cn/strings.po")
    settings_root = ET.parse(BOBBI / "resources/settings.xml").getroot()

    categories = settings_root.findall(".//category")
    assert [c.get("id") for c in categories] == [
        "interface_category",
        "home_navigation_category",
        "playback_subtitles_category",
        "content_preferences_category",
        "network_devices_category",
        "maintenance_category",
    ]
    for c in categories:
        lbl = int(c.get("label"))
        assert lbl in en_po and lbl in zh_po

    settings = settings_root.findall(".//setting")
    setting_ids = [s.get("id") for s in settings]
    assert len(setting_ids) == 233
    assert len(set(setting_ids)) == 233

    hidden = {s.get("id") for s in settings if s.findtext("visible") == "false"}
    assert "update_action" in hidden
    assert "skip_intro_auto" in hidden
    assert "trakt_client" in hidden and "trakt_secret" in hidden
    assert len(hidden) == 45

    # Verify numeric PO labels on cinema_continuity_enabled and audio/subtitle options
    cont = settings_root.find(".//setting[@id='cinema_continuity_enabled']")
    assert cont.get("label").isdigit() and cont.get("help").isdigit()
    for lang_sid in ("auto_audio_language", "subtitle_language"):
        node = settings_root.find(f".//setting[@id='{lang_sid}']")
        for opt in node.findall("constraints/options/option"):
            assert opt.get("label", "").isdigit(), f"Non-numeric option label in {lang_sid}: {opt.attrib}"
            assert int(opt.get("label")) in en_po

    # Verify all 53 action routes exist in ROUTE_SPECS
    from lib.router import ROUTE_SPECS

    route_names = {act_name for spec in ROUTE_SPECS for act_name in spec.actions}
    assert route_names, "Could not extract ROUTE_SPECS actions from router.py"

    actions = [s for s in settings if s.get("type") == "action"]
    assert len(actions) == 53
    for act in actions:
        data = act.findtext("data", "").strip()
        m = re.fullmatch(r"RunPlugin\((plugin://plugin\.video\.bobbi/\?[^)]+)\)", data)
        assert m, f"Unexpected action data on {act.get('id')}: {data}"
        qs = parse_qs(urlsplit(m.group(1)).query)
        action_name = qs["action"][0]
        assert action_name in route_names, f"Action {act.get('id')} -> {action_name} missing in ROUTE_SPECS"

    # Cross-check against settings-migration.json if available in scratch pack
    pack_json = Path(
        r"C:\Users\theon\.gemini\antigravity\brain\52d8d26d-5b40-4200-86e4-d5d0ec60ee16\scratch\pack_20261126"
        r"\BobbiTV_CE2185_Integrated_ExecutionPack_20261126\spec\settings\settings-migration.json"
    )
    if pack_json.is_file():
        expected_meta = json.loads(pack_json.read_text(encoding="utf-8"))["settings"]
        assert {row["id"] for row in expected_meta} == set(setting_ids)
        expected_hidden = {row["id"] for row in expected_meta if row["explicitly_hidden"]}
        assert hidden == expected_hidden | {"update_action"}


def test_android_helper_and_host_resources_and_staging():
    res_root = ROOT / "android/app/src/main/res"
    zh_default = {n.get("name"): (n.text or "") for n in ET.parse(res_root / "values/strings.xml").getroot().findall("string")}
    zh_cn = {n.get("name"): (n.text or "") for n in ET.parse(res_root / "values-zh-rCN/strings.xml").getroot().findall("string")}
    en = {n.get("name"): (n.text or "") for n in ET.parse(res_root / "values-en/strings.xml").getroot().findall("string")}

    assert set(zh_default) == set(zh_cn) == set(en)
    assert len(en) >= 75
    spec_re = re.compile(r"%\d+\$[sd]")
    for key in en:
        assert zh_default[key].strip() and en[key].strip()
        assert spec_re.findall(zh_default[key]) == spec_re.findall(en[key]), f"Android format mismatch on {key}"

    # Zero inline CJK in Java UI/service files and no global Locale.setDefault mutation
    java_files = [
        ROOT / "android/app/src/main/java/org/bobbi/helper/MainActivity.java",
        ROOT / "android/app/src/main/java/org/bobbi/helper/EnginePresentation.java",
        ROOT / "android/app/src/main/java/org/bobbi/helper/EngineService.java",
        ROOT / "android/app/src/main/java/org/bobbi/helper/AppLocale.java",
        ROOT / "native/android-host/java/org/bobbi/helper/EngineService.java",
        ROOT / "native/android-host/java/org/bobbi/helper/HostBridge.java",
    ]
    for jf in java_files:
        src = jf.read_text(encoding="utf-8")
        assert not re.search(r"[\u4e00-\u9fff]", src), f"Inline CJK found in {jf}"
        assert "Locale.setDefault" not in src, f"Forbidden global Locale.setDefault in {jf}"

    # Host string resources parity
    host_res = ROOT / "native/android-host/res"
    h_def = {n.get("name"): (n.text or "") for n in ET.parse(host_res / "values/bobbi_host_strings.xml").getroot().findall("string")}
    h_zh = {n.get("name"): (n.text or "") for n in ET.parse(host_res / "values-zh-rCN/bobbi_host_strings.xml").getroot().findall("string")}
    h_en = {n.get("name"): (n.text or "") for n in ET.parse(host_res / "values-en/bobbi_host_strings.xml").getroot().findall("string")}
    assert set(h_def) == set(h_zh) == set(h_en)
    assert "bobbi_host_channel_name" in h_en

    stage_src = (ROOT / "native/stage-android-host.py").read_text(encoding="utf-8")
    assert "values-en" in stage_src and "values-zh-rCN" in stage_src and "bobbi_host_strings.xml" in stage_src


def test_windows_nsis_and_win32_launcher_bilingual_resources(tmp_path):
    nsi = (ROOT / "native/windows/installer.nsi").read_text(encoding="utf-8")
    zh_pos = nsi.index('!insertmacro MUI_LANGUAGE "SimpChinese"')
    en_pos = nsi.index('!insertmacro MUI_LANGUAGE "English"')
    assert zh_pos < en_pos, "SimpChinese must be declared first as default fresh-install language"
    assert 'Software\\bobbi TV\\Installer' in nsi
    for msg_id in ("MSG_REQUIRE_X64", "MSG_CLOSE_BEFORE_UNINSTALL", "MSG_CHOOSE_EMPTY_DIR", "MSG_NOT_MANAGED_GENERATION", "DESC_SEC_MAIN"):
        assert f"LangString {msg_id} ${{LANG_SIMPCHINESE}}" in nsi
        assert f"LangString {msg_id} ${{LANG_ENGLISH}}" in nsi
    # Ensure no hardcoded English literal remains in MessageBox calls
    for m in re.finditer(r'MessageBox\s+\S+\s+"([^"]+)"', nsi):
        assert m.group(1).startswith("$(") and m.group(1).endswith(")"), f"Unlocalized NSIS MessageBox: {m.group(0)}"

    header = (ROOT / "native/windows/launcher.h").read_text(encoding="utf-8")
    rc = (ROOT / "native/windows/launcher.rc").read_text(encoding="utf-8")
    cpp = (ROOT / "native/windows/launcher.cpp").read_text(encoding="utf-8")
    for sym in ("IDS_APP_TITLE_ZH", "IDS_STARTUP_ERROR_ZH", "IDS_APP_TITLE_EN", "IDS_STARTUP_ERROR_EN"):
        assert sym in header and sym in rc and sym in cpp
    assert "LoadStringW" in cpp

    vcvars = Path(r"D:\AM6B-Project\toolchains\VS2022\VC\Auxiliary\Build\vcvars64.bat")
    if os.name == "nt" and vcvars.is_file():
        res_out = tmp_path / "launcher.res"
        obj_out = tmp_path / "launcher.obj"
        exe_out = tmp_path / "bobbi_test.exe"
        bat_out = tmp_path / "build_launcher_test.cmd"
        win_dir = ROOT / "native/windows"
        bat_out.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    f'call "{vcvars}" >nul',
                    "if errorlevel 1 exit /b %errorlevel%",
                    f'rc /nologo /c65001 /fo"{res_out}" "{win_dir / "launcher.rc"}"',
                    "if errorlevel 1 exit /b %errorlevel%",
                    (
                        f'cl /nologo /std:c++17 /utf-8 /O2 /MT /EHsc /DUNICODE /D_UNICODE '
                        f'/I"{win_dir}" /Fo"{obj_out}" "{win_dir / "launcher.cpp"}" "{res_out}" '
                        f'/Fe:"{exe_out}" /link /SUBSYSTEM:WINDOWS shell32.lib ole32.lib bcrypt.lib user32.lib advapi32.lib'
                    ),
                    "exit /b %errorlevel%",
                ]
            )
            + "\r\n",
            encoding="utf-8",
        )
        proc = subprocess.run(["cmd.exe", "/d", "/c", str(bat_out)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, f"MSVC launcher build failed:\n{proc.stdout}\n{proc.stderr}"
        assert exe_out.is_file()

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
        kernel32.LoadLibraryExW.restype = ctypes.c_void_p
        kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
        user32.LoadStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
        user32.LoadStringW.restype = ctypes.c_int

        hmod = kernel32.LoadLibraryExW(str(exe_out), None, 0x00000002)  # LOAD_LIBRARY_AS_DATAFILE
        assert hmod, "Failed to load compiled bobbi_test.exe as Win32 resource datafile"
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n_zh = user32.LoadStringW(hmod, 102, buf, 1024)
            assert n_zh > 0 and "未能安全启动" in buf.value
            n_en = user32.LoadStringW(hmod, 202, buf, 1024)
            assert n_en > 0 and "could not start safely" in buf.value
        finally:
            kernel32.FreeLibrary(hmod)
