import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests
import xbmcgui

from lib.api.stremio.addon_manager import (
    build_addon_instance_key,
    build_legacy_addon_instance_key,
)
from lib.clients.stremio.constants import (
    STREMIO_ADDONS_CATALOGS_KEY,
    STREMIO_ADDONS_KEY,
    STREMIO_TV_ADDONS_KEY,
    STREMIO_USER_ADDONS,
    decode_selected_ids,
    encode_selected_ids,
)
from lib.db.cached import cache
from lib.db.pickle_db import PickleDatabase
from lib.utils.general.utils import (
    clear_all_cache,
    clear_debrid_cache,
    clear_mdblist_cache,
    clear_stremio_cache,
    clear_tmdb_cache,
    clear_trakt_db_cache,
)
from lib.utils.kodi.utils import (
    ADDON,
    ADDON_ID,
    ADDON_PATH,
    ADDON_PROFILE_PATH,
    ADDON_VERSION,
    dialog_ok,
    get_cached_setting_property,
    get_setting,
    notification,
    set_cached_setting_property,
    set_setting,
    translatePath,
    translation,
)

BACKUP_VERSION = 1
CUSTOM_ADDON_EXPIRY = timedelta(days=365 * 20)
SETTINGS_XML_PATH = os.path.join(ADDON_PATH, "resources", "settings.xml")
EXPORT_FILENAME_TEMPLATE = "jacktook-settings-backup-{timestamp}.json"
RESTORE_SOURCE_FILE = "file"
RESTORE_SOURCE_URL = "url"
MAX_BACKUP_BYTES = 8 * 1024 * 1024

CUSTOM_SELECTION_KEYS = {
    "stream": STREMIO_ADDONS_KEY,
    "catalog": STREMIO_ADDONS_CATALOGS_KEY,
    "tv": STREMIO_TV_ADDONS_KEY,
}

SENSITIVE_SETTING_IDS = {
    "real_debrid_token",
    "alldebrid_token",
    "debrider_token",
    "torbox_token",
    "offcloud_token",
    "premiumize_token",
    "easynews_password",
    "stremio_pass",
    "stremio_auth_key",
    "jackett_apikey",
    "prowlarr_apikey",
    "jackgram_token",
    "deepl_api_key",
    "fanart_client_key",
    "tmdb_api_key",
    "mdblist_api_key",
    "trakt_secret",
    "simkl_access_token",
    "nuvio_access_token",
    "nuvio_refresh_token",
    "nuvio_expires_at",
    "webdav_password",
}

IDENTITY_SETTING_IDS = {
    "stremio_email",
    "easynews_user",
    "webdav_username",
    "real_debrid_user",
    "alldebrid_user",
    "torbox_user",
    "offcloud_user",
    "trakt_user",
}

AUTH_STATE_SETTING_IDS = {
    "real_debid_authorized",
    "alldebrid_authorized",
    "debrider_authorized",
    "stremio_loggedin",
    "is_trakt_auth",
    "simkl_authenticated",
    "nuvio_authenticated",
    "nuvio_profile_id",
}

SCRUBBED_SETTING_IDS = SENSITIVE_SETTING_IDS | IDENTITY_SETTING_IDS | AUTH_STATE_SETTING_IDS

EXTRA_DYNAMIC_SETTINGS = {
    "trakt_token": "",
    "trakt_refresh": "",
    "trakt_expires": "",
}

SENSITIVE_DYNAMIC_SETTING_IDS = set(EXTRA_DYNAMIC_SETTINGS)


def _stringify_setting_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _load_settings_schema(settings_xml_path=SETTINGS_XML_PATH):
    root = ET.parse(settings_xml_path).getroot()
    schema = {}
    for setting in root.findall(".//setting"):
        setting_id = setting.get("id")
        setting_type = setting.get("type")
        if not setting_id or setting_type == "action":
            continue
        default_node = setting.find("default")
        default_value = ""
        if default_node is not None:
            default_value = default_node.text or ""
        schema[setting_id] = {
            "type": setting_type or "string",
            "default": default_value,
        }
    return schema


def _setting_clear_value(setting_id, schema_entry):
    if setting_id in AUTH_STATE_SETTING_IDS:
        return "false"
    if setting_id == "trakt_user":
        return schema_entry.get("default") or "unknown_user"
    return schema_entry.get("default", "")


def _custom_addon_key(addon):
    return build_addon_instance_key(addon) or None


def _custom_addon_keys(addon):
    return {
        key for key in (_custom_addon_key(addon), build_legacy_addon_instance_key(addon)) if key
    }


def _get_custom_stremio_addons(user_addons=None):
    user_addons = user_addons if user_addons is not None else (cache.get(STREMIO_USER_ADDONS) or [])
    custom_addons = []
    for addon in user_addons:
        if addon.get("transportName") != "custom":
            continue
        if not _custom_addon_key(addon):
            continue
        custom_addons.append(addon)
    return custom_addons


def _get_custom_selection_map(custom_addons):
    key_map = {
        candidate: _custom_addon_key(addon)
        for addon in custom_addons
        for candidate in _custom_addon_keys(addon)
    }
    selections = {}
    for label, cache_key in CUSTOM_SELECTION_KEYS.items():
        selected_keys = decode_selected_ids(cache.get(cache_key))
        selections[label] = [key_map[key] for key in selected_keys if key in key_map]
    return selections


def build_backup_payload(strip_sensitive=False, settings_xml_path=SETTINGS_XML_PATH):
    schema = _load_settings_schema(settings_xml_path)
    settings_payload = {}
    for setting_id in schema:
        if strip_sensitive and setting_id in SCRUBBED_SETTING_IDS:
            continue
        settings_payload[setting_id] = ADDON.getSetting(setting_id)

    cache_payload = {}
    if not strip_sensitive:
        custom_addons = _get_custom_stremio_addons()
        cache_payload["custom_stremio_addons"] = custom_addons
        cache_payload["custom_stremio_selections"] = _get_custom_selection_map(custom_addons)

    dynamic_settings_payload = {}
    for setting_id, default_value in EXTRA_DYNAMIC_SETTINGS.items():
        if strip_sensitive and setting_id in SENSITIVE_DYNAMIC_SETTING_IDS:
            continue
        dynamic_settings_payload[setting_id] = (
            get_cached_setting_property(setting_id) or default_value
        )

    return {
        "backup_version": BACKUP_VERSION,
        "addon_id": ADDON_ID,
        "addon_version": ADDON_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "strip_sensitive": bool(strip_sensitive),
        "custom_stremio_addons_included": not bool(strip_sensitive),
        "settings": settings_payload,
        "dynamic_settings": dynamic_settings_payload,
        "cache": cache_payload,
    }


def _ensure_backup_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Backup payload must be an object")

    settings_payload = payload.get("settings")
    dynamic_settings_payload = payload.get("dynamic_settings", {})
    cache_payload = payload.get("cache", {})
    if not isinstance(settings_payload, dict):
        raise ValueError("Backup settings must be an object")
    if not isinstance(dynamic_settings_payload, dict):
        raise ValueError("Backup dynamic settings must be an object")
    if not isinstance(cache_payload, dict):
        raise ValueError("Backup cache must be an object")

    custom_addons = cache_payload.get("custom_stremio_addons", [])
    if not isinstance(custom_addons, list):
        raise ValueError("Custom Stremio addons must be a list")

    custom_selections = cache_payload.get("custom_stremio_selections", {})
    if not isinstance(custom_selections, dict):
        raise ValueError("Custom Stremio selections must be an object")

    return settings_payload, dynamic_settings_payload, cache_payload


def _normalize_custom_addons(custom_addons):
    normalized = []
    seen_keys = set()
    for addon in custom_addons:
        if not isinstance(addon, dict):
            continue
        addon = dict(addon)
        addon["transportName"] = "custom"
        addon_key = _custom_addon_key(addon)
        if not addon_key or addon_key in seen_keys:
            continue
        seen_keys.add(addon_key)
        normalized.append(addon)
    return normalized


def _filtered_custom_selection_map(cache_payload, custom_addons):
    key_map = {
        candidate: _custom_addon_key(addon)
        for addon in custom_addons
        for candidate in _custom_addon_keys(addon)
    }
    raw_selections = cache_payload.get("custom_stremio_selections", {})
    filtered = {}
    for label in CUSTOM_SELECTION_KEYS:
        values = raw_selections.get(label, [])
        if not isinstance(values, list):
            values = []
        filtered[label] = [key_map[value] for value in values if value in key_map]
    return filtered


def apply_backup_payload(payload, settings_xml_path=SETTINGS_XML_PATH):
    schema = _load_settings_schema(settings_xml_path)
    settings_payload, dynamic_settings_payload, cache_payload = _ensure_backup_payload(payload)
    strip_sensitive = bool(payload.get("strip_sensitive"))

    for setting_id, value in settings_payload.items():
        if setting_id not in schema:
            continue
        set_setting(setting_id, _stringify_setting_value(value))

    for setting_id, default_value in EXTRA_DYNAMIC_SETTINGS.items():
        if strip_sensitive:
            set_cached_setting_property(setting_id, default_value)
            continue
        set_cached_setting_property(
            setting_id,
            _stringify_setting_value(dynamic_settings_payload.get(setting_id, default_value)),
        )

    if strip_sensitive:
        for setting_id in SCRUBBED_SETTING_IDS:
            schema_entry = schema.get(setting_id)
            if not schema_entry:
                continue
            set_setting(setting_id, _setting_clear_value(setting_id, schema_entry))

    current_user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    current_custom_addons = _get_custom_stremio_addons(current_user_addons)
    current_custom_keys = {
        key for addon in current_custom_addons for key in _custom_addon_keys(addon)
    }
    non_custom_addons = [
        addon for addon in current_user_addons if addon.get("transportName") != "custom"
    ]

    restored_custom_addons = []
    restored_selection_map = {label: [] for label in CUSTOM_SELECTION_KEYS}
    if not strip_sensitive:
        restored_custom_addons = _normalize_custom_addons(
            cache_payload.get("custom_stremio_addons", [])
        )
        restored_selection_map = _filtered_custom_selection_map(
            cache_payload, restored_custom_addons
        )

    cache.set(
        STREMIO_USER_ADDONS,
        non_custom_addons + restored_custom_addons,
        CUSTOM_ADDON_EXPIRY,
    )

    for label, cache_key in CUSTOM_SELECTION_KEYS.items():
        selected_keys = decode_selected_ids(cache.get(cache_key))
        selected_keys = [key for key in selected_keys if key not in current_custom_keys]
        for backup_key in restored_selection_map[label]:
            if backup_key not in selected_keys:
                selected_keys.append(backup_key)
        cache.set(cache_key, encode_selected_ids(selected_keys), CUSTOM_ADDON_EXPIRY)


def reset_all_settings(settings_xml_path=SETTINGS_XML_PATH):
    schema = _load_settings_schema(settings_xml_path)
    for setting_id, schema_entry in schema.items():
        set_setting(setting_id, _setting_clear_value(setting_id, schema_entry))

    for setting_id, default_value in EXTRA_DYNAMIC_SETTINGS.items():
        set_cached_setting_property(setting_id, default_value)

    current_user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    current_custom_addons = _get_custom_stremio_addons(current_user_addons)
    current_custom_keys = {
        key for addon in current_custom_addons for key in _custom_addon_keys(addon)
    }
    non_custom_addons = [
        addon for addon in current_user_addons if addon.get("transportName") != "custom"
    ]
    cache.set(STREMIO_USER_ADDONS, non_custom_addons, CUSTOM_ADDON_EXPIRY)

    for cache_key in CUSTOM_SELECTION_KEYS.values():
        selected_keys = decode_selected_ids(cache.get(cache_key))
        selected_keys = [key for key in selected_keys if key not in current_custom_keys]
        cache.set(cache_key, encode_selected_ids(selected_keys), CUSTOM_ADDON_EXPIRY)


def _clear_factory_reset_database_state():
    pickle_db = PickleDatabase()
    for key in ("jt:watch", "jt:lth", "jt:lfh", "jt:lib"):
        pickle_db.set_key(key, {}, commit=False)
    for key in (
        "search_query",
        "search_catalog_query",
        "anime_query",
        "collection_search_query",
    ):
        pickle_db.set_key(key, "", commit=False)
    pickle_db.commit()


def factory_reset(settings_xml_path=SETTINGS_XML_PATH):
    reset_all_settings(settings_xml_path=settings_xml_path)
    clear_all_cache()
    clear_trakt_db_cache()
    clear_tmdb_cache()
    clear_stremio_cache()
    clear_debrid_cache()
    clear_mdblist_cache()
    cache.clear_list(key="multi")
    cache.clear_list(key="direct")
    _clear_factory_reset_database_state()


def _get_export_path(filename_template=EXPORT_FILENAME_TEMPLATE):
    folder = xbmcgui.Dialog().browse(
        0,
        translation(90268),
        "files",
        "",
        False,
        False,
        "",
    )
    if not folder:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.join(translatePath(folder), filename_template.format(timestamp=timestamp))


def _catalog_context(dialog, required_scope=None):
    """Reuse the current profile's existing Host and logged-in account only."""
    from bobbi_platform.paths import ProfileBinding
    from bobbi_platform.runtime import bind_call
    binding = ProfileBinding()
    rpc = bind_call(binding.root() / 'runtime.json')
    binding.require_current()
    accounts = [row for row in rpc('pan_status', {})['providers'] if
        row['provider'] != '115' and row['account']['authenticated'] and
        (required_scope is None or all(row['account'].get(key) == value for key, value in required_scope.items()))]
    binding.require_current()
    if not accounts:
        dialog.ok('人工片库描述', '请先在当前 Kodi 用户中登录对应网盘并登记、扫描文件。此操作不会复制或切换账号。')
        return None
    selected = dialog.select('当前 Kodi 用户 · 选择片库账号', [row['label'] for row in accounts]) if len(accounts) > 1 else 0
    if not 0 <= selected < len(accounts):
        return None
    expected = accounts[selected]['account']

    def invoke(action, **body):
        binding.require_current()
        result = rpc(action, dict(expected=expected, **body))
        binding.require_current()
        return result

    return expected, invoke, binding.require_current


def _export_catalog_descriptions(dialog):
    from bobbi_core import catalog_transfer
    context = _catalog_context(dialog)
    if context is None:
        return
    expected, invoke, scope_check = context
    offset, revision, excluded = 0, None, 0
    while True:
        records, start = [], offset
        while len(records) < catalog_transfer.MAX_ENTRIES:
            page = invoke('catalog_manual_records', offset=offset,
                limit=min(5, catalog_transfer.MAX_ENTRIES - len(records)), projection_revision=revision)
            if revision is not None and page['projection_revision'] != revision:
                raise ValueError('CATALOG_CURSOR_STALE')
            revision = page['projection_revision']
            excluded = max(excluded, page.get('excluded_supplements', 0))
            records.extend(page['items'])
            following = page['next_offset']
            if following is None:
                break
            if type(following) is not int or following <= offset:
                raise ValueError('CATALOG_CURSOR_STALE')
            offset = following
        if not records:
            dialog.ok('没有可导出的人工描述', '自动候选、账号凭据、播放进度和临时授权均不导出。'
                      + ('\n另有 %s 项补充内容关联，本版暂不迁移。' % excluded if excluded else ''))
            return
        raw = catalog_transfer.dumps(catalog_transfer.export_records(expected, records))
        target = _get_export_path('bobbi-manual-descriptions-{timestamp}-' + str(start) + '.json')
        if target is None:
            return
        scope_check()
        if not os.path.isabs(target):
            raise ValueError('Local backup file required')
        # A distinct user-selected JSON artifact, never overwrite a database
        # or settings backup and never bundle this with credential settings.
        with open(target, 'x', encoding='utf-8') as stream:
            stream.write(raw)
        dialog.ok('已导出人工片库描述', '%s 项；不含账号凭据或观看进度。' % len(records)
                  + ('\n另有 %s 项补充内容关联，本版暂不迁移。' % excluded if excluded else ''))
        if following is None or not dialog.yesno('继续导出下一份？',
                '当前文件只包含本轮最多 100 项；还有人工描述未导出。下一份继续同一只读修订。'):
            return


def _restore_catalog_descriptions(payload, dialog):
    from bobbi_core import catalog_transfer
    from bobbi_platform.catalog_ui import review_entries
    payload = catalog_transfer.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    context = _catalog_context(dialog, payload['scope'])
    if context is None:
        return
    expected, invoke, scope_check = context
    current, revision = [], None
    ids = [row['reference']['id'] for row in payload['entries']]
    for start in range(0, len(ids), 5):
        pending = ids[start:start + 5]
        while pending:
            page = invoke('catalog_manual_records', file_ids=pending,
                          projection_revision=revision)
            if revision is not None and page['projection_revision'] != revision:
                raise ValueError('CATALOG_CURSOR_STALE')
            revision = page['projection_revision']
            current.extend(page['items'])
            if page['next_offset'] is None:
                break
            observed = {row['file_ref']['id'] for row in page['items']}
            remainder = [file for file in pending if file not in observed]
            if len(remainder) >= len(pending):
                raise ValueError('CATALOG_REPLY_LIMIT')
            pending = remainder
    result = catalog_transfer.preview(payload, expected, current)['items']
    labels = {'unchanged': '已有相同描述，无需修改', 'ready': '身份和内容证据匹配',
              'review_required': '缺少内容哈希，需逐项人工核对', 'conflict': '目标已有人工修改，不覆盖',
              'unresolved': '未找到当前文件或证据已变，不导入'}
    scope_check()
    dialog.textviewer('导入差异（尚未保存）', '\n'.join(row['name'] + ' · ' + labels[row['status']]
        for row in result) + '\n\n只迁移人工描述，不导入播放授权、文件秒数、旧请求编号或账号。'
        '\n花絮等补充关系暂不迁移，目标已有此类关系时不覆盖。')
    candidates = [row for row in result if row['status'] in ('ready', 'review_required')]
    if not candidates:
        return
    selected = dialog.multiselect('逐项选择描述；缺少内容证据的文件默认不选',
        [row['name'] + ' · ' + labels[row['status']] for row in candidates],
        preselect=[index for index, row in enumerate(candidates) if row['status'] == 'ready'])
    if not selected:
        return
    scope_check()
    entries = [dict(name=candidates[index]['name'], command=candidates[index]['command']) for index in selected]
    return review_entries(dialog, expected, entries, invoke=invoke, scope_check=scope_check)


def export_settings_backup(params=None):
    dialog = xbmcgui.Dialog()
    kind = dialog.select('备份内容', ['设置备份（沿用现有敏感信息选项）', '人工片库描述（不含账号凭据）'])
    if kind not in (0, 1):
        return
    if kind == 1:
        try:
            return _export_catalog_descriptions(dialog)
        except (ValueError, OSError, RuntimeError):
            dialog.ok('人工描述未完成导出', '账号、文件索引或当前 Kodi 用户可能已变化；原文件和人工记录均保留，请刷新后重试。')
        return
    export_path = _get_export_path()
    if not export_path:
        return

    payload = build_backup_payload(bool(get_setting("settings_backup_strip_sensitive", False)))

    try:
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as backup_file:
            json.dump(payload, backup_file, indent=2, sort_keys=True)
        notification(translation(90265))
    except Exception:
        dialog_ok(translation(90267), translation(90273), export_path)


def _get_restore_path():
    restore_path = xbmcgui.Dialog().browse(
        1,
        translation(90269),
        "files",
        ".json",
        False,
        False,
        ADDON_PROFILE_PATH,
    )
    if not restore_path:
        notification(translation(90272))
        return None
    return translatePath(restore_path)


def _get_restore_source():
    selected_index = xbmcgui.Dialog().select(
        translation(90346),
        [translation(90347), translation(90348)],
    )
    if selected_index == 0:
        return RESTORE_SOURCE_FILE
    if selected_index == 1:
        return RESTORE_SOURCE_URL
    notification(translation(90277))
    return None


def _get_restore_url():
    restore_url = xbmcgui.Dialog().input(
        heading=translation(90349),
        type=xbmcgui.INPUT_ALPHANUM,
    )
    restore_url = (restore_url or "").strip()
    if not restore_url:
        notification(translation(90350))
        return None
    return restore_url


def _load_backup_payload_from_file(restore_path):
    with open(restore_path, encoding="utf-8") as backup_file:
        raw = backup_file.read(MAX_BACKUP_BYTES + 1)
    if len(raw.encode('utf-8')) > MAX_BACKUP_BYTES:
        raise ValueError('Backup exceeds local file budget')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate backup field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _load_backup_payload_from_url(restore_url):
    response = requests.get(restore_url, timeout=15)
    response.raise_for_status()
    return response.json()


def restore_settings_backup(params=None):
    restore_source = _get_restore_source()
    if not restore_source:
        return

    restore_target = (
        _get_restore_path() if restore_source == RESTORE_SOURCE_FILE else _get_restore_url()
    )
    if not restore_target:
        return

    try:
        confirmed = xbmcgui.Dialog().yesno(
            translation(90275),
            translation(90276),
        )
        if not confirmed:
            notification(translation(90277))
            return

        if restore_source == RESTORE_SOURCE_FILE:
            payload = _load_backup_payload_from_file(restore_target)
        else:
            payload = _load_backup_payload_from_url(restore_target)
        if type(payload) is dict and payload.get('schema') == 'bobbi-catalog-manual-v1':
            if restore_source != RESTORE_SOURCE_FILE:
                raise ValueError('Manual descriptions require an explicitly selected local file')
            return _restore_catalog_descriptions(payload, xbmcgui.Dialog())
        apply_backup_payload(payload)
        notification(translation(90266))
    except ValueError:
        dialog_ok(translation(90267), translation(90270))
    except requests.RequestException:
        dialog_ok(translation(90267), translation(90351), restore_target)
    except Exception:
        dialog_ok(translation(90267), translation(90274), restore_target)


def reset_all_settings_action(params=None):
    confirmed = xbmcgui.Dialog().yesno(
        translation(90278),
        translation(90279),
    )
    if not confirmed:
        notification(translation(90280))
        return

    try:
        reset_all_settings()
        notification(translation(90281))
    except Exception:
        dialog_ok(translation(90282), translation(90283))


def factory_reset_action(params=None):
    confirmed = xbmcgui.Dialog().yesno(
        translation(90285),
        translation(90286),
    )
    if not confirmed:
        notification(translation(90287))
        return

    try:
        factory_reset()
        notification(translation(90288))
    except Exception:
        dialog_ok(translation(90289), translation(90290))
