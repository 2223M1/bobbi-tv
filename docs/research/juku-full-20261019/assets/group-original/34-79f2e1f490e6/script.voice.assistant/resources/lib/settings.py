"""One validated settings contract for Kodi, the web page and runtime."""
from collections import namedtuple
from pathlib import Path
from .dependencies.catalog import catalog

PREFIX = 'v2_'
_ASR_CATALOG = catalog(str(Path(__file__).resolve().parents[2]))['asr_models']
ASR_MODELS = tuple((name, model['label']) for name, model in _ASR_CATALOG.items())
ZIPFORMER_MODELS = tuple(name for name, model in _ASR_CATALOG.items() if model['family'] == 'zipformer')
ZIPFORMER_VISIBLE = 'recognition_engine=onnx&onnx_model=' + ','.join(ZIPFORMER_MODELS)


Field = namedtuple('Field', 'default label section options minimum maximum visible secret',
                  defaults=((), 0, 0, '', False))


FIELDS = {
    'voice_input': Field('usb', '音频输入设备', 'input',
        (('ur02', 'Ugoos 遥控（UR01 / UR02）'), ('nanosic', '腾讯极光遥控'),
         ('cmcc', '移动高清遥控'), ('usb', 'USB 麦克风 / 2.4G 遥控'),
         ('r22', '华为 R22 遥控（按住说话）'), ('b25', 'Homatics 遥控（B21 / B25）'))),
    'alsa_device': Field('', 'ALSA 录音设备（留空自动）', 'input', visible='voice_input=usb'),
    'max_seconds': Field(30, '单次最长录音（秒）', 'input', minimum=3, maximum=30),
    'start_timeout': Field(6, '等待开始说话（秒）', 'input', minimum=2, maximum=15),
    'silence_ms': Field(1000, '说话后静音结束（毫秒）', 'input', minimum=500, maximum=3000),
    'ur02_threshold': Field(1000, 'Ugoos 语音音量门槛', 'input', minimum=30, maximum=3000, visible='voice_input=ur02'),
    'threshold': Field(200, '语音音量门槛', 'input', minimum=30, maximum=3000, visible='voice_input!=ur02'),
    'recognition_engine': Field('off', '语音转文字', 'asr',
        (('off', '关闭'), ('onnx', 'sherpa-onnx（本地）'), ('doubao', '豆包流式语音识别（联网）'), ('codex', 'Codex 订阅听写（联网）'))),
    'onnx_model': Field('zipformer-2025', '本地识别模型', 'asr', ASR_MODELS, visible='recognition_engine=onnx'),
    'zipformer_max_active_paths': Field(4, '解码候选数', 'asr', minimum=1, maximum=16,
        visible=ZIPFORMER_VISIBLE),
    'zipformer_hotwords_score': Field('2', '热词权重', 'asr',
        tuple((format(i / 2, 'g'), format(i / 2, 'g')) for i in range(21)),
        visible=ZIPFORMER_VISIBLE),
    'doubao_key_file': Field('', '豆包语音apikey文件', 'asr', visible='recognition_engine=doubao'),
    'doubao_resource_id': Field('volc.seedasr.sauc.duration', '豆包语音模型类型', 'asr',
        (('volc.seedasr.sauc.duration', '模型 2.0 · 时长'), ('volc.seedasr.sauc.concurrent', '模型 2.0 · 并发')),
        visible='recognition_engine=doubao'),
    'doubao_timeout': Field(20, '豆包请求超时（秒）', 'asr', minimum=5, maximum=60, visible='recognition_engine=doubao'),
    'codex_dictation_timeout': Field(30, '订阅听写超时（秒）', 'asr', minimum=5, maximum=60, visible='recognition_engine=codex'),
    'agent_backend': Field('off', '智能体', 'agent', (('off', '关闭'), ('codex', 'Codex'), ('codebuddy', 'CodeBuddy'))),
    'codex_provider': Field('chatgpt', 'Codex 登录方式', 'agent', (('chatgpt', 'Codex 订阅'), ('api', '兼容 API')), visible='agent_backend=codex'),
    'codebuddy_region': Field('external', 'CodeBuddy 区域', 'agent',
        (('external', '国际版'), ('internal', '国内版')), visible='agent_backend=codebuddy'),
    'codebuddy_model': Field('', 'CodeBuddy 模型（留空自动）', 'agent', visible='agent_backend=codebuddy&codebuddy_region=external'),
    'codebuddy_internal_model': Field('', 'CodeBuddy 模型（留空自动）', 'agent', visible='agent_backend=codebuddy&codebuddy_region=internal'),
    'codebuddy_approval_strategy': Field('request', 'CodeBuddy 审批策略', 'agent',
        (('request', '请求审批'), ('full_access', '完全访问控制')), visible='agent_backend=codebuddy'),
    'codebuddy_proxy': Field('', 'CodeBuddy HTTP 代理（可选）', 'agent', visible='agent_backend=codebuddy'),
    'codebuddy_proxy_username': Field('', 'CodeBuddy 代理用户名', 'agent', visible='agent_backend=codebuddy'),
    'codebuddy_proxy_password': Field('', 'CodeBuddy 代理密码', 'agent', visible='agent_backend=codebuddy', secret=True),
    'codex_chatgpt_model': Field('', '订阅模型（留空自动）', 'agent', visible='agent_backend=codex&codex_provider=chatgpt'),
    'codex_chatgpt_effort': Field('', '订阅思考强度（留空自动）', 'agent', visible='agent_backend=codex&codex_provider=chatgpt'),
    'agent_base_url': Field('https://api.deepseek.com', '兼容 Responses API 地址', 'agent', visible='agent_backend=codex&codex_provider=api'),
    'agent_key_file': Field('', 'apikey文件', 'agent', visible='agent_backend=codex&codex_provider=api'),
    'agent_model': Field('deepseek-flash', '兼容 API 模型', 'agent', visible='agent_backend=codex&codex_provider=api'),
    'agent_effort': Field('none', '兼容 API 思考强度', 'agent', visible='agent_backend=codex&codex_provider=api'),
    'agent_code_mode': Field('off', '启用 Code Mode', 'agent',
        (('off', '关'), ('on', '开（接口需支持 exec 自定义工具）')), visible='agent_backend=codex&codex_provider=api'),
    'permission_level': Field('settings', 'AI 权限档位', 'agent',
        (('media', '一档：查询与播放控制'), ('settings', '二档：额外修改设置'), ('full', '三档：不设限'))),
    'approval_strategy': Field('request', '审批策略', 'agent',
        (('request', '请求审批'), ('auto_review', '帮我审批（Codex 自动审批）'), ('full_access', '完全访问控制')), visible='agent_backend=codex'),
    'session_policy': Field('conversation', '对话 session 有效期', 'agent',
        (('conversation', '每次完整对话'), ('daily', '每天'), ('forever', '永久共用并自动压缩'))),
    'agent_timeout': Field(60, '智能体请求超时（秒）', 'agent', minimum=5, maximum=180),
    'codex_proxy': Field('', 'Codex HTTP 代理（可选）', 'agent', visible='agent_backend=codex'),
    'codex_proxy_username': Field('', 'Codex 代理用户名', 'agent', visible='agent_backend=codex'),
    'codex_proxy_password': Field('', 'Codex 代理密码', 'agent', visible='agent_backend=codex', secret=True),
    'tts_enabled': Field('off', '语音合成（Matcha）', 'speech', (('off', '关'), ('on', '开'))),
    'tts_scope': Field('final', '朗读范围', 'speech', (('final', '仅最终回复'), ('all', '工作说明和最终回复')), visible='tts_enabled=on'),
    'tts_volume': Field(50, '播报相对音量（%）', 'speech', minimum=0, maximum=100, visible='tts_enabled=on'),
    'tts_pause': Field('1.0', '停顿系数', 'speech', tuple((x, x) for x in ('0.2', '0.5', '0.75', '1.0', '1.25', '1.5', '2.0')), visible='tts_enabled=on'),
    'tts_lead_in': Field('1.0', '音频唤醒时长（秒）', 'speech', tuple((x, x) for x in ('0', '0.5', '1.0', '1.5', '2.0', '3.0', '5.0')), visible='tts_enabled=on'),
    'tts_ai_pronunciation': Field('off', 'AI 修正多音字', 'speech', (('off', '关'), ('on', '开')), visible='tts_enabled=on'),
}


# A tool cannot raise its own privilege level or redirect authenticated requests.
ASSISTANT_FIELDS = {name for name, field in FIELDS.items() if field.section in ('input', 'asr', 'speech')
                    and name != 'doubao_key_file'} | {'session_policy', 'agent_timeout'}


def validate(name, value):
    if name not in FIELDS:
        raise ValueError('未知设置。')
    field = FIELDS[name]
    if type(field.default) is int:
        if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
            raise ValueError(field.label + '必须是整数。')
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValueError(field.label + '必须是整数。') from None
        if not field.minimum <= value <= field.maximum:
            raise ValueError(field.label + '超出范围。')
    else:
        if not isinstance(value, str) or len(value) > 512 or any(ord(c) < 32 for c in value):
            raise ValueError(field.label + '格式无效。')
        if name not in ('codex_proxy_username', 'codex_proxy_password', 'codebuddy_proxy_username', 'codebuddy_proxy_password'):
            value = value.strip()
        if name in ('codex_proxy_username', 'codebuddy_proxy_username') and ':' in value:
            raise ValueError(field.label + '不能包含冒号。')
        if name in ('codex_proxy_username', 'codex_proxy_password', 'codebuddy_proxy_username', 'codebuddy_proxy_password') and '\x7f' in value:
            raise ValueError(field.label + '格式无效。')
        if field.options and value not in dict(field.options):
            raise ValueError(field.label + '选项无效。')
        if name in ('agent_effort', 'codex_chatgpt_effort') and value not in ('', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
            raise ValueError('思考强度无效。')
        if name == 'agent_base_url':
            from .configuration.credentials import validate_url
            value = validate_url(value)
        if name in ('codex_proxy', 'codebuddy_proxy'):
            from .proxy import validate_proxy
            value = validate_proxy(value, allow_credentials=False)
    return value


class Settings:
    def __init__(self, addon):
        self.addon = addon

    def get(self, name):
        field = FIELDS[name]
        raw = self.addon.getSetting(PREFIX + name)
        try:
            return validate(name, raw if raw != '' else field.default)
        except ValueError:
            return field.default

    def values(self):
        return {name: self.get(name) for name in FIELDS}

    def capture_values(self):
        """Validate only recording/ASR settings before the first transcription."""
        result = {name: self.get(name) for name, field in FIELDS.items()
                  if field.section in ('input', 'asr')}
        if result['recognition_engine'] == 'codex':
            result.update({name: self.get(name) for name in
                           ('codex_proxy', 'codex_proxy_username', 'codex_proxy_password')})
        return result

    def validate_changes(self, changes, logged_in=False, models=()):
        values = self.values()
        if not isinstance(changes, dict):
            raise ValueError('设置必须是对象。')
        validated = {name: validate(name, value) for name, value in changes.items()}
        values.update(validated)
        from .proxy import configured_proxy
        configured_proxy(values)
        from .codebuddy_protocol import configured_proxy as buddy_proxy
        buddy_proxy(values)
        # Choosing subscription dictation must work before Codex is downloaded
        # and logged in; otherwise first-run configuration has a circular gate.
        model = next((m for m in models if m.get('model') == values['codex_chatgpt_model']), None)
        if models and values['codex_provider'] == 'chatgpt' and values['codex_chatgpt_model'] and model is None:
            raise ValueError('请选择当前目录中的订阅模型。')
        if model and values['codex_chatgpt_effort'] and values['codex_chatgpt_effort'] not in [e['reasoningEffort'] for e in model.get('supportedReasoningEfforts', [])]:
            raise ValueError('此模型不支持选择的思考强度。')
        return validated

    def apply(self, changes, logged_in=False, models=()):
        validated = self.validate_changes(changes, logged_in, models)
        for name, value in validated.items():
            self.addon.setSetting(PREFIX + name, str(value))
        if any(self.addon.getSetting(PREFIX + name) != str(value) for name, value in validated.items()):
            raise ValueError('请先关闭 Kodi 插件设置窗口，再保存网页设置。')
        return self.values()


def get_setting(addon, name):
    return Settings(addon).get(name)


def get_proxy(addon):
    from .proxy import configured_proxy
    config = Settings(addon)
    return configured_proxy({name: config.get(name) for name in
                             ('codex_proxy', 'codex_proxy_username', 'codex_proxy_password')})


def set_setting(addon, name, value):
    # Internal UI actions already perform their own login/model validation.
    addon.setSetting(PREFIX + name, str(validate(name, value)))


def web_schema():
    return {name: {'default': field.default, 'label': field.label, 'section': field.section,
                  'options': list(field.options), 'minimum': field.minimum, 'maximum': field.maximum,
                  'visible': field.visible, 'secret': field.secret} for name, field in FIELDS.items()}


def assistant_settings(config, query=''):
    current = config.values()
    return {'settings': [{'id': name, 'label': FIELDS[name].label, 'value': current[name]}
        for name in sorted(ASSISTANT_FIELDS) if query.lower() in (name + FIELDS[name].label).lower()]}


def apply_assistant_setting(config, name, value, logged_in=False):
    if name not in ASSISTANT_FIELDS:
        raise ValueError('凭据、权限及服务登录方式请使用配置网页。')
    config.apply({name: value}, logged_in)
    return {'setting': name, 'updated': True}
