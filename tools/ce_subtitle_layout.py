"""Device subtitle evidence; explicit backed-up idle offset adjustment.

Status/capture never mutate settings or playback. offset-idle changes only the
observed F9 offset, never mode, font, styles, player, account or calibration.
The screenshot includes GUI/subtitle overlays, not the AMLogic hardware video plane.
"""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json, pathlib, struct, time, urllib.request, zlib, xml.etree.ElementTree as ET
from pathlib import Path
def rpc(method, params=None):
    req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc', json.dumps(dict(
        jsonrpc='2.0',id=1,method=method,params=params or {})).encode(), {'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as f:
        value=json.load(f)
    if 'error' in value: raise RuntimeError('RPC_FAILED')
    return value['result']
def current():
    players=rpc('Player.GetActivePlayers')
    native=rpc('Player.BobiState').get('playback') or {}
    value=dict(players=players,native={k:native.get(k) for k in (
        'native_instance','request_id','phase','subtitle_intent','subtitle_auto_intent',
        'subtitle_visible','subtitle_file_applied','subtitle_file_sha256','sequence','user_intent')})
    if len(players)==1 and players[0].get('type')=='video':
        value['player']=rpc('Player.GetProperties',dict(playerid=players[0]['playerid'],
            properties=['time','totaltime','speed','percentage','subtitleenabled','currentsubtitle',
                        'subtitles','currentvideostream','currentaudiostream']))
    return value
def require(row):
    if (row['native'].get('native_instance')!=INSTANCE or row['native'].get('request_id')!=REQUEST
            or row['native'].get('phase')!='AV_STARTED'):
        raise RuntimeError('PLAYBACK_INSTANCE_CHANGED')
result=dict(before=current(),settings={})
for name in ['subtitles.marginvertical','subtitles.align','subtitles.overridefonts','subtitles.overridestyles',
             'subtitles.overrideass','subtitles.fontsize','subtitles.fontname','subtitles.colorpick',
             'subtitles.pgsverticalmode','subtitles.pgsverticaloffset','videoscreen.screenmode','videoplayer.adjustrefreshrate',
             'videoplayer.usedisplayasclock']:
    try:result['settings'][name]=rpc('Settings.GetSettingValue',dict(setting=name))['value']
    except RuntimeError:result['settings'][name]=dict(unavailable=True)
labels=['System.ScreenWidth','System.ScreenHeight','System.ScreenResolution','Player.SubtitleDelay',
        'Player.SubtitleOffset','VideoPlayer.Title','VideoPlayer.VideoAspect','Player.Subtitle','Skin.CurrentTheme']
result['labels']=rpc('XBMC.GetInfoLabels',dict(labels=labels))
result['gui']=rpc('GUI.GetProperties',dict(properties=['currentwindow','currentcontrol','skin']))
document=ET.parse('/storage/.kodi/userdata/guisettings.xml').getroot()
result['saved_calibrations']=[ET.tostring(n,encoding='unicode') for n in document.findall('./resolutions/resolution')]
result['saved_position_settings']={n.get('id'):n.text for n in document.findall('setting') if n.get('id','').startswith('subtitles.pgs')}
definition=Path('/usr/share/kodi/system/settings/settings.xml')
if definition.is_file():
 result['position_definitions']=[ET.tostring(n,encoding='unicode') for n in ET.parse(definition).iter('setting') if n.get('id','').startswith('subtitles.pgs')]
if OFFSET is not None:
    assert not result['before']['players'],'PLAYBACK_ACTIVE'
    assert result['settings']['subtitles.pgsverticalmode']==5,'MODE_CHANGED'
    assert result['settings']['subtitles.pgsverticaloffset']==EXPECTED_OFFSET,'OFFSET_CHANGED'
    target=Path('/storage/.kodi/temp/bobbi-subtitle-layout');target.mkdir(exist_ok=True)
    backup=target/(STAMP+'-settings-before.json')
    with backup.open('x') as stream:json.dump(result['settings'],stream)
    assert not current()['players'],'PLAYBACK_STARTED'
    assert rpc('Settings.SetSettingValue',dict(setting='subtitles.pgsverticaloffset',value=OFFSET)) is True,'SET_FAILED'
    result['offset_after']=rpc('Settings.GetSettingValue',dict(setting='subtitles.pgsverticaloffset'))['value']
    assert result['offset_after']==OFFSET,'OFFSET_NOT_APPLIED'
    result['settings_backup']=str(backup)
if CAPTURE:
    require(result['before'])
    target=Path('/storage/.kodi/temp/bobbi-subtitle-layout')
    target.mkdir(exist_ok=True)
    path=target/(STAMP+'.png')
    path.write_bytes(framebuffer_png())
    result['after']=current()
    require(result['after'])
    result['image']=str(path)
    result['scope']='Displayed Kodi GUI/subtitle plane; hardware video plane not captured'
print(json.dumps(result,ensure_ascii=True))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('status','capture','offset-idle'))
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--instance')
    p.add_argument('--request')
    p.add_argument('--brief',action='store_true')
    p.add_argument('--offset',type=int,choices=range(4))
    p.add_argument('--expect-offset',type=int,choices=range(4))
    a=p.parse_args()
    if a.mode=='capture' and not (a.instance and a.request):
        p.error('capture requires observed --instance and --request')
    if a.mode=='offset-idle' and (a.offset is None or a.expect_offset is None):
        p.error('offset-idle requires --offset and the observed --expect-offset')
    if a.mode!='offset-idle' and (a.offset is not None or a.expect_offset is not None):
        p.error('offset arguments are only allowed in offset-idle')
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('layout_wire',a.transport_source/'ui-redesign/tools/device_transport.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    stamp=str(time.time_ns())
    a.output.mkdir(parents=True,exist_ok=True)
    helper=(ROOT/'tools/ce_ui_preview_remote.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(helper).body if isinstance(n,ast.FunctionDef) and n.name=='framebuffer_png')
    header='from pathlib import Path\n'+ast.get_source_segment(helper,node)+'\n'
    values=dict(CAPTURE=a.mode=='capture',INSTANCE=a.instance,REQUEST=a.request,STAMP=stamp,
                OFFSET=a.offset,EXPECTED_OFFSET=a.expect_offset)
    script='\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'+header+REMOTE
    client,wire=m.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=35)
        if result.get('image'):
            expected='/storage/.kodi/temp/bobbi-subtitle-layout/'+stamp+'.png'
            if result['image']!=expected:raise RuntimeError('UNEXPECTED_CAPTURE_PATH')
            local=a.output/('layout-'+stamp+'.png')
            with client.open_sftp() as s:s.get(expected,str(local))
            result['local_image']=str(local)
    finally:client.close()
    record=a.output/('layout-'+stamp+'.json')
    record.write_text(json.dumps(dict(exit_code=rc,diagnostic_present=bool(diagnostic),result=result),
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    display={k:v for k,v in result.items() if k not in ('saved_calibrations','position_definitions','before','after')} if a.brief else result
    print(json.dumps(dict(evidence=str(record),**display),ensure_ascii=False))
    return int(bool(rc or diagnostic))


if __name__=='__main__':raise SystemExit(main())
