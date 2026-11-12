"""Real PhoneManagement + MediaIndex over test-only stdio; opens no socket."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--count', type=int, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    for addon in ('script.module.bobbi.core', 'script.module.bobbi.platform'):
        sys.path.insert(0, str(root / 'addons' / addon / 'lib'))
    from bobbi_core.file_ref import from_selected
    from bobbi_core.media_library_index import MediaIndex
    path = root / 'addons/plugin.video.bobbi/lib/services/phone_management.py'
    spec = importlib.util.spec_from_file_location('audited_phone_management', path)
    phone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(phone)
    expected = dict(provider='quark', account_id='quark:' + 'a' * 64, epoch=1, authenticated=True)
    origin, now, writes = 'http://127.0.0.1:9752', [100.0], []

    def emit(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)

    with TemporaryDirectory(prefix='bobbi-phone-contract-') as temporary:
        index = MediaIndex(Path(temporary) / 'index.sqlite3')
        try:
            task = index.start('a' * 32, expected)
            index.begin(task)
            for start in range(0, args.count, 20):
                files = [from_selected(expected, dict(file_id=str(n), directory=False,
                    name='Show.S01E%03d.mkv' % n, size=1024), 'folder')
                    for n in range(start + 1, min(start + 20, args.count) + 1)]
                index.batch(task, files, dict(page=start // 20 + 1), len(files))
            index.finish(task, 'completed')

            def rpc(action, body, **kwargs):
                if action == 'pan_status':
                    return dict(providers=[dict(provider='quark', account=dict(expected))])
                assert body['expected'] == expected
                params = {key: value for key, value in body.items() if key != 'expected'}
                if action == 'catalog_apply':
                    writes.append(dict(request_id=params['request_id'], commands=params['commands']))
                return getattr(index, action.removeprefix('catalog_'))(expected, **params)

            manager = phone.PhoneManagement(expected, origin, rpc=rpc, clock=lambda: now[0])
            emit(dict(ready=True, pairing_code=manager.pairing_url.split('#')[1]))
            for raw in sys.stdin:
                message = json.loads(raw)
                operation = message['op']
                if operation == 'handle':
                    headers = dict(message.get('headers') or {}, Host='127.0.0.1:9752', Origin=origin)
                    try:
                        value, cookie = manager.handle(message['path'], headers,
                            json.dumps(message['body'], ensure_ascii=False).encode('utf-8'))
                        result = dict(status=200, value=value, cookie=cookie)
                    except phone.PhoneError as error:
                        result = dict(status=error.status, value=dict(error=str(error)), cookie=None)
                elif operation == 'state':
                    result = dict(saved=index.db.execute("SELECT count(*) FROM reviews WHERE provenance='manual'").fetchone()[0],
                                  preview_cache=len(manager.previews), writes=writes)
                elif operation == 'advance':
                    now[0] += message['seconds']
                    result = dict(advanced=True)
                elif operation == 'mutate':
                    result = index.apply(expected, uuid4().hex, [message['command']])
                elif operation == 'close':
                    emit(dict(id=message['id'], result=dict(closed=True)))
                    break
                else:
                    raise ValueError('Unknown test operation')
                emit(dict(id=message['id'], result=result))
        finally:
            index.close()


if __name__ == '__main__':
    main()
