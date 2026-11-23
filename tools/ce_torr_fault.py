"""Inspect one exact BT video's registered local TorrServer; no injection yet."""
import argparse
import json
import os
from pathlib import Path

import ce_115_direct_trial as transport
import ce_torr_fault_remote as remote


def exclusive(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())


def inspect_once(source, output, request, instance, sender=transport.dispatch):
    remote.require(remote.RID.fullmatch(request) and remote.UUID.fullmatch(instance), 'SCOPE_INVALID')
    pending = dict(operation='inspect', state='unconfirmed', mode='read_only', retry_allowed=False)
    exclusive(output, pending)
    code = 'import sys\nsys.dont_write_bytecode=True\n' + Path(remote.__file__).read_text(encoding='utf-8')
    code += '\nprint(json.dumps(inspect_entry(' + repr(dict(operation='inspect', request_id=request,
                                                           native_instance=instance)) + ')))\n'
    try:
        result = sender(source, code)
    except Exception as error:
        result = dict(pending, **remote.safe_error(error))
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def capabilities_once(source, output, sender=transport.dispatch):
    pending = dict(operation='capabilities', state='unconfirmed', mode='read_only', retry_allowed=False)
    exclusive(output, pending)
    code = 'import sys\nsys.dont_write_bytecode=True\n' + Path(remote.__file__).read_text(encoding='utf-8')
    code += '\nprint(json.dumps(inspect_entry({"operation":"capabilities"})))\n'
    try:
        result = sender(source, code)
    except Exception as error:
        result = dict(pending, **remote.safe_error(error))
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('capabilities','inspect'))
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request')
    parser.add_argument('--instance')
    args = parser.parse_args()
    try:
        if args.operation == 'capabilities':
            remote.require(args.request is None and args.instance is None, 'SCOPE_INVALID')
            result = capabilities_once(args.transport_source, args.output)
        else:
            remote.require(args.request and args.instance, 'SCOPE_INVALID')
            result = inspect_once(args.transport_source, args.output, args.request, args.instance)
        print(json.dumps(dict(evidence=str(args.output), result=result), ensure_ascii=False))
        return 0 if result.get('state') == 'inspected' else 1
    except Exception as error:
        print(json.dumps(dict(evidence=str(args.output), **remote.safe_error(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
