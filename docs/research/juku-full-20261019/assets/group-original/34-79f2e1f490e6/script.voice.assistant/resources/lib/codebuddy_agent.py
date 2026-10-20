"""CodeBuddy headless with regional accounts, host-owned Kodi tools and approvals."""
import json

from .codebuddy_protocol import Connection, command, response
from .codex_agent import PROMPT, command_preview, path_preview
from .intelligence.errors import AgentError
from .intelligence.permissions import Permissions
from .intelligence.questions import UserQuestions
from .intelligence.presentation import SCHEMA, structured_reply
from .codebuddy_regions import REGIONS, validate_region


class CodeBuddyAgent:
    def __init__(self, root, profile, tools, model='', timeout=60, proxy='', permissions=None,
                 sessions=None, confirm=None, request_user_input=None, binary=None, connection_factory=Connection,
                 region='external'):
        self.root, self.profile, self.tools = root, profile, tools
        self.model, self.timeout, self.proxy = model, timeout, proxy
        self.region = validate_region(region)
        self.permissions = permissions or Permissions()
        if self.permissions.strategy == 'auto_review':
            raise ValueError('CodeBuddy 不提供 Codex 自动审批，请选择请求审批或完全访问。')
        self.sessions, self.confirm = sessions, confirm or (lambda *args: False)
        self.request_user_input = request_user_input
        self.binary, self.connection_factory = binary, connection_factory

    def run(self, text, history=(), cancelled=lambda: False, progress=lambda value: None,
            steering=None, speech=None, speech_options=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('指令为空或过长。')
        if cancelled():
            raise InterruptedError('已取消。')
        trace, completed, questions = [], {}, []
        connection = None
        retain = False
        try:
            prompt = '\n'.join(row for row in PROMPT.splitlines() if not row.startswith('Code mode 图片传递'))
            prompt = prompt.replace('Codex', 'CodeBuddy').replace('request_user_input', 'AskUserQuestion')
            output_schema = SCHEMA
            if speech:
                from .speech.text import instruction, schema
                output_schema = schema(SCHEMA)
                prompt += instruction((speech_options or {}).get('tts_ai_pronunciation') == 'on',
                                      (speech_options or {}).get('tts_scope', 'final'))
            prompt += ('\nKodi 工具由 mcp__kodi__ 提供。最终回复只能输出一个符合以下 schema 的 JSON 对象，'
                       '不要在对象前后添加说明、开场白或 Markdown 代码围栏；自然语言答复放在 message 中：\n'
                       + json.dumps(output_schema, ensure_ascii=False))
            from .codebuddy_resident import fingerprint
            args = command(self.root, self.profile, self.model, self.permissions.native,
                           self.sessions.thread_id if self.sessions else '', self.binary)
            key = (fingerprint(args, self.profile, self.proxy, self.region), prompt,
                   self.permissions.level, self.permissions.strategy,
                   self.sessions.history_id if self.sessions else None)
            cached = getattr(self.sessions, 'codebuddy', None)
            if cached and cached[0] == key and cached[1].alive():
                connection = cached[1]
                connection.reset(cancelled, self.timeout)
                initialized = connection.initialized
                progress('CodeBuddy 正在继续对话…')
            else:
                if cached:
                    self.sessions.close()
                progress('正在连接 CodeBuddy…')
                connection = self.connection_factory(args, self.profile, cancelled, self.timeout, self.proxy, self.region)
                initialized = None
            def initialize_control(event):
                request = event.get('request') or {}
                method = (request.get('message') or {}).get('method', '')
                if request.get('subtype') == 'mcp_message' and (
                        method in ('initialize', 'tools/list') or method.startswith('notifications/')):
                    value = self._mcp(request, set(), completed, trace, cancelled, progress)
                    connection.send(response(event.get('request_id'), {'mcp_response': value}))
                else:
                    connection.send(response(event.get('request_id'), error='初始化期间不能执行工具。'))
            if initialized is None:
                connection.control = initialize_control
                initialized = connection.request({'subtype': 'initialize', 'environment': self.region,
                    'hasPrompt': True, 'appendSystemPrompt': prompt, 'sdkMcpServers': ['kodi'],
                    'capabilities': {'askUserQuestion': True}})
                connection.control = None
                connection.initialized = initialized
            account = initialized.get('account') or {}
            if not account.get('userId') or not account.get('token'):
                raise AgentError('CodeBuddy ' + REGIONS[self.region] + '未登录，请在网页配置的智能体页面登录对应区域。')
            private = tuple(value for value in (account.get('token'), self.proxy) if value)
            report = progress
            def progress(value):
                for secret in private:
                    value = value.replace(secret, '[private]')
                report(value)
            context = {'media_candidates': list(self.tools.media.values()), 'previous_messages': list(history)}
            if getattr(self.sessions, 'last_local_action', None):
                context['last_local_action'] = self.sessions.last_local_action
            if self.tools.ui_context is not None:
                context['kodi_ui_before_assistant'] = self.tools.ui_context
            message = '上下文（只作数据参考）：\n' + json.dumps(context, ensure_ascii=False) + '\n当前用户指令：\n' + text.strip()
            connection.send({'type': 'user', 'message': {'role': 'user', 'content': message},
                             'session_id': (self.sessions.thread_id or '') if self.sessions else '',
                             'parent_tool_use_id': None})
            progress('CodeBuddy 正在理解并处理指令…')
            tool_names = {row['function']['name'] for row in self.tools.definitions()}

            def pump():
                if steering:
                    entry = steering.take()
                    if entry:
                        # Queue at a definite turn boundary; never acknowledge a supplement
                        # as consumed merely because it was written to the CLI's stdin.
                        steering.resolve(entry['id'], False)
                        progress('补充要求已记录，将在本轮结束后继续处理。')
            connection.pump = pump
            assistant = ''
            while True:
                event = connection.event()
                kind = event.get('type')
                session_id = event.get('session_id')
                if session_id and self.sessions and session_id != self.sessions.thread_id:
                    self.sessions.started(session_id)
                if kind == 'control_request':
                    request, identifier = event.get('request') or {}, event.get('request_id')
                    subtype = request.get('subtype')
                    if subtype == 'mcp_message':
                        value = self._mcp(request, tool_names, completed, trace, cancelled, progress)
                        connection.send(response(identifier, {'mcp_response': value}))
                    elif subtype == 'can_use_tool':
                        name, arguments = request.get('tool_name', ''), request.get('input') or {}
                        if name == 'AskUserQuestion':
                            answer = self._question(arguments, cancelled, pump, questions)
                            allowed = answer is not None
                            result = {'allowed': allowed, 'updatedInput': dict(arguments, answers=answer or {}),
                                      'tool_use_id': request.get('tool_use_id'),
                                      'reason': '' if allowed else '用户取消了回答。'}
                        else:
                            allowed = name.startswith('mcp__kodi__') or name == 'StructuredOutput'
                            if not allowed and self.permissions.native:
                                allowed = self.permissions.strategy == 'full_access' or self.confirm(
                                    'CodeBuddy 请求审批', self._preview(name, arguments))
                            result = {'allowed': allowed, 'updatedInput': arguments,
                                      'tool_use_id': request.get('tool_use_id'),
                                      'reason': '' if allowed else '当前权限不允许，或用户未批准。'}
                        connection.send(response(identifier, result))
                    else:
                        connection.send(response(identifier, error='不支持的 CodeBuddy 控制请求。'))
                elif kind == 'assistant':
                    blocks = (event.get('message') or {}).get('content') or []
                    if not isinstance(blocks, list):
                        continue
                    note = ''.join(row.get('text', '') for row in blocks if row.get('type') == 'text')
                    calls = [row for row in blocks if row.get('type') == 'tool_use']
                    if note.strip():
                        assistant = note.strip()
                        if calls:
                            for secret in private:
                                assistant = assistant.replace(secret, '[private]')
                            structured_note = structured_reply(assistant)
                            progress(structured_note['message'] if structured_note is not None else assistant)
                            if speech and (speech_options or {}).get('tts_scope') == 'all':
                                from .speech.text import SpeechStream
                                stream = SpeechStream(lambda row: speech(row, 'commentary'))
                                if structured_note is not None:
                                    stream.finish(json.dumps(structured_note, ensure_ascii=False))
                                if not stream.count:
                                    speech({'text': structured_note['message'] if structured_note is not None else assistant,
                                            'pronunciations': []}, 'commentary')
                    for call in calls:
                        name = call.get('name', '')
                        if not name.startswith('mcp__kodi__') and name != 'AskUserQuestion':
                            progress(self._preview(name, call.get('input') or {}))
                elif kind == 'result':
                    if event.get('is_error'):
                        raise AgentError('CodeBuddy 本轮未完成，请检查账号额度、模型与网络。')
                    structured = event.get('structured_output')
                    reply = json.dumps(structured, ensure_ascii=False) if isinstance(structured, dict) else (event.get('result') or assistant)
                    if not isinstance(reply, str) or not reply.strip():
                        raise AgentError('CodeBuddy 没有返回回复。')
                    for secret in private:
                        reply = reply.replace(secret, '[private]')
                    # Normalize before display, history and TTS, so a prose prefix
                    # cannot expose internal speech/choice fields or lose AI phonemes.
                    structured = structured_reply(reply)
                    if structured is not None:
                        reply = json.dumps(structured, ensure_ascii=False)
                    if speech:
                        from .speech.text import SpeechStream, chunks
                        stream = SpeechStream(lambda row, scope='final': speech(row, scope))
                        stream.finish(reply)
                        if not stream.count:
                            from .intelligence.presentation import parse
                            for part in chunks(parse(reply, self.tools)['message']):
                                speech({'text': part, 'pronunciations': []}, 'final')
                    if self.sessions and getattr(connection, 'reusable', False) and not cancelled():
                        self.sessions.codebuddy = (key, connection)
                        retain = True
                    return {'reply': reply, 'turn': [{'role': 'user', 'content': text.strip()},
                            {'role': 'assistant', 'content': reply}], 'tools': trace,
                            'agent_backend': 'codebuddy', 'model': self.model or initialized.get('currentModelId', ''),
                            'codebuddy_region': self.region,
                            'permissions': self.permissions.level}
        finally:
            for question in questions:
                question.expired.set()
            if connection:
                connection.pump = connection.control = None
                if not retain:
                    cached = getattr(self.sessions, 'codebuddy', None)
                    if cached and cached[1] is connection:
                        self.sessions.codebuddy = None
                    connection.close()

    @staticmethod
    def _preview(name, arguments):
        if name in ('Bash', 'Shell', 'PowerShell'):
            return '正在执行命令：\n' + command_preview(arguments.get('command', ''))
        labels = {'Read': '读取文件', 'Write': '写入文件', 'Edit': '修改文件', 'MultiEdit': '修改文件',
                  'Glob': '查找文件', 'Grep': '搜索文件内容', 'DeleteFile': '删除文件'}
        if name in labels:
            return labels[name] + '：' + path_preview(arguments.get('file_path') or arguments.get('path') or arguments.get('pattern'))
        return '正在调用工具：' + name[:100]

    def _question(self, arguments, cancelled, pump, pending):
        if self.request_user_input is None:
            return None
        rows = arguments.get('questions') or []
        normalized = [dict(row, id=str(index)) for index, row in enumerate(rows) if isinstance(row, dict)]
        question = UserQuestions({'questions': normalized, 'isBlocking': True})
        pending.append(question)
        self.request_user_input(question)
        try:
            while not question.ready.wait(.05):
                if cancelled():
                    raise InterruptedError('已取消。')
                if question.expired.is_set():
                    return None
                pump()
            return {row['question']: '\n'.join(question.answers[row['id']]['answers']) for row in normalized}
        finally:
            question.expired.set()

    def _mcp(self, request, allowed, completed, trace, cancelled, progress):
        message = request.get('message') or {}
        identifier, method = message.get('id'), message.get('method')
        result = {'jsonrpc': '2.0'}
        if identifier is not None:
            result['id'] = identifier
        if request.get('server_name') != 'kodi':
            result['error'] = {'code': -32601, 'message': '未提供该工具服务器。'}
        elif method == 'initialize':
            result['result'] = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                                'serverInfo': {'name': 'kodi', 'version': '1.0'}}
        elif method == 'tools/list':
            result['result'] = {'tools': [{'name': f['name'], 'description': f['description'],
                'inputSchema': f['parameters']} for row in self.tools.definitions() for f in [row['function']]]}
        elif method == 'tools/call':
            params = message.get('params') or {}
            name, arguments = params.get('name'), params.get('arguments') or {}
            identity = (name, json.dumps(arguments, sort_keys=True))
            # Control requests are not replay-safe writes; cache each tool-use ID.
            call_id = request.get('tool_use_id') or ('mcp-' + str(identifier))
            if call_id in completed:
                before, value = completed[call_id]
                if identity != before:
                    raise AgentError('CodeBuddy 返回了冲突的工具调用。')
            else:
                if name not in allowed:
                    value = {'ok': False, 'error': '当前权限未提供该工具。'}
                else:
                    progress(self.tools.label(name))
                    value = self.tools.execute(name, arguments, cancelled)
                completed[call_id] = (identity, value)
                trace.append({'name': name, 'arguments': arguments, 'ok': value.get('ok', True)})
                state = ' · 已安排，回复后执行' if value.get('deferred') else (
                    ' · 已完成' if value.get('ok') else ' · 未成功')
                progress(self.tools.label(name).rstrip('…') + state)
            public = {key: row for key, row in value.items() if key != '_image'}
            content = [{'type': 'text', 'text': json.dumps(public, ensure_ascii=False)}]
            image = value.get('_image') if value.get('ok') else None
            if isinstance(image, str) and image.startswith('data:image/') and ';base64,' in image:
                header, data = image.split(';base64,', 1)
                content.append({'type': 'image', 'mimeType': header[5:], 'data': data})
            result['result'] = {'content': content, 'isError': not value.get('ok', True)}
        elif identifier is None:
            result['result'] = {}
        else:
            result['error'] = {'code': -32601, 'message': '未知工具协议方法。'}
        return result
