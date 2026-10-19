"""Independent capture and decoding threads; Kodi UI remains on its main thread."""
import queue
import threading
import time

from .audio import RATE, open_microphone, record
from .asr.factory import default_recognizer as create_recognizer


class StreamingSession:
    def __init__(self, root, gate, device='', model_path='',
                 microphone_factory=open_microphone, recognizer_factory=create_recognizer):
        self.root, self.gate = root, gate
        self.device, self.model_path = device, model_path
        self.microphone_factory = microphone_factory
        self.recognizer_factory = recognizer_factory
        self.stop = threading.Event()
        self.endpoint = threading.Event()
        self.capture_done = threading.Event()
        self.decode_done = threading.Event()
        self.lock = threading.Lock()
        # record caps total PCM at max_seconds * 32000 bytes. The producer
        # never waits for the slower decoder, so ALSA cannot overrun due to ASR.
        self.audio = queue.Queue()
        self.queued_bytes = 0
        self.started = time.monotonic()
        self.values = {'phase': 'starting', 'text': '', 'level': 0.0,
                       'peak_rms': 0.0, 'audio_seconds': 0.0,
                       'speech_detected': False, 'decoded_seconds': 0.0,
                       'partial_updates': 0, 'partial_while_recording': False}
        self.threads = [threading.Thread(target=self._capture, name='voice-capture'),
                        threading.Thread(target=self._decode, name='voice-decode')]

    def start(self):
        for thread in self.threads:
            thread.start()

    def cancel(self):
        self.stop.set()

    def finish_capture(self):
        """Close the microphone, then finish decoding all already queued PCM."""
        if not self.capture_done.is_set():
            self._set(manual_stop_requested=True)
            self.endpoint.set()

    def join(self):
        for thread in self.threads:
            thread.join()

    @property
    def done(self):
        return self.capture_done.is_set() and self.decode_done.is_set()

    def snapshot(self):
        with self.lock:
            return dict(self.values)

    def _set(self, **values):
        with self.lock:
            self.values.update(values)

    def _failed(self, error):
        self._set(error=str(error))
        self.stop.set()

    def _level(self, level, elapsed, speech):
        with self.lock:
            self.values.update(level=level, audio_seconds=round(self.gate.elapsed, 3),
                               speech_detected=speech, peak_rms=max(self.values['peak_rms'], level))

    def _offer(self, pcm, speech):
        # Decode from the first USB packet. A volume threshold can confirm
        # speech late and must never trim soft syllables at the beginning.
        self.audio.put(pcm)
        self.queued_bytes += len(pcm)

    def _capture(self):
        try:
            with self.microphone_factory(self.device) as microphone:
                self._set(device=microphone.device, phase='listening')
                pcm = record(microphone, self.gate, self.stop.is_set, self._level, self._offer,
                             finished=self.endpoint.is_set)
                self._set(speech_detected=bool(pcm),
                          audio_seconds=round(self.gate.elapsed, 3),
                          capture_seconds=round(time.monotonic() - self.started, 3),
                          queued_seconds=round(self.queued_bytes / (RATE * 2), 3),
                          phase='recognizing')
            self._set(**getattr(microphone, 'statistics', {}))
        except InterruptedError as error:
            if not self.stop.is_set():
                self._failed(error)
        except Exception as error:
            self._failed(error)
        finally:
            self.capture_done.set()
            self.audio.put(None)

    def _publish(self, text, decoded_bytes):
        with self.lock:
            self.values['decoded_seconds'] = round(decoded_bytes / (RATE * 2), 3)
            if self.values['speech_detected'] and text and text != self.values['text']:
                self.values['text'] = text
                self.values['partial_updates'] += 1
                if 'first_partial_seconds' not in self.values:
                    self.values['first_partial_seconds'] = round(time.monotonic() - self.started, 3)
                if not self.capture_done.is_set():
                    self.values['partial_while_recording'] = True

    def _decode(self):
        try:
            with self.recognizer_factory(self.root, self.model_path) as recognizer:
                load_seconds = time.monotonic() - self.started
                self._set(model_load_seconds=round(load_seconds, 3))
                work_seconds = 0.0
                decoded_bytes = 0
                pending = bytearray()
                end = False
                while not self.stop.is_set() and not end:
                    try:
                        block = self.audio.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if block is None:
                        end = True
                    else:
                        pending.extend(block)
                    # Coalesce small USB packets into 100 ms decoder blocks.
                    while len(pending) >= 3200 or (end and pending):
                        if self.stop.is_set():
                            return
                        chunk = bytes(pending[:3200])
                        del pending[:3200]
                        work_start = time.monotonic()
                        text = recognizer.accept(chunk)
                        work_seconds += time.monotonic() - work_start
                        decoded_bytes += len(chunk)
                        self._publish(text, decoded_bytes)
                        if self.gate.recognizer_endpoint and getattr(recognizer, 'is_endpoint', False):
                            self._set(endpoint_detected=True)
                            self.endpoint.set()
                if not self.stop.is_set() and self.snapshot()['speech_detected']:
                    work_start = time.monotonic()
                    self._set(text=recognizer.finish())
                    work_seconds += time.monotonic() - work_start
                else:
                    self._set(text='')
                self._set(recognition_seconds=round(load_seconds + work_seconds, 3))
        except InterruptedError as error:
            if not self.stop.is_set():
                self._failed(error)
        except Exception as error:
            self._failed(error)
        finally:
            self.decode_done.set()
