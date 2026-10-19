"""Observed XiaoPaiRC_173 HID framing, separate from the running Kodi service.

Report 0x2b carries start/stop text or fragments of a 60-byte WNVC frame.
The remote starts audio itself. This module never sends HID/GATT commands.
"""


class NanosicFrames:
    def __init__(self):
        self.active = False
        self.partial = None
        self.sequence = None
        self.fragment = None
        self.previous = None
        self.stats = dict(frames=0, discarded_frames=0, invalid_reports=0,
                          missing_frames=0, starts=0, stops=0)

    @property
    def discarded(self):
        return self.stats['discarded_frames'] + self.stats['missing_frames']

    def _discard(self):
        if self.partial is not None:
            self.stats['discarded_frames'] += 1
        self.partial = self.sequence = self.fragment = None

    def feed(self, report):
        """Return ('start'/'stop', None), ('frame', bytes), or None."""
        if not report or report[0] != 0x2b:
            return None
        payload = report[1:]
        control = payload.rstrip(b'\x00 ')
        if control == b'nanosic voice start':
            self._discard()
            self.active = True
            self.previous = None
            self.stats['starts'] += 1
            return 'start', None
        if control == b'nanosic voice stop':
            self._discard()
            self.active = False
            self.previous = None
            self.stats['stops'] += 1
            return 'stop', None
        if not self.active:
            return None
        if len(payload) != 20:
            self.stats['invalid_reports'] += 1
            self._discard()
            return None
        if payload[:2] == b'\xaa\x99':
            self._discard()
            if payload[3] != 0 or payload[4] != 60:
                self.stats['invalid_reports'] += 1
                return None
            self.sequence = payload[2]
            self.fragment = 1
            self.partial = bytearray(payload[5:])
        elif (payload[0] == 0x99 and self.partial is not None
              and payload[1] == self.sequence and payload[2] == self.fragment):
            self.partial.extend(payload[3:])
            self.fragment += 1
        else:
            self.stats['invalid_reports'] += 1
            self._discard()
            return None
        if len(self.partial) < 60:
            return None
        frame = bytes(self.partial[:60])  # Final fragment has six padding bytes.
        if self.previous is not None:
            self.stats['missing_frames'] += (self.sequence - self.previous - 1) % 256
        self.previous = self.sequence
        self.partial = self.sequence = self.fragment = None
        self.stats['frames'] += 1
        return 'frame', frame
