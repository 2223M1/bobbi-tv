"""Maintainer-only exact Gattaca 115 diagnostic; inspect never plays media.

Run inspect with explicitly supplied ordinary selection evidence from attempt 3
or later. The selected release stays pinned; each receipt supplies its own exact
request for the independent history/account check. New output
paths are mandatory. This first phase reads the catalog/history/account scope;
it does not resolve a signed URL, change settings or contact a media CDN.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import ce_115_direct_remote as remote


def target_from_baseline(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    record = (value.get('result') or {}).get('record') or {}
    result = value.get('result') or {}
    card = record.get('selected_card') or {}
    test = record.get('test') or {}
    remote.require(test == dict(title='Gattaca', tmdb_id=782, kind='movie', year=1997), 'TARGET_INVALID')
    remote.require(value.get('operation') == 'select' and value.get('work') == 'gattaca'
        and type(value.get('attempt')) is int and value['attempt'] >= 3
        and value.get('regression_attempt') is True
        and value.get('transport_exit_code') == 0 and result.get('operation') == 'select'
        and result.get('name') == 'gattaca' and result.get('selected') is True
        and record.get('launch_mode') == 'ordinary_ui' and record.get('ordinary_ui') is True
        and record.get('picker_mode') is True, 'TARGET_INVALID')
    return remote.checked_target(dict(request_id=record.get('request_id'),
        selection_identity=record.get('selection_identity'),
        source_key=card.get('Container(1000).ListItem.Property(source_key)'),
        title=card.get('Container(1000).ListItem.Label'), size=55082330412,
        media='movies:782:0:0', year=1997))


def dispatch(source, code):
    """One transport dispatch only; no retries after an ambiguous response."""
    sys.path.insert(0, str(source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ce_115_direct_transport',
        source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        rc, result, diagnostic = wire.readonly(client, code.encode(), deadline_seconds=30)
        remote.require(not rc and not diagnostic and isinstance(result, dict), 'OWNER_UNAVAILABLE')
        return result
    finally:
        client.close()


def execute_inspect(source, output, target, sender=dispatch):
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive receipt persists even if connect/dispatch/ACK fails. No replay.
    receipt = dict(schema=1, operation='inspect', state='unconfirmed', retry_allowed=False,
                   diagnostic_only=True, product_proof=False)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    code = 'import sys\nsys.dont_write_bytecode=True\n' + Path(remote.__file__).read_text(encoding='utf-8')
    code += '\nprint(json.dumps(remote_entry(' + repr(dict(operation='inspect', target=target)) + ')))\n'
    try:
        result = sender(source, code)
    except Exception as error:
        result = dict(receipt, **remote.safe_error(error))
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('inspect',))
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        target = target_from_baseline(args.baseline)
        result = execute_inspect(args.transport_source, args.output, target)
    except Exception as error:
        print(json.dumps(dict(evidence=str(args.output), **remote.safe_error(error))))
        return 1
    print(json.dumps(dict(evidence=str(args.output), result=result), ensure_ascii=False))
    return 0 if result.get('state') == 'validated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
