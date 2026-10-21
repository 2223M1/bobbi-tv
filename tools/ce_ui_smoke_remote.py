"""Attended on-device UI smoke, dummy QR only; never reads/changes accounts."""
import json
from pathlib import Path
import sys
import time
import traceback
import hashlib
import faulthandler
from threading import Event, Thread

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from ce_ui_preview_remote import framebuffer_png

ROOT = Path(__file__).resolve().parent
trace = (ROOT/'smoke-stack.txt').open('w')
faulthandler.dump_traceback_later(20, file=trace)
addons = Path(xbmcvfs.translatePath('special://home/addons'))
for path in sorted(addons.glob('script.module.*/lib')):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(addons/'plugin.video.bobbi'))
sys.path.insert(0, str(addons/'script.bobbi.setup'))
native_addon = xbmcaddon.Addon
xbmcaddon.Addon = lambda id=None: native_addon(id or 'plugin.video.bobbi')
sys.argv = ['plugin://plugin.video.bobbi/', '-1', '']
monitor = xbmc.Monitor()
result = dict(scope='real installed UI; synthetic QR/card data; no login exchange or playback', panels=[])
result['display_before'] = {name:xbmc.getCondVisibility(name) for name in
    ('System.ScreenSaverActive', 'System.DPMSActive', 'Window.IsActive(screensaver)')}
window = None
frame_stop = Event()
frame_worker = None


def inspect(name, current):
    if monitor.waitForAbort(.8) or xbmc.Player().isPlaying():
        raise RuntimeError('UI_SMOKE_INTERRUPTED')
    row = dict(name=name, dialog=xbmcgui.getCurrentWindowDialogId(), focus=current.getFocusId())
    result['panels'].append(row)
    (ROOT/'progress.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    for attempt in range(5):
        if xbmc.Player().isPlaying() or xbmcgui.getCurrentWindowDialogId()!=row['dialog']:
            raise RuntimeError('UI_SMOKE_INTERRUPTED')
        try:
            raw=framebuffer_png()
        except RuntimeError as error:
            if str(error)!='FRAMEBUFFER_MOVING' or attempt==4:raise
            if monitor.waitForAbort(.15):raise RuntimeError('UI_SMOKE_INTERRUPTED')
        else:
            (ROOT/(name+'.png')).write_bytes(raw)
            row['capture_retries']=attempt
            break
    row['capture_method'] = 'displayed-gui-framebuffer; no video plane'
    return row


def card_patch():
    """Pixels of the first card's static quality/text; excludes status badges."""
    base=Path('/sys/class/graphics/fb0')
    stride=int((base/'stride').read_text())
    for attempt in range(3):
        pan=int((base/'pan').read_text().split(',')[1])
        with Path('/dev/fb0').open('rb',buffering=0) as stream:
            stream.seek((pan+220)*stride)
            raw=stream.read(stride*70)
        if pan==int((base/'pan').read_text().split(',')[1]):
            patch=b''.join(raw[row*stride+620*4:row*stride+760*4] for row in range(70))
            return hashlib.sha256(patch).hexdigest()
    return None


try:
    if xbmc.Player().isPlaying():
        raise RuntimeError('PLAYBACK_ACTIVE')
    xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0',id=1,method='Input.ExecuteAction',params={'action':'noop'})))
    monitor.waitForAbort(1)
    result['display_after'] = {name:xbmc.getCondVisibility(name) for name in result['display_before']}
    from bobbi_platform.account_dialog import create
    from bobbi_platform._vendor import segno
    image = ROOT/'dummy-qr.png'
    segno.make('https://example.invalid/bobbi-ui-preview', micro=False).save(str(image), scale=10, border=4)
    window = create(image)
    window.show()
    row = inspect('account', window)
    row['title'] = window.getControl(100).getLabel()
    window.onClick(9001)
    row['cancelled'] = window.cancelled

    from lib.gui.terminal_actions import TerminalActions
    window = TerminalActions('terminal-actions.xml', str(addons/'plugin.video.bobbi'), 'Default', '1080i')
    window.configure(lambda: not xbmc.Player().isPlaying(), True, True)
    window.show()
    row = inspect('terminal', window)
    row['title'] = window.getControl(100).getLabel()
    window.onClick(9003)
    row['no_play_action'] = window.choice is None

    from metadata_credits import MetadataCredits
    window = MetadataCredits('tmdb-attribution.xml', str(addons/'script.bobbi.setup'), 'Default', '1080i')
    window.show()
    inspect('metadata', window)
    window.close()

    from lib.gui.source_select import SourceSelect
    from lib.domain.torrent import TorrentStream
    from bobbi_core.source_list_session import SourceListSession
    def source(number, quality='1080p'):
        return TorrentStream(type='Torrent', guid='ui-fixture:'+str(number),
            title='[UI preview] S01E01 '+quality+' x264 '+str(number), size=1024**3,
            infoHash=('%040x'%number), indexer='Preview', quality=quality)
    session = SourceListSession({'tmdb_id': 30991, 'season': 1, 'episode': 1},
        rank=lambda rows: list(reversed(rows)))
    session.publish(session.epoch, 'fixture', [source(1), source(2)], state='RUNNING')
    window = SourceSelect('source_select.xml', str(addons/'plugin.video.bobbi'),
        item_information={'title':'增量选源显示验收', 'ids':{'tmdb_id':30991}, 'mode':'tv'}, sources=[])
    window.source_session = session
    window.show()
    inspect('sources-before', window)
    qualities = window.getControl(1300)
    qualities.selectItem(window._quality_keys.index('1080p'))
    monitor.waitForAbort(.2)
    window._handle_quality_select_action()  # Same filter handler as user click.
    monitor.waitForAbort(.2)
    window.display_list.selectItem(1)
    monitor.waitForAbort(.3)
    original = dict(window._rendered_cards)
    selected = window.display_list.getSelectedItem().getProperty('source_key')
    selected_quality = qualities.getSelectedItem().getProperty('quality')
    result['initial_selection'] = dict(position=window.display_list.getSelectedPosition(),
        source_key=selected,quality=selected_quality,filter=list(window._filter_spec))
    class Meter:
        def __init__(self, control): self.control, self.resets, self.selects = control, 0, 0
        def __getattr__(self, name): return getattr(self.control, name)
        def reset(self): self.resets += 1; return self.control.reset()
        def selectItem(self, position): self.selects += 1; return self.control.selectItem(position)
    meter = Meter(window.display_list)
    window.display_list = meter
    frame_hashes=[]
    frame_expected=card_patch()
    def capture_frames():
        while not frame_stop.wait(.04):
            frame_hashes.append(card_patch())
    frame_worker=Thread(target=capture_frames,daemon=True)
    frame_worker.start()
    for number in range(3, 8):
        arrivals = [source(number)] + ([source(8, '2160p')] if number == 3 else [])
        session.publish(session.epoch, 'fixture', arrivals, state='RUNNING')
        window._refresh_progressive_sources()
        if monitor.waitForAbort(.35): raise RuntimeError('UI_SMOKE_INTERRUPTED')
        result.setdefault('arrival_selections', []).append(dict(position=window.display_list.getSelectedPosition(),
            source_key=window.display_list.getSelectedItem().getProperty('source_key'),
            quality=qualities.getSelectedItem().getProperty('quality')))
    session.publish(session.epoch, 'fixture', state='COMPLETE')
    window._refresh_progressive_sources()
    # Do not run a full /dev/fb0 read concurrently with the pixel sampler.
    # On CE the two reader paths can block each other inside the driver.
    frame_stop.set()
    frame_worker.join(2)
    if frame_worker.is_alive(): raise RuntimeError('FRAME_SAMPLER_DID_NOT_STOP')
    row = inspect('sources-after', window)
    row.update(resets=meter.resets, focus_commands=meter.selects,
        original_items_retained=all(window._rendered_cards[k] is v for k,v in original.items()),
        selected_key_retained=window.display_list.getSelectedItem().getProperty('source_key') == selected,
        quality_retained=qualities.getSelectedItem().getProperty('quality') == selected_quality,
        quality_keys=window._quality_keys,
        native_item_count=window.display_list.size(),frame_samples=len(frame_hashes),
        stable_card_pixels=bool(frame_hashes and frame_expected and all(h==frame_expected for h in frame_hashes)))
    result['passed'] = (result['panels'][0]['focus'] == 9001 and result['panels'][0]['cancelled']
        and result['panels'][1]['focus'] == 9003 and result['panels'][1]['no_play_action']
        and row['resets'] == 0 and row['focus_commands'] == 5 and row['original_items_retained']
        and result['initial_selection']['position'] == 1 and selected_quality == '1080p'
        and all(s['source_key']==selected and s['quality']==selected_quality for s in result['arrival_selections'])
        and row['quality_retained'] and '4k' in row['quality_keys']
        and row['selected_key_retained'] and row['native_item_count'] == 7 and row['stable_card_pixels'])
except Exception as error:
    result.update(passed=False, error=type(error).__name__,
        frames=[dict(module=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
finally:
    frame_stop.set()
    if frame_worker: frame_worker.join(2)
    if window is not None: window.close()
    faulthandler.cancel_dump_traceback_later()
    trace.close()
    (ROOT/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
