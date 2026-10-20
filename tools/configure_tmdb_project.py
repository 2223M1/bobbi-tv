"""One-use loopback form to import a project APPLICATION key without logging it.

The browser owner explicitly requested application-key provisioning. No login
password, account session or user access token belongs in this resource.
"""
import json
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import time
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / 'addons/script.module.bobbi.core/resources/tmdb-project.json'
    if path.exists():
        raise SystemExit('Existing project configuration retained; explicit replacement required')
    route = '/' + secrets.token_hex(24)
    completed = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, status, body):
            raw = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path != route:
                return self.reply(404, 'Not found')
            self.reply(200, '<title>波比 TV 本机应用配置</title><h1>TMDb 项目应用 Key 导入</h1>'
                '<p>仅写入本机候选构建；不保存 TMDb 密码或登录会话。</p>'
                '<form method="post" autocomplete="off"><label>应用 API Key'
                '<input name="key" type="password" autocomplete="off" required></label>'
                '<button type="submit">导入本机候选</button></form>')
        def do_POST(self):
            if self.path != route or completed:
                return self.reply(404, 'Not found')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 512:
                return self.reply(400, 'Invalid input')
            fields = parse_qs(self.rfile.read(size).decode('ascii'))
            key = fields.get('key', [''])[0]
            if set(fields) != {'key'} or len(fields['key']) != 1 or not re.fullmatch('[a-f0-9]{32}', key):
                return self.reply(400, 'Invalid application key')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as output:
                json.dump(dict(schema=1, application='Bobbi TV', api_key=key,
                    use='personal-noncommercial', attribution=(
                    'This application uses TMDB and the TMDB APIs but is not endorsed, '
                    'certified, or otherwise approved by TMDB.')), output, indent=2)
            completed.append(True)
            self.reply(200, '<title>配置已导入</title><p>应用配置已导入；本机接收窗口已关闭。</p>')
    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = 1
        print('http://127.0.0.1:{}{}'.format(server.server_port, route), flush=True)
        deadline = time.monotonic()+600
        while not completed and time.monotonic() < deadline:
            server.handle_request()
    if not completed:
        raise SystemExit('No application configuration imported')
    print('TMDb project application configuration imported; no login/session copied')


if __name__ == '__main__':
    main()
