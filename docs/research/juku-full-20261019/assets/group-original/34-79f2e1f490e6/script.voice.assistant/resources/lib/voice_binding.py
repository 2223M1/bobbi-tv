"""Learned key binding, following controller.switcher's numeric Kodi key format."""
from .data_paths import data_path
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ACTION = 'RunScript(script.voice.assistant,--voice)'
LONG_PRESS = 0x01000000


def binding_status(profile):
    import time
    from .storage import read_json
    value = read_json(data_path(Path(profile), 'voice-binding.json'), {})
    if value.get('state') in ('requested', 'listening') and time.time() - value.get('updated_at', 0) > 30:
        return {'state': 'cancelled', 'error': '绑定等待已结束，请重试。'}
    return value


def begin_binding(profile):
    import secrets
    if binding_status(profile).get('state') in ('requested', 'listening'):
        raise ValueError('正在等待遥控按键，请在电视上完成绑定。')
    identifier = secrets.token_hex(16)
    update_binding(profile, identifier, 'requested', initial=True)
    return identifier


def update_binding(profile, identifier, state, initial=False, **details):
    import time
    from .storage import write_json
    if not initial and binding_status(profile).get('id') != identifier:
        raise ValueError('绑定请求已过期，请重新开始。')
    write_json(data_path(Path(profile), 'voice-binding.json'), dict(details, id=identifier, state=state, updated_at=time.time()))


def bound_codes(directory):
    """Resolve global voice bindings without letting window-local Back override them."""
    names = json.loads((Path(__file__).resolve().parents[1] / 'config/keyboard-mapping.json').read_text(encoding='utf-8'))
    bindings = {}
    paths = (p for p in Path(directory).glob('*') if p.is_file() and p.suffix.lower() == '.xml')
    for path in sorted(paths, key=lambda p: (p.name.casefold(), p.name)):
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for keyboard in root.findall('global/keyboard'):
            for key in keyboard:
                code = key.get('id') if key.tag.lower() == 'key' else names.get(key.tag.lower())
                mod = key.get('mod', '').lower()
                if code is not None and mod in ('', 'longpress'):
                    bindings[(str(code), mod)] = (key.text or '').strip()
    return {code for (code, mod), action in bindings.items() if action == ACTION}


def current_codes():
    import xbmcvfs
    return bound_codes(xbmcvfs.translatePath('special://userdata/keymaps/'))


def is_voice_key(action, codes):
    return button_code(getattr(action, 'getButtonCode', lambda: 0)()) in codes


def button_code(value):
    value = int(value)
    if not 0 < value <= 0xffffffff:
        return None
    code = value & ~LONG_PRESS
    return str(code) if code else None


def target_file(directory):
    directory = Path(directory)
    files = sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == '.xml'),
                   key=lambda p: (p.name.casefold(), p.name)) if directory.exists() else []
    return files[-1] if files else directory / 'voice-assistant.xml'


def _replace(path, data, mode):
    import tempfile
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as output:
        temporary = Path(output.name)
        try:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            output.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def bind(directory, code):
    code = button_code(code)
    if code is None:
        raise ValueError('没有收到有效的按键。')
    target = target_file(directory)
    original = target.read_bytes() if target.exists() else None
    try:
        root = ET.fromstring(original, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))) if original is not None else ET.Element('keymap')
    except ET.ParseError:
        raise ValueError('按字母排序最后的 XML 无法解析：' + target.name) from None
    if root.tag != 'keymap':
        raise ValueError('目标 XML 的根节点不是 keymap：' + target.name)
    names = json.loads((Path(__file__).resolve().parents[1] / 'config/keyboard-mapping.json').read_text(encoding='utf-8'))
    global_nodes = root.findall('global')
    if not global_nodes:
        global_nodes = [ET.SubElement(root, 'global')]
    # Update only this key in global; preserve all unrelated devices/windows.
    for context in global_nodes:
        for keyboard in context.findall('keyboard'):
            for key in list(keyboard):
                if not isinstance(key.tag, str):
                    continue
                identifier = key.get('id') if key.tag.lower() == 'key' else names.get(key.tag.lower())
                if str(identifier) == code and key.get('mod', '').lower() in ('', 'longpress'):
                    keyboard.remove(key)
    context = global_nodes[-1]
    keyboards = context.findall('keyboard')
    keyboard = keyboards[-1] if keyboards else ET.SubElement(context, 'keyboard')
    # Kodi suppresses hold autorepeat only with an explicit longpress mapping.
    # Both gestures launch once; no repeated interpreter creation while held.
    for mod in ('', 'longpress'):
        attributes = {'id': code}
        if mod:
            attributes['mod'] = mod
        ET.SubElement(keyboard, 'key', attributes).text = ACTION
    ET.indent(root, space='    ')
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if data == original:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target_file(directory) != target or (target.read_bytes() if target.exists() else None) != original:
        raise ValueError('按键文件已发生变化，请重新绑定。')
    mode = target.stat().st_mode & 0o777 if original is not None else 0o644
    if original is not None:
        _replace(target.with_suffix(target.suffix + '.voice-assistant.bak'), original, mode)
    _replace(target, data, mode)
    return target
