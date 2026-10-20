"""Agent work stays in a worker; approval dialogs stay on Kodi's main thread."""
from ..data_paths import data_path
import queue
import threading
import time
import xbmc
import xbmcgui
import xbmcaddon

from ..recording_ui import RecordingProgress
from ..intelligence.runtime import create_agent, create_tools
from ..intelligence.presentation import parse
from ..storage import write_json
from ..settings import Settings, assistant_settings, apply_assistant_setting
from ..version import VERSION


def playback_state():
    """Underlying video window stays active while our modal dialog is on top."""
    try:
        player = xbmc.Player()
        if player.isPlayingVideo():
            return bool(xbmc.getCondVisibility('Window.IsActive(fullscreenvideo)')), player.getPlayingFile()
    except RuntimeError:
        pass
    return False, ''


def close_for_playback(before, after, tools):
    return bool(after[0] and (after != before or getattr(tools, 'playback_started', False)
                            or getattr(tools, 'fullscreen_requested', False)))


def run_turn(root, profile, values, text, sessions, rpc, builtin, home, monitor, progress=None, poll_input=None, on_message=None, speech=None,
             ui_context=None, selection=None):
    stop, done = threading.Event(), threading.Event()
    requests = queue.Queue()
    questions = queue.Queue()
    question_flow = None
    agent_name = ('本地命令' if values.get('agent_backend') == 'off' else
                  'CodeBuddy' if values.get('agent_backend') == 'codebuddy' else 'Codex')
    shared = {'message': '正在连接 ' + agent_name + '…'}
    from ..intelligence.steering import Steering
    steering = Steering() if poll_input else None
    round_ready, next_ready = threading.Event(), threading.Event()
    finishing = False
    activities = queue.Queue()
    before_playback = playback_state()
    embedded = progress is not None
    progress = progress or RecordingProgress(str(root))
    progress.create('语音助手 · ' + agent_name, text[-160:])
    progress.set_recording(False)
    if embedded and hasattr(progress, 'window') and on_message:
        from .questions import QuestionFlow
        question_flow = QuestionFlow(questions, progress.window, on_message)
    began = time.monotonic()
    playback_timing = []

    def report(message):
        shared['message'] = message
        activities.put(message)

    def drain_activity():
        while True:
            try:
                message = activities.get_nowait()
            except queue.Empty:
                return
            if hasattr(progress, 'activity'):
                progress.activity(message)

    def cancelled():
        return stop.is_set() or monitor.abortRequested()

    def worker_rpc(method, params):
        if method != 'Player.Open':
            return rpc(method, params)
        # Kodi may process disc/remote-file preparation on its GUI thread.
        # Do not dispatch it while the opening message is still in our queue.
        event, answer = threading.Event(), {}
        started = time.monotonic()
        timing = {'requested_seconds': round(started - began, 3)}
        playback_timing.append(timing)
        requests.put(('@before-playback', None, event, answer))
        while not event.wait(.05):
            if cancelled():
                raise InterruptedError('已取消，未开始打开影片。')
        if cancelled() or not answer.get('ready'):
            raise InterruptedError('已取消，未开始打开影片。')
        timing['ui_ready_seconds'] = answer['at']
        timing['ui_wait_seconds'] = round(time.monotonic() - started, 3)
        started = time.monotonic()
        timing['dispatch_seconds'] = round(started - began, 3)
        try:
            return rpc(method, params)
        finally:
            timing['rpc_seconds'] = round(time.monotonic() - started, 3)

    def confirm(title, message):
        event, answer = threading.Event(), {}
        requests.put((title, message, event, answer))
        while not event.wait(.05):
            if cancelled():
                raise InterruptedError('已取消。')
        if cancelled():
            raise InterruptedError('已取消。')
        return answer.get('value', False)

    def settings_request(operation, payload):
        event, answer = threading.Event(), {}
        requests.put(('@' + operation, payload, event, answer))
        while not event.wait(.05):
            if cancelled():
                raise InterruptedError('已取消。')
        if cancelled():
            raise InterruptedError('已取消。')
        if answer.get('error'):
            raise ValueError(answer['error'])
        return answer['value']

    def work():
        try:
            from ..intelligence.commands import Commands, movie_request
            tool_options = dict(
                assistant_get=lambda query: settings_request('settings-get', query),
                assistant_set=lambda setting, value: settings_request('settings-set', (setting, value)), defer_ui=True,
                ui_context=ui_context)
            tools = create_tools(profile, values, worker_rpc, builtin, confirm, sessions, **tool_options)
            shared['tools'] = tools
            current, current_selection = text, selection
            agent = None
            all_tools = []
            while True:
                options = {'steering': steering} if steering else {}
                if speech and speech.available:
                    options.update(speech=speech.say, speech_options=values)
                outcome = Commands(tools).process(current, current_selection, cancelled, report)
                current_selection = None
                if outcome is not None:
                    if hasattr(sessions, 'record_local'):
                        sessions.record_local(current, parse(outcome['reply'], tools)['message'])
                elif values.get('agent_backend') == 'off':
                    outcome = Commands._outcome(current,
                        '未找到相近的影视或频道。智能体已关闭，尚未执行播放。' if movie_request(current) else '')
                else:
                    if agent is None:
                        agent, tools = create_agent(root, profile, values, worker_rpc, builtin, confirm, sessions,
                            request_user_input=questions.put if question_flow else None, tools=tools, **tool_options)
                        shared['tools'] = tools
                    outcome = agent.run(current, cancelled=cancelled, progress=report, **options)
                all_tools.extend(outcome['tools'])
                shared['outcome'] = dict(outcome, tools=list(all_tools))
                sessions.completed(tools.media.values())
                if steering is None:
                    break
                round_ready.set()
                while not next_ready.wait(.05):
                    if cancelled():
                        raise InterruptedError('已取消。')
                next_ready.clear()
                if cancelled():
                    raise InterruptedError('已取消。')
                current = shared.get('next_text')
                if current is None:
                    break
        except InterruptedError:
            shared['cancelled'] = True
        except Exception as error:
            # Credentials are scrubbed by the Codex and ASR boundaries.
            shared['error'] = str(error)
        finally:
            done.set()

    worker = threading.Thread(target=work, name='assistant-codex')
    worker.start()
    try:
        while not done.is_set():
            drain_activity()
            if monitor.abortRequested() or progress.iscanceled():
                stop.set()
                break
            try:
                title, message, event, answer = requests.get_nowait()
            except queue.Empty:
                pass
            else:
                if title == '@before-playback':
                    try:
                        drain_activity()
                        progress.update(0, shared['message'] + '\n返回取消')
                        # Yield one normal UI polling interval so Kodi can draw
                        # the updated controls before handling Player.Open.
                        if monitor.waitForAbort(.05) or progress.iscanceled():
                            stop.set()
                        else:
                            answer.update(ready=True, at=round(time.monotonic() - began, 3))
                    finally:
                        event.set()
                    continue
                if title in ('@settings-get', '@settings-set'):
                    try:
                        config = Settings(xbmcaddon.Addon('script.voice.assistant'))
                        if title == '@settings-get':
                            answer['value'] = assistant_settings(config, message)
                        else:
                            name, value = message
                            answer['value'] = apply_assistant_setting(config, name, value,
                                home.getProperty('VoiceAssistant.CodexLoggedIn') == 'true')
                    except ValueError as error:
                        answer['error'] = str(error)
                    finally:
                        event.set()
                    continue
                if not embedded:
                    progress.close()
                try:
                    answer['value'] = xbmcgui.Dialog().yesno(title, message)
                finally:
                    event.set()
                if not embedded:
                    progress = RecordingProgress(str(root))
                progress.create('语音助手 · ' + agent_name, text[-160:])
                progress.set_recording(False)
            if question_flow:
                question_flow.tick()
            if poll_input and not finishing:
                target = question_flow.token if question_flow else ''
                supplement = poll_input(drain_activity)
                if monitor.abortRequested() or progress.iscanceled():
                    stop.set()
                    break
                if supplement:
                    try:
                        if question_flow and target:
                            question_flow.answer(supplement, target)
                            continue
                        if isinstance(supplement, dict):
                            continue  # A late click on an expired question is never a new command.
                        if speech: speech.restart()
                        steering.submit(supplement)
                    except ValueError as error:
                        report(str(error))
                    else:
                        if on_message:
                            on_message('user', supplement.strip())
                        report('正在发送补充要求…')
            if round_ready.is_set():
                followup = steering.followup()
                if followup is not None:
                    previous = parse(shared['outcome']['reply'], shared['tools'])
                    if on_message:
                        on_message('assistant', previous['message'])
                    report('上一轮已结束，继续处理补充要求。')
                finishing = followup is None
                shared['next_text'] = followup
                round_ready.clear()
                next_ready.set()
            home.setProperty('VoiceAssistant.State', 'thinking')
            progress.update(0, ('请选择选项或用语音、文字回答' if question_flow and question_flow.token else shared['message']) + ('\n返回取消' if embedded else '\n' + text[-120:] + '\n返回取消'))
            monitor.waitForAbort(.05)
        worker.join()
        drain_activity()
        if cancelled() or shared.get('cancelled'):
            if speech: speech.stop()
            if not monitor.abortRequested() and getattr(progress, 'task_stopped', lambda: False)():
                return {'message': '任务已停止。已完成的操作不会自动撤销，可以继续输入新要求。',
                        'interaction': 'continue', 'choices': []}
            return None
        if shared.get('error'):
            raise RuntimeError(shared['error'])
        outcome, tools = shared['outcome'], shared['tools']
        scheduled = tools.commit_deferred(monitor.abortRequested)
        presentation = parse(outcome['reply'], tools)
        if getattr(tools, 'ui_action', None):
            presentation['ui_action'] = tools.ui_action
        if close_for_playback(before_playback, playback_state(), tools):
            presentation['interaction'] = 'close'
        home.setProperty('VoiceAssistant.AgentReply', presentation['message'])
        write_json(data_path(profile, 'last_agent.json'), {'state': 'done', 'version': VERSION,
            'permissions': values['permission_level'], 'approval_strategy': values['approval_strategy'],
            'elapsed_seconds': round(time.monotonic() - began, 3), 'tools': outcome['tools'],
            'reply': presentation['message'], 'maintenance': scheduled,
            'agent_backend': outcome.get('agent_backend', values.get('agent_backend', 'codex')),
            'model_invocations': outcome.get('model_invocations'), 'matching': outcome.get('matching'),
            'playback_timing': playback_timing})
        return presentation
    finally:
        stop.set()
        worker.join()
        if question_flow:
            question_flow.clear()
        progress.close()
