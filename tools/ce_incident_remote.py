"""Drive real Kodi EventServer input and observe Kodi on a named test box.

The caller chooses the directory/film/source in the running GUI. This tool
never opens media or supplies substitute provider results. The packet format
is the Kodi EventServer v2 wire format (HELO/BUTTON/BYE).
"""
import json
import secrets
import socket
import struct
import time
from urllib.request import ProxyHandler, Request, build_opener


class Remote:
    def __init__(self, host, name='', *, port=9777):
        self.peer = (host, port)
        self.rpc_url = 'http://{}:8080/jsonrpc'.format(host)
        self.uid = secrets.randbits(32) or 1
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.name = name
        self.http = build_opener(ProxyHandler({}))

    def packet(self, kind, payload=b''):
        header = struct.pack('!4sBBHIIHI10x', b'XBMC', 2, 0, kind, 1, 1, len(payload), self.uid)
        self.sock.sendto(header + payload, self.peer)

    def __enter__(self):
        self.packet(1, self.name.encode('utf-8') + bytes(12))
        return self

    def __exit__(self, *unused):
        try:
            self.packet(2)
        finally:
            self.sock.close()

    def button(self, name):
        # Named standard remote button, a single pressed/queued non-repeat event.
        self.packet(3, struct.pack('!HHH', 0, 0x33, 0) + b'R1\0' + name.encode('ascii') + b'\0')

    def rpc(self, method, **params):
        req = Request(self.rpc_url, json.dumps(dict(jsonrpc='2.0', id=1, method=method,
                      params=params)).encode(), {'Content-Type': 'application/json'})
        with self.http.open(req, timeout=5) as response:
            reply = json.load(response)
        if 'error' in reply:
            raise RuntimeError(method + ': ' + str(reply['error'].get('code')))
        return reply['result']

    def focus(self):
        gui = self.rpc('GUI.GetProperties', properties=['currentwindow', 'currentcontrol'])
        labels = self.rpc('XBMC.GetInfoLabels', labels=['Container.Position', 'ListItem.Label', 'System.CurrentControlID'])
        return (gui['currentwindow']['id'], labels['System.CurrentControlID'],
                labels['Container.Position'], labels['ListItem.Label'])

    def measured_move(self, button, timeout=2):
        before = self.focus()
        start = time.monotonic()
        self.button(button)
        while time.monotonic() - start < timeout:
            after = self.focus()
            if after != before:
                return dict(before=before, after=after, observed_ms=round((time.monotonic()-start)*1000))
            time.sleep(.015)
        raise RuntimeError('No observed focus or item change after ' + button)



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--name', default='', help='EventServer device name, including an empty name')
    modes = parser.add_subparsers(dest='action', required=True)
    modes.add_parser('hello', help='Connect for four seconds for a frame comparison')
    for action in ('press', 'measure'):
        modes.add_parser(action).add_argument('button', choices=('left','right','up','down','select','back'))
    args = parser.parse_args()
    with Remote(args.host,args.name) as remote:
        time.sleep(.1)
        if args.action == 'hello':
            time.sleep(4)
        elif args.action == 'measure':
            print(json.dumps(remote.measured_move(args.button), ensure_ascii=False))
        else:
            remote.button(args.button)
            time.sleep(.15)
