"""Real Kodi keyboard acceptance. Only a uniquely titled empty test dialog is driven."""
import json
from pathlib import Path
from threading import Thread
import time
import traceback
import xbmc
import xbmcgui
from ce_ui_preview_remote import framebuffer_png

ROOT = Path(__file__).resolve().parent
TITLE = '波比拼音验收 · ' + ROOT.name
monitor = xbmc.Monitor()
result = dict(scope='native Kodi keyboard + installed skin; synthetic shi input only', rounds=[])
window = xbmcgui.Window(10103)


def ours():
    return (not xbmc.Player().isPlaying() and xbmcgui.getCurrentWindowDialogId() == 10103
            and xbmc.getInfoLabel('Control.GetLabel(311)') == TITLE)


def wait(predicate, seconds=3):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return
        if monitor.waitForAbort(.05): raise RuntimeError('ABORTED')
    raise RuntimeError('WAIT_EXPIRED')


def click(control):
    if not ours():raise RuntimeError('DIALOG_OWNERSHIP_CHANGED')
    xbmc.executebuiltin('SendClick(10103,%d)'%control)
    monitor.waitForAbort(.15)


def drive():
    original_layout=None
    try:
        wait(ours)
        original_layout=xbmc.getInfoLabel('Control.GetLabel(309)')
        result['initial_layout']=original_layout
        for _ in range(16):
            layout=xbmc.getInfoLabel('Control.GetLabel(309)')
            if layout in ('Chinese BasePY','中文拼音'):break
            click(309)
        else:raise RuntimeError('CHINESE_LAYOUT_NOT_CONFIGURED')
        wait(lambda:bool(window.getProperty('BobiIME.Owner')))
        result['helper_started']=True
        for index in range(10):
            click(308)
            wait(lambda:not window.getControl(312).getText())
            for letter in 'shi':
                matches=[n for n in range(100,180) if xbmc.getInfoLabel('Control.GetLabel(%d)'%n)==letter]
                if len(matches)!=1:raise RuntimeError('CHARACTER_KEY_NOT_UNIQUE')
                click(matches[0])
            wait(lambda:window.getProperty('BobiIME.Ready')=='1'
                and xbmc.getInfoLabel('Control.GetLabel(313)')=='shi')
            expected=window.getProperty('BobiIME.Word%d'%index)
            if not expected:raise RuntimeError('TEN_CANDIDATES_NOT_AVAILABLE')
            before=window.getControl(312).getText()
            if index==0:(ROOT/'keyboard-candidates.png').write_bytes(framebuffer_png())
            # Use the visible candidate's actual XML onclick, not a direct
            # text assignment and not a synthetic call to the hidden button.
            window.setFocusId(500+index)
            wait(lambda:ours() and window.getFocusId()==500+index)
            response=json.loads(xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0',id=1,
                method='Input.Select'))))
            if 'error' in response:raise RuntimeError('CANDIDATE_CLICK_FAILED')
            wait(lambda:window.getControl(312).getText()==before+expected)
            row=dict(visible_button=500+index,native_button=400+index,expected=expected,
                     actual=window.getControl(312).getText(),composition=xbmc.getInfoLabel('Control.GetLabel(313)'))
            result['rounds'].append(row)
            if index==0:(ROOT/'keyboard-selected.png').write_bytes(framebuffer_png())
        result['passed']=True
    except Exception as error:
        result.update(passed=False,error=type(error).__name__,code=str(error),
            frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
    finally:
        if ours():
            # Preserve the previous layout; do not alter the configured list.
            for _ in range(16):
                current=xbmc.getInfoLabel('Control.GetLabel(309)')
                if current==original_layout or {current,original_layout} <= {'Chinese BasePY','中文拼音'}:break
                click(309)
            click(300 if result.get('passed') else 301)


try:
    if xbmc.Player().isPlaying() or xbmcgui.getCurrentWindowDialogId() not in (0,9999):
        raise RuntimeError('DEVICE_NOT_IDLE')
    keyboard=xbmc.Keyboard('',TITLE,False)
    worker=Thread(target=drive)
    worker.start()
    keyboard.doModal(45000)
    worker.join(5)
    result['confirmed']=keyboard.isConfirmed()
    result['returned_text']=keyboard.getText() if result['confirmed'] else ''
    result['passed']=bool(result.get('passed') and not worker.is_alive() and result['confirmed']
        and result['returned_text']==result['rounds'][-1]['actual'])
except Exception as error:
    result.update(passed=False,error=type(error).__name__,code=str(error))
finally:
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
