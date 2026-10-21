"""The installed IME helper publishes one current page, not a stale Ready bit."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

SKIN=Path(__file__).resolve().parents[1]/'addons/skin.bobbi.cinema'


def exercise(monkeypatch, change_during_publish=False):
    spec=importlib.util.spec_from_file_location('ime_page_subject',SKIN/'scripts/cinema_keyboard.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    native={'code':'sh','page':'0.旧 1.页','ticks':0,'changed':False,'focus':120}
    props, published, stale=[],[],[]
    props={}
    def current():
        return bool(props.get('BobiIME.Ready') and props.get('BobiIME.Code')==native['code']
                    and props.get('BobiIME.Page')==native['page'])
    class Window:
        def getProperty(self,k):return props.get(k,'')
        def clearProperty(self,k):props.pop(k,None)
        def getFocusId(self):return native['focus']
        def setFocusId(self,v):native['focus']=v
        def setProperty(self,k,v):
            props[k]=v
            if k=='BobiIME.Word1' and change_during_publish and not native['changed']:
                native.update(code='shi',page='0.是 1.使',changed=True)
            if k=='BobiIME.Ready' and v:
                published.append((current(),props['BobiIME.Code'],props['BobiIME.Page']))
    class Monitor:
        def abortRequested(self):return native['ticks']>=2
        def waitForAbort(self,seconds):
            native['ticks']+=1
            if native['ticks']==1 and not change_during_publish:
                native.update(code='shi',page='0.是 1.使')
                stale.append((props.get('BobiIME.Ready'),current()))
            return self.abortRequested()
    def label(name):
        return {'Control.GetLabel(313)':native['code'],'Control.GetLabel(314)':native['page'],
                'Control.GetLabel(309)':'中文拼音'}[name]
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(Monitor=Monitor,getInfoLabel=label,
        getCondVisibility=lambda _:True,executebuiltin=lambda _:None))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(Window=lambda _:Window()))
    helper.main()
    assert props=={}  # Owner, Code and Page are ephemeral, including cancel.
    return published,stale


def test_changed_native_page_is_not_clickable_with_old_ready(monkeypatch):
    published,stale=exercise(monkeypatch)
    assert stale==[('1',False)]
    assert published==[(True,'sh','0.旧 1.页'),(True,'shi','0.是 1.使')]


def test_change_mid_publish_never_publishes_mixed_page_and_retries(monkeypatch):
    published,_=exercise(monkeypatch,True)
    assert published==[(True,'shi','0.是 1.使')]


def test_xml_visibility_click_and_native_fallback_share_binding():
    expression=ET.parse(SKIN/'1080p/Variables.xml').find("expression[@name='BobiIMECurrent']").text
    assert all(s in expression for s in ('BobiIME.Ready','Control.GetLabel(313)',
        'Control.GetLabel(314)','BobiIME.Code','BobiIME.Page'))
    word=ET.parse(SKIN/'1080p/Includes_Dialogs.xml').find("include[@name='KbWord']/definition/control")
    assert '$EXP[BobiIMECurrent]' in word.findtext('visible')
    assert word.find('onclick').get('condition')=='$EXP[BobiIMECurrent]'
    fallback=ET.parse(SKIN/'1080p/DialogKeyboard.xml').find(".//control[@id='314']/animation")
    assert fallback.get('condition')=='$EXP[BobiIMECurrent]'
    keyboard=ET.parse(SKIN/'1080p/DialogKeyboard.xml')
    for control in ('510','511'):
        assert keyboard.find(".//control[@id='%s']/onclick"%control).get('condition')=='$EXP[BobiIMECurrent]'
