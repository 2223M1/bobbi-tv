"""Local structural gates. These do not start an Android engine or certify a device."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('bootstrap_android', ROOT / 'tools/bootstrap_android.py')
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)


def elf64(alignment=16384, address=0, machine=183, interpreter=b'/system/bin/linker64\0'):
    data = bytearray(256)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HH', data, 16, 3, machine)
    struct.pack_into('<Q', data, 32, 64)
    struct.pack_into('<HH', data, 54, 56, 2)
    struct.pack_into('<I', data, 64, 1)
    struct.pack_into('<QQ', data, 72, 0, address)
    struct.pack_into('<Q', data, 112, alignment)
    struct.pack_into('<I', data, 120, 3)
    struct.pack_into('<Q', data, 128, 192)
    data[192:192 + len(interpreter)] = interpreter
    return data


class BootstrapTests(unittest.TestCase):
    def probe(self, data, machine=183):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'input'
            target.write_bytes(data)
            return BOOT.elf_info(target, machine)

    def test_arm64_pie_android_and_16k(self):
        result = self.probe(elf64())
        self.assertTrue(result['supports_16k_alignment'])
        self.assertEqual('/system/bin/linker64', result['interpreter'])

    def test_16k_requires_congruent_load_addresses(self):
        self.assertFalse(self.probe(elf64(address=4096))['supports_16k_alignment'])
        self.assertFalse(self.probe(elf64(alignment=4096))['supports_16k_alignment'])

    def test_truncated_and_wrong_architecture_rejected(self):
        for data in (b'\x7fELF', elf64(machine=62), elf64()[:100],
                     elf64(interpreter=b'/lib64/ld-linux-x86-64.so.2\0')):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                self.probe(data)

    def test_archive_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            archive = directory / 'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('../escaped.txt', 'no')
            with patch.object(BOOT, 'PRIVATE', directory), self.assertRaises(ValueError):
                BOOT.unpack(archive, 'tool', 'expected-hash')
            self.assertFalse((directory.parent / 'escaped.txt').exists())

    def test_archive_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            archive = directory / 'unsafe.zip'
            entry = zipfile.ZipInfo('link')
            entry.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr(entry, 'elsewhere')
            with patch.object(BOOT, 'PRIVATE', directory), self.assertRaises(ValueError):
                BOOT.unpack(archive, 'tool', 'expected-hash')

    def test_fetch_rejects_unknown_network_origin(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(BOOT, 'PRIVATE', Path(folder)):
            with self.assertRaises(ValueError):
                BOOT.fetch({'url': 'https://example.com/tool', 'sha256': '0' * 64})

    def test_sdk_revision_must_match_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            package = directory / 'platform-tools'
            package.mkdir()
            (package / 'source.properties').write_text('#Pkg.Revision=wrong\nPkg.Revision=37.0.1\n')
            lock = {'sdk_revisions': {'platform-tools': '37.0.1'}}
            self.assertEqual({'platform-tools': '37.0.1'}, BOOT.sdk_versions(directory, lock))
            lock['sdk_revisions']['platform-tools'] = '999'
            with self.assertRaises(ValueError):
                BOOT.sdk_versions(directory, lock)

    def test_lock_names_real_android_arm_inputs(self):
        lock = json.loads((ROOT / 'android/toolchain-lock.json').read_text())
        self.assertEqual({'armeabi-v7a', 'arm64-v8a'}, set(lock['engine']['binaries']))
        self.assertEqual('MatriX.147', lock['engine']['version'])
        self.assertEqual(set(lock['sdk_packages']), set(lock['sdk_revisions']))
        for item in lock['engine']['binaries'].values():
            self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
            self.assertIn('/TorrServer-android-', item['url'])


if __name__ == '__main__':
    unittest.main()
