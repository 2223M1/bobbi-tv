"""Minimal generated/projected ZH/EN strings and official zh_cn pack verifier for start bootstrap.

Runs inside script.bobbi.start/bootstrap BEFORE script.module.bobbi.platform is
installed or registered in Kodi. Never imports bobbi_core or assumes xbmcaddon
can resolve script.module.bobbi.platform.
"""
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile

ZH_CN_ADDON_ID = 'resource.language.zh_cn'
ZH_CN_VERSION = '11.0.105'
ZH_CN_FILENAME = 'resource.language.zh_cn-11.0.105.zip'
ZH_CN_BYTES = 169288
ZH_CN_SHA256 = '3afd256581ffb40c6439c8f55f00db747459d97b0e664f97b84aab6a81821a9a'
ZH_CN_RELATIVE_DIR = Path('resources/language_packs')

# Authoritative minimal installer/recovery/storage/language strings (IDs 32900+).
# Resolved dynamically at call time from Kodi's active locale; never cached at import.
STRINGS = {
    'recover_retry': (32900, '重试恢复', 'Retry recovery'),
    'recover_prev': (32901, '恢复上一版本（保留个人数据）', 'Restore previous version (keep personal data)'),
    'recover_exit': (32902, '退出，稍后处理', 'Exit and handle later'),
    'recover_title': (32903, '安装未完成', 'Installation incomplete'),
    'source_title': (32904, '安装来源', 'Installation source'),
    'source_browse': (32905, '选择完整安装包', 'Choose full installation ZIP'),
    'source_embedded': (32906, '使用内附版本', 'Use embedded package'),
    'source_browse_heading': (32907, '选择波比 TV 完整安装包', 'Select Bobbi TV full installation ZIP'),
    'online_title': (32908, '波比 TV 更新', 'Bobbi TV Update'),
    'online_checking': (32909, '正在检查更新，可取消。', 'Checking for updates (cancellable).'),
    'online_up_to_date_title': (32910, '无需重复更新', 'Already up to date'),
    'online_stable_behind': (
        32911,
        '稳定版尚未追上已安装版本，等待同轨道后续更新；不会自动降级。\n',
        'Stable track has not yet caught up with the installed version; automatic downgrade is disabled.\n',
    ),
    'online_up_to_date_body': (
        32912,
        '此版本或更新版本已安装过。需要恢复时，请选择“恢复上一版本”或“选择恢复版本”。',
        'This or a newer version is already installed. Use "Restore previous version" or "Select recovery version" to roll back.',
    ),
    'online_offer_title': (32913, '更新版本', 'Update details'),
    'online_offer_body': (
        32914,
        '轨道 {track}\n已装 {installed}\n候选 {tag}\n镜像 {mirror}',
        'Track: {track}\nInstalled: {installed}\nCandidate: {tag}\nMirrors: {mirror}',
    ),
    'track_stable': (32915, '稳定版', 'Stable'),
    'track_preview': (32916, '预览版', 'Preview'),
    'not_installed': (32917, '未安装', 'Not installed'),
    'mirror_sync': (32918, '已同步', 'Synchronized'),
    'mirror_out_of_sync': (32919, '尚未同步，使用较新版本', 'Out of sync — using newer verified feed'),
    'mirror_unavailable': (32920, '部分不可用，使用已核实镜像', 'Partially unavailable — using verified mirror'),
    'mirror_unreported': (32921, '未报告', 'Not reported'),
    'online_confirm_title': (32922, '安装 {tag}', 'Install {tag}'),
    'online_confirm_body': (
        32923,
        '完整安装包约 {mb} MB，已有组件可复用。若 Kodi 询问是否保持临时皮肤，请选“是”。账号与观看记录保留。继续安装？',
        'Full package is about {mb} MB; unchanged components are reused. Choose "Yes" if Kodi asks to keep the temporary skin. Accounts and history are preserved. Continue?',
    ),
    'online_downloading': (
        32924,
        '正在下载更新，已有组件会复用。可随时取消。',
        'Downloading update; existing components are reused. Cancel anytime.',
    ),
    'menu_title': (32925, '波比 TV', 'Bobbi TV'),
    'menu_settings': (32926, '影院设置', 'Cinema settings'),
    'menu_install_local': (32927, '安装本地完整包', 'Install local full package'),
    'menu_rollback': (32928, '恢复上一版本', 'Restore previous version'),
    'menu_return_kodi': (32929, '返回 Kodi 界面', 'Return to Kodi interface'),
    'menu_online': (32930, '检查在线更新', 'Check online updates'),
    'menu_storage': (32931, '存储空间与清理', 'Storage and cleanup'),
    'menu_recovery': (32932, '选择恢复版本', 'Select recovery version'),
    'menu_track': (32933, '更新轨道（稳定版 / 预览版）', 'Update track (Stable / Preview)'),
    'track_title': (32934, '更新轨道', 'Update track'),
    'track_opt_stable': (32935, '稳定版（默认）', 'Stable (default)'),
    'track_opt_preview': (32936, '预览版（测试）', 'Preview (testing)'),
    'track_preview_confirm_title': (32937, '使用预览版？', 'Switch to preview track?'),
    'track_preview_confirm_body': (
        32938,
        '预览版可能有未验证功能。切回稳定版不会自动降级。继续？',
        'Preview builds may include unverified features. Switching back to Stable will not downgrade automatically. Continue?',
    ),
    'restored_title': (32939, '版本已恢复', 'Version restored'),
    'restored_body': (
        32940,
        '请重启 Kodi 后再观看，账号与观看记录保留。',
        'Restart Kodi before watching. Accounts and watch history are preserved.',
    ),
    'installed_title': (32941, '安装完成', 'Installation complete'),
    'installed_online_body': (
        32942,
        '账号与观看记录保留。即将进入设置，观看前请重启 Kodi。',
        'Accounts and watch history are preserved. Opening settings next; restart Kodi before watching.',
    ),
    'installed_offline_body': (
        32943,
        '账号、片库与观看记录保留。即将进入设置，观看前请重启 Kodi。',
        'Accounts, libraries and watch history are preserved. Opening settings next; restart Kodi before watching.',
    ),
    'space_title': (32944, '安装所需空间', 'Required installation space'),
    'install_confirm_title': (32945, '安装波比影院', 'Install Bobbi Cinema'),
    'install_confirm_body': (
        32946,
        '预计需新增至少 {required:.1f} MiB，当前可用 {free:.1f} MiB。\n账号与音画设置保留。若 Kodi 询问是否保持临时皮肤，请选“是”。继续安装？',
        'Requires at least {required:.1f} MiB additional space; {free:.1f} MiB available.\nAccounts and AV settings are preserved. Choose "Yes" if Kodi asks to keep the temporary skin. Continue?',
    ),
    'rollback_confirm_title': (32947, '恢复上一版本？', 'Restore previous version?'),
    'rollback_confirm_body': (
        32948,
        '仅恢复程序，账号、片库与观看记录保留。完成后需重启 Kodi。',
        'Restores program files only; accounts, libraries and history are preserved. Restart Kodi afterwards.',
    ),
    'report_old_backup_title': (32949, '无法恢复旧版', 'Cannot restore previous version'),
    'report_failed_title': (32950, '操作未完成', 'Operation incomplete'),
    'report_old_backup_body': (
        32951,
        '旧备份不完整或缺少核对记录。请保留备份，改用完整安装包恢复。',
        'Previous backup is incomplete or missing its verification receipt. Keep existing files and use a full package instead.',
    ),
    'report_diag_prefix': (32952, '\n诊断（可拍照） ', '\nDiagnostic: '),
    'dep_upgrade_title': (32953, '需要更新 Kodi 依赖', 'Kodi dependency update required'),
    'dep_upgrade_body': (
        32954,
        '组件 {addon} 当前已安装版本为 {have}，至少需要 {need}（不会覆盖现有目录）。\n选“是”将打开 Kodi“依赖项”列表（addons://dependencies/），请在其中点选 {addon} 并点击“更新”，完成后重新打开“波比 TV · 开始使用”继续安装。',
        'Add-on {addon} is installed at version {have}, but version {need} or newer is required (existing files are not overwritten).\nChoose "Yes" to open Kodi Dependencies (addons://dependencies/), select {addon} and click "Update", then reopen "Bobbi TV · Get Started" to continue.',
    ),
    'dep_upgrade_recheck_title': (32955, '重新检查依赖', 'Re-check dependency'),
    'dep_upgrade_recheck_body': (
        32956,
        '已在 Kodi 中完成 {addon}（需 >= {need}）更新后，选“是”重新读取版本并继续；选“否”退出本次安装。',
        'After updating {addon} (>= {need}) in Kodi, choose "Yes" to re-read its version and continue, or "No" to exit.',
    ),
    'lang_prompt_title': (32957, '选择界面语言 / Interface Language', 'Interface Language / 选择界面语言'),
    'lang_opt_zh': (32958, '简体中文（推荐 / Default）', '简体中文 (Chinese Simplified · Recommended)'),
    'lang_opt_keep_en': (32959, 'Keep current language (English) / 保留当前英文', 'Keep current language (English) / 保留当前英文'),
    'lang_pack_unavailable_title': (32960, '中文语言包未就绪', 'Chinese language pack unavailable'),
    'lang_pack_unavailable_body': (
        32961,
        '未能验证或启用官方简体中文语言资源，已保留当前可用语言。稍后可在设置中重试。',
        'Could not verify or enable the official Chinese (Simplified) language pack. Current language was kept; retry later in Settings.',
    ),
    'recovery_empty_title': (32962, '暂无恢复版本', 'No saved recovery versions'),
    'recovery_empty_body': (
        32963,
        '空间足够时，更新后会保存最近三个版本。也可返回使用“恢复上一版本”。',
        'When space permits, the three most recent versions are saved during updates. You can also use "Restore previous version".',
    ),
    'recovery_select_title': (32964, '选择恢复版本', 'Select recovery version'),
    'recovery_row': (32965, '版本 {seq} · {mib:.1f} MiB', 'Version {seq} · {mib:.1f} MiB'),
    'recovery_info_title': (32966, '恢复版本说明', 'Recovery version details'),
    'recovery_info_body': (
        32967,
        '将恢复到版本 {seq}，完成后需重启 Kodi。\n账号、观看记录和媒体保留，不改第三方插件与音画设置。\n有 {unavailable} 个不可用的恢复包未列出，原文件仍保留。',
        'Will restore version {seq}; restart Kodi afterwards.\nAccounts, watch history and media are kept; third-party add-ons and AV settings are untouched.\n{unavailable} unavailable recovery archive(s) were omitted and left intact.',
    ),
    'recovery_confirm_title': (32968, '恢复这个版本？', 'Restore this version?'),
    'recovery_confirm_body': (
        32969,
        '仅恢复程序，个人数据保留。完成后需重启 Kodi。',
        'Restores program files only; personal data is preserved. Restart Kodi afterwards.',
    ),
    'storage_plan_main': (
        32970,
        '本次至少需要 {required} MiB，当前可用 {free} MiB。\n已下载 {archive} MiB，解压需 {stage} MiB，补齐依赖需 {seed} MiB，另预留 {reserve} MiB。\n另预留安装记录 {metadata} MiB；上一版恢复使用重命名，不重复复制程序。\n现有程序 {current} MiB、备份 {backup} MiB 均保留。\nKodi 额外下载可能需要更多空间，安装前会再次检查。',
        'Requires at least {required} MiB; {free} MiB currently available.\nArchive: {archive} MiB, staging: {stage} MiB, missing seeds: {seed} MiB, reserve: {reserve} MiB.\nTransaction metadata: {metadata} MiB; previous-version rollback uses rename without duplicating code.\nInstalled code ({current} MiB) and backups ({backup} MiB) are preserved.\nAdditional Kodi downloads may require extra space and are rechecked before install.',
    ),
    'storage_plan_incomplete': (
        32971,
        '\n部分程序与备份未统计完整，实际占用可能更多。',
        '\nSome installed or backup directories were only partially scanned; actual usage may be higher.',
    ),
    'storage_plan_footer': (
        32972,
        '\n空间足够时会另存完整恢复包，最多保留三个版本。未另存时，仍可使用上一版本备份。',
        '\nWhen space allows, up to three full recovery packages are retained alongside one-step rollback.',
    ),
    'storage_title': (32973, '存储空间与清理', 'Storage and cleanup'),
    'storage_preview_main': (
        32974,
        '当前可用 {free:.1f} MiB。\n可清理下载缓存 {cache:.1f} MiB（{files} 个文件），旧安装临时文件 {retired:.1f} MiB（{transactions} 份）。\n另有 {kept:.1f} MiB 仍需保留，包含在用备份、未完成安装或无法确认用途的文件。\n清理后缓存需重新下载，无法撤销。恢复版本所需文件、账号、观看记录和媒体均保留。',
        'Available: {free:.1f} MiB.\nReclaimable download cache: {cache:.1f} MiB ({files} files); retired install transactions: {retired:.1f} MiB ({transactions}).\nProtected: {kept:.1f} MiB (active backups, pending installs or unverified directories).\nCleared cache must be re-downloaded. Recovery archives, accounts, history and media are preserved.',
    ),
    'storage_preview_prep': (
        32975,
        '\n可安全回收未提交准备文件 {prep:.1f} MiB（{count} 份）。',
        '\nReclaimable uncommitted staging files: {prep:.1f} MiB ({count}).',
    ),
    'storage_preview_unknown': (
        32976,
        '\n{unknown} 份旧临时目录归属未确认，保留不动。',
        '\n{unknown} unverified temporary folder(s) will be left untouched.',
    ),
    'storage_preview_incomplete': (
        32977,
        '\n部分目录未统计完整，实际占用可能更多；这些目录不会清理。',
        '\nSome directories were not completely scanned and will not be deleted.',
    ),
    'storage_confirm_title': (32978, '清理这些文件？', 'Clean up these files?'),
    'storage_confirm_body': (
        32979,
        '将删除 {size:.1f} MiB（{files} 个缓存文件、{tx} 份旧安装临时文件），无法撤销。\n恢复版本所需文件与个人数据保留。',
        'Delete {size:.1f} MiB ({files} cache files, {tx} temporary install sets)? This cannot be undone.\nRecovery archives and personal data are kept.',
    ),
    'storage_done_title': (32980, '清理完成', 'Cleanup complete'),
    'storage_done_body': (
        32981,
        '已清理 {removed:.1f} MiB。当前程序、恢复文件与个人数据保留。',
        'Reclaimed {removed:.1f} MiB. Installed programs, recovery archives and personal data were kept.',
    ),
}


def normalize_locale(locale):
    """Map Kodi addon locale IDs or ISO tags to 'zh_cn' or 'en_gb'."""
    if not isinstance(locale, str) or not locale.strip():
        return None
    low = locale.strip().lower().replace('-', '_')
    if low in ('zh_cn', 'zh_hans', 'zh_tw', 'zh_hk', 'zh', 'chinese', 'chinese (simple)'):
        return 'zh_cn'
    if low.startswith('resource.language.zh_'):
        return 'zh_cn'
    if low in ('default',):
        return None
    return 'en_gb'


def is_cjk_locale(locale=None, *, host=None, rpc_fn=None):
    if locale is None:
        locale = active_locale(host=host, rpc_fn=rpc_fn)
    if not isinstance(locale, str) or not locale.strip():
        return False
    low = locale.strip().lower().replace('-', '_')
    return any(tag in low for tag in ('zh_cn', 'zh_tw', 'zh_hk', 'zh_hans', 'zh_hant', 'ja_jp', 'ko_kr')) or low in ('zh', 'ja', 'ko')


def active_locale(host=None, rpc_fn=None):
    """Read Kodi's live UI locale dynamically without caching across switches."""
    raw = None
    if host is not None and callable(getattr(host, 'locale', None)):
        try:
            raw = host.locale()
        except Exception:
            raw = None
    if raw is None and callable(rpc_fn):
        try:
            import sys
            xbmc_mod = sys.modules.get('xbmc')
            if xbmc_mod is not None and hasattr(xbmc_mod, 'executeJSONRPC'):
                res = rpc_fn('Settings.GetSettingValue', {'setting': 'locale.language'})
                if isinstance(res, dict):
                    raw = res.get('value')
        except Exception:
            raw = None
    normalized = normalize_locale(raw)
    return normalized or 'zh_cn'


def tr(key, locale=None, *, host=None, rpc_fn=None, **kwargs):
    """Return localized string for key in active/specified locale ('zh_cn' default, 'en_gb' fallback)."""
    entry = STRINGS[key]
    lang = normalize_locale(locale) if locale is not None else active_locale(host=host, rpc_fn=rpc_fn)
    text = entry[1] if (lang or 'zh_cn') == 'zh_cn' else entry[2]
    return text.format(**kwargs) if kwargs else text


def parse_po(raw_text):
    """Parse Kodi Gettext PO #32xxx entries without external libraries."""
    entries = {}
    current_id = None
    msgid_lines = []
    msgstr_lines = []
    mode = None

    def flush():
        nonlocal current_id, msgid_lines, msgstr_lines, mode
        if current_id is not None:
            msgid = ''.join(msgid_lines)
            msgstr = ''.join(msgstr_lines)
            if current_id in entries:
                raise ValueError(f'Duplicate PO id #{current_id}')
            entries[current_id] = (msgid, msgstr)
        current_id = None
        msgid_lines = []
        msgstr_lines = []
        mode = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith('msgctxt '):
            flush()
            m = re.match(r'^msgctxt\s+"#(\d+)"$', line)
            if m:
                current_id = int(m.group(1))
            continue
        if line.startswith('#'):
            continue
        if line.startswith('msgid '):
            mode = 'id'
            msgid_lines = [_unescape_po(line[6:].strip())]
        elif line.startswith('msgstr '):
            mode = 'str'
            msgstr_lines = [_unescape_po(line[7:].strip())]
        elif line.startswith('"') and mode in ('id', 'str'):
            (msgid_lines if mode == 'id' else msgstr_lines).append(_unescape_po(line))
    flush()
    return entries


def _unescape_po(token):
    if len(token) < 2 or not (token.startswith('"') and token.endswith('"')):
        raise ValueError('Invalid PO quoted string')
    body = token[1:-1]
    return (
        body.replace(r'\n', '\n')
        .replace(r'\t', '\t')
        .replace(r'\"', '"')
        .replace(r'\\', '\\')
    )


def render_minimal_po(lang='en_gb'):
    """Project STRINGS to standard Kodi strings.po format for verification/build."""
    lines = [
        '# Bobbi TV bootstrap minimal strings',
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        f'"Language: {lang}\\n"',
        '',
    ]
    for _key, (num_id, zh_val, en_val) in sorted(STRINGS.items(), key=lambda kv: kv[1][0]):
        esc_en = en_val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        esc_zh = zh_val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        lines.append(f'msgctxt "#{num_id}"')
        lines.append(f'msgid "{esc_en}"')
        lines.append(f'msgstr "{esc_zh if lang == "zh_cn" else ""}"')
        lines.append('')
    return '\n'.join(lines)


def verify_zh_cn_archive(raw_bytes, provenance=None, *, host_resource_version='1.0.0'):
    """Verify official Kodi Omega resource.language.zh_cn archive bytes and inner manifest."""
    from .updates import UpdateError, archive_rows
    from .upstream_addons import compare_versions, kodi_version

    if not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) != ZH_CN_BYTES:
        raise UpdateError('LANGUAGE_PACK_SIZE_INVALID')
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest != ZH_CN_SHA256:
        raise UpdateError('LANGUAGE_PACK_HASH_INVALID')
    if provenance is not None:
        if (not isinstance(provenance, dict)
                or provenance.get('addon_id') != ZH_CN_ADDON_ID
                or provenance.get('version') != ZH_CN_VERSION
                or provenance.get('file') != ZH_CN_FILENAME
                or provenance.get('bytes') != ZH_CN_BYTES
                or provenance.get('sha256') != ZH_CN_SHA256):
            raise UpdateError('LANGUAGE_PACK_PROVENANCE_INVALID')
    try:
        zf = zipfile.ZipFile(BytesIO(raw_bytes))
    except zipfile.BadZipFile as error:
        raise UpdateError('LANGUAGE_PACK_ARCHIVE_INVALID') from error
    with zf:
        rows = archive_rows(zf, {'id': ZH_CN_ADDON_ID})
        names = {row.filename for row in rows if not row.is_dir()}
        required_members = {
            'resource.language.zh_cn/addon.xml',
            'resource.language.zh_cn/resources/langinfo.xml',
            'resource.language.zh_cn/resources/strings.po',
        }
        if not required_members <= names:
            raise UpdateError('LANGUAGE_PACK_MEMBERS_INVALID')
        xml_raw = zf.read('resource.language.zh_cn/addon.xml')
        if b'<!DOCTYPE' in xml_raw.upper() or b'<!ENTITY' in xml_raw.upper():
            raise UpdateError('LANGUAGE_PACK_XML_REJECTED')
        try:
            root = ET.fromstring(xml_raw)
        except ET.ParseError as error:
            raise UpdateError('LANGUAGE_PACK_XML_INVALID') from error
        if root.tag != 'addon' or root.get('id') != ZH_CN_ADDON_ID or root.get('version') != ZH_CN_VERSION:
            raise UpdateError('LANGUAGE_PACK_IDENTITY_INVALID')
        kodi_version(root.get('version'))
        ext = root.find('./extension[@point="kodi.resource.language"]')
        if ext is None or ext.get('locale', '').lower() != 'zh_cn':
            raise UpdateError('LANGUAGE_PACK_LOCALE_INVALID')
        for dep in root.findall('./requires/import'):
            if dep.get('optional') == 'true':
                continue
            dep_id = dep.get('addon')
            dep_ver = dep.get('version', '0.0.0')
            kodi_version(dep_ver)
            if dep_id != 'kodi.resource':
                raise UpdateError('LANGUAGE_PACK_DEPENDENCY_UNSUPPORTED:' + str(dep_id))
            if host_resource_version is not None and compare_versions(host_resource_version, dep_ver) < 0:
                raise UpdateError('LANGUAGE_PACK_HOST_INCOMPATIBLE')
        for row in rows:
            parts = PurePosixPath(row.filename).parts
            if not parts or parts[0] != ZH_CN_ADDON_ID:
                raise UpdateError('LANGUAGE_PACK_ARCHIVE_INVALID')
    return {
        'addon_id': ZH_CN_ADDON_ID,
        'version': ZH_CN_VERSION,
        'bytes': ZH_CN_BYTES,
        'sha256': ZH_CN_SHA256,
    }
