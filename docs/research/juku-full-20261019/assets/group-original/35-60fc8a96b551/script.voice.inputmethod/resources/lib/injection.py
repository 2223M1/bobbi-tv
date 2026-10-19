"""Deliver recognized text into the focused Kodi input dialog.

Kodi gives add-ons exactly one text channel: the JSON-RPC ``Input.SendText``
method.  Measured behaviour on CoreELEC / Kodi 21.3:

* ``Input.SendText(text, done=false)`` replaces the whole content of the
  focused on-screen keyboard and leaves the dialog open.
* ``Input.SendText(text, done=true)`` does the same, then closes the dialog as
  if the user had pressed OK.

There is no API to read the current content and no way to insert at the caret,
so a dictation always replaces whatever the box already held.  The add-on warns
about this in its settings text.
"""
import json

import xbmc

# CGUIDialogKeyboardGeneric and its touch variant.  Both are the on-screen
# keyboards Kodi shows for Dialog().input(), skin search boxes and so on.
KEYBOARD_WINDOWS = (10103, 10138)


def rpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps(
        {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
    if 'error' in response:
        raise ValueError('Kodi 操作失败：' + response['error'].get('message', method))
    return response.get('result')


def focused_window_id():
    """Return the id of the window that currently owns focus, or None."""
    try:
        result = rpc('GUI.GetProperties', {'properties': ['currentwindow']})
    except (ValueError, KeyError, TypeError):
        return None
    window = (result or {}).get('currentwindow') or {}
    try:
        return int(window.get('id'))
    except (TypeError, ValueError):
        return None


def is_keyboard(window_id):
    return window_id in KEYBOARD_WINDOWS


def send(text, done=False):
    """Write text into the focused input dialog.  Raises ValueError on refusal."""
    if not isinstance(text, str) or not text:
        raise ValueError('没有可写入的文字。')
    rpc('Input.SendText', {'text': text, 'done': bool(done)})
