"""sherpa-ncnn sentence recognition over the shared isolated PCM worker.

Kodi must never load the bundled sherpa-ncnn itself; see ncnn_worker.py for
why.  This class is the only part of the ncnn engine that runs inside Kodi,
and it only talks to the child process.
"""
import subprocess

from .pcm_worker import PcmWorkerRecognizer


class NcnnWorkerRecognizer(PcmWorkerRecognizer):
    def __init__(self, addon_root, model_path='', decoding_method='modified_beam_search',
                 num_active_paths=4, model_quality='balanced', endpoint_silence=0.0,
                 log_path='', timeout=30, cancelled=lambda: False,
                 process_factory=subprocess.Popen):
        # Loading the streaming model takes about a second on an Amlogic box;
        # the first call also pays for the interpreter and library start-up.
        config = {'model_path': model_path, 'decoding_method': decoding_method,
                  'num_active_paths': num_active_paths, 'model_quality': model_quality,
                  'endpoint_silence': endpoint_silence, 'log': str(log_path or '')}
        super().__init__(addon_root, 'ncnn_worker.py', config, '本地', timeout,
                         cancelled, process_factory)

    def accept(self, pcm):
        super().accept(pcm)
        return self.text
