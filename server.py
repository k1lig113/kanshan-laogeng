#!/usr/bin/env python3
"""看山老梗 · 本地服务
- 静态托管项目文件
- GET /api/zhida?q=...  实时调用知乎直答（zhihu-cli answer 流式输出），不缓存
- POST /api/quiz         调用独立大模型（OpenAI 兼容接口）为梗出选择题
  环境变量：
    QUIZ_API_BASE  接口地址，默认 https://api.openai.com/v1
    QUIZ_API_KEY   API Key（未配置时 /api/quiz 返回 not_configured，前端自动降级本地题库）
    QUIZ_MODEL     模型名，默认 gpt-4o-mini
启动：python3 server.py  然后访问 http://localhost:8931
"""
import http.server
import socketserver
import subprocess
import urllib.parse
import urllib.request
import json
import os
import re
import shutil
import sqlite3
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------- 匿名用户与全网统计（SQLite） ----------
DATA_DIR = os.path.join(ROOT, 'data')
DB_PATH = os.path.join(DATA_DIR, 'kanshan.db')
_db = None
_db_lock = threading.Lock()


def get_db():
    global _db
    if _db is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.execute('CREATE TABLE IF NOT EXISTS users('
                    'uid TEXT PRIMARY KEY, first_seen INTEGER, last_seen INTEGER)')
        _db.execute('CREATE TABLE IF NOT EXISTS views('
                    'id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, phrase TEXT, ts INTEGER)')
        _db.execute('CREATE INDEX IF NOT EXISTS idx_views_uid ON views(uid, phrase)')
        _db.commit()
    return _db


def global_stats(now):
    db = get_db()
    users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    views = db.execute('SELECT COUNT(*) FROM views').fetchone()[0]
    today = db.execute(
        'SELECT COUNT(DISTINCT uid) FROM users WHERE last_seen >= ?', (now - 86400,)
    ).fetchone()[0]
    return {'users': users, 'views': views, 'today': today}


def read_json(self):
    length = int(self.headers.get('Content-Length') or 0)
    raw = self.rfile.read(length) if length else b''
    return json.loads(raw.decode('utf-8') or '{}')


def resolve_cli():
    """zhihu-cli 可执行文件路径。
    优先级：ZHIHU_CLI 环境变量 > macOS 本地安装路径 > PATH 中的 zhihu / zhihu-cli。
    """
    env = os.environ.get('ZHIHU_CLI', '').strip()
    if env:
        return env
    mac = os.path.expanduser('~/Library/Application Support/zhihu-cli/current/zhihu-cli')
    if os.path.exists(mac):
        return mac
    return shutil.which('zhihu') or shutil.which('zhihu-cli') or 'zhihu-cli'


CLI = resolve_cli()


def load_env_file(path):
    """轻量 .env 加载：KEY=VALUE 每行一个，已存在的环境变量优先。"""
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass


load_env_file(os.path.join(ROOT, '.env'))

HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8931'))
QUIZ_API_BASE = os.environ.get('QUIZ_API_BASE', 'https://api.openai.com/v1').rstrip('/')
QUIZ_API_KEY = os.environ.get('QUIZ_API_KEY', '')
QUIZ_MODEL = os.environ.get('QUIZ_MODEL', 'gpt-4o-mini')


def build_quiz_prompt(phrase, knowledge):
    return (
        '你是「看山出题官」，为知乎老梗出四选一选择题。请基于下面提供的知识，'
        f'出一道关于「{phrase}」的题目。\n'
        '要求：\n'
        '1. 只输出一个 JSON 对象，不要任何多余文字、注释或代码块标记。\n'
        '2. JSON 格式：{"question":"题目","options":["选项A","选项B","选项C","选项D"],"answer":0,"explanation":"30字左右的答案解析"}\n'
        '3. answer 是正确选项的下标（0 到 3）。\n'
        '4. 题目要有意思：可以考来源、含义、用法、衍生梗或冷知识；选项要有迷惑性；'
        '确保只有一个正确答案，且能由给出的知识推出。\n'
        '5. 不要编造知识里没有的内容。\n\n'
        '知识：\n' + knowledge
    )


def call_quiz_llm(payload):
    if not QUIZ_API_KEY:
        return {'error': 'not_configured'}
    body = json.dumps({
        'model': QUIZ_MODEL,
        'messages': [
            {'role': 'system', 'content': '你只输出合法 JSON。'},
            {'role': 'user', 'content': build_quiz_prompt(payload.get('phrase', ''), payload.get('knowledge', ''))}
        ],
        'temperature': 0.8,
        'max_tokens': 800
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        QUIZ_API_BASE + '/chat/completions',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + QUIZ_API_KEY
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    content = data['choices'][0]['message']['content']
    match = re.search(r'\{[\s\S]*\}', content)
    if not match:
        return {'error': 'parse'}
    quiz = json.loads(match.group(0))
    if not isinstance(quiz, dict):
        return {'error': 'parse'}
    question = str(quiz.get('question', '')).strip()
    options = quiz.get('options')
    answer = quiz.get('answer')
    explanation = str(quiz.get('explanation', '')).strip()
    if (
        not question
        or not isinstance(options, list)
        or len(options) != 4
        or not all(isinstance(o, str) and o.strip() for o in options)
        or not isinstance(answer, int)
        or answer < 0
        or answer > 3
    ):
        return {'error': 'invalid'}
    return {
        'question': question,
        'options': [o.strip() for o in options],
        'answer': answer,
        'explanation': explanation
    }


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

    def do_POST(self):
        if self.path.startswith('/api/quiz'):
            self.handle_quiz()
        elif self.path.startswith('/api/user/hello'):
            self.handle_user_hello()
        elif self.path.startswith('/api/user/view'):
            self.handle_user_view()
        else:
            self.send_error(404)

    def handle_user_hello(self):
        try:
            payload = read_json(self)
            uid = str(payload.get('uid') or '').strip()
            if not uid or len(uid) > 128:
                self.send_json({'error': 'bad uid'}, 400)
                return
            now = int(time.time())
            db = get_db()
            with _db_lock:
                row = db.execute('SELECT first_seen FROM users WHERE uid=?', (uid,)).fetchone()
                first = row[0] if row else now
                db.execute(
                    'INSERT INTO users(uid, first_seen, last_seen) VALUES(?,?,?) '
                    'ON CONFLICT(uid) DO UPDATE SET last_seen=excluded.last_seen',
                    (uid, first, now))
                hist = db.execute(
                    'SELECT phrase, MAX(ts) FROM views WHERE uid=? GROUP BY phrase '
                    'ORDER BY MAX(ts) DESC LIMIT 300', (uid,)).fetchall()
                stats = global_stats(now)
                db.commit()
            self.send_json({
                'ok': True,
                'first_visit': row is None,
                'history': [{'phrase': p, 'ts': t} for p, t in hist],
                'stats': stats
            })
        except Exception as exc:
            self.send_json({'error': 'server_error', 'detail': str(exc)}, 500)

    def handle_user_view(self):
        try:
            payload = read_json(self)
            uid = str(payload.get('uid') or '').strip()
            phrase = str(payload.get('phrase') or '').strip()
            if not uid or len(uid) > 128 or not phrase or len(phrase) > 64:
                self.send_json({'error': 'bad params'}, 400)
                return
            now = int(time.time())
            db = get_db()
            with _db_lock:
                db.execute('INSERT INTO views(uid, phrase, ts) VALUES(?,?,?)', (uid, phrase, now))
                db.execute(
                    'INSERT INTO users(uid, first_seen, last_seen) VALUES(?,?,?) '
                    'ON CONFLICT(uid) DO UPDATE SET last_seen=excluded.last_seen',
                    (uid, now, now))
                db.commit()
            self.send_json({'ok': True})
        except Exception as exc:
            self.send_json({'error': 'server_error', 'detail': str(exc)}, 500)

    def handle_quiz(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b''
            payload = json.loads(raw.decode('utf-8') or '{}')
            if not payload.get('phrase'):
                self.send_json({'error': 'missing phrase'}, 400)
                return
            result = call_quiz_llm(payload)
            code = 501 if result.get('error') == 'not_configured' else 200
            self.send_json(result, code)
        except Exception as exc:
            self.send_json({'error': 'server_error', 'detail': str(exc)}, 500)

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

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
    with Server((HOST, PORT), Handler) as s:
        print(f'看山老梗 → http://{HOST}:{PORT}')
        s.serve_forever()
