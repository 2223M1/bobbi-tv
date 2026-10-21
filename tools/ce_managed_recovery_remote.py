"""Idle-device lifecycle trial; real installed KodiHost, no playback/account IO."""
import json
from pathlib import Path
import sys
import time
import traceback
import faulthandler
import xbmc
import xbmcaddon
import xbmcvfs

ROOT = Path(__file__).resolve().parent
addons = Path(xbmcvfs.translatePath('special://home/addons'))
sys.path.insert(0, str(addons/'script.module.bobbi.platform/lib'))
from bobbi_platform.ce_install_ui import KodiHost
from bobbi_platform.instance_lock import InstanceLock
from bobbi_platform.paths import profile
from bobbi_platform.runtime import call

host = KodiHost()
result = dict(scope='real CE native managed recovery and quiesce; no media commands', events=[])
def checkpoint(event):
    result['events'].append(event)
    (ROOT/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if event == 'normal_quiesce_lease_acquired':
        faulthandler.dump_traceback_later(8, file=trace)
enabled = skin = None
trace = (ROOT/'trial-stack.txt').open('w')
faulthandler.dump_traceback_later(8, file=trace)
try:
    if xbmc.Player().isPlaying(): raise RuntimeError('PLAYBACK_ACTIVE')
    enabled, skin = host.enabled(), host.skin()
    result.update(enabled_before=enabled,skin_before=skin)
    checkpoint('before_initial_snapshot')
    initial = call('playback', {'operation': 'snapshot'}, timeout=.3)
    result['initial_owner'] = dict(adapter=initial.get('adapter', 'native'), boot_id=initial.get('boot_id'))
    # Stop the service invocation without changing its enabled flag. This is
    # deliberately the enabled-but-missing-owner recovery condition, not reboot.
    # StopScript compares invocation filenames; unlike RunScript it does not
    # translate special:// aliases on this Kodi build.
    paths = (str(addons/'plugin.video.bobbi/service.py'),
             xbmcaddon.Addon('plugin.video.bobbi').getAddonInfo('path').rstrip('/')+'/service.py',
             'special://home/addons/plugin.video.bobbi/service.py')
    quiesce_only = globals().get('QUIESCE_ONLY', False)
    result['quiesce_only'] = quiesce_only
    cooperative = globals().get('COOPERATIVE_STOP', False)
    result['cooperative_stop'] = cooperative
    if cooperative and not quiesce_only:
        if call('quiesce', {'protocol':1}, timeout=.5) != {'accepted':True}:
            raise RuntimeError('COOPERATIVE_STOP_NOT_ACCEPTED')
    for path in (() if quiesce_only or cooperative else dict.fromkeys(paths)):
        xbmc.executebuiltin('StopScript('+path+')')
    until = time.monotonic()+15
    while not quiesce_only:
        lease = InstanceLock(str(profile(name='runtime.json'))+'.lock')
        try:
            lease.acquire()
        except OSError:
            if host.monitor.waitForAbort(.1) or time.monotonic() >= until:
                raise RuntimeError('OLD_SERVICE_DID_NOT_STOP')
        else:
            lease.close()
            break
    if not host.details('plugin.video.bobbi')['enabled']: raise RuntimeError('FIXTURE_NOT_ENABLED')
    if not quiesce_only:
        checkpoint('enabled_owner_missing_lease_free')
        host.ensure_running()
    ready = call('playback', {'operation': 'snapshot'}, timeout=.3)
    checkpoint('managed_recovery_ready')
    result['recovered_owner'] = dict(adapter=ready.get('adapter', 'native'), boot_id=ready.get('boot_id'))
    checkpoint('before_normal_quiesce')
    host.quiesce()
    checkpoint('normal_quiesce_lease_acquired')
    host.restore(skin, enabled)
    final = call('playback', {'operation': 'snapshot'}, timeout=.3)
    checkpoint('managed_restore_ready')
    result['enabled_vector_restored'] = set(host.enabled()) == set(enabled)
    result['skin_restored'] = host.skin() == skin
    result['passed'] = (result['enabled_vector_restored'] and result['skin_restored']
        and (quiesce_only or ready.get('boot_id') != initial.get('boot_id'))
        and final.get('boot_id') != ready.get('boot_id'))
    result['cycles'] = 1
    for unused in range(1, globals().get('CYCLES', 1)):
        previous = final
        checkpoint('before_normal_quiesce')
        host.quiesce()
        checkpoint('normal_quiesce_lease_acquired')
        host.restore(skin, enabled)
        final = call('playback', {'operation': 'snapshot'}, timeout=.3)
        checkpoint('managed_restore_ready')
        result['passed'] = (result['passed'] and final.get('boot_id') != previous.get('boot_id')
                            and set(host.enabled()) == set(enabled) and host.skin() == skin)
        result['cycles'] += 1
except Exception as error:
    result.update(passed=False, error=type(error).__name__, code=str(error) if str(error).isupper() else None,
        frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
finally:
    try:
        if enabled is not None: host.restore(skin, enabled)
        result['restored_at_exit'] = enabled is not None and set(host.enabled()) == set(enabled)
    except Exception as error:
        result.update(passed=False, restore_error=type(error).__name__)
    host.close()
    faulthandler.cancel_dump_traceback_later()
    trace.close()
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
