"""Standalone ASR smoke test: run the bundled AISHELL sample through the engine.

Runs with the box's own python3, so recognition can be verified without Kodi
or a microphone.  By default it goes through the isolated worker - the exact
path Kodi uses - and ``--direct`` runs the engine in this process instead, to
tell a native-library problem apart from a transport problem.

Usage: python3 asr-selftest.py [ncnn|doubao] [model_quality] [--direct]
"""
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SAMPLE = ROOT / 'resources/config/asr-test.wav'
EXPECTED = '甚至出现交易几乎停滞的情况。'


def transcribe_direct(pcm, quality):
    from resources.lib.ncnn_recognizer import NcnnRecognizer
    engine = NcnnRecognizer(str(ROOT), '', 'modified_beam_search', model_quality=quality)
    try:
        return engine.transcribe(pcm)
    finally:
        engine.close()


def transcribe_worker(pcm, quality):
    from resources.lib.ncnn_worker_recognizer import NcnnWorkerRecognizer
    engine = NcnnWorkerRecognizer(str(ROOT), model_quality=quality,
                                  log_path=ROOT / 'ncnn-worker.log')
    try:
        return engine.transcribe(pcm)
    finally:
        engine.close()


def main():
    arguments = [value for value in sys.argv[1:] if not value.startswith('--')]
    direct = '--direct' in sys.argv
    quality = arguments[1] if len(arguments) > 1 else 'balanced'
    with wave.open(str(SAMPLE), 'rb') as source:
        assert source.getnchannels() == 1, 'sample must be mono'
        assert source.getsampwidth() == 2, 'sample must be S16_LE'
        assert source.getframerate() == 16000, 'sample must be 16 kHz'
        pcm = source.readframes(source.getnframes())
        frames = source.getnframes()
    print('sample : %d frames, %.2fs' % (frames, frames / 16000))
    print('model  : %s' % quality)
    print('path   : %s' % ('direct' if direct else 'worker'))
    started = time.monotonic()
    text = transcribe_direct(pcm, quality) if direct else transcribe_worker(pcm, quality)
    elapsed = time.monotonic() - started
    print('total  : %.2fs' % elapsed)
    print('expect : %s' % EXPECTED)
    print('actual : %s' % text)
    print('RESULT : %s' % ('PASS' if text.strip('。 ') == EXPECTED.strip('。 ') else 'DIFF'))


if __name__ == '__main__':
    main()
