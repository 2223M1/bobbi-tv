"""Handshake probe run in a child interpreter; must not import Kodi modules.

Kept as a real file rather than an inline string so it can be run and debugged
on the box directly:

    python3 resources/lib/key_probe_child.py <addon_root> <key_file>
"""
import json
import sys
import uuid

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[1] + '/resources/vendor')

import websocket
from resources.lib.doubao_config import read_key_file

RESOURCES = [('volc.seedasr.sauc.duration', '2.0 duration'),
             ('volc.seedasr.sauc.concurrent', '2.0 concurrent'),
             ('volc.bigasr.sauc.duration', '1.0 duration'),
             ('volc.bigasr.sauc.concurrent', '1.0 concurrent')]
URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream'


def main():
    key = read_key_file(sys.argv[2])
    results = []
    for resource, label in RESOURCES:
        request_id = str(uuid.uuid4())
        headers = {'X-Api-Key': key, 'X-Api-Resource-Id': resource,
                   'X-Api-Request-Id': request_id, 'X-Api-Connect-Id': request_id,
                   'X-Api-Sequence': '-1'}
        try:
            connection = websocket.create_connection(URL, header=headers, timeout=15,
                                                     enable_multithread=True, redirect_limit=0)
        except websocket.WebSocketBadStatusException as error:
            body = error.resp_body or b''
            if isinstance(body, bytes):
                body = body.decode('utf-8', 'replace')
            results.append([resource, label, error.status_code, body.strip()[:120]])
        except Exception as error:
            results.append([resource, label, 0, type(error).__name__ + ': ' + str(error)[:100]])
        else:
            connection.shutdown()
            results.append([resource, label, 200, ''])
    print(json.dumps({'length': len(key), 'results': results}))


if __name__ == '__main__':
    main()
