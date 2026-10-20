"""Exclusive LED ownership, with crash-recoverable state in /run."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

LEDS = Path('/sys/class/leds')
DRIVER = Path('/sys/bus/i2c/drivers/leds-tca6507')
DEVICE = Path('/sys/bus/i2c/devices/3-0045')
STATE = Path('/run/aurora6s-led-original.json')
CHANNELS = ('strip-red', 'strip-green', 'strip-blue')


def check_platform(led=False):
    from device import detect
    profile = detect(check_kernel=not led, runtime_profile=led)
    if led:
        if profile['dt_id'] != profile['expected_dt_id']:
            raise RuntimeError('请先安装对应机型的硬件修复并重启')
        if not DEVICE.exists():
            raise RuntimeError('未找到灯控芯片，请重启后重试')
    return profile


def write(path, value):
    path.write_text(str(value))


def read_led(name):
    p = LEDS / name
    return dict(trigger=(p / 'trigger').read_text(encoding='utf-8').split('[')[1].split(']')[0],
                brightness=int((p / 'brightness').read_text(encoding='utf-8')))


class Controller:
    def __init__(self):
        self.fd = None
        self.lock = None
        self.last = None

    def acquire(self):
        if self.fd is not None:
            return
        profile = check_platform(led=True)
        self.lock = open('/run/aurora6s-led.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            self.lock = None
            raise RuntimeError('灯控已由另一个插件进程使用')
        try:
            bound = DEVICE / 'driver'
            if bound.exists() and bound.resolve() != DRIVER:
                raise RuntimeError('灯控芯片被其他驱动接管')
            if not STATE.exists():
                if not bound.exists():
                    raise RuntimeError('灯控驱动未绑定，无法保存原状态')
                state = {n: read_led(n) for n in CHANNELS + ('sys_led',)}
                temp = STATE.with_suffix('.tmp')
                temp.write_text(json.dumps(state), encoding='utf-8')
                os.replace(temp, STATE)
            # Keep chip enabled; never use heartbeat on its enable GPIO.
            write(LEDS / 'sys_led/trigger', 'none')
            write(LEDS / 'sys_led/brightness', 1)
            if bound.exists():
                write(DRIVER / 'unbind', DEVICE.name)
            if not Path('/dev/i2c-3').exists():
                if profile['branch'] == 'ng':
                    raise RuntimeError('I2C 接口未就绪，请检查 aurora6s-ng-led.service')
                subprocess.run(['modprobe', 'i2c-dev'], check=True, timeout=10)
            self.fd = os.open('/dev/i2c-3', os.O_RDWR)
            fcntl.ioctl(self.fd, 0x0703, 0x45)  # no I2C_SLAVE_FORCE
        except Exception:
            self.close()
            raise

    def resume(self):
        """Restore chip enable and invalidate registers potentially lost in sleep."""
        self.last = None
        self.acquire()
        write(LEDS / 'sys_led/trigger', 'none')
        write(LEDS / 'sys_led/brightness', 1)

    def apply(self, registers, verify=True):
        self.acquire()
        if registers == self.last:
            return
        command = b'\x10' + registers
        if os.write(self.fd, command) != len(command):
            raise OSError('灯控写入不完整')
        if verify:
            os.write(self.fd, b'\x10')
            actual = os.read(self.fd, 11)
            if len(actual) != 11 or actual[:10] != registers[:10]:
                raise OSError('灯控参数读回不匹配')
        self.last = registers

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.lock is None:
            return
        try:
            if STATE.exists():
                state = json.loads(STATE.read_text(encoding='utf-8'))
                if not (DEVICE / 'driver').exists():
                    write(DRIVER / 'bind', DEVICE.name)
                for _ in range(40):
                    if all((LEDS / n / 'brightness').exists() for n in CHANNELS):
                        break
                    time.sleep(.05)
                for n in CHANNELS:
                    write(LEDS / n / 'trigger', 'none')
                    write(LEDS / n / 'brightness', 0)
                for n in CHANNELS + ('sys_led',):
                    write(LEDS / n / 'brightness', state[n]['brightness'])
                    write(LEDS / n / 'trigger', state[n]['trigger'])
                STATE.unlink()
        finally:
            self.last = None
            self.lock.close()
            self.lock = None
