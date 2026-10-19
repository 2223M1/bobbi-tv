"""Isolated sherpa-ncnn worker: the engine never shares a process with Kodi.

Kodi links a new-ABI libstdc++ long before any add-on runs, while the bundled
aarch64 sherpa-ncnn build uses the pre-C++11 std::string ABI.  Both define the
same weak template symbols - std::regex internals among them - so a plain
dlopen binds our calls to Kodi's newer-ABI copies, the object layouts disagree
and the heap ends up corrupted.  Kodi then dies either inside
ZipformerModel::InitEncoderInputOutputIndexes() (SIGABRT) or, once
RTLD_DEEPBIND hides that one symptom, later in the Python exception handler
that follows (SIGSEGV in _PyErr_ExceptionMatches).  Each crash counts towards
CoreELEC's crash-loop guard, which moves the whole user profile aside.

Running the engine in its own python3 process removes Kodi from that equation:
a failure here is a reported error instead of a dead media centre.  The
transport is the shared PCM worker protocol implemented in pcm_worker.py.
"""
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from resources.lib.ncnn_recognizer import NcnnRecognizer

# The settings contract caps a single recording at 30 seconds.
MAX_AUDIO_BYTES = 30 * 32000


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def exact(size):
    result = bytearray()
    while len(result) < size:
        chunk = sys.stdin.buffer.read(size - len(result))
        if not chunk:
            raise InterruptedError('调用方已结束本地识别。')
        result.extend(chunk)
    return bytes(result)


def redirect_stderr(path):
    """Send C-level diagnostics to a file; the caller's pipe only carries JSON.

    A crash inside the native engine never reaches Python, so its last words
    would otherwise be lost - pcm_worker.py opens the child with stderr on
    /dev/null to keep the protocol stream clean.
    """
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    except OSError:
        return
    os.dup2(descriptor, 2)
    os.close(descriptor)


def main():
    engine = None
    try:
        raw = sys.stdin.buffer.readline(4097)
        if len(raw) > 4096 or not raw.endswith(b'\n'):
            raise ValueError('本地识别请求配置无效。')
        config = json.loads(raw)
        if config.get('log'):
            redirect_stderr(config['log'])
        engine = NcnnRecognizer(ROOT, config.get('model_path', ''),
            config.get('decoding_method', 'modified_beam_search'),
            int(config.get('num_active_paths', 4)),
            model_quality=config.get('model_quality', 'balanced'),
            endpoint_silence=float(config.get('endpoint_silence', 0.0)))
        emit({'type': 'ready'})
        total = 0
        while True:
            size = struct.unpack('>I', exact(4))[0]
            if size == 0:
                emit({'type': 'result', 'text': engine.finish(), 'last': True})
                break
            if size % 2 or not 0 < size <= 6400:
                raise ValueError('本地音频输入无效。')
            total += size
            if total > MAX_AUDIO_BYTES:
                raise ValueError('本地单次录音不能超过 30 秒。')
            emit({'type': 'result', 'text': engine.accept(exact(size)), 'last': False,
                  'endpoint': bool(engine.is_endpoint)})
    except InterruptedError:
        pass
    except Exception as error:
        emit({'type': 'error', 'error': str(error) or error.__class__.__name__})
    finally:
        if engine is not None:
            engine.close()


if __name__ == '__main__':
    main()
