"""One service owner for input adapters and the LAN configuration bridge."""
from ..data_paths import data_path
import fcntl
from pathlib import Path
import time
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from ..cmcc_service import Controller, find_remote as find_cmcc
from ..nanosic_service import NanosicController, find_remote as find_nanosic
from ..ur02_service import Ur02Controller, find_remote as find_ur02
from ..r22_service import R22Controller, find_remote as find_r22
from ..b25_service import B25Controller, find_remote as find_b25
from ..settings import Settings


def main():
    addon = xbmcaddon.Addon('script.voice.assistant')
    monitor, home = xbmc.Monitor(), xbmcgui.Window(10000)
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    profile = Path(xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    profile.mkdir(parents=True, exist_ok=True)
    from ..profile_upgrade import prepare_profile
    if not prepare_profile(profile, monitor.abortRequested, service=True):
        return
    with (data_path(profile, 'cmcc-service.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        adapters = []
        web = None
        resident = None
        buddy = None
        speech = None
        asr = None
        dependencies = None
        stopfile = data_path(profile, 'cmcc-stop.flag')
        stopfile.unlink(missing_ok=True)
        try:
            for source, prefix, cls, discover in (
                    ('cmcc', 'CMCC', Controller, find_cmcc),
                    ('nanosic', 'Nanosic', NanosicController, find_nanosic),
                    ('ur02', 'UR02', Ur02Controller, find_ur02),
                    ('r22', 'R22', R22Controller, find_r22),
                    ('b25', 'B25', B25Controller, find_b25)):
                controller = cls(profile, root, launch=lambda token, name=prefix:
                    home.setProperty('VoiceAssistant.' + name + 'Session', token),
                    log=lambda text: xbmc.log('[voice-input] ' + text, xbmc.LOGWARNING))
                controller.activation = 'hold' if source == 'r22' else 'tap'
                controller.open()
                adapters.append((source, prefix, controller, discover))
            from ..configuration.server import Configuration
            from ..application import rpc
            from ..dependencies.service import Manager
            dependencies = Manager(root, profile)
            settings_open = lambda: xbmc.getCondVisibility('Window.IsVisible(addonsettings)')
            web = Configuration(root, profile, addon, rpc, xbmc.executebuiltin, dependencies=dependencies, settings_open=settings_open)
            from ..asr.service import Service as AsrService
            asr = AsrService(root, profile, rpc=rpc)
            from ..intelligence.resident import Resident
            resident = Resident(root, profile)
            from ..codebuddy_resident import Resident as BuddyResident
            buddy = BuddyResident(root, profile,
                log=lambda message: xbmc.log('[voice-codebuddy] ' + message, xbmc.LOGWARNING))
            from ..speech.service import Service
            from ..speech.output import AlsaOutput
            try:
                # isPlaying() also stays true while paused; only advancing media
                # should keep the audio device or interrupt a spoken response.
                speech = Service(root, profile, AlsaOutput(rpc, xbmc.audioSuspend, xbmc.audioResume),
                    lambda: xbmc.getCondVisibility('Player.Playing'),
                    log=lambda message: xbmc.log('[voice-speech] ' + message, xbmc.LOGWARNING))
            except Exception as error:
                xbmc.log('[voice-speech] 启动失败：' + type(error).__name__, xbmc.LOGWARNING)
            home.setProperty('VoiceAssistant.CMCCService', 'running')
            home.setProperty('VoiceAssistant.CMCCServiceVersion', addon.getAddonInfo('version'))
            last_check = -1
            settings = Settings(addon).values()
            previous_settings = dict(settings)
            prompt_dependencies = False
            while not monitor.abortRequested() and not stopfile.exists():
                now = time.monotonic()
                if resident:
                    resident.tick(settings)
                if buddy:
                    buddy.tick(settings)
                web.pump()
                if web.input_changed:
                    settings = Settings(addon).values()
                    last_check = -1
                    web.input_changed = False
                if asr:
                    asr.tick(settings)
                    with dependencies.lock:
                        dependencies.runtime['asr'] = dict(asr.status)
                if speech:
                    recording = (home.getProperty('VoiceAssistant.State') in ('starting','listening','recognizing')
                        or bool(home.getProperty('VoiceAssistant.USBRecordRequested'))
                        or any(getattr(controller.session, 'recording', False)
                               for source, prefix, controller, discover in adapters))
                    try:
                        speech.tick(settings, recording=recording)
                        home.setProperty('VoiceAssistant.SpeechReady', 'true' if speech.engine.ready.is_set() and speech.enabled else 'false')
                    except Exception as error:
                        xbmc.log('[voice-speech] 播放失败：' + type(error).__name__, xbmc.LOGWARNING)
                        speech.close()
                        speech = None
                        home.setProperty('VoiceAssistant.SpeechReady', 'false')
                if home.getProperty('VoiceAssistant.AccountRefreshRequested'):
                    try:
                        web.job('account')
                        home.clearProperty('VoiceAssistant.AccountRefreshRequested')
                    except ValueError:
                        pass
                if home.getProperty('VoiceAssistant.ConfigureRequested'):
                    home.clearProperty('VoiceAssistant.ConfigureRequested')
                    token = web.activate()
                    address = xbmc.getIPAddress()
                    home.setProperty('VoiceAssistant.ConfigureURL',
                        'http://{}:{}/#{}'.format(address, web.http.server_port, token))
                    home.setProperty('VoiceAssistant.ConfigurePIN', web.pin)
                with web.lock:
                    logged_in = web.snapshot['logged_in']
                home.setProperty('VoiceAssistant.CodexLoggedIn', 'true' if logged_in else 'false')
                if now - last_check >= 1:
                    if not settings_open():
                        settings = Settings(addon).values()
                    dependencies.update(settings)
                    if settings != previous_settings:
                        prompt_dependencies = not dependencies.web_saved
                        previous_settings = dict(settings)
                    dependencies.web_saved = False
                    if (prompt_dependencies and not xbmc.getCondVisibility('Window.IsVisible(addonsettings)')
                            and home.getProperty('VoiceAssistant.State') in ('', 'idle')):
                        with (data_path(profile, 'invocation.lock')).open('a') as invocation:
                            try:
                                fcntl.flock(invocation, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                needs = dependencies.state(settings)['missing']
                                prompt_dependencies = False
                            except BlockingIOError:
                                needs = []
                        if needs:
                            xbmc.executebuiltin('RunScript(script.voice.assistant,--dependencies)')
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
                    home.setProperty('VoiceAssistant.' + prefix + 'Status', controller.status if enabled else 'disabled')
                    home.setProperty('VoiceAssistant.' + prefix + 'Connected', 'true' if controller.hid is not None else 'false')
                    home.setProperty('VoiceAssistant.' + prefix + 'Session',
                        controller.session.token if controller.session and controller.session.peer is None else '')
        except Exception as error:
            xbmc.log('[voice-service] ' + str(error), xbmc.LOGERROR)
        finally:
            if asr:
                asr.close()
            if speech:
                speech.close()
                home.clearProperty('VoiceAssistant.SpeechReady')
            if resident:
                resident.close()
            if buddy:
                buddy.close()
            if web:
                web.close()
            if dependencies:
                dependencies.close()
            for source, prefix, controller, discover in reversed(adapters):
                controller.close()
                for suffix in ('Status', 'Connected', 'Session'):
                    home.clearProperty('VoiceAssistant.' + prefix + suffix)
            for suffix in ('CMCCService', 'CMCCServiceVersion', 'ConfigureURL', 'ConfigurePIN', 'ConfigureRequested', 'CodexLoggedIn'):
                home.clearProperty('VoiceAssistant.' + suffix)
            stopfile.unlink(missing_ok=True)
