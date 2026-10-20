"""Optional local ONNX and cloud recognition, independent of the agent."""
from ..audio import SpeechGate


def default_recognizer(root, model_path=''):
    raise ValueError('请先选择语音识别引擎。')


def gate(values, source):
    return SpeechGate(threshold=values['ur02_threshold'] if source == 'ur02' else values['threshold'],
        silence_seconds=values['silence_ms'] / 1000,
        start_timeout=values['start_timeout'], max_seconds=values['max_seconds'],
        startup_seconds=.3 if source in ('nanosic', 'ur02', 'b25') else 0,
        adaptive_noise=source == 'ur02')


def recognizer(root, profile, values, speech_gate, cancelled, rpc=None):
    engine = values['recognition_engine']
    if engine == 'onnx':
        from .recognizer import Recognizer
        return Recognizer(profile, values['onnx_model'], cancelled)
    if engine == 'doubao':
        from ..doubao_recognizer import DoubaoRecognizer
        return DoubaoRecognizer(root, profile, values['doubao_resource_id'], values['doubao_timeout'],
                                cancelled, key_file=values['doubao_key_file'])
    if engine == 'codex':
        from ..codex_dictation_recognizer import CodexDictationRecognizer
        from ..proxy import configured_proxy
        return CodexDictationRecognizer(root, profile, values['codex_dictation_timeout'], cancelled, configured_proxy(values))
    raise ValueError('语音转文字已关闭，请先在设置中启用。')
