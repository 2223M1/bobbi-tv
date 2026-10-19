"""The supported ASR engines, configured independently of any assistant."""
from pathlib import Path

from ..audio import SpeechGate


def default_recognizer(root, model_path=''):
    """Local engine used when no explicit factory is supplied."""
    from ..ncnn_worker_recognizer import NcnnWorkerRecognizer
    return NcnnWorkerRecognizer(root, model_path)


def gate(values, source):
    return SpeechGate(threshold=values['ur02_threshold'] if source == 'ur02' else values['threshold'],
        silence_seconds=values['silence_ms'] / 1000,
        start_timeout=values['start_timeout'], max_seconds=values['max_seconds'],
        startup_seconds=.3 if source in ('nanosic', 'ur02', 'b25') else 0,
        adaptive_noise=source == 'ur02' and values['recognition_engine'] != 'ncnn')


def recognizer(root, profile, values, speech_gate, cancelled):
    engine = values['recognition_engine']
    if engine == 'ncnn':
        # Kodi never loads sherpa-ncnn itself: the bundled build uses the
        # pre-C++11 std::string ABI and corrupts Kodi's heap. See ncnn_worker.
        from ..ncnn_worker_recognizer import NcnnWorkerRecognizer
        return NcnnWorkerRecognizer(root, values['ncnn_model_path'],
            values['ncnn_decoding_method'],
            model_quality=values['ncnn_model_quality'],
            endpoint_silence=speech_gate.silence_seconds if speech_gate.recognizer_endpoint else 0,
            log_path=Path(profile) / 'ncnn-worker.log',
            cancelled=cancelled)
    if engine == 'doubao':
        from ..doubao_recognizer import DoubaoRecognizer
        return DoubaoRecognizer(root, profile, values['doubao_resource_id'], values['doubao_timeout'],
                                cancelled, key_file=values['doubao_key_file'])
    raise ValueError('未知语音识别引擎。')
