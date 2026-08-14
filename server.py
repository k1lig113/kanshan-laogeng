#!/usr/bin/env python3
"""看山老梗 · 本地服务
- 静态托管项目文件
- GET /api/zhida?q=...  实时调用知乎直答（zhihu-cli answer 流式输出），不缓存
启动：python3 server.py  然后访问 http://localhost:8931
"""
import http.server
import socketserver
import subprocess
import urllib.parse
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.expanduser('~/Library/Application Support/zhihu-cli/current/zhihu-cli')
PORT = int(os.environ.get('PORT', '8931'))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith('/api/zhida'):
            self.handle_zhida()
        else:
            super().do_GET()

    def handle_zhida(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        q = (qs.get('q') or [''])[0].strip()
        if not q:
            self.send_error(400, 'missing q')
            return
        try:
            proc = subprocess.Popen(
                [CLI, 'answer', '--query', q, '--stream', '--output', 'text',
                 '--timeout', '90s'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            self.send_error(502, 'zhihu-cli unavailable')
            return
        try:
            # 先窥视首段输出：直答正文不会以 { 开头，以 { 开头的视为错误 JSON
            first = b''
            while not first.strip():
                first = proc.stdout.read1(1024)
                if not first:
                    break
            head = first.decode('utf-8', 'replace').strip()
            if head.startswith('{'):
                rest = proc.stdout.read1(8192).decode('utf-8', 'replace')
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                msg = 'zhida error'
                try:
                    msg = json.loads(head + rest).get('error', {}).get('message') or msg
                except Exception:
                    pass
                body = json.dumps({'error': msg}, ensure_ascii=False).encode('utf-8')
                self.send_response(502)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if first:
                self.wfile.write(first)
                self.wfile.flush()
            while True:
                chunk = proc.stdout.read1(2048)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            proc.kill()
        finally:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    with Server(('127.0.0.1', PORT), Handler) as s:
        print(f'看山老梗 → http://localhost:{PORT}')
        s.serve_forever()
