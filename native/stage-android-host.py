"""Assemble the Android lifecycle bridge and packaged, ABI-native BT engine."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID = '{http://schemas.android.com/apk/res/android}'
SHARED = ('EngineRunner.java', 'EnginePolicy.java', 'EngineHttp.java', 'Credentials.java')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unknown Android host template: ' + old[:60])
    return text.replace(old, new, 1)


def stage(app, abi, engine_root, native_library, probe_library, font_directory):
    app, engine_root, native_library = map(Path, (app, engine_root, native_library))
    lock = json.loads((ROOT/'android/toolchain-lock.json').read_text())['engine']
    engine = engine_root/abi/'libbobbi_torrserver.so'
    expected = lock['binaries'][abi]
    raw = engine.read_bytes()
    if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise ValueError('Wrong Android engine input')
    native = native_library.read_bytes()
    probe_library = Path(probe_library)
    probe = probe_library.read_bytes()
    if (probe[:4] != b'\x7fELF' or not 1024**2 < len(probe) < 32*1024**2 or
            struct.unpack_from('<H', probe, 18)[0] != expected['elf_machine']):
        raise ValueError('Android probe ABI/input missing')
    font_inputs = {}
    for name in ('libbobbi_7zip.so', 'libbobbi_font_limiter.so'):
        data = (Path(font_directory)/name).read_bytes()
        if (data[:4] != b'\x7fELF' or len(data) > 8*1024**2 or
                struct.unpack_from('<H', data, 18)[0] != expected['elf_machine']):
            raise ValueError('Android font tool ABI/input missing')
        font_inputs[name] = data
    if (native[:4] != b'\x7fELF' or len(native) < 20*1024**2 or
            struct.unpack_from('<H', native, 18)[0] != expected['elf_machine'] or
            any(marker not in native for marker in (b'handoff_protocol', b'bobitv.original_audio.language', b'System.BobiAndroid'))):
        raise ValueError('Recompiled native host contracts or ABI missing')
    java = app/'java/org/bobbi/helper'
    java.mkdir(parents=True, exist_ok=True)
    for name in SHARED:
        text = (ROOT/'android/app/src/main/java/org/bobbi/helper'/name).read_text(encoding='utf-8')
        (java/name).write_text(text.replace('BuildConfig.', 'EngineBuildConfig.'), encoding='utf-8')
    policy = 'package org.bobbi.helper;\nfinal class EngineBuildConfig {\n'
    fields = {'ENGINE_VERSION': lock['version'],
              'ENGINE_ARM32_SHA256': lock['binaries']['armeabi-v7a']['sha256'],
              'ENGINE_ARM64_SHA256': lock['binaries']['arm64-v8a']['sha256']}
    for key, value in fields.items():
        policy += 'static final String ' + key + ' = ' + json.dumps(value) + ';\n'
    (java/'EngineBuildConfig.java').write_text(policy + '}\n')
    for file in (ROOT/'native/android-host/java/org/bobbi/helper').glob('*.java'):
        shutil.copy2(file, java/file.name)
    main = java/'Main.java'
    text = main.read_text()
    for call, replacement in (
        ('super.onResume();', 'super.onResume();\n    HostBridge.resume(this);'),
        ('super.onPause();', 'HostBridge.pause(this);\n    super.onPause();'),
        ('super.onDestroy();', 'HostBridge.destroy(this);\n    super.onDestroy();')):
        text = replace_once(text, call, replacement)
    main.write_text(text)
    manifest = app/'AndroidManifest.xml'
    ET.register_namespace('android', ANDROID[1:-1])
    tree = ET.parse(manifest)
    root = tree.getroot()
    for name in ('FOREGROUND_SERVICE', 'FOREGROUND_SERVICE_SPECIAL_USE', 'POST_NOTIFICATIONS',
                 'REQUEST_INSTALL_PACKAGES'):
        if not root.findall("uses-permission[@android:name='android.permission.%s']" % name,
                            {'android': ANDROID[1:-1]}):
            ET.SubElement(root, 'uses-permission', {ANDROID+'name': 'android.permission.'+name})
    app_element = root.find('application')
    app_element.set(ANDROID+'extractNativeLibs', 'true')
    app_element.set(ANDROID+'allowBackup', 'false')
    service = ET.SubElement(app_element, 'service', {ANDROID+'name': '.EngineService',
        ANDROID+'exported': 'false', ANDROID+'stopWithTask': 'false',
        ANDROID+'foregroundServiceType': 'specialUse'})
    ET.SubElement(service, 'property', {ANDROID+'name': 'android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE',
        ANDROID+'value': 'Local BitTorrent media selected by the user in the integrated player; visible stop control.'})
    ET.SubElement(app_element, 'receiver', {ANDROID+'name': '.InstallReceiver', ANDROID+'exported': 'false'})
    tree.write(manifest, encoding='utf-8', xml_declaration=True)
    gradle = app/'build.gradle'
    text = gradle.read_text()
    text = replace_once(text, "doNotStrip '**.setup'", "doNotStrip '**.setup'\n      doNotStrip '**/libbobbi_*.so'\n      doNotStrip '**/libkodi.so'\n      jniLibs.useLegacyPackaging = true")
    text = replace_once(text, '    sourceSets {', '    compileOptions {\n        sourceCompatibility JavaVersion.VERSION_11\n        targetCompatibility JavaVersion.VERSION_11\n    }\n    sourceSets {')
    gradle.write_text(text)
    lib = app/'lib'/abi
    shutil.copy2(engine, lib/engine.name)
    shutil.copy2(native_library, lib/'libkodi.so')
    shutil.copy2(probe_library, lib/'libbobbi_ffprobe.so')
    for name, data in font_inputs.items():
        (lib/name).write_bytes(data)
    receipt = {'schema': 1, 'abi': abi, 'engine_sha256': expected['sha256'],
               'native_library_sha256': hashlib.sha256(native).hexdigest(),
               'media_probe_sha256': hashlib.sha256(probe).hexdigest(),
               'font_decoder_sha256': hashlib.sha256(font_inputs['libbobbi_7zip.so']).hexdigest(),
               'font_limiter_sha256': hashlib.sha256(font_inputs['libbobbi_font_limiter.so']).hexdigest(),
               'native_contracts': ['transport_capsule_v1', 'original_audio', 'android_host_v1'],
               'real_device_verified': False}
    (app/'assets/system/bobbi-android-host.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt
