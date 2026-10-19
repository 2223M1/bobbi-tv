"""Homatics ATVV adapter; B25 voice verified, B21 identity from controller.switcher."""
from pathlib import Path

from .ur02_service import Ur02Controller

DOWN = bytes.fromhex('022102')
UP = bytes.fromhex('020000')
IDENTITIES = {'B21': '0005:00000957:00000006', 'B25': '0005:00000957:0000000A'}


def find_remote(sysfs=Path('/sys/class/hidraw')):
    for path in sorted(sysfs.glob('hidraw*')):
        try:
            info = dict(line.split('=', 1) for line in
                        (path / 'device/uevent').read_text().splitlines() if '=' in line)
        except OSError:
            continue
        expected = IDENTITIES.get(info.get('HID_NAME'))
        if expected and info.get('HID_ID', '').upper() == expected:
            return '/dev/' + path.name
    return None


class B25Controller(Ur02Controller):
    remote_name = 'Homatics'
    socket_name = 'b25.sock'
    input_source = 'b25'

    def on_report(self, data, maximum=10):
        if data == DOWN and not self.pressed:
            self.pressed = True
            self.trigger('hid', maximum)
        elif data == UP:
            # B25 emits this immediately, even when the key is physically held.
            self.pressed = False
        elif self.caps is None:
            self.query()
