"""One service owner for the Bluetooth remote input adapters and LAN configuration.

The USB/ALSA microphone needs no service: it is opened on demand by the
dictation script itself.  Only the Bluetooth remotes (Ugoos UR01/UR02, Tencent
Aurora, CMCC) need a long-lived owner, because their microphone is opened over
GATT/HID and the audio has to be drained while Kodi is busy recording.

The same loop also drives the LAN configuration server, because that server
must not touch ``xbmcaddon`` from an HTTP thread.
"""
import fcntl
from pathlib import Path
import time
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from ..b25_service import B25Controller, find_remote as find_b25
from ..cmcc_service import Controller, find_remote as find_cmcc
from ..nanosic_service import NanosicController, find_remote as find_nanosic
from ..r22_service import R22Controller, find_remote as find_r22
from ..ur02_service import Ur02Controller, find_remote as find_ur02
from ..settings import Settings

ADDON_ID = 'script.voice.inputmethod'
PROPERTY = 'VoiceInput.'
# Must match ADDRESSES in configuration/ui.py: the dialog reads and clears a
# fixed range of ConfigureURL<N> properties, so publishing more would strand
# addresses nobody shows and nobody clears.
ADDRESSES = 4


def local_urls(port, token):
    """Every LAN address this box answers on, primary first.

    ``xbmc.getIPAddress()`` reports a single interface, but a box with both
    Ethernet and Wi-Fi can be reachable on two addresses on the same subnet.
    Showing all of them means a phone that can only see one still scans a
    working QR code.
    """
    primary = xbmc.getIPAddress()
    addresses = [primary] if primary else []
    try:
        import socket
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith('127.'):
                addresses.append(address)
    except OSError:
        pass
    # Never hand the dialog an empty list; it indexes the first entry.
    return ' '.join('http://{}:{}/#{}'.format(address, port, token)
                    for address in addresses[:ADDRESSES]) or \
        'http://127.0.0.1:{}/#{}'.format(port, token)


def main():
    addon = xbmcaddon.Addon(ADDON_ID)
    monitor, home = xbmc.Monitor(), xbmcgui.Window(10000)
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    profile = Path(xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    profile.mkdir(parents=True, exist_ok=True)
    with (profile / 'input-service.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        adapters = []
        web = None
        stopfile = profile / 'input-stop.flag'
        stopfile.unlink(missing_ok=True)
        try:
            for source, prefix, cls, discover, activation in (
                    ('cmcc', 'CMCC', Controller, find_cmcc, 'tap'),
                    ('nanosic', 'Nanosic', NanosicController, find_nanosic, 'tap'),
                    ('ur02', 'UR02', Ur02Controller, find_ur02, 'tap'),
                    ('b25', 'B25', B25Controller, find_b25, 'tap'),
                    ('r22', 'R22', R22Controller, find_r22, 'hold')):
                controller = cls(profile, root, launch=lambda token, name=prefix:
                    home.setProperty(PROPERTY + name + 'Session', token),
                    log=lambda text: xbmc.log('[voice-input] ' + text, xbmc.LOGWARNING))
                controller.activation = activation
                controller.open()
                adapters.append((source, prefix, controller, discover))
            # A failed listener must never take the Bluetooth adapters with it;
            # dictation is the core feature, the web page is a convenience.
            from ..configuration.server import Configuration
            try:
                web = Configuration(root, profile, addon)
            except OSError as error:
                xbmc.log('[voice-service] configuration page unavailable: %s' % error,
                         xbmc.LOGERROR)
                web = None
            home.setProperty(PROPERTY + 'Service', 'running')
            home.setProperty(PROPERTY + 'ServiceVersion', addon.getAddonInfo('version'))
            last_check = -1
            settings = Settings(addon).values()
            while not monitor.abortRequested() and not stopfile.exists():
                now = time.monotonic()
                if web:
                    web.pump()
                if web and home.getProperty(PROPERTY + 'ConfigureRequested'):
                    home.clearProperty(PROPERTY + 'ConfigureRequested')
                    token = web.activate()
                    # A box with both Ethernet and Wi-Fi answering on the same
                    # LAN has two valid addresses; getIPAddress() only reports
                    # one, so list the rest as fallbacks on the TV.
                    urls = local_urls(web.port, token).split()
                    for index, item in enumerate(urls, 1):
                        home.setProperty(PROPERTY + 'ConfigureURL%d' % index, item)
                    home.setProperty(PROPERTY + 'ConfigureURLCount', str(len(urls)))
                    home.setProperty(PROPERTY + 'ConfigureURL', urls[0])
                    # The dialog mirrors the PIN on the TV and checks it again
                    # before accepting the web page, so a browser that guessed
                    # the token still needs the code only the TV shows.
                    home.setProperty(PROPERTY + 'ConfigurePIN', web.pin)
                if now - last_check >= 1:
                    settings = Settings(addon).values()
                    for source, prefix, controller, discover in adapters:
                        enabled = source == settings['voice_input']
                        if not enabled and controller.hid is not None:
                            controller.detach('音频输入设备已切换。')
                        elif enabled and controller.hid is None:
                            device = discover()
                            if device:
                                try:
                                    controller.attach(device)
                                except (OSError, ValueError) as error:
                                    controller.error = str(error)
                    last_check = now
                for source, prefix, controller, discover in adapters:
                    controller.tick(settings['max_seconds'], timeout=.005)
                    enabled = settings['voice_input'] == source
                    home.setProperty(PROPERTY + prefix + 'Status', controller.status if enabled else 'disabled')
                    home.setProperty(PROPERTY + prefix + 'Connected', 'true' if controller.hid is not None else 'false')
                    home.setProperty(PROPERTY + prefix + 'Session',
                        controller.session.token if controller.session and controller.session.peer is None else '')
                monitor.waitForAbort(.01)
        except Exception as error:
            xbmc.log('[voice-service] ' + str(error), xbmc.LOGERROR)
        finally:
            if web:
                web.close()
            for source, prefix, controller, discover in reversed(adapters):
                controller.close()
                for suffix in ('Status', 'Connected', 'Session'):
                    home.clearProperty(PROPERTY + prefix + suffix)
            for suffix in ('Service', 'ServiceVersion', 'ConfigureURL',
                           'ConfigureURLCount',
                           'ConfigurePIN', 'ConfigureRequested'):
                home.clearProperty(PROPERTY + suffix)
            for index in range(1, ADDRESSES + 1):
                home.clearProperty(PROPERTY + 'ConfigureURL%d' % index)
            stopfile.unlink(missing_ok=True)
