"""Sentence dictation through this plugin's managed ChatGPT subscription."""
import subprocess

from .codex_agent import validate_proxy
from .pcm_worker import PcmWorkerRecognizer


class CodexDictationRecognizer(PcmWorkerRecognizer):
    def __init__(self, addon_root, profile, timeout=30, cancelled=lambda: False,
                 proxy='', process_factory=subprocess.Popen):
        timeout = max(5, min(60, int(timeout)))
        # The auth token stays inside the worker; it is never carried by this IPC.
        config = {'profile': str(profile), 'timeout': timeout, 'proxy': validate_proxy(proxy)}
        super().__init__(addon_root, 'codex_dictation_worker.py', config, 'Codex 订阅听写',
                         timeout, cancelled, process_factory, own_group=True)
