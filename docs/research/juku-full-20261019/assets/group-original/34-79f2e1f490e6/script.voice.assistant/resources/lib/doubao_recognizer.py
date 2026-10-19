"""Doubao sentence recognition over the shared isolated PCM worker transport."""
import subprocess
import uuid

from .doubao_config import DEFAULT_RESOURCE, load_key, validate_resource
from .pcm_worker import PcmWorkerRecognizer


class DoubaoRecognizer(PcmWorkerRecognizer):
    def __init__(self, addon_root, profile, resource_id=DEFAULT_RESOURCE, timeout=20,
                 cancelled=lambda: False, process_factory=subprocess.Popen, key_file=''):
        timeout = max(5, min(60, int(timeout)))
        config = {'api_key': load_key(profile, key_file), 'resource_id': validate_resource(resource_id),
                  'timeout': timeout, 'request_id': str(uuid.uuid4())}
        super().__init__(addon_root, 'doubao_worker.py', config, '豆包', timeout,
                         cancelled, process_factory)

    def accept(self, pcm):
        super().accept(pcm)
        return self.text
