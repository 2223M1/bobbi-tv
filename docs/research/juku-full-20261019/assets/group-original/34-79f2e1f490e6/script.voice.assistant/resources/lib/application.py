"""Compose the input, ASR, Codex and configuration modules on Kodi's main thread."""
from .data_paths import data_path
import fcntl
from pathlib import Path
import sys
import time
from contextlib import nullcontext
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from .settings import Settings, get_setting, set_setting, get_proxy

ADDON_ID = 'script.voice.assistant'
PROPERTY = 'VoiceAssistant.'


def rpc(method, params):
    import json
    response = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1,
                                                       'method': method, 'params': params})))
    if 'error' in response:
        raise ValueError('Kodi 操作失败：' + response['error'].get('message', method))
    return response.get('result')


def capture(addon, profile, microphone_factory=None, values=None, progress=None, tick=None):
    from .asr.factory import gate, recognizer
    from .streaming import StreamingSession
    from .recording_ui import RecordingProgress
    values = values if values is not None else Settings(addon).capture_values()
    if values['recognition_engine'] == 'off':
        raise ValueError('语音转文字已关闭，请先在设置中启用。')
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    owner = getattr(microphone_factory, '__self__', None)
    source = getattr(owner, 'input_source', values['voice_input']) if microphone_factory else values['voice_input']
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    previous_state = home.getProperty(PROPERTY + 'State')
    progress = progress or RecordingProgress(root)
    speech_gate = gate(values, source)
    speech_gate.recognizer_endpoint = False
    stream = None
    session = {'version': addon.getAddonInfo('version'), 'input_source': source, 'engine': values['recognition_engine'], 'state': 'error'}
    try:
        hint = recording_hint(source)
        progress.create('语音助手 · 正在听', hint)
        home.clearProperty(PROPERTY + 'PartialText')
        options = {'microphone_factory': microphone_factory} if microphone_factory else {}
        stream = StreamingSession(root, speech_gate, values['alsa_device'], recognizer_factory=lambda path, model:
            recognizer(path, profile, values, speech_gate, stream.stop.is_set, rpc=rpc), **options)
        stream.start()
        cancelled = False
        while not stream.done:
            if tick:
                tick()
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
            message = (('录音已结束 · 正在识别' if source == 'r22' else '麦克风已关闭 · 正在识别') if phase == 'recognizing' else
                       '正在听 · 音量 {:.0f}'.format(current['level']))
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
            xbmcgui.Dialog().notification('语音助手', '没有识别出文字，请靠近麦克风再说一次。')
            return None
        session['state'] = 'done'
        home.setProperty(PROPERTY + 'LastText', text)
        return text
    finally:
        if stream and not stream.done:
            stream.cancel()
            stream.join()
        # Capture owns these temporary states. Release them before the next
        # speech session is opened, including cancelled/failed recordings.
        if home.getProperty(PROPERTY + 'State') in ('starting', 'listening', 'recognizing'):
            home.setProperty(PROPERTY + 'State', previous_state
                             if previous_state in ('thinking', 'conversation') else 'idle')
        progress.close()
        from .storage import write_json
        write_json(data_path(Path(profile), 'last_session.json'), session)


def recording_hint(source):
    return ('按住语音键说话 · 松开结束 · OK 提交 · 返回取消' if source == 'r22' else
            '请说话 · 停顿自动结束 · OK 提交 · 返回取消')


def conversation(addon, profile, initial_token=None, initial_source=None, initial_text=None):
    with (data_path(Path(profile), 'conversation.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            return _conversation(addon, profile, initial_token, initial_source, initial_text)
        finally:
            home = xbmcgui.Window(10000)
            if home.getProperty(PROPERTY + 'State') in ('starting', 'listening', 'recognizing', 'thinking', 'conversation'):
                home.setProperty(PROPERTY + 'State', 'idle')


def _conversation(addon, profile, initial_token=None, initial_source=None, initial_text=None):
    from .inputs.registry import claim, pending, resolve_token
    from .intelligence.ui_context import capture as capture_ui_context
    # Read once before RecordingProgress/ConversationWindow owns the focus.
    # Follow-up voice, keyboard and steering input keep this same entry snapshot.
    ui_context = capture_ui_context(rpc)
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    config = Settings(addon)
    home, monitor = xbmcgui.Window(10000), xbmc.Monitor()
    source = initial_source or config.get('voice_input')
    if initial_text is None:
        if source != 'usb':
            initial_token = resolve_token(home, source, monitor, initial_token)
            if initial_token is None:
                return
        values = config.capture_values()
        if values['recognition_engine'] == 'off':
            raise ValueError('语音转文字已关闭，请先在设置中启用。')
        from .recording_ui import RecordingProgress
        progress = RecordingProgress(root)
        try:
            # Render before client imports/claim and ASR setup. The resident
            # input service buffers Bluetooth PCM while the frontend starts.
            progress.create('语音助手 · 正在听', recording_hint(source))
            while not progress.window.ready.is_set():
                if monitor.waitForAbort(.01):
                    return
                if progress.iscanceled():
                    break
            if monitor.abortRequested():
                return
            # Even an early Back must claim/release an existing lease so the
            # resident service closes the remote's microphone immediately.
            with claim(profile, source, home, monitor, initial_token) as factory:
                if factory is False or monitor.abortRequested() or progress.iscanceled():
                    return
                initial_text = capture(addon, profile, factory, values, progress=progress)
        finally:
            progress.close()
    if not initial_text:
        return
    import queue
    from .intelligence.sessions import Sessions, signature
    values = config.values()
    sessions = Sessions(profile, values['session_policy'], signature(values))
    from .ui.conversation import ConversationWindow
    from .ui.agent_turn import run_turn, playback_state, close_for_playback
    from .ui.conversation import ConversationProgress
    from .intelligence.transcript import Transcript
    from .ui.live_input import LiveInput
    transcript = Transcript(profile, sessions.history_id)
    text = initial_text
    selection = None
    window = None
    speaker = None
    from .speech.client import Speech
    try:
        window = ConversationWindow('VoiceConversation.xml', root, 'Default', '1080i')
        window.show()
        while not window.ready.is_set() and not monitor.abortRequested():
            monitor.waitForAbort(.02)
        if monitor.abortRequested():
            return
        window.restore(transcript.rounds)
        window.activity_sink = transcript.activity
        while text and not monitor.abortRequested():
            if speaker: speaker.stop()
            values = Settings(addon).values()
            sessions.refresh(policy=values['session_policy'], signature=signature(values))
            if transcript.session_id != sessions.history_id:
                transcript = Transcript(profile, sessions.history_id)
                window.restore(transcript.rounds)
                window.activity_sink = transcript.activity
            home.setProperty(PROPERTY + 'State', 'thinking')
            speaker = Speech(profile, values)
            trim_history = len(transcript.rounds) >= transcript.LIMIT
            transcript.begin(text)
            if trim_history:
                window.restore(transcript.rounds[:-1])
            window.last_activity = None
            window.append_message('user', text)
            before_playback = playback_state()
            live_input = LiveInput(addon, profile, values, window, home, monitor, capture, cancel_speech=speaker.stop)
            def append_input(role, message):
                window.append_message(role, message)
                transcript.message(role, message)
            window.accepting_input = window.task_active = True
            window.task_stop.clear()
            try:
                presentation = (run_turn(root, profile, values, text, sessions, rpc, xbmc.executebuiltin, home, monitor,
                                        progress=ConversationProgress(window), poll_input=live_input.poll, on_message=append_input, speech=speaker,
                                        ui_context=ui_context, selection=selection))
            except Exception as error:
                speaker.stop()
                presentation = {'message': '处理失败：' + str(error), 'interaction': 'continue', 'choices': []}
            finally:
                selection = None
                window.accepting_input = window.task_active = False
                window.task_stop.clear()
            if presentation is None:
                return
            ui_action = presentation.pop('ui_action', None)
            transcript.finish(presentation)
            if ui_action:
                from .ui.navigation import handoff
                handoff(window, ui_action, monitor, xbmc.executebuiltin, rpc=rpc)
                return
            values = Settings(addon).values()
            source = values['voice_input']
            if presentation['interaction'] == 'close':
                return
            window.present(presentation)
            speaker.finish(presentation['message'])
            home.setProperty(PROPERTY + 'State', 'conversation')
            text = None
            next_playback_check = 0
            while not window.cancelled.is_set() and not monitor.abortRequested():
                window.refresh()
                if time.monotonic() >= next_playback_check:
                    # Addons/native commands may start video after the AI has replied.
                    if close_for_playback(before_playback, playback_state(), None):
                        return
                    next_playback_check = time.monotonic() + .25
                token = pending(home, source) if source != 'usb' else ''
                usb_requested = home.getProperty(PROPERTY + 'USBRecordRequested')
                try:
                    action, value = window.events.get_nowait()
                except queue.Empty:
                    action, value = '', ''
                if action == 'text':
                    speaker.stop()
                    text = value
                    break
                if action == 'media':
                    speaker.stop()
                    selection = value
                    text = '请播放我选择的影视：' + value['title']
                    break
                if action == 'keyboard':
                    speaker.stop()
                    text = xbmcgui.Dialog().input('继续对话').strip()
                    if text:
                        break
                if token or (source == 'usb' and (usb_requested or action == 'voice')):
                    speaker.stop()
                    home.clearProperty(PROPERTY + 'USBRecordRequested')
                    with claim(profile, source, home, monitor, token or None) as factory:
                        if factory is not False:
                            try:
                                text = capture(addon, profile, factory, values, progress=ConversationProgress(window))
                            except Exception as error:
                                text = None
                                window.activity('语音识别失败，请重试：' + str(error))
                    if text and not window.cancelled.is_set():
                        break
                    text = None
                    home.setProperty(PROPERTY + 'State', 'conversation')
                elif action == 'voice':
                    window.status('请轻按遥控器的语音键开始说话')
                monitor.waitForAbort(.05)
            if window.cancelled.is_set():
                return
    finally:
        if speaker: speaker.stop()
        sessions.close()
        transcript.interrupt()
        if window:
            window.close()
        home.setProperty(PROPERTY + 'State', 'idle')


def account_info(addon, profile):
    """Read native account/model metadata without blocking the Kodi GUI."""
    import threading
    from .codex_account import CodexAccount
    stop, done = threading.Event(), threading.Event()
    result = {}
    monitor = xbmc.Monitor()
    progress = xbmcgui.DialogProgress()
    root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    def work():
        try:
            with CodexAccount(root, profile, stop.is_set, proxy=get_proxy(addon)) as account:
                result.update(account.status())
                result['models'] = account.models() if result['logged_in'] else []
        except Exception:
            result['error'] = '无法读取 Codex 账号，请检查网络或重新登录。'
        finally:
            done.set()
    worker = threading.Thread(target=work, name='codex-model-list')
    progress.create('Codex 订阅', '正在读取账号和模型…')
    worker.start()
    try:
        while not done.is_set():
            if monitor.abortRequested() or progress.iscanceled():
                stop.set()
                break
            monitor.waitForAbort(.05)
        worker.join()
        if stop.is_set():
            raise InterruptedError()
        if result.get('error'):
            raise ValueError(result['error'])
        return result
    finally:
        stop.set()
        worker.join()
        progress.close()


def action(addon, profile, arguments):
    if not arguments:
        xbmcgui.Dialog().ok('语音助手', '请先将语音按键绑定到运行本插件，再按语音键运行。\n可在插件设置中选择“绑定语音按键”。')
    elif '--settings' in arguments:
        addon.openSettings()
    elif '--dependencies' in arguments:
        from .dependencies.ui import show
        show(profile)
    elif '--bind-voice-key' in arguments:
        from .ui.key_binding import show
        request = next((arg.split('=', 1)[1] for arg in arguments if arg.startswith('--bind-request=')), None)
        show(addon, request)
    elif '--configure' in arguments:
        from .configuration.ui import show
        show(addon, profile)
    elif arguments.intersection({'--codex-login', '--codex-account', '--codex-logout'}):
        from .codex_account_ui import login, account_action
        if '--codex-login' in arguments:
            login(addon, profile)
        else:
            account_action(addon, profile, logout='--codex-logout' in arguments)
        xbmcgui.Window(10000).setProperty(PROPERTY + 'AccountRefreshRequested', 'true')
        if '--codex-logout' in arguments:
            (data_path(profile, 'conversation.json')).unlink(missing_ok=True)
            if get_setting(addon, 'recognition_engine') == 'codex':
                set_setting(addon, 'recognition_engine', 'off')
    elif arguments.intersection({'--select-asr', '--select-codex-model', '--select-codex-effort'}):
        if '--select-asr' in arguments:
            from .settings import FIELDS
            options = FIELDS['recognition_engine'].options
            index = xbmcgui.Dialog().select('选择语音转文字', [label for key, label in options])
            if index >= 0:
                set_setting(addon, 'recognition_engine', options[index][0])
        else:
            status = account_info(addon, profile)
            if not status['logged_in']:
                xbmcgui.Dialog().ok('订阅模型', '请先登录 Codex。')
                return True
            models = status['models']
            if '--select-codex-model' in arguments:
                index = xbmcgui.Dialog().select('订阅模型', ['自动选择'] + [m.get('displayName', m['model']) for m in models])
                if index >= 0:
                    set_setting(addon, 'codex_chatgpt_model', '' if index == 0 else models[index - 1]['model'])
                    set_setting(addon, 'codex_chatgpt_effort', '')
            else:
                model = next((m for m in models if m['model'] == get_setting(addon, 'codex_chatgpt_model')),
                             next((m for m in models if m.get('isDefault')), models[0] if models else {}))
                efforts = [e['reasoningEffort'] for e in model.get('supportedReasoningEfforts', [])]
                index = xbmcgui.Dialog().select('思考强度', ['模型默认'] + efforts)
                if index >= 0:
                    set_setting(addon, 'codex_chatgpt_effort', '' if index == 0 else efforts[index - 1])
    elif '--clear-agent-context' in arguments:
        (data_path(profile, 'conversation.json')).unlink(missing_ok=True)
        xbmcgui.Dialog().notification('语音助手', '下次指令将新建对话。')
    else:
        return False
    return True


def main(addon=None, profile=None, invocation_owned=False):
    addon = addon or xbmcaddon.Addon(ADDON_ID)
    profile = Path(profile or xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    profile.mkdir(parents=True, exist_ok=True)
    if not sys.argv[1:]:
        action(addon, profile, set())
        return
    if not invocation_owned:
        from .profile_upgrade import prepare_profile
        if not prepare_profile(profile):
            return
    with (nullcontext(None) if invocation_owned else (data_path(profile, 'invocation.lock')).open('a')) as lock:
        try:
            if not invocation_owned:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            home = xbmcgui.Window(10000)
            if sys.argv[1:] == ['--voice'] and home.getProperty(PROPERTY + 'State') in ('conversation', 'thinking') and get_setting(addon, 'voice_input') == 'usb':
                home.setProperty(PROPERTY + 'USBRecordRequested', str(time.monotonic()))
            return
        try:
            if action(addon, profile, set(sys.argv[1:])):
                return
            if sys.argv[1:] != ['--voice']:
                return
            # Bluetooth service owns capture.lock for its lease. USB owns it here.
            source = get_setting(addon, 'voice_input')
            if source == 'usb':
                with (data_path(profile, 'capture.lock')).open('a') as capture_lock:
                    try:
                        fcntl.flock(capture_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return
                    conversation(addon, profile)
            else:
                conversation(addon, profile)
        except InterruptedError:
            pass
        except Exception as error:
            import traceback
            xbmc.log('[voice-assistant] ' + traceback.format_exc(), xbmc.LOGERROR)
            xbmcgui.Dialog().ok('语音助手', str(error))
