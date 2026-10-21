"""Read real resume projections and drive idle navigation; never edit history."""
if __name__=='__main__':
    raise RuntimeError('PERSONAL_PROBE_SUSPENDED_AFTER_NATIVE_CRASH')
import json
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import urlsplit,parse_qs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from ce_ui_preview_remote import framebuffer_png

ROOT=Path(__file__).resolve().parent
(ROOT/'progress.json').write_text('{"stage":"imports_loaded"}',encoding='utf-8')
addons=Path(xbmcvfs.translatePath('special://home/addons'))
for path in sorted(addons.glob('script.module.*/lib')):sys.path.insert(0,str(path))
sys.path.insert(0,str(addons/'plugin.video.bobbi'))
native_addon=xbmcaddon.Addon
xbmcaddon.Addon=lambda id=None:native_addon(id or 'plugin.video.bobbi')
sys.argv=['plugin://plugin.video.bobbi/','-1','']
monitor=xbmc.Monitor()
result=dict(scope='installed resume projection and idle personal page; no history writes')


def acceptance(value):
    expected=value['expected_identity']
    directory,personal=value['directory'],value['personal']
    if expected is None:
        # Empty widgets have no positive item-bound completion receipt. Do not
        # turn a transient empty/loading view into verified empty-state proof.
        return False
    # Unidentified legacy entries cannot provide a trustworthy identity oracle.
    return (expected[0] in ('movie','tv') and value['resume_count']>0
        and value.get('directory_position')==0 and not personal.get('loading',True)
        and all(int(row['count'] or 0)>0 and row['identity']==expected
                and row['percent']==value['expected_percent'] for row in (directory,personal)))


def wait(predicate,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if xbmc.Player().isPlaying():raise RuntimeError('PLAYBACK_STARTED')
        if predicate():return
        if monitor.waitForAbort(.1):raise RuntimeError('ABORTED')
    raise RuntimeError('WAIT_EXPIRED')


def navigate(action,window):
    if xbmc.Player().isPlaying():raise RuntimeError('PLAYBACK_STARTED')
    xbmc.executebuiltin(action)
    wait(lambda:xbmcgui.getCurrentWindowId()==window and not xbmc.getCondVisibility('Container.IsUpdating'))
    monitor.waitForAbort(1)


def capture(name):
    for attempt in range(5):
        if xbmc.Player().isPlaying():raise RuntimeError('PLAYBACK_STARTED')
        try:raw=framebuffer_png()
        except RuntimeError as error:
            if str(error)!='FRAMEBUFFER_MOVING' or attempt==4:raise
            monitor.waitForAbort(.15)
        else:(ROOT/name).write_bytes(raw);return


try:
    (ROOT/'progress.json').write_text('{"stage":"precheck"}',encoding='utf-8')
    if xbmc.Player().isPlaying() or xbmcgui.getCurrentWindowDialogId() not in (0,9999):
        raise RuntimeError('DEVICE_NOT_IDLE')
    from lib.db.pickle_db import PickleDatabase
    from lib.cinema.frontend_contract import clean_title,history_identity,history_rows,progress
    from lib.utils.views.last_files import parse_time
    (ROOT/'progress.json').write_text('{"stage":"history_imports_loaded"}',encoding='utf-8')
    history=PickleDatabase().get_key('jt:lfh')
    rows=history_rows(history.items(),parse_time)
    (ROOT/'progress.json').write_text('{"stage":"history_projected"}',encoding='utf-8')
    expected_identity=history_identity(rows[0][1]) if rows else None
    def selected_identity(prefix):
        # A UI row carries its original playback payload. Inspect only its
        # media identity in memory; never export the route or cloud URL.
        path=xbmc.getInfoLabel(prefix+'.FileNameAndPath')
        if not path:return None
        query=parse_qs(urlsplit(path).query)
        payload=json.loads(query.get('data',['{}'])[0])
        return history_identity(payload)
    def safe(data):
        tv=data.get('tv_data') or {}
        return dict(title=clean_title(data.get('title'))[:180],identity=history_identity(data)[:4],
            timestamp=data.get('timestamp'),parsed_timestamp=parse_time(('',data)).isoformat(),
            mode=data.get('mode'),progress=progress(data),completed=data.get('completed'),
            terminal_reason=data.get('terminal_reason'),current_time=data.get('current_time'),
            total_time=data.get('total_time'),season=tv.get('season'),episode=tv.get('episode'))
    result.update(history_count=len(history),resume_count=len(rows),
        localtime=time.strftime('%Y-%m-%d %H:%M:%S %z'),
        recent=[safe(row[1]) for row in sorted(history.items(),key=parse_time,reverse=True)[:12]])
    url='plugin://plugin.video.bobbi/?action=continue_watching_menu'
    (ROOT/'progress.json').write_text('{"stage":"directory_open"}',encoding='utf-8')
    navigate('ActivateWindow(Videos,"'+url+'",return)',10025)
    wait(lambda:xbmc.getInfoLabel('Container.FolderPath')==url
        and not xbmc.getCondVisibility('Window.IsActive(busydialog)')
        and not xbmc.getCondVisibility('Window.IsActive(busydialognocancel)')
        and (not rows or int(xbmc.getInfoLabel('Container.NumItems') or 0)>0))
    # Never call ControlList methods on a borrowed native container: F9's
    # selectItem binding crashed here. Drive the ordinary GUI action instead.
    xbmc.executebuiltin('SetFocus(50)')
    wait(lambda:xbmcgui.Window(10025).getFocusId()==50)
    xbmc.executeJSONRPC('{"jsonrpc":"2.0","id":1,"method":"Input.ExecuteAction","params":{"action":"firstpage"}}')
    wait(lambda:xbmc.getInfoLabel('Container(50).CurrentItem')=='1')
    result['directory_position']=int(xbmc.getInfoLabel('Container(50).CurrentItem'))-1
    result['directory']=dict(folder=xbmc.getInfoLabel('Container.FolderPath'),
        count=xbmc.getInfoLabel('Container.NumItems'),label=xbmc.getInfoLabel('ListItem.Label'),
        percent=xbmc.getInfoLabel('ListItem.Property(PercentPlayed)'),
        identity=selected_identity('ListItem'))
    capture('personal-directory.png')
    (ROOT/'progress.json').write_text('{"stage":"personal_open"}',encoding='utf-8')
    navigate('ActivateWindow(1197)',11197)
    if rows:
        wait(lambda:not xbmc.getCondVisibility('Container(9130).IsUpdating')
            and int(xbmc.getInfoLabel('Container(9130).NumItems') or 0)>0
            and selected_identity('Container(9130).ListItem')==expected_identity)
    result['personal']=dict(count=xbmc.getInfoLabel('Container(9130).NumItems'),
        loading=xbmc.getCondVisibility('Container(9130).IsUpdating'),
        label=xbmc.getInfoLabel('Container(9130).ListItem.Label'),
        percent=xbmc.getInfoLabel('Container(9130).ListItem.Property(PercentPlayed)'),
        identity=selected_identity('Container(9130).ListItem'))
    result['expected_identity']=expected_identity
    result['expected_percent']=str(round(progress(rows[0][1]))) if rows else ''
    window=xbmcgui.Window(11197)
    window.setFocusId(9100)
    wait(lambda:window.getFocusId()==9100)
    xbmc.executeJSONRPC('{"jsonrpc":"2.0","id":1,"method":"Input.Right"}')
    expected=9110 if int(result['personal']['count'] or 0)>0 else 9101
    wait(lambda:window.getFocusId()==expected)
    result['right_focus']=window.getFocusId()
    xbmc.executeJSONRPC('{"jsonrpc":"2.0","id":1,"method":"Input.Left"}')
    wait(lambda:window.getFocusId()==9100)
    result['left_focus']=window.getFocusId()
    capture('personal-page.png')
    result['passed']=acceptance(result)
    (ROOT/'progress.json').write_text('{"stage":"complete"}',encoding='utf-8')
except Exception as error:
    result.update(passed=False,error=type(error).__name__,code=str(error),
        frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
finally:
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
