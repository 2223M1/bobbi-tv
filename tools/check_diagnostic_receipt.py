"""Opt-in local historical receipt check; no device, transport or account access."""
import argparse
import hashlib
import json
from pathlib import Path

from ce_playback_log_probe import diagnostic_scope


def check(path, request):
    path = Path(path)
    if path.is_symlink():
        return dict(state='invalid', reason='UNSAFE_RECEIPT', device_acceptance=False)
    if not path.exists():
        return dict(state='not_run', reason='RECEIPT_NOT_AVAILABLE', device_acceptance=False)
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('RECEIPT_BOUND')
        before = path.read_bytes()
        scope = diagnostic_scope(path, request)
        digest = hashlib.sha256(before).hexdigest()
        if path.read_bytes() != before or scope['receipt_sha256'] != digest:
            raise ValueError('RECEIPT_CHANGED')
    except (OSError, ValueError, TypeError, KeyError):
        return dict(state='invalid', reason='RECEIPT_CHECK_FAILED', device_acceptance=False)
    return dict(state='verified', scope=scope, unchanged=True, device_acceptance=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args(argv)
    result = check(args.receipt, args.request)
    print(json.dumps(result))
    return {'verified': 0, 'invalid': 1, 'not_run': 2}[result['state']]


if __name__ == '__main__':
    raise SystemExit(main())
