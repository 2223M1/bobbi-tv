"""Check the configured Doubao key against the real service, from the TV.

The dictation path reports "豆包 API Key 无效或已失效" for every 401, which
cannot be acted on: a key from another product line, a key issued in a
different project, a disabled key and a truncated paste all look identical.
This self-test opens the same WebSocket the recogniser uses, without sending
audio, and reports the service's own status so the next step is obvious.

The probe itself runs in ``key_probe_child.py``: like the recogniser, it must
not import the TLS/WebSocket stack into Kodi's process.
"""
import json
from pathlib import Path
import subprocess
import sys

from .strings import text

SCRIPT = Path(__file__).with_name('key_probe_child.py')
TIMEOUT = 90


def _probe(root, profile, values):
    """Return (report, error_message)."""
    key_path = values.get('doubao_key_file') or str(Path(profile) / 'doubao-api-key.txt')
    if not Path(key_path).is_file():
        return None, text(31111, key_path)
    try:
        completed = subprocess.run([sys.executable, str(SCRIPT), str(root), key_path],
                                   capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, text(31112)
    lines = (completed.stdout or '').strip().splitlines()
    if not lines:
        tail = ' / '.join((completed.stderr or '').strip().splitlines()[-3:])
        return None, text(31113, tail or '无输出')
    try:
        return json.loads(lines[-1]), ''
    except ValueError:
        return None, text(31113, lines[-1][:200])


def check(root, profile, values):
    """Return (headline, detail) describing whether the key works."""
    report, failure = _probe(root, profile, values)
    if report is None:
        return text(31110), failure
    results = report.get('results', [])
    accepted = [label for resource, label, status, body in results if status == 200]
    rows = [text(31106, report.get('length', 0))]
    for resource, label, status, body in results:
        # The body always opens with the same two words when rejected; the
        # status code carries the information, so keep the line short.
        rows.append('%s %s → %s' % ('✓' if status == 200 else '✗', label, status))
    detail = '\n'.join(rows)
    statuses = {status for resource, label, status, body in results}
    if accepted:
        return text(31104, accepted[0]), detail + '\n' + text(31105)
    if statuses == {401}:
        return text(31107), detail + '\n' + text(31108)
    if 403 in statuses:
        return text(31109), detail + '\n' + text(31108)
    return text(31110), detail + '\n' + text(31112)
