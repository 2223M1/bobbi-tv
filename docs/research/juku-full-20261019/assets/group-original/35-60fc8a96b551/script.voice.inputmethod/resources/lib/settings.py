"""One validated settings contract shared by the settings window and runtime."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    default: object
    label: str
    section: str
    options: tuple = ()
    minimum: int = 0
    maximum: int = 0
    # Optional show-if rule for the web page, e.g. 'voice_input=usb' or
    # 'recognition_engine!=doubao'. Kodi's settings window uses <visible>
    # in settings.xml instead; this only drives the LAN configuration page.
    visible: str = ''


FIELDS = {
    'voice_input': Field('usb', '音频输入设备', 'input',
        (('ur02', 'Ugoos 遥控（UR01 / UR02）'), ('nanosic', '腾讯极光遥控'),
         ('cmcc', '移动高清遥控'), ('r22', '华为 R22 遥控（按住说话）'),
         ('b25', 'Homatics 遥控（B21 / B25）'), ('usb', 'USB 麦克风 / 2.4G 遥控'))),
    'alsa_device': Field('', 'ALSA 录音设备（留空自动）', 'input', visible='voice_input=usb'),
    'max_seconds': Field(30, '单次最长录音（秒）', 'input', minimum=3, maximum=30),
    'start_timeout': Field(6, '等待开始说话（秒）', 'input', minimum=2, maximum=15),
    'silence_ms': Field(1000, '说话后静音结束（毫秒）', 'input', minimum=500, maximum=3000),
    'ur02_threshold': Field(1000, 'Ugoos 语音音量门槛', 'input', minimum=30, maximum=3000,
        visible='voice_input=ur02'),
    'threshold': Field(200, '语音音量门槛', 'input', minimum=30, maximum=3000,
        visible='voice_input!=ur02'),
    'recognition_engine': Field('ncnn', '语音转文字', 'asr',
        (('ncnn', 'sherpa-ncnn 流式识别（本地离线）'), ('doubao', '豆包流式语音识别（联网）'))),
    'ncnn_model_quality': Field('balanced', '本地识别模型', 'asr',
        (('balanced', '均衡（中文/英文）'), ('fast', '快速（中文，占用更低）')),
        visible='recognition_engine=ncnn'),
    'ncnn_model_path': Field('', '自定义模型目录（留空用内置）', 'asr',
        visible='recognition_engine=ncnn'),
    'ncnn_decoding_method': Field('modified_beam_search', '本地识别搜索方式', 'asr',
        (('modified_beam_search', '多候选（更准）'), ('greedy_search', '快速')),
        visible='recognition_engine=ncnn'),
    'doubao_key_file': Field('', '豆包语音 apikey 文件', 'asr',
        visible='recognition_engine=doubao'),
    'doubao_resource_id': Field('volc.seedasr.sauc.duration', '豆包语音模型类型', 'asr',
        (('volc.seedasr.sauc.duration', '模型 2.0 · 时长'),
         ('volc.seedasr.sauc.concurrent', '模型 2.0 · 并发')),
        visible='recognition_engine=doubao'),
    'doubao_timeout': Field(20, '豆包请求超时（秒）', 'asr', minimum=5, maximum=60,
        visible='recognition_engine=doubao'),
    'submit_mode': Field('open', '识别出文字后', 'output',
        (('open', '写入输入框，等你按确定'), ('submit', '写入并立即提交'))),
    'no_input_action': Field('notify', '没有输入框时', 'output',
        (('notify', '弹窗显示识别结果'), ('ignore', '什么都不做'),
         ('juku', '发送给巨库语音接口'))),
}


def validate(name, value):
    if name not in FIELDS:
        raise ValueError('未知设置。')
    field = FIELDS[name]
    if type(field.default) is int:
        if isinstance(value, bool):
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
        value = value.strip()
        if field.options and value not in dict(field.options):
            raise ValueError(field.label + '选项无效。')
    return value


class Settings:
    def __init__(self, addon):
        self.addon = addon

    def values(self):
        result = {}
        for name, field in FIELDS.items():
            raw = self.addon.getSetting(name)
            try:
                result[name] = validate(name, raw if raw != '' else field.default)
            except ValueError:
                result[name] = field.default
        return result

    def validate_changes(self, changes):
        """Validate a partial update from the configuration page."""
        if not isinstance(changes, dict):
            raise ValueError('设置必须是对象。')
        return {name: validate(name, value) for name, value in changes.items()}

    def apply(self, changes):
        validated = self.validate_changes(changes)
        for name, value in validated.items():
            self.addon.setSetting(name, str(value))
        # Kodi silently drops writes while its own settings window is open, so
        # read back rather than reporting a save that did not happen.
        if any(self.addon.getSetting(name) != str(value) for name, value in validated.items()):
            raise ValueError('请先关闭 Kodi 插件设置窗口，再保存网页设置。')
        return self.values()


def web_schema():
    """Describe every field for the LAN configuration page."""
    return {name: {'default': field.default, 'label': field.label, 'section': field.section,
                   'options': [list(option) for option in field.options],
                   'minimum': field.minimum, 'maximum': field.maximum,
                   'visible': field.visible} for name, field in FIELDS.items()}
