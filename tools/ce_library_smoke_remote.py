"""Installed library UI + native VFS metadata, using an isolated removable fixture."""
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
import traceback
import xbmc
import xbmcgui
import xbmcvfs
from ce_ui_preview_remote import framebuffer_png

ROOT=Path(__file__).resolve().parent
addons=Path(xbmcvfs.translatePath('special://home/addons'))
sys.path.insert(0,str(addons/'script.module.bobbi.platform/lib'))
from bobbi_platform.library_ui import registry
from bobbi_platform.libraries import vfs_source

monitor=xbmc.Monitor()
result=dict(scope='real installed library plugin entry + Kodi metadata; synthetic local files, no media playback')
source=None
store=None


def rpc(method,params=None):
    value=json.loads(xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {}))))
    if 'error' in value:raise RuntimeError('RPC_FAILED')
    return value['result']


def wait(predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if xbmc.Player().isPlaying():raise RuntimeError('PLAYBACK_STARTED_EXTERNALLY')
        if predicate():return
        if monitor.waitForAbort(.1):raise RuntimeError('ABORTED')
    raise RuntimeError('WAIT_EXPIRED')


def labels():
    names=['Label','Label2','Size','Date','Property(Bobi.Library.Kind)','Property(Bobi.Library.Location)',
           'Property(Bobi.Library.Manage)','Property(Bobi.NextPage)']
    return {name:xbmc.getInfoLabel('Container(50).ListItem.'+name) for name in names}


try:
    if xbmc.Player().isPlaying() or xbmcgui.getCurrentWindowDialogId() not in (0,9999):
        raise RuntimeError('DEVICE_NOT_IDLE')
    fixture=ROOT/'files'
    fixture.mkdir()
    for index in range(201):
        (fixture/('fixture-%03d.mkv'%index)).write_bytes(b'x'*12345 if index==0 else b'')
    source=vfs_source('UI 验收临时片库',str(fixture)+'/',source_id=uuid4().hex)
    native=json.loads(xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0',id=1,method='Files.GetDirectory',
        params=dict(directory=str(fixture)+'/',media='files',properties=['size','lastmodified'],limits=dict(start=0,end=10001))))))
    if 'error' in native:result['native_metadata']=native
    else:result['native_metadata']=dict(limits=native['result'].get('limits'),sample=native['result'].get('files',[])[:2])
    store=registry(xbmcvfs.translatePath)
    store.save(source)
    url='plugin://plugin.video.bobbi.library/?action=root'
    # A previous removable fixture may be remembered by the native window.
    # Replace that navigation entry instead of restoring a deleted directory.
    xbmc.executebuiltin('ReplaceWindow(Videos,'+url+')')
    wait(lambda:xbmc.getInfoLabel('Container.FolderPath')==url and not xbmc.getCondVisibility('Container.IsUpdating')
        and int(xbmc.getInfoLabel('Container(50).NumItems') or 0)>=2)
    window=xbmcgui.Window(10025)
    control=window.getControl(50)
    window.setFocusId(50)
    result['root_rows']=[]
    # Python's wrapper size() is empty for a native XML panel populated by
    # another plugin invocation. Read Kodi's actual container count instead.
    for index in range(int(xbmc.getInfoLabel('Container(50).NumItems') or 0)):
        control.selectItem(index)
        monitor.waitForAbort(.25)
        current=labels()
        result['root_rows'].append(current)
        if current['Property(Bobi.Library.Manage)']=='true':result['manage']=current
        if current['Label']==source.name:result['source']=current
    if result.get('source',{}).get('Property(Bobi.Library.Kind)')!='local':raise RuntimeError('SOURCE_KIND_MISSING')
    result['root_metadata_passed']=bool(result['source']['Property(Bobi.Library.Location)']=='本机目录' and 'manage' in result)
    (ROOT/'library-root.png').write_bytes(framebuffer_png())
    url='plugin://plugin.video.bobbi.library/?action=browse&source='+source.id
    xbmc.executebuiltin('Container.Update('+url+')')
    wait(lambda:xbmc.getInfoLabel('Container.FolderPath')==url and not xbmc.getCondVisibility('Container.IsUpdating'))
    control=window.getControl(50)
    wait(lambda:int(xbmc.getInfoLabel('Container(50).NumItems') or 0)>=201)
    for index in range(3):
        control.selectItem(index);monitor.waitForAbort(.15)
        current=labels()
        if current['Label']=='fixture-000.mkv':result['file']=current;break
    if not result.get('file',{}).get('Size') or not result['file'].get('Date'):raise RuntimeError('FILE_METADATA_MISSING')
    (ROOT/'library-file.png').write_bytes(framebuffer_png())
    control.selectItem(int(xbmc.getInfoLabel('Container(50).NumItems'))-1);monitor.waitForAbort(.3)
    result['next']=labels()
    if result['next']['Label']!='下一页' or result['next']['Property(Bobi.NextPage)']!='true':raise RuntimeError('NEXT_PAGE_MISSING')
    (ROOT/'library-next.png').write_bytes(framebuffer_png())
    result['passed']=result['root_metadata_passed']
except Exception as error:
    result.update(passed=False,error=type(error).__name__,code=str(error),
        frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
    result['observed']=dict(window=xbmcgui.getCurrentWindowId(),dialog=xbmcgui.getCurrentWindowDialogId(),
        folder=xbmc.getInfoLabel('Container.FolderPath'),size=xbmc.getInfoLabel('Container(50).NumItems'),
        native_size=window.getControl(50).size() if 'window' in globals() else None,labels=labels())
    (ROOT/'library-root.png').write_bytes(framebuffer_png())
finally:
    if not xbmc.Player().isPlaying() and xbmc.getInfoLabel('Container.FolderPath').startswith('plugin://plugin.video.bobbi.library/'):
        # Retire the fixture path while it still exists. Home alone leaves the
        # native Videos window remembering a source that cleanup will remove.
        root_url='plugin://plugin.video.bobbi.library/?action=root'
        xbmc.executebuiltin('Container.Update('+root_url+',replace)')
        try:wait(lambda:xbmc.getInfoLabel('Container.FolderPath')==root_url and not xbmc.getCondVisibility('Container.IsUpdating'))
        except RuntimeError:pass
        xbmc.executebuiltin('ActivateWindow(Home)')
        try:wait(lambda:xbmcgui.getCurrentWindowId()==10000)
        except RuntimeError:pass
    if source is not None and store is not None:
        try:
            if store.get(source.id)==source:store.remove(source.id)
            result['fixture_source_removed']=True
        except Exception as error:result.update(passed=False,cleanup_error=type(error).__name__)
    if store is not None:store.close()
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
