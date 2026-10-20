"""Run inside Kodi: standard adapter on F9, NOT another CE hardware certificate.

Only two local generated clips and a fresh temporary account/profile are used.
No cinema account/history/native API or firmware changes; no global stop calls.
"""
import json
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4

import xbmc
import xbmcvfs

ROOT = Path(__file__).resolve().parent
for addon in ('script.module.bobbi.platform', 'script.module.bobbi.core', 'plugin.video.bobbi'):
    path = Path(xbmcvfs.translatePath('special://home/addons')) / addon
    sys.path.insert(0, str(path / 'lib' if addon.startswith('script.') else path))

from bobbi_platform.host import Host
from bobbi_platform.kodi import standard_handoff
from bobbi_platform.playback import selected_identity
from lib.services.standard_playback import StandardPlayback

result = dict(scope='actual standard adapter on existing F9; generated media only',
              other_ce_hardware_tested=False, history=[], reports=[], used_native_api=False, samples=[])
host = standard = None
try:
    if xbmc.Player().isPlaying():
        raise RuntimeError('PLAYBACK_ACTIVE')
    host = Host(ROOT / 'temporary-profile', report=result['reports'].append)
    host.start()
    standard = StandardPlayback(host)
    standard.session.history = lambda data: result['history'].append({key: data.get(key) for key in
        ('request_id', 'terminal_reason', 'completed', 'current_time', 'total_time', 'lifecycle_evidence')})
    def clip(letter):
        return dict(request_id=uuid4().hex, _account=host.accounts.snapshot(), selection_policy='exact',
            title='Standard adapter fixture '+letter, url=str(ROOT/(letter+'.mp4')),
            subtitles_path=[str(ROOT/'fixture.zh.srt')], file_evidence='AUTO_VERIFIED_FILE')
    first, second = clip('a'), clip('b')
    standard.session.next_loader = lambda current, cancelled: second if current['request_id'] == first['request_id'] else None
    standard.dispatch(dict(operation='select', request_id=first['request_id'], account=first['_account']))
    # Kodi embeds optimized Python: an assert expression is not executed there.
    # Registration must happen regardless of __debug__, just like production.
    registration = standard.dispatch(dict(operation='register', request_id=first['request_id'], data=first))
    if not registration['accepted']:
        raise RuntimeError('FIXTURE_REGISTRATION_REJECTED')
    identity = selected_identity(first['url'])
    standard_handoff(identity, -1).submit(identity, first)
    monitor, deadline = xbmc.Monitor(), time.monotonic()+40
    requests = set()
    while not monitor.waitForAbort(.1) and time.monotonic() < deadline:
        host.tick()
        standard.tick()
        row = standard.session.current
        if len(result['samples']) < 30:
            sample = dict(playing=standard.player.isPlaying(), video=standard.player.isPlayingVideo(),
                          session_state=row['state'] if row else None)
            if sample['video']:
                try:
                    sample.update(file=standard.player.getPlayingFile(), seconds=standard.player.getTime(),
                        property=standard.player.getPlayingItem().getProperty('bobbi.standard.request'),
                        unique=standard.player.getVideoInfoTag().getUniqueID('bobbi_request'))
                except Exception as error:sample['error']=type(error).__name__
            result['samples'].append(sample)
        if row and row['state'] == 'playing':
            requests.add(row['request_id'])
        if len([r for r in result['history'] if r['terminal_reason'] == 'NATURAL_EOF']) == 2:
            break
    result['real_av_requests'] = len(requests)
    result['real_eof_count'] = len([r for r in result['history'] if r['terminal_reason'] == 'NATURAL_EOF'])
    result['passed'] = result['real_av_requests'] == 2 and result['real_eof_count'] == 2
except Exception as error:
    result.update(passed=False, error=type(error).__name__, frames=[dict(name=f.name,line=f.lineno)
        for f in traceback.extract_tb(error.__traceback__)])
finally:
    if standard: standard.close()
    if host: host.close()
    (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
