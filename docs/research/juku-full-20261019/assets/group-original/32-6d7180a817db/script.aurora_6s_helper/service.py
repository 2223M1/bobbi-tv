import fcntl
import json
from pathlib import Path
import sys
import threading
import time

import xbmc
import xbmcgui

sys.path.insert(0, str(Path(__file__).parent / 'resources/lib'))
from config import ADDON_ID, load_profile, migrate_colors
from effects import encode, levels, software_frame, smooth_levels
from hardware import Controller
from diagnostics import exception_details
from bluetooth_startup import recover_once


class Monitor(xbmc.Monitor):
    dirty = True
    wake_generation = 0

    def onSettingsChanged(self):
        self.dirty = True

    def onNotification(self, sender, method, data):
        if sender == "xbmc" and method == "System.OnWake":
            self.wake_generation += 1
        if method.startswith('Player.') or (sender == ADDON_ID and method == 'Other.aurora.apply'):
            self.dirty = True


def main():
    service_lock = open('/run/aurora6s-service.lock', 'a')
    try:
        fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        service_lock.close()
        xbmc.log('[Aurora6S] service already running', xbmc.LOGINFO)
        return
    monitor = Monitor()
    bluetooth_thread = threading.Thread(
        target=recover_once,
        args=(monitor, lambda message: xbmc.log('[Aurora6S] Bluetooth: ' + message, xbmc.LOGINFO)),
        name='aurora-bluetooth-startup', daemon=True)
    bluetooth_thread.start()
    player = xbmc.Player()
    controller = Controller()
    current = None
    started = 0
    software = False
    values = (0, 0, 0)
    last_error = None
    retry_at = 0
    handled_wake = 0
    status = Path('/run/aurora6s-led-status.json')
    try:
        migrate_colors()
        while not monitor.abortRequested():
            playing = player.isPlaying()  # remains true while paused
            wake_generation = monitor.wake_generation
            waking = wake_generation != handled_wake
            if monitor.dirty or waking or current is None or playing != (current['name'] == 'playback'):
                monitor.dirty = False
                # Failed wake writes use the existing timed retry.
                handled_wake = wake_generation
                try:
                    profile = load_profile(playing)
                    if profile != current or last_error or waking:
                        if not profile['enabled']:
                            controller.close()
                            software = False
                            backend = 'disabled'
                        else:
                            if waking:
                                controller.resume()
                            values = (0, 0, 0) if profile['mode'] == 'off' else levels(profile['rgb'], profile['brightness'])
                            breathing = profile['mode'] == 'breathing'
                            if breathing and profile.get('smooth', True):
                                values = smooth_levels(values)
                            software = breathing and len(set(values) - {0}) > 2
                            # A software fade starts dark; do not flash the peak first.
                            initial = (0, 0, 0) if software else values
                            controller.apply(encode(initial, breathing and not software, profile['speed']))
                            backend = 'software' if software else 'hardware'
                        current = profile
                        started = time.monotonic()
                        last_error = None
                        status.write_text(json.dumps(dict(profile=profile, backend=backend), ensure_ascii=False), encoding='utf-8')
                        xbmc.log('[Aurora6S] applied ' + profile['name'] + ' / ' + backend, xbmc.LOGINFO)
                        if waking:
                            xbmc.log('[Aurora6S] lighting restored after wake / ' + backend, xbmc.LOGINFO)
                except Exception as exc:
                    software = False
                    try:
                        controller.close()
                    except Exception as restore_error:
                        xbmc.log('[Aurora6S] restore: ' + str(restore_error), xbmc.LOGERROR)
                    if str(exc) != last_error:
                        xbmc.log(exception_details('lighting'), xbmc.LOGERROR)
                        xbmcgui.Dialog().notification('极光 6S 灯条', str(exc), xbmcgui.NOTIFICATION_ERROR, 5000)
                    last_error = str(exc)
                    # Avoid retrying every frame when hardware is absent on first install.
                    current = dict(name='playback' if playing else 'normal')
                    retry_at = time.monotonic() + 15
                    status.write_text(json.dumps(dict(error=last_error), ensure_ascii=False), encoding='utf-8')
            if software:
                try:
                    controller.apply(encode(software_frame(values, time.monotonic() - started, current['speed'])), verify=False)
                except Exception as exc:
                    software = False
                    monitor.dirty = True
                    last_error = str(exc)
            if last_error and time.monotonic() >= retry_at:
                monitor.dirty = True
            if monitor.waitForAbort(.016 if software else .25):
                break
    finally:
        try:
            controller.close()
        except Exception as exc:
            xbmc.log('[Aurora6S] restore on exit: ' + str(exc), xbmc.LOGERROR)
        status.unlink(missing_ok=True)
        service_lock.close()


if __name__ == '__main__':
    main()
