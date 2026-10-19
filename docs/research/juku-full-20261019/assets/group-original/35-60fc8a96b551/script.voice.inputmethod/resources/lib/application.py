"""Compose the input, ASR and text-injection modules on Kodi's main thread.

The add-on has exactly one job: turn a spoken phrase into text and put that
text into whatever input field Kodi currently shows.  Everything the original
assistant did after recognition (intent parsing, tool calls, conversation
window, text to speech) is deliberately absent.
"""
import fcntl
import json
from pathlib import Path
import sys
import time
import traceback
from contextlib import nullcontext
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import injection
from .settings import Settings
from .storage import write_json
# ``tr`` rather than ``text``: the recognized phrase is also called ``text`` here.
from .strings import text as tr

ADDON_ID = 'script.voice.inputmethod'
PROPERTY = 'VoiceInput.'


def rpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1,
                                                       'method': method, 'params': params})))
    if 'error' in response:
        raise ValueError(tr(31067, response['error'].get('message', method)))
    return response.get('result')


class WavMicrophone:
    """Replays a wav file through the very same capture path as a real microphone.

    Used by ``--dictate-sample`` so the whole chain (capture, speech gate, ASR,
    injection) can be exercised without anybody speaking into the remote.
    """

    def __init__(self, path, chunk_bytes=3200):
        import wave
        self.source = wave.open(str(path), 'rb')
        self.device = 'file:' + Path(path).name
        self.chunk_bytes = chunk_bytes
        self.eof = False
        self.statistics = {}

    def read(self):
        data = self.source.readframes(self.chunk_bytes // 2)
        if not data:
            self.eof = True
        return data

    def close(self):
        self.source.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


def capture(addon, profile, microphone_factory=None, values=None, progress=None):
    """Record one phrase and return the recognized text, or None."""
    from .asr.factory import gate, recognizer
    from .streaming import StreamingSession
    from .recording_ui import RecordingProgress
    values = values or Settings(addon).values()
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    owner = getattr(microphone_factory, '__self__', None)
    source = getattr(owner, 'input_source', values['voice_input']) if microphone_factory else values['voice_input']
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    progress = progress or RecordingProgress(root)
    speech_gate = gate(values, source)
    speech_gate.recognizer_endpoint = source == 'ur02' and values['recognition_engine'] == 'ncnn'
    stream = None
    session = {'version': addon.getAddonInfo('version'), 'input_source': source,
               'engine': values['recognition_engine'], 'state': 'error'}
    try:
        hint = tr(31073) if source == 'r22' else tr(31046)
        progress.create(tr(31045), hint)
        home.clearProperty(PROPERTY + 'PartialText')
        options = {'microphone_factory': microphone_factory} if microphone_factory else {}
        stream = StreamingSession(root, speech_gate, values['alsa_device'], recognizer_factory=lambda path, model:
            recognizer(path, profile, values, speech_gate, stream.stop.is_set), **options)
        stream.start()
        cancelled = False
        while not stream.done:
            if monitor.abortRequested() or progress.iscanceled():
                cancelled = True
                stream.cancel()
                break
            current = stream.snapshot()
            phase = current['phase']
            progress.set_recording(phase in ('starting', 'listening'))
            if progress.finish_requested.is_set():
                stream.finish_capture()
            home.setProperty(PROPERTY + 'State', phase)
            home.setProperty(PROPERTY + 'PartialText', current['text'])
            message = (tr(31074) if phase == 'recognizing' and source == 'r22' else
                       tr(31047) if phase == 'recognizing' else
                       tr(31048, current['level']))
            message += '\n' + (current['text'] or hint)
            progress.update(0, message)
            monitor.waitForAbort(.05)
        stream.join()
        current = stream.snapshot()
        session.update({k: v for k, v in current.items() if k not in ('text', 'level', 'phase')})
        if cancelled or monitor.abortRequested():
            session['state'] = 'cancelled'
            return None
        if current.get('error'):
            raise RuntimeError(current['error'])
        text = current['text'].strip()
        if not current['speech_detected'] or not text:
            session['state'] = 'no_text'
            xbmcgui.Dialog().notification(tr(31050), tr(31049))
            return None
        session['state'] = 'done'
        home.setProperty(PROPERTY + 'LastText', text)
        return text
    finally:
        if stream and not stream.done:
            stream.cancel()
            stream.join()
        progress.close()
        write_json(Path(profile) / 'last_session.json', session)


def wait_for_keyboard(timeout=3.0):
    """After our overlay closes, wait for the input dialog to regain focus."""
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        focused = injection.focused_window_id()
        if injection.is_keyboard(focused):
            xbmc.log('[voice-input] input dialog regained focus after %.2fs'
                     % (timeout - (deadline - time.monotonic())), xbmc.LOGINFO)
            return True
        if not seen or seen[-1] != focused:
            seen.append(focused)
        monitor.waitForAbort(.05)
    xbmc.log('[voice-input] input dialog never regained focus; windows seen: %r' % (seen,),
             xbmc.LOGWARNING)
    return False


def deliver(text, target, values):
    """Write the text where the user was typing, or report it when nowhere was."""
    from urllib.parse import quote
    home = xbmcgui.Window(10000)
    home.setProperty(PROPERTY + 'LastText', text)
    focused = injection.focused_window_id()
    xbmc.log('[voice-input] deliver: target=%r focused=%r' % (target, focused), xbmc.LOGINFO)
    if injection.is_keyboard(target) and wait_for_keyboard():
        injection.send(text, done=values['submit_mode'] == 'submit')
        home.setProperty(PROPERTY + 'LastInjected', text)
        xbmc.log('[voice-input] injected %d chars into window %r' % (len(text), target),
                 xbmc.LOGINFO)
        return 'injected'
    action = values['no_input_action']
    if action == 'notify':
        xbmcgui.Dialog().notification(tr(31050), text, time=8000)
        xbmc.log('[voice-input] no input dialog, text shown as a notification', xbmc.LOGINFO)
        return 'notified'
    if action == 'juku':
        # Juku 0.78.6+ exposes action=voice_command; it reads "query" (or "q").
        url = 'plugin://plugin.video.juku/?action=voice_command&query=' + quote(text)
        xbmc.executebuiltin('RunPlugin(' + url + ')')
        xbmc.log('[voice-input] no input dialog, forwarded to juku: ' + text, xbmc.LOGINFO)
        return 'juku'
    xbmc.log('[voice-input] no input dialog, text discarded', xbmc.LOGINFO)
    return 'ignored'


def dictate(addon, profile, sample=None):
    with (Path(profile) / 'dictation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            return _dictate(addon, profile, sample)
        finally:
            home = xbmcgui.Window(10000)
            if home.getProperty(PROPERTY + 'State') in ('starting', 'listening', 'recognizing'):
                home.setProperty(PROPERTY + 'State', 'idle')


def _dictate(addon, profile, sample=None):
    from .inputs.registry import claim, pending
    values = Settings(addon).values()
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    source = values['voice_input']
    # Read the focused window before the recording overlay takes focus away.
    target = injection.focused_window_id()
    xbmc.log('[voice-input] dictate start: source=%r target=%r keyboard=%s'
             % (source, target, injection.is_keyboard(target)), xbmc.LOGINFO)
    if sample is not None:
        text = capture(addon, profile, lambda device: WavMicrophone(sample), values)
    elif source == 'usb':
        text = capture(addon, profile, None, values)
    else:
        token = pending(home, source)
        with claim(profile, source, home, monitor, token) as factory:
            if factory is False:
                xbmcgui.Dialog().notification(tr(31050), tr(31054))
                return
            text = capture(addon, profile, factory, values)
    if not text:
        return
    return deliver(text, target, values)


def test_asr(addon, profile):
    """Transcribe the bundled AISHELL sample; verifies the engine end to end."""
    import wave
    from .asr.factory import gate, recognizer
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    values = Settings(addon).values()
    sample = Path(root) / 'resources/config/asr-test.wav'
    if not sample.is_file():
        xbmcgui.Dialog().ok(tr(31050) + ' · ' + tr(31055), tr(31063, sample))
        return True
    with wave.open(str(sample), 'rb') as source:
        pcm = source.readframes(source.getnframes())
    speech_gate = gate(values, 'usb')
    started = time.monotonic()
    with recognizer(root, profile, values, speech_gate, lambda: False) as engine:
        text = engine.transcribe(pcm)
    elapsed = time.monotonic() - started
    expected = '甚至出现交易几乎停滞的情况。'
    # Logged as well as shown: the self-test is also how a headless box is
    # checked, and the dialog cannot be read from an SSH session.
    xbmc.log('[voice-input] asr self-test: engine=%s in %.2fs expected=%r actual=%r'
             % (values['recognition_engine'], elapsed, expected, text), xbmc.LOGINFO)
    xbmcgui.Dialog().ok(tr(31050) + ' · ' + tr(31055),
                        tr(31056, values['recognition_engine'], expected, text or tr(31057)))
    return True


def test_key(addon, profile):
    """Ask the Doubao service what it thinks of the configured key.

    The dictation path collapses every 401 into "Key 无效", which cannot be
    acted on; this reports the real status for each resource id and, when the
    key is rejected, says what to look at in the console.
    """
    from .key_selftest import check
    root = Path(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    values = Settings(addon).values()
    headline, detail = check(root, profile, values)
    # Logged as well: the dialog cannot be read over SSH.
    xbmc.log('[voice-input] key self-test: %s | %s'
             % (headline, detail.replace('\n', ' ; ')), xbmc.LOGINFO)
    xbmcgui.Dialog().ok(tr(31050) + ' · ' + tr(31103), headline + '\n' + detail)
    return True


def test_inject(addon):
    """Write a fixed phrase into the focused input, to check injection alone."""
    target = injection.focused_window_id()
    if not injection.is_keyboard(target):
        xbmcgui.Dialog().ok(tr(31050) + ' · ' + tr(31058), tr(31059, target))
        return True
    injection.send(tr(31069), done=False)
    xbmcgui.Dialog().notification(tr(31050), tr(31060))
    return True


def action(addon, profile, arguments):
    if not arguments:
        xbmcgui.Dialog().ok(tr(31050), tr(31064) + '\n' + tr(31070))
    elif '--settings' in arguments:
        addon.openSettings()
    elif '--bind-voice-key' in arguments:
        from .ui.key_binding import show
        show(addon)
    elif '--configure' in arguments:
        from .configuration.ui import show
        show(addon, profile)
    elif '--test-asr' in arguments:
        return test_asr(addon, profile)
    elif '--test-key' in arguments:
        return test_key(addon, profile)
    elif '--test-inject' in arguments:
        return test_inject(addon)
    elif '--dictate-sample' in arguments:
        sample = Path(xbmcvfs.translatePath(addon.getAddonInfo('path'))) / 'resources/config/asr-test.wav'
        if not sample.is_file():
            xbmcgui.Dialog().ok(tr(31050) + ' · ' + tr(31061), tr(31063, sample))
            return True
        result = dictate(addon, profile, sample)
        if result == 'injected':
            xbmcgui.Dialog().notification(tr(31050), tr(31062))
        elif result == 'notified':
            pass
        return True
    else:
        return False
    return True


def main(addon=None, profile=None, invocation_owned=False):
    addon = addon or xbmcaddon.Addon(ADDON_ID)
    profile = Path(profile or xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    profile.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:]:
        xbmc.log('[voice-input] invoked with %r' % (sys.argv[1:],), xbmc.LOGINFO)
    if not sys.argv[1:]:
        action(addon, profile, set())
        return
    with (nullcontext(None) if invocation_owned else (profile / 'invocation.lock').open('a')) as lock:
        try:
            if not invocation_owned:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            xbmc.log('[voice-input] another invocation is still running, ignoring', xbmc.LOGWARNING)
            return
        try:
            if action(addon, profile, set(sys.argv[1:])):
                return
            if sys.argv[1:] != ['--voice']:
                return
            # Bluetooth adapters own capture.lock for their lease; USB owns it here.
            source = Settings(addon).values()['voice_input']
            if source == 'usb':
                with (profile / 'capture.lock').open('a') as capture_lock:
                    try:
                        fcntl.flock(capture_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        xbmc.log('[voice-input] another capture is already running, ignoring',
                                 xbmc.LOGWARNING)
                        return
                    dictate(addon, profile)
            else:
                dictate(addon, profile)
        except InterruptedError:
            pass
        except Exception as error:
            xbmc.log('[voice-input] ' + traceback.format_exc(), xbmc.LOGERROR)
            xbmcgui.Dialog().ok(tr(31050), str(error))
