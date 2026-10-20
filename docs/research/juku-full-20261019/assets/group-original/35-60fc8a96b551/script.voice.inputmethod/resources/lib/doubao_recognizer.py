"""Doubao sentence recognition over the shared isolated PCM worker transport."""
import subprocess
import uuid

from .doubao_config import DEFAULT_RESOURCE, load_key, validate_resource
from .pcm_worker import PcmWorkerRecognizer

# The service acknowledges a packet only once it has enough audio to produce a
# new partial, so acks arrive strictly slower than packets: measured on a
# Tencent Aurora 4 Pro, 42 blocks of 100 ms produced 20 acks, each a constant
# two blocks behind the one just sent. PcmWorkerRecognizer.accept() waits for
# its own block's answer, which therefore never comes and reports a 20 second
# "识别超时" on every real recording. Doubao is also in sentence mode (the
# final text arrives after the closing packet), so the answer belongs to the
# capture, not to an individual block: block acks are counted but not awaited,
# and only finish() waits, bounded by the same timeout.
ACK_RATIO = 2


class DoubaoRecognizer(PcmWorkerRecognizer):
    def __init__(self, addon_root, profile, resource_id=DEFAULT_RESOURCE, timeout=20,
                 cancelled=lambda: False, process_factory=subprocess.Popen, key_file=''):
        timeout = max(5, min(60, int(timeout)))
        config = {'api_key': load_key(profile, key_file), 'resource_id': validate_resource(resource_id),
                  'timeout': timeout, 'request_id': str(uuid.uuid4())}
        super().__init__(addon_root, 'doubao_worker.py', config, '豆包', timeout,
                         cancelled, process_factory)
        # Slower than one ack per block: a long phrase must not spend the whole
        # timeout waiting for acks, which are not what finish() needs anyway.
        self.ack_timeout = max(2, self.timeout // 2)

    def accept(self, pcm):
        self._check()
        if self.finished or len(pcm) % 2 or len(pcm) > 6400:
            raise ValueError('{}音频输入无效。'.format(self.label))
        self.audio_bytes += len(pcm)
        if self.audio_bytes > 30 * 32000:
            raise ValueError('{}单次录音不能超过 30 秒。'.format(self.label))
        if pcm and not self.final:
            self._send(self._frame(pcm), timeout=self.ack_timeout)
            self.sent_frames += 1
            self._wait(lambda: self.read_results * ACK_RATIO >= self.sent_frames or self.final,
                       timeout=self.ack_timeout)
        self._poll()
        return self.text

    def finish(self):
        # The closing packet is what makes the service emit its final text, so
        # it is sent before waiting; _wait would otherwise spin for 20 seconds
        # against a flag that only that packet can set.
        self.finished = True
        if not self.final:
            self._send(self._frame(b''))
        self._wait(lambda: self.final)
        return self.text
