"""Short guidance must retain the next action and consequential choices."""
import ast
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from bobbi_platform import cloud_ui, library_ui, onboarding
from test_account_ui import context

ROOT = Path(__file__).resolve().parents[1]


def strings(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_setup_actions_remain_stable_with_short_menu_labels():
    rows = onboarding.steps({'standard_playback': True}, helper_state='ready')
    assert [key for key, _ in rows] == [
        'check', 'helper', 'library', 'language', 'test', 'cloud', 'catalog',
        'cinema', 'updates', 'diagnostics', 'status']
    assert all(len(label) <= 32 for _, label in rows)
    assert '可选' in dict(rows)['helper']
    assert '试播' in dict(rows)['test']
    addon = ET.parse(ROOT / 'addons/script.bobbi.setup/addon.xml').getroot()
    assert '影院设置' in addon.get('name')
    assert addon.get('id') == 'script.bobbi.setup'


def test_logout_explains_effect_before_user_confirms(context):
    context.selections, context.confirmations = [1], [False]
    assert cloud_ui.login() is False
    text = context.yesnos[0][1]
    assert all(word in text for word in ('停止', '播放', '待处理任务', '网盘文件保留'))
    assert len(text) <= 60
    assert [name for name, _ in context.calls] == ['account_status']


def test_phone_cancel_has_specific_message_and_keeps_current_account(context):
    from bobbi_platform.cloud115 import CloudError
    old = context.current.copy()
    context.polls = [CloudError('QR_CANCELLED')]
    assert cloud_ui.login() is False
    assert context.dialogs[-1][0] == '已取消登录'
    assert '当前账号保留' in context.dialogs[-1][1]
    assert context.current == old
    assert [name for name, _ in context.calls] == ['account_status']


def test_error_guidance_keeps_real_limits_and_does_not_echo_error_details():
    from bobbi_platform.libraries import LibraryError
    assert '2 MB' in library_ui.message(LibraryError('CATALOG_TOO_LARGE'))
    assert '2000' in library_ui.message(LibraryError('CATALOG_TOO_LARGE'))
    assert '32' in library_ui.message(LibraryError('TOO_MANY_SOURCES'))
    assert 'fixture-secret' not in library_ui.message(LibraryError('fixture-secret'))
    assert 'fixture-secret' not in onboarding.engine_message('fixture-secret')


def test_risky_maintenance_guidance_keeps_data_and_restart_consequences():
    base = 'addons/script.module.bobbi.platform/lib/bobbi_platform/'
    installer = '\n'.join(strings(base + 'ce_install_ui.py'))
    recovery = '\n'.join(strings(base + 'ce_recovery.py'))
    storage = '\n'.join(strings(base + 'ce_storage.py'))
    library = '\n'.join(strings(base + 'library_ui.py'))
    assert '仅恢复程序' in installer and '重启 Kodi' in installer
    assert '账号、片库与观看记录保留' in installer
    assert '个人数据保留' in recovery and '重启 Kodi' in recovery
    assert '无法撤销' in storage and '恢复版本所需文件与个人数据保留' in storage
    assert '明文传输账号密码' in library and 'HTTPS' in library


def test_primary_guidance_avoids_developer_jargon_and_obsolete_entry_name():
    base = 'addons/script.module.bobbi.platform/lib/bobbi_platform/'
    names = ('cloud_ui.py', 'account_dialog.py', 'cloud_hub.py', 'onboarding.py',
             'library_ui.py', 'ce_install_ui.py', 'ce_recovery.py', 'ce_storage.py')
    for name in names:
        for text in strings(base + name):
            if not re.search('[\u4e00-\u9fff]', text):
                continue
            assert not any(word in text for word in ('代际', '事务', '实例', 'bobbi 首次设置'))
            assert not any(mark in text for mark in ('：', '—', '–'))


def test_empty_picker_hint_matches_direct_dialog_fallback():
    base = ROOT / 'addons/plugin.video.bobbi/resources/skins/Default/1080i'
    dialog = ET.parse(base / 'source_select_direct.xml')
    hint = '按上键选择“全部”清晰度，或放宽筛选条件'
    assert hint in [node.text for node in dialog.findall('.//label')]
    assert hint in strings('addons/plugin.video.bobbi/lib/gui/source_select.py')
    for name in ('source_select.xml', 'source_select_direct.xml'):
        assert '正在查找更多片源，可先选择已显示的版本' in [
            node.text for node in ET.parse(base / name).findall('.//label')]
