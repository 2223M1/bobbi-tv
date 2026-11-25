"""R3 L1 host zh_cn pack verification, bootstrap minimal i18n, CJK font gate, and 3-way language policy tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'addons/script.module.bobbi.platform/lib') not in sys.path:
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))

from bobbi_platform import bootstrap_i18n as bi18n
from bobbi_platform.updates import UpdateError
import bobbi_platform.ce_install_ui as ui
from bobbi_platform.ce_install_ui import (
    KodiHost,
    LANGUAGE_MARKER,
    classify_language_profile,
    ensure_host_language,
    load_verified_zh_cn_pack,
    readable_text,
)
import build_ce_entry

PACK_DIR = ROOT / 'addons/script.module.bobbi.platform/resources/language_packs'
PACK_ZIP = PACK_DIR / bi18n.ZH_CN_FILENAME
PROVENANCE = PACK_DIR / 'provenance.json'


def test_embedded_official_zh_cn_pack_and_provenance_integrity(tmp_path):
    assert PACK_ZIP.is_file() and PROVENANCE.is_file()
    raw = PACK_ZIP.read_bytes()
    assert len(raw) == bi18n.ZH_CN_BYTES == 169288
    assert hashlib.sha256(raw).hexdigest() == bi18n.ZH_CN_SHA256

    prov = json.loads(PROVENANCE.read_text(encoding='utf-8'))
    assert prov['addon_id'] == 'resource.language.zh_cn'
    assert prov['version'] == '11.0.105'
    assert prov['sha256'] == bi18n.ZH_CN_SHA256
    assert prov['bytes'] == 169288

    info = bi18n.verify_zh_cn_archive(raw, prov)
    assert (info['addon_id'], info['version']) == ('resource.language.zh_cn', '11.0.105')
    assert load_verified_zh_cn_pack(addons_root=ROOT / 'addons') == raw

    # Tampered byte or wrong size must fail closed
    tampered = bytearray(raw)
    tampered[-10] ^= 0xFF
    with pytest.raises((ValueError, UpdateError)):
        bi18n.verify_zh_cn_archive(bytes(tampered), prov)
    with pytest.raises((ValueError, UpdateError)):
        bi18n.verify_zh_cn_archive(raw[:-1], prov)


def test_bootstrap_i18n_runs_isolated_without_platform_and_switches_dynamically():
    assert 'bootstrap_i18n.py' in build_ce_entry.BOOTSTRAP

    zh_po = bi18n.render_minimal_po('zh_cn')
    en_po = bi18n.render_minimal_po('en_gb')
    parsed_zh = bi18n.parse_po(zh_po)
    parsed_en = bi18n.parse_po(en_po)
    assert len(parsed_zh) == len(bi18n.STRINGS) == len(parsed_en)
    for _key, (num_id, zh_text, en_text) in bi18n.STRINGS.items():
        assert parsed_zh[num_id] == (en_text, zh_text)
        assert parsed_en[num_id] == (en_text, '')

    # Isolated subprocess with -I -B and no PYTHONPATH can import bootstrap_i18n standalone
    mod_path = (ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/bootstrap_i18n.py').as_posix()
    code = (
        f"import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('bi18n', '{mod_path}'); "
        f"m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        f"assert m.tr('menu_title', 'zh_cn') == '波比 TV'; "
        f"assert m.tr('menu_title', 'en_gb') == 'Bobbi TV'"
    )
    proc = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

    # Dynamic per-call locale switching without restart or import-time cache
    live_locale = {'value': 'resource.language.en_gb'}
    host = SimpleNamespace(locale=lambda: live_locale['value'])
    assert 'Checking for updates' in bi18n.tr('online_checking', host=host)
    live_locale['value'] = 'resource.language.zh_cn'
    assert '正在检查更新' in bi18n.tr('online_checking', host=host)


def test_start_default_rescue_keeps_bilingual_message_and_stable_code_when_bootstrap_missing(tmp_path, monkeypatch):
    broken_start = tmp_path / 'script.bobbi.start'
    broken_start.mkdir()
    default_src = (ROOT / 'addons/script.bobbi.start/default.py').read_text(encoding='utf-8')
    entry_copy = broken_start / 'default.py'
    entry_copy.write_text(default_src, encoding='utf-8')

    shown = []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(log=lambda *a, **k: None, LOGERROR=3))
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(
        Addon=lambda *a: SimpleNamespace(getAddonInfo=lambda _: str(broken_start))
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda p: str(p)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Dialog=lambda: SimpleNamespace(ok=lambda title, msg: shown.append((title, msg)))
    ))
    monkeypatch.delitem(sys.modules, 'bobbi_platform', raising=False)
    monkeypatch.delitem(sys.modules, 'bobbi_platform.ce_install_ui', raising=False)
    filtered_path = [str(broken_start), *[p for p in sys.path if 'addons' not in p.replace('\\', '/')]]
    monkeypatch.setattr(sys, 'path', filtered_path)

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(entry_copy), run_name='__main__')
    assert exc.value.code == 0
    assert len(shown) == 1
    title, msg = shown[0]
    assert 'Bobbi TV' in title and '操作未完成' in title
    assert '初始化 · ENTRY_BOOTSTRAP_UNAVAILABLE' in msg
    assert 'Bootstrap unavailable; re-download the full script.bobbi.start ZIP.' in msg


def test_readable_text_is_locale_aware_and_never_blocks_english_default_font():
    """R3-L10N-HOST-C03: Estuary + Default font in English never demands Arial; Chinese still checks."""
    settings = {'lookandfeel.font': 'Default', 'locale.language': 'resource.language.en_gb'}
    prompts = []

    def fake_rpc(method, params=None):
        if method == 'Settings.GetSettingValue':
            return {'value': settings[params['setting']]}
        if method == 'Settings.SetSettingValue':
            settings[params['setting']] = params['value']
            return True
        raise AssertionError(method)

    dialog = SimpleNamespace(
        yesno=lambda *args: (prompts.append(args) or True),
        ok=lambda *args: None,
    )
    host = SimpleNamespace(
        skin=lambda: 'skin.estuary',
        locale=lambda: settings['locale.language'],
        check_idle=lambda: None,
    )

    # English UI with no CJK prompt -> passes immediately without touching font or prompting!
    assert readable_text(host, dialog, rpc_fn=fake_rpc) is True
    assert prompts == []
    assert settings['lookandfeel.font'] == 'Default'

    # Chinese UI on Estuary + Default -> prompts to switch to Arial and verifies readback
    settings['locale.language'] = 'resource.language.zh_cn'
    assert readable_text(host, dialog, rpc_fn=fake_rpc) is True
    assert len(prompts) == 1
    assert settings['lookandfeel.font'] == 'Arial'


def test_fresh_managed_profile_defaults_to_verified_zh_cn_once_with_readback(tmp_path):
    """R3-L10N-HOST-C01: Fresh profile seeds verified zh_cn, verifies readback, writes init marker once."""
    userdata = tmp_path / 'userdata'
    addons = tmp_path / 'addons'
    work = userdata / 'addon_data/script.bobbi.start'
    addons.mkdir(parents=True)
    work.mkdir(parents=True)

    settings = {'locale.language': 'resource.language.en_gb', 'lookandfeel.font': 'Arial'}
    enabled_addons = set()

    def fake_rpc(method, params=None):
        if method == 'Settings.GetSettingValue':
            return {'value': settings[params['setting']]}
        if method == 'Settings.SetSettingValue':
            settings[params['setting']] = params['value']
            return True
        if method == 'Addons.SetAddonEnabled':
            enabled_addons.add(params['addonid'])
            return 'OK'
        raise AssertionError(method)

    def details(aid):
        if aid == 'kodi.resource':
            return {'version': '1.0.0', 'enabled': True}
        if (addons / aid / 'addon.xml').is_file():
            return {'version': '11.0.105', 'enabled': aid in enabled_addons}
        return None

    host = SimpleNamespace(
        locale=lambda: settings['locale.language'],
        details=details,
        refresh=lambda: None,
        skin=lambda: 'skin.estuary',
        check_idle=lambda: None,
    )
    installer = SimpleNamespace(work=work, addons=addons, userdata=userdata, trust=None, _read=lambda: None)
    dialog = SimpleNamespace(
        select=lambda *a, **k: pytest.fail('Fresh profile must not prompt language ambiguity'),
        yesno=lambda *a, **k: True,
        ok=lambda *a, **k: None,
    )

    assert classify_language_profile(host.locale(), work=work, addons_root=addons, userdata_root=userdata) == 'fresh_managed'
    result = ensure_host_language(host, installer, dialog, rpc_fn=fake_rpc)
    assert result['action'] == 'default_zh_cn'
    assert result['locale'] == 'resource.language.zh_cn'
    assert settings['locale.language'] == 'resource.language.zh_cn'
    assert 'resource.language.zh_cn' in enabled_addons
    assert not (addons / 'resource.language.zh_cn/origin').exists()
    marker = json.loads((work / LANGUAGE_MARKER).read_text(encoding='utf-8'))
    assert marker['decision'] == 'default_zh_cn'

    # User later switches to English explicitly -> subsequent runs preserve English and never re-force zh_cn!
    settings['locale.language'] = 'resource.language.en_gb'
    second = ensure_host_language(host, installer, dialog, rpc_fn=fake_rpc)
    assert second['action'] == 'already_initialized'
    assert settings['locale.language'] == 'resource.language.en_gb'


def test_explicit_existing_and_ambiguous_historical_language_profiles(tmp_path, monkeypatch):
    """R3-L10N-HOST-C02: Explicit EN preserved; ambiguous historical prompts once; corrupt pack never writes fake marker."""
    # Case 1: Explicit existing English choice in guisettings.xml -> preserved without prompting
    u1, a1, w1 = tmp_path / 'u1', tmp_path / 'a1', tmp_path / 'u1/addon_data/script.bobbi.start'
    a1.mkdir(parents=True)
    w1.mkdir(parents=True)
    (u1 / 'guisettings.xml').write_text(
        '<settings version="2"><setting id="locale.language">resource.language.en_gb</setting></settings>',
        encoding='utf-8',
    )
    host1 = SimpleNamespace(
        locale=lambda: 'resource.language.en_gb',
        details=lambda aid: {'version': '1.0.0', 'enabled': True} if aid == 'kodi.resource' else None,
        refresh=lambda: None,
        skin=lambda: 'skin.estuary',
        check_idle=lambda: None,
    )
    inst1 = SimpleNamespace(work=w1, addons=a1, userdata=u1, trust=None, _read=lambda: None)
    assert classify_language_profile('resource.language.en_gb', work=w1, addons_root=a1, userdata_root=u1) == 'explicit_existing'
    res1 = ensure_host_language(
        host1, inst1,
        SimpleNamespace(select=lambda *a, **k: pytest.fail('Must not prompt explicit EN user')),
        rpc_fn=lambda *a, **k: {},
    )
    assert res1 == {'action': 'preserved_existing', 'locale': 'resource.language.en_gb'}

    # Case 2: Ambiguous historical Kodi (default="true" en_gb + historical sources.xml, no Bobbi marker)
    u2, a2, w2 = tmp_path / 'u2', tmp_path / 'a2', tmp_path / 'u2/addon_data/script.bobbi.start'
    a2.mkdir(parents=True)
    w2.mkdir(parents=True)
    (u2 / 'guisettings.xml').write_text(
        '<settings version="2"><setting id="locale.language" default="true">resource.language.en_gb</setting></settings>',
        encoding='utf-8',
    )
    (u2 / 'sources.xml').write_text('<sources/>', encoding='utf-8')
    inst2 = SimpleNamespace(work=w2, addons=a2, userdata=u2, trust=None, _read=lambda: None)
    assert classify_language_profile('resource.language.en_gb', work=w2, addons_root=a2, userdata_root=u2) == 'ambiguous_historical'

    # Corrupt/missing pack when user selects Chinese (choice=0) -> keeps English and NEVER writes fake marker!
    monkeypatch.setattr(ui, 'load_verified_zh_cn_pack', lambda **kw: None)
    select_calls = []
    res_missing = ensure_host_language(
        host1, inst2,
        SimpleNamespace(
            select=lambda title, opts, preselect=0: (select_calls.append((title, opts, preselect)) or 0),
            ok=lambda *a: None,
        ),
        rpc_fn=lambda *a, **k: {},
    )
    assert select_calls[0][2] == 0  # Chinese highlighted as default option!
    assert res_missing['action'] == 'pack_unavailable'
    assert not (w2 / LANGUAGE_MARKER).exists()

    # User chooses "Keep current language (English)" (choice=1) -> records choice and never re-prompts
    res_keep = ensure_host_language(
        host1, inst2,
        SimpleNamespace(select=lambda title, opts, preselect=0: 1, ok=lambda *a: None),
        rpc_fn=lambda *a, **k: {},
    )
    assert res_keep == {'action': 'kept_current', 'locale': 'resource.language.en_gb'}
    assert (w2 / LANGUAGE_MARKER).is_file()
    res_again = ensure_host_language(
        host1, inst2,
        SimpleNamespace(select=lambda *a, **k: pytest.fail('Must not re-prompt after user chose keep_current')),
        rpc_fn=lambda *a, **k: {},
    )
    assert res_again['action'] == 'already_initialized'


def test_existing_zh_cn_setting_with_missing_language_addon_provisions_pack_on_upgrade(tmp_path):
    """Real-box CE2185 upgrade case: locale.language is resource.language.zh_cn but addon is absent."""
    userdata = tmp_path / 'userdata'
    addons = tmp_path / 'addons'
    work = userdata / 'addon_data/script.bobbi.start'
    (addons / 'script.module.bobbi.platform/resources/language_packs').mkdir(parents=True)
    (addons / 'script.module.bobbi.platform/resources/language_packs' / bi18n.ZH_CN_FILENAME).write_bytes(PACK_ZIP.read_bytes())
    (addons / 'script.module.bobbi.platform/resources/language_packs/provenance.json').write_bytes(PROVENANCE.read_bytes())
    work.mkdir(parents=True)
    (userdata / 'guisettings.xml').write_text(
        '<settings version="2"><setting id="locale.language">resource.language.zh_cn</setting></settings>',
        encoding='utf-8',
    )

    settings = {'locale.language': 'resource.language.zh_cn', 'lookandfeel.font': 'Default'}
    enabled_addons = set()

    def fake_rpc(method, params=None):
        if method == 'Settings.GetSettingValue':
            return {'value': settings[params['setting']]}
        if method == 'Settings.SetSettingValue':
            settings[params['setting']] = params['value']
            return True
        if method == 'Addons.SetAddonEnabled':
            enabled_addons.add(params['addonid'])
            return 'OK'
        raise AssertionError(method)

    def details(aid):
        if aid == 'kodi.resource':
            return {'version': '1.0.0', 'enabled': True}
        if aid == 'plugin.video.bobbi':
            return {'version': '0.1.99', 'enabled': True}
        if (addons / aid / 'addon.xml').is_file():
            return {'version': '11.0.105', 'enabled': aid in enabled_addons}
        return None

    host = SimpleNamespace(
        locale=lambda: settings['locale.language'],
        details=details,
        refresh=lambda: None,
        skin=lambda: 'skin.bobbi.cinema',
        check_idle=lambda: None,
    )
    installer = SimpleNamespace(
        work=work,
        addons=addons,
        userdata=userdata,
        trust=None,
        _read=lambda: {'sequence': 2026102188, 'phase': 'complete'},
    )
    dialog = SimpleNamespace(
        select=lambda *a, **k: pytest.fail('Must not prompt when locale.language is already zh_cn'),
        yesno=lambda *a, **k: pytest.fail('skin.bobbi.cinema must not prompt for Estuary Arial'),
        ok=lambda *a, **k: None,
    )

    res = ensure_host_language(host, installer, dialog, rpc_fn=fake_rpc)
    assert res['action'] == 'explicit_existing'
    assert res['repaired'] is True
    assert res['locale'] == 'resource.language.zh_cn'
    assert 'resource.language.zh_cn' in enabled_addons
    assert (addons / 'resource.language.zh_cn/addon.xml').is_file()
