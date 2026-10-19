"""sherpa-ncnn C API, bundled for both CoreELEC user spaces (armv7 and aarch64).

This module is engine code: it must only ever be imported by the isolated
worker process (ncnn_worker.py) or by a standalone smoke test.  Importing it
inside Kodi is what crashed the media centre; see ncnn_worker.py.
"""
from array import array
import ctypes as C
import math
from pathlib import Path
import sys

from .asr.text import display_text, validate_hotwords, vocabulary
from .native_libs import directory, library, load


MODELS = {
    'fast': 'sherpa-ncnn-streaming-zipformer-zh-14M-2023-02-23',
    'balanced': 'sherpa-ncnn-streaming-zipformer-small-bilingual-zh-en-2023-02-16',
    'accurate': 'sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13',
}


def model_directory(addon_root, model_path='', model_quality='balanced'):
    if model_path:
        return Path(model_path)
    if model_quality not in MODELS:
        raise ValueError('未知语音模型：' + str(model_quality))
    return Path(addon_root) / 'resources/models' / MODELS[model_quality]


class FeatureConfig(C.Structure):
    _fields_ = [('sampling_rate', C.c_float), ('feature_dim', C.c_int32)]


class ModelConfig(C.Structure):
    _fields_ = [(name, C.c_char_p) for name in ('encoder_param', 'encoder_bin',
        'decoder_param', 'decoder_bin', 'joiner_param', 'joiner_bin', 'tokens')] + [
        ('use_vulkan_compute', C.c_int32), ('num_threads', C.c_int32)]


class DecoderConfig(C.Structure):
    _fields_ = [('decoding_method', C.c_char_p), ('num_active_paths', C.c_int32)]


class RecognizerConfig(C.Structure):
    _fields_ = [('feat_config', FeatureConfig), ('model_config', ModelConfig),
        ('decoder_config', DecoderConfig), ('enable_endpoint', C.c_int32),
        ('rule1_min_trailing_silence', C.c_float), ('rule2_min_trailing_silence', C.c_float),
        ('rule3_min_utterance_length', C.c_float), ('hotwords_file', C.c_char_p),
        ('hotwords_score', C.c_float)]


class Result(C.Structure):
    _fields_ = [('text', C.c_char_p), ('tokens', C.c_char_p),
                ('timestamps', C.POINTER(C.c_float)), ('count', C.c_int32)]


# The 32-bit build is a patched sherpa-ncnn that names its C API after the
# hotword feature; the 64-bit build is the stock upstream wheel. Both export
# the same unprefixed entry points and the same RecognizerConfig layout.
C_API = ('libsherpa-ncnn-c-api-hotwords.so', 'libsherpa-ncnn-c-api.so')


class NcnnRecognizer:
    def __init__(self, addon_root, model_path='', decoding_method='modified_beam_search',
                 num_active_paths=4, model_quality='balanced', hotwords_file='',
                 hotwords_score=1.0, format_text=lambda text: text, endpoint_silence=0.0):
        if decoding_method not in ('greedy_search', 'modified_beam_search'):
            raise ValueError('Unsupported ncnn decoding method: ' + decoding_method)
        if not 1 <= num_active_paths <= 16:
            raise ValueError('ncnn candidate count must be between 1 and 16')
        root = Path(addon_root)
        native = directory(root, 'ncnn')
        model = model_directory(root, model_path, model_quality)
        if not math.isfinite(hotwords_score) or not 0 < hotwords_score <= 3:
            raise ValueError('热词优先程度超出支持范围。')
        if hotwords_file:
            if decoding_method != 'modified_beam_search':
                raise ValueError('热词需要均衡的文字候选搜索。')
            validate_hotwords(hotwords_file, vocabulary(model / 'tokens.txt'))
        self.format_text = format_text
        if not math.isfinite(endpoint_silence) or not 0 <= endpoint_silence <= 3:
            raise ValueError('语音结束停顿时限无效。')
        self.endpoint_enabled = endpoint_silence > 0
        if not native.is_dir():
            raise RuntimeError('插件没有内置当前系统的 sherpa-ncnn 运行库：{}（{} 位用户态）。'
                               .format(native, C.sizeof(C.c_void_p) * 8))
        self.references = []
        # Load dependencies in order by absolute path. ctypes.util.find_library
        # is unavailable on CoreELEC and no system library paths are modified.
        # libgomp ships under an auditwheel-mangled name and is a DT_NEEDED of
        # libncnn, so it has to reach the global scope before libncnn loads.
        # load() keeps each object on its own C++ symbols; see native_libs.
        for name in ('libgomp-d22c30c5.so.1.0.0', 'libkaldi-native-fbank-core.so',
                     'libncnn.so', 'libsherpa-ncnn-core.so'):
            path = native / name
            if path.is_file():
                self.references.append(load(path))
        api = library(root, 'ncnn', C_API)
        if not api.is_file():
            raise RuntimeError('插件缺少 sherpa-ncnn 运行库：' + api.name)
        self.lib = load(api, global_=False)
        signatures = {
            'CreateRecognizer': ([C.POINTER(RecognizerConfig)], C.c_void_p),
            'DestroyRecognizer': ([C.c_void_p], None),
            'CreateStream': ([C.c_void_p], C.c_void_p),
            'DestroyStream': ([C.c_void_p], None),
            'AcceptWaveform': ([C.c_void_p, C.c_float, C.POINTER(C.c_float), C.c_int32], None),
            'IsReady': ([C.c_void_p, C.c_void_p], C.c_int32),
            'Decode': ([C.c_void_p, C.c_void_p], None),
            'GetResult': ([C.c_void_p, C.c_void_p], C.POINTER(Result)),
            'DestroyResult': ([C.POINTER(Result)], None),
            'InputFinished': ([C.c_void_p], None),
            'IsEndpoint': ([C.c_void_p, C.c_void_p], C.c_int32),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        config = RecognizerConfig()
        config.feat_config = FeatureConfig(16000.0, 80)
        for network in ('encoder', 'decoder', 'joiner'):
            for kind in ('param', 'bin'):
                path = model / '{}_jit_trace-pnnx.ncnn.{}'.format(network, kind)
                if not path.is_file():
                    raise RuntimeError('中文流式模型缺少文件：' + str(path))
                setattr(config.model_config, network + '_' + kind, str(path).encode())
        tokens = model / 'tokens.txt'
        if not tokens.is_file():
            raise RuntimeError('中文流式模型缺少字典：' + str(tokens))
        config.model_config.tokens = str(tokens).encode()
        config.model_config.num_threads = 1
        config.model_config.use_vulkan_compute = 0
        config.decoder_config = DecoderConfig(decoding_method.encode(), num_active_paths)
        if hotwords_file:
            config.hotwords_file = str(hotwords_file).encode()
            config.hotwords_score = hotwords_score
        # Checking an endpoint does not reset the stream or discard words.
        config.enable_endpoint = int(self.endpoint_enabled)
        if self.endpoint_enabled:
            config.rule1_min_trailing_silence = 6.0
            config.rule2_min_trailing_silence = endpoint_silence
            config.rule3_min_utterance_length = 1000.0
        self.recognizer = self.stream = None
        self.recognizer = self.lib.CreateRecognizer(C.byref(config))
        if not self.recognizer:
            raise RuntimeError('无法创建 sherpa-ncnn 中文识别器。')
        self.stream = self.lib.CreateStream(self.recognizer)
        if not self.stream:
            self.close()
            raise RuntimeError('无法创建 sherpa-ncnn 音频流。')

    def _text(self):
        result = self.lib.GetResult(self.recognizer, self.stream)
        if not result:
            raise RuntimeError('sherpa-ncnn 没有返回识别结果。')
        try:
            return self.format_text(display_text((result.contents.text or b'').decode('utf-8')))
        finally:
            self.lib.DestroyResult(result)

    def accept(self, pcm):
        if len(pcm) % 2:
            raise ValueError('PCM must contain complete S16_LE samples')
        samples = array('h')
        samples.frombytes(pcm)
        if sys.byteorder != 'little':
            samples.byteswap()
        normalized = array('f', (sample / 32768.0 for sample in samples))
        floats = (C.c_float * len(normalized)).from_buffer(normalized)
        self.lib.AcceptWaveform(self.stream, 16000.0, floats, len(normalized))
        while self.lib.IsReady(self.recognizer, self.stream):
            self.lib.Decode(self.recognizer, self.stream)
        return self._text()

    def finish(self):
        # Flush right-context frames as in upstream decode-file-c-api.c.
        self.accept(bytes(16000))  # 0.5 seconds of mono S16_LE silence
        self.lib.InputFinished(self.stream)
        while self.lib.IsReady(self.recognizer, self.stream):
            self.lib.Decode(self.recognizer, self.stream)
        return self._text()

    @property
    def is_endpoint(self):
        return self.endpoint_enabled and bool(self.lib.IsEndpoint(self.recognizer, self.stream))

    def transcribe(self, pcm, cancelled=lambda: False, update=lambda *args: None):
        for offset in range(0, len(pcm), 3200):
            if cancelled():
                return ''
            self.accept(pcm[offset:offset + 3200])
            update(min(100, int((offset + 3200) * 100 / len(pcm))))
        return '' if cancelled() else self.finish()

    def close(self):
        if self.stream:
            self.lib.DestroyStream(self.stream)
            self.stream = None
        if self.recognizer:
            self.lib.DestroyRecognizer(self.recognizer)
            self.recognizer = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
