"""Small synchronous BlueZ client using CoreELEC's public libsystemd sd-bus API.

The connection stays alive while notifications are subscribed. No Python
D-Bus packages, Bluetooth grabs, HCI writes or platform firmware are needed.
"""
from collections import deque
import ctypes as C
import json
import os
import subprocess


class BusError(C.Structure):
    _fields_ = [('name', C.c_char_p), ('message', C.c_char_p), ('needs_free', C.c_int)]


def characteristics(address, uuids):
    prefix = '/org/bluez/hci0/dev_' + address.replace(':', '_').upper() + '/'
    def run(command):
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired as error:
            raise OSError('蓝牙语音通道查询超时。') from error
    result = run(['busctl', '--system', '--timeout=2', 'tree', '--list', 'org.bluez'])
    if result.returncode:
        raise OSError(result.stderr.strip() or '无法列出蓝牙服务。')
    found = {}
    for path in result.stdout.splitlines():
        if not path.startswith(prefix) or '/char' not in path or '/desc' in path:
            continue
        reply = run(['busctl', '--system', '--timeout=2', 'get-property', 'org.bluez',
            path, 'org.bluez.GattCharacteristic1', 'UUID'])
        if reply.returncode or not reply.stdout.startswith('s '):
            continue
        uuid = json.loads(reply.stdout[2:]).lower()
        if uuid in uuids:
            found[uuid] = path
        if len(found) == len(uuids):
            return found
    raise OSError('没有找到完整的遥控器蓝牙语音通道。')


class GattBus:
    """Own one system bus connection and return bounded copies of Value signals."""
    def __init__(self, address):
        self.bus = C.c_void_p()
        self.slot = C.c_void_p()
        self.events = deque()
        self.failure = None
        self.lib = C.CDLL('libsystemd.so.0')
        self.fast = C.PyDLL('libsystemd.so.0')
        pointer, char, string = C.c_void_p, C.c_char, C.c_char_p
        signatures = {
            'sd_bus_open_system': ([C.POINTER(pointer)], C.c_int),
            'sd_bus_set_method_call_timeout': ([pointer, C.c_uint64], C.c_int),
            'sd_bus_get_fd': ([pointer], C.c_int),
            'sd_bus_process': ([pointer, C.POINTER(pointer)], C.c_int),
            'sd_bus_add_match': ([pointer, C.POINTER(pointer), string, pointer, pointer], C.c_int),
            'sd_bus_slot_unref': ([pointer], pointer),
            'sd_bus_flush_close_unref': ([pointer], pointer),
            'sd_bus_message_new_method_call': ([pointer, C.POINTER(pointer), string, string,
                                               string, string], C.c_int),
            'sd_bus_message_append': ([pointer, string], C.c_int),
            'sd_bus_message_append_array': ([pointer, char, pointer, C.c_size_t], C.c_int),
            'sd_bus_message_open_container': ([pointer, char, string], C.c_int),
            'sd_bus_message_close_container': ([pointer], C.c_int),
            'sd_bus_call': ([pointer, pointer, C.c_uint64, C.POINTER(BusError), C.POINTER(pointer)], C.c_int),
            'sd_bus_error_free': ([C.POINTER(BusError)], None),
            'sd_bus_message_unref': ([pointer], pointer),
            'sd_bus_message_get_path': ([pointer], string),
            'sd_bus_message_is_signal': ([pointer, string, string], C.c_int),
            'sd_bus_message_read': ([pointer, string], C.c_int),
            'sd_bus_message_enter_container': ([pointer, char, string], C.c_int),
            'sd_bus_message_exit_container': ([pointer], C.c_int),
            'sd_bus_message_read_array': ([pointer, char, C.POINTER(pointer), C.POINTER(C.c_size_t)], C.c_int),
            'sd_bus_message_skip': ([pointer, string], C.c_int),
        }
        blocking = {'sd_bus_open_system', 'sd_bus_add_match', 'sd_bus_call', 'sd_bus_flush_close_unref'}
        for name, (arguments, result) in signatures.items():
            # Copying/parsing a signal performs many tiny native operations.
            # Keep the GIL for these nonblocking calls to avoid a convoy with
            # Kodi's other Python interpreters. Blocking I/O releases it.
            function = getattr(self.lib if name in blocking else self.fast, name)
            function.argtypes, function.restype = arguments, result
            setattr(self.lib, name, function)
        try:
            self._check(self.lib.sd_bus_open_system(C.byref(self.bus)))
            self._check(self.lib.sd_bus_set_method_call_timeout(self.bus, 2000000))
            prefix = '/org/bluez/hci0/dev_' + address.replace(':', '_').upper()
            self.prefix = prefix + '/'
            match = ("type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',"
                     "member='PropertiesChanged',path_namespace='" + prefix + "'")
            self._check(self.lib.sd_bus_add_match(self.bus, C.byref(self.slot), match.encode(),
                                                  None, None))
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(result):
        if result < 0:
            raise OSError(-result, os.strerror(-result))
        return result

    @property
    def fd(self):
        return self._check(self.lib.sd_bus_get_fd(self.bus))

    def _signal(self, message):
        try:
            if not self.lib.sd_bus_message_is_signal(message,
                    b'org.freedesktop.DBus.Properties', b'PropertiesChanged'):
                return
            path = self.lib.sd_bus_message_get_path(message).decode()
            if not path.startswith(self.prefix):
                return
            interface = C.c_char_p()
            self._check(self.lib.sd_bus_message_read(message, b's', C.byref(interface)))
            if interface.value != b'org.bluez.GattCharacteristic1':
                return
            self._check(self.lib.sd_bus_message_enter_container(message, b'a', b'{sv}'))
            while self._check(self.lib.sd_bus_message_enter_container(message, b'e', b'sv')):
                key = C.c_char_p()
                self._check(self.lib.sd_bus_message_read(message, b's', C.byref(key)))
                if key.value == b'Value':
                    self._check(self.lib.sd_bus_message_enter_container(message, b'v', b'ay'))
                    data, length = C.c_void_p(), C.c_size_t()
                    self._check(self.lib.sd_bus_message_read_array(message, b'y', C.byref(data), C.byref(length)))
                    if length.value > 8192 or len(self.events) >= 1024:
                        raise OSError('蓝牙音频通知缓冲超限。')
                    self.events.append((path, C.string_at(data, length.value)))
                    self._check(self.lib.sd_bus_message_exit_container(message))
                else:
                    self._check(self.lib.sd_bus_message_skip(message, b'v'))
                self._check(self.lib.sd_bus_message_exit_container(message))
            self._check(self.lib.sd_bus_message_exit_container(message))
        except Exception as error:
            self.failure = error

    def poll(self):
        # Parse messages in the owning interpreter. CFUNCTYPE callbacks use
        # PyGILState_Ensure, which is unsuitable for Kodi's subinterpreters.
        for unused in range(512):
            message = C.c_void_p()
            try:
                if not self._check(self.lib.sd_bus_process(self.bus, C.byref(message))):
                    break
                if message:
                    self._signal(message)
            finally:
                self.lib.sd_bus_message_unref(message)
        if self.failure:
            raise OSError(str(self.failure))
        result = list(self.events)
        self.events.clear()
        return result

    def call(self, path, method, value=None):
        message, reply, error = C.c_void_p(), C.c_void_p(), BusError()
        try:
            self._check(self.lib.sd_bus_message_new_method_call(self.bus, C.byref(message), b'org.bluez',
                path.encode(), b'org.bluez.GattCharacteristic1', method.encode()))
            if value is not None:
                buffer = C.create_string_buffer(value)
                self._check(self.lib.sd_bus_message_append_array(message, b'y', buffer, len(value)))
                self._check(self.lib.sd_bus_message_open_container(message, b'a', b'{sv}'))
                self._check(self.lib.sd_bus_message_open_container(message, b'e', b'sv'))
                self._check(self.lib.sd_bus_message_append(message, b's', C.c_char_p(b'type')))
                self._check(self.lib.sd_bus_message_open_container(message, b'v', b's'))
                self._check(self.lib.sd_bus_message_append(message, b's', C.c_char_p(b'command')))
                for unused in range(3):
                    self._check(self.lib.sd_bus_message_close_container(message))
            result = self.lib.sd_bus_call(self.bus, message, 2000000, C.byref(error), C.byref(reply))
            if result < 0:
                description = error.message.decode(errors='replace') if error.message else os.strerror(-result)
                raise OSError(-result, description)
        finally:
            self.lib.sd_bus_message_unref(message)
            self.lib.sd_bus_message_unref(reply)
            self.lib.sd_bus_error_free(C.byref(error))

    def subscribe(self, path):
        self.call(path, 'StartNotify')

    def write(self, path, value):
        self.call(path, 'WriteValue', value)

    def close(self):
        if self.slot:
            self.lib.sd_bus_slot_unref(self.slot)
            self.slot = C.c_void_p()
        if self.bus:
            self.lib.sd_bus_flush_close_unref(self.bus)
            self.bus = C.c_void_p()
        self.events.clear()
