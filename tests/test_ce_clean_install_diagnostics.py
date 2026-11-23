"""Fresh CE entry: real dependency manifests, no pre-existing user library."""
from pathlib import Path
from types import SimpleNamespace
import runpy
import shutil
import sys
import xml.etree.ElementTree as ET

import pytest
from bobbi_platform import ce_install_ui as ui
from bobbi_platform.updates import UpdateError

ROOT = Path(__file__).resolve().parents[1]


def fresh_kodi(tmp_path, monkeypatch):
    stage, live = tmp_path/'verified', tmp_path/'empty-kodi'/'addons'
    live.mkdir(parents=True)
    enabled = {'script.module.pycryptodome': {'version':'3.4.3','enabled':True}}
    observed = []
    for name in ui.MANAGED | ui.UPSTREAM_COMPONENTS:
        # Use the production manifests for the actual required dependency edges.
        src = (ROOT/('third_party/addons' if name in ui.UPSTREAM_COMPONENTS else 'addons')/name/'addon.xml')
        (stage/name).mkdir(parents=True)
        shutil.copyfile(src,stage/name/'addon.xml')
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.details = lambda name: enabled.get(name)
    def refresh():
        for path in live.glob('*/addon.xml'):
            node = ET.parse(path).getroot()
            enabled.setdefault(node.get('id'),dict(version=node.get('version'),enabled=False))
    def rpc(method, params):
        assert method=='Addons.SetAddonEnabled' and params['enabled']
        name=params['addonid']
        imports=ET.parse(live/name/'addon.xml').findall('./requires/import')
        if any(i.get('addon') in ui.UPSTREAM_COMPONENTS and i.get('optional')!='true'
               and not enabled.get(i.get('addon'),{}).get('enabled') for i in imports):
            raise RuntimeError('Kodi RPC failed: Addons.SetAddonEnabled')
        enabled[name]['enabled']=True
        observed.append(name)
        return 'OK'
    host.refresh=refresh
    host.xbmc=SimpleNamespace(executebuiltin=lambda *args: pytest.fail('offline test must not download'))
    monkeypatch.setitem(sys.modules,'xbmcvfs',SimpleNamespace(translatePath=lambda _:str(live)))
    monkeypatch.setattr(ui,'rpc',rpc)
    return host,stage,live,enabled,observed


def test_package_dependencies_register_in_import_order_on_empty_profile(tmp_path,monkeypatch):
    host,stage,live,enabled,calls=fresh_kodi(tmp_path,monkeypatch)
    host.dependencies(stage)
    assert all(enabled[n]['enabled'] for n in ui.UPSTREAM_COMPONENTS)
    assert calls.index('script.module.urllib3')<calls.index('script.module.requests')<calls.index('script.module.jurialmunkey')<calls.index('script.skinvariables')
    marker=live/'script.module.requests'/'existing-user-origin';marker.write_bytes(b'preserve')
    before=list(calls);host.dependencies(stage)
    assert calls==before and marker.read_bytes()==b'preserve'


def test_dependency_cycle_rejected_before_first_copy(tmp_path,monkeypatch):
    host,stage,live,_,_=fresh_kodi(tmp_path,monkeypatch)
    xml=stage/'script.module.urllib3'/'addon.xml';tree=ET.parse(xml)
    ET.SubElement(tree.getroot().find('requires'),'import',addon='script.module.requests',version='1.0.0')
    tree.write(xml)
    with pytest.raises(UpdateError,match='DEPENDENCY_GRAPH_INVALID'):
        host.dependencies(stage)
    assert not list(live.iterdir())


def test_failure_even_during_constructor_is_photographable_and_same_as_log(tmp_path,monkeypatch):
    dialogs=[];logs=[]
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(LOGERROR=4,log=lambda msg,lvl:logs.append(msg),
        getInfoLabel=lambda _: '21.3 (21.3.0) Git:private'))
    monkeypatch.setitem(sys.modules,'xbmcaddon',SimpleNamespace(Addon=lambda _:SimpleNamespace(getAddonInfo=lambda _: '0.2.102')))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(Dialog=lambda: SimpleNamespace(ok=lambda *a:dialogs.append(a))))
    monkeypatch.setitem(sys.modules,'xbmcvfs',SimpleNamespace(translatePath=lambda _:str(tmp_path)))
    monkeypatch.setattr(ui,'KodiHost',lambda: SimpleNamespace())
    monkeypatch.setattr(ui,'profile',lambda _:tmp_path)
    def fail(*a):raise PermissionError(13,'http://private.invalid?token=SECRET')
    monkeypatch.setattr(ui,'Installer',fail)
    ui.main()
    assert len(logs)==len(dialogs)==1 and dialogs[0][0]=='操作未完成'
    line=logs[0].removeprefix('[bobbi-install] ')
    assert '初始化 · IO_EACCES' in line and 'ZIP 0.2.102 / Kodi 21.3' in line
    assert dialogs[0][1].endswith(line) and '可拍照' in dialogs[0][1] and 'private' not in str(dialogs)+str(logs) and 'SECRET' not in str(dialogs)+str(logs)


@pytest.mark.parametrize('message,shown',[
    ('DEPENDENCY_ENABLE_FAILED:script.module.requests','script.module.requests'),
    ('COMPONENT_REGISTRATION_FAILED:plugin.video.bobbi','plugin.video.bobbi'),
    ('DEPENDENCY_UNAVAILABLE:https://invalid?token=SECRET','DEPENDENCY_UNAVAILABLE'),
    ('PRIVATE_TOKEN_SECRET','PACKAGE_CHECK')])
def test_only_reviewed_reason_and_components_leave_the_installer(message,shown):
    line=ui.diagnosis('apply',UpdateError(message))
    assert shown in line and 'SECRET' not in line and 'http' not in line


def test_damaged_entry_before_platform_import_reports_without_installed_platform(tmp_path, monkeypatch):
    logs,dialogs=[],[]
    def addon(name):
        if name=='script.bobbi.start':
            return SimpleNamespace(getAddonInfo=lambda _:str(tmp_path))
        raise RuntimeError('private path or credentials')
    monkeypatch.setitem(sys.modules,'xbmcaddon',SimpleNamespace(Addon=addon))
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(LOGERROR=4,log=lambda msg,lvl:logs.append(msg)))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(Dialog=lambda:SimpleNamespace(ok=lambda *a:dialogs.append(a))))
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(ROOT/'addons/script.bobbi.start/default.py'))
    assert stop.value.code==0 and len(logs)==len(dialogs)==1
    assert logs[0].removeprefix('[bobbi-install] ') in dialogs[0][1] and 'private' not in str(dialogs)


def test_owned_component_activation_failure_has_actionable_id(monkeypatch):
    host=ui.KodiHost.__new__(ui.KodiHost)
    host.details=lambda _: {'enabled':False}
    def denied(*_):
        raise RuntimeError('Kodi RPC failed: Addons.SetAddonEnabled')
    monkeypatch.setattr(ui,'rpc',denied)
    with pytest.raises(UpdateError) as raised:
        host.activate({'plugin.video.bobbi':'1.0.0'})
    assert 'COMPONENT_ENABLE_FAILED · plugin.video.bobbi' in ui.diagnosis('apply',raised.value)
    assert '恢复' in ui.failure_message(raised.value)


def test_unexpected_error_does_not_expose_value_or_tell_offline_user_to_retry_download():
    assert 'KeyError' in ui.diagnosis('apply',KeyError('SECRET'))
    assert 'SECRET' not in ui.diagnosis('apply',KeyError('SECRET'))
    assert '下载' not in ui.failure_message(OSError('SECRET'),'apply')
