"""Learned key binding, following controller.switcher's numeric Kodi key format."""
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

ACTION = 'RunScript(script.voice.inputmethod,--voice)'
LONG_PRESS = 0x01000000

# Kodi's keymap documentation is explicit: <global> is only a fall-through for
# buttons the current window's section does not define.  The on-screen keyboard
# is the <VirtualKeyboard> window, and Kodi's system keymap already routes
# several of its buttons to the built-in ``VoiceRecognizer`` action.  A binding
# written only into <global> therefore stops working the moment the keyboard
# opens - which is exactly when dictation is wanted.  Write into both sections.
SECTIONS = ('global', 'VirtualKeyboard')

# Buttons Kodi's <VirtualKeyboard> section sends to ``VoiceRecognizer``.  Kodi
# ships no voice recognition implementation, so today they do nothing at all.
# This add-on *is* the voice input implementation, so it claims them.
VIRTUAL_KEYBOARD_BUTTONS = ('browser_search', 'menu', 'play_pause')

# ``browser_search`` is mapped to an *empty* action in Kodi's <global> section -
# i.e. deliberately disabled, because Kodi has no voice implementation behind it.
# Cheap to claim, and it catches remotes whose voice button is reported as HID
# consumer usage 0x221 (AC Search, Linux KEY_SEARCH) rather than 0x0CF (Voice
# Command).  ``menu``/``play_pause`` are left alone here: they have real
# functions (ContextMenu / PlayPause) on ordinary screens.
GLOBAL_BUTTONS = ('browser_search',)

SECTION_BUTTONS = (('global', GLOBAL_BUTTONS), ('VirtualKeyboard', VIRTUAL_KEYBOARD_BUTTONS))


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
    return files[-1] if files else directory / 'voice-input.xml'


def _identifier(element, names):
    if element.tag.lower() == 'key':
        return element.get('id')
    return names.get(element.tag.lower())


def _is_ours(element):
    """True for an element this add-on wrote itself, whatever key it was on."""
    return ' '.join((element.text or '').split()).casefold() == ACTION.casefold()


def _replace(path, data, mode):
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


def _section(root, name):
    nodes = root.findall(name)
    return nodes if nodes else [ET.SubElement(root, name)]


def _keyboard(context):
    keyboards = context.findall('keyboard')
    return keyboards[-1] if keyboards else ET.SubElement(context, 'keyboard')


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
    for section in SECTIONS:
        # Drop this key's previous entries *and* anything this add-on bound
        # before, so re-binding does not leave the old key behind.  Without
        # this the file accumulates one stale binding per re-bind.
        for context in _section(root, section):
            for keyboard in context.findall('keyboard'):
                for key in list(keyboard):
                    if not isinstance(key.tag, str):
                        continue
                    if _is_ours(key):
                        keyboard.remove(key)
                        continue
                    if str(_identifier(key, names)) == code and key.get('mod', '').lower() in ('', 'longpress'):
                        keyboard.remove(key)
        keyboard = _keyboard(_section(root, section)[-1])
        # Kodi suppresses hold autorepeat only with an explicit longpress
        # mapping.  Both gestures launch once; no repeated interpreter creation
        # while the key is held.
        for mod in ('', 'longpress'):
            attributes = {'id': code}
            if mod:
                attributes['mod'] = mod
            ET.SubElement(keyboard, 'key', attributes).text = ACTION
    # Claim the buttons Kodi already reserves for voice input.
    for section, buttons in SECTION_BUTTONS:
        keyboard = _keyboard(_section(root, section)[-1])
        for name in buttons:
            for key in list(keyboard):
                if isinstance(key.tag, str) and key.tag.lower() == name:
                    keyboard.remove(key)
            ET.SubElement(keyboard, name).text = ACTION
    ET.indent(root, space='    ')
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if data == original:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target_file(directory) != target or (target.read_bytes() if target.exists() else None) != original:
        raise ValueError('按键文件已发生变化，请重新绑定。')
    mode = target.stat().st_mode & 0o777 if original is not None else 0o644
    if original is not None:
        _replace(target.with_suffix(target.suffix + '.voice-input.bak'), original, mode)
    _replace(target, data, mode)
    return target
