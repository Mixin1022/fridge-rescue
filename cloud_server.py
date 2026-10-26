"""Single-owner cloud service. Run one instance behind an HTTPS reverse proxy."""
import hmac
import json
import os
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from build_library import app_html
from cloud_store import Store
from cloud_worker import start_worker

ROOT = Path(__file__).parent
MAX_VIDEO = 250 * 1024 * 1024


def make_server(address, store, token):
    if len(token) < 24 or token.startswith('replace-with-'):
        raise ValueError('FRIDGE_ACCESS_TOKEN 至少需要 24 个字符')
    allowed_origins = {x.strip() for x in os.getenv('FRIDGE_ALLOWED_ORIGINS', '').split(',') if x.strip()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Never log credentials, submitted share URLs, or private file names.

        def send(self, code, body, mime='application/json; charset=utf-8'):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            elif isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', mime)
            origin = self.headers.get('Origin', '')
            if origin in allowed_origins:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            if self.headers.get('Origin', '') not in allowed_origins:
                self.send(403, {'error': '来源未允许'})
                return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Fridge-Token')
            self.send_header('Vary', 'Origin')
            self.end_headers()

        def auth(self):
            if not hmac.compare_digest(self.headers.get('X-Fridge-Token', '').encode('utf-8'), token.encode('utf-8')):
                self.send(401, {'error': '请连接你自己的菜谱服务，访问口令不正确'})
                return False
            return True

        def length(self, maximum):
            try:
                length = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                length = -1
            if length < 0 or self.headers.get('Transfer-Encoding'):
                raise ValueError('请求需要明确的 Content-Length')
            if length > maximum:
                raise OverflowError('文件或请求过大')
            return length

        def read_json(self):
            length = self.length(30 * 1024 * 1024)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求必须是 JSON 对象')
            return data

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                self.send(200, app_html([], cloud=True), 'text/html; charset=utf-8')
            elif path == '/api/health':
                self.send(200, {'status': 'ok', 'mode': 'single-owner-cloud','pipeline':'recipe-pipeline-v2','art_layout':'tiles-v1'})
            elif path == '/manifest.webmanifest':
                self.send(200, {'name': 'Fridge Rescue · 料理便签', 'short_name': '料理便签', 'start_url': '/',
                    'scope': '/', 'display': 'standalone', 'background_color': '#faf9f5', 'theme_color': '#faf9f5',
                    'icons': [{'src': '/app-icon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}]}, 'application/manifest+json')
            elif path in ('/assets/home-hero-silent-v2.mp4', '/assets/home-hero-poster-v2.jpg', '/assets/home-hero-silent-v3.mp4', '/assets/home-hero-poster-v3.jpg', '/assets/home-hero-motion-v1.webp', '/assets/home-hero-motion-v2.webp'):
                file = Path(__file__).parent / path.lstrip('/')
                self.send(200, file.read_bytes(), 'video/mp4' if path.endswith('.mp4') else 'image/webp' if path.endswith('.webp') else 'image/jpeg')
            elif path in ('/sw.js', '/app-icon.svg'):
                file = ROOT / 'pwa' / path[1:]
                self.send(200, file.read_bytes(), 'application/javascript; charset=utf-8' if path.endswith('.js') else 'image/svg+xml')
            elif path.startswith('/api/'):
                if not self.auth():
                    return
                if path == '/api/recipes':
                    self.send(200, store.recipes())
                elif path == '/api/jobs':
                    self.send(200, store.jobs())
                elif path == '/api/feedback':
                    self.send(200, store.feedback(include_snapshots=False))
                else:
                    self.send(404, {'error': '找不到接口'})
            else:
                self.send(404, {'error': '找不到页面'})

        def do_POST(self):
            path = urlsplit(self.path).path
            if not self.auth():
                return
            self.connection.settimeout(120)
            try:
                if path == '/api/jobs/video':
                    length = self.length(MAX_VIDEO)
                    if length < 12:
                        raise ValueError('视频文件为空或无效')
                    folder = store.folder / 'uploads'
                    folder.mkdir(exist_ok=True)
                    video = folder / (uuid.uuid4().hex + '.mp4')
                    try:
                        with video.open('wb') as stream:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise ValueError('上传被中断，请重试')
                                stream.write(chunk)
                                remaining -= len(chunk)
                        with video.open('rb') as stream:
                            if stream.read(12)[4:8] != b'ftyp':
                                raise ValueError('请上传 MP4/MOV 视频，或将视频导出为 MP4')
                        job = store.create_job('video', str(video))
                    except Exception:
                        video.unlink(missing_ok=True)
                        raise
                    self.send(202, {'id': job, 'state': 'queued'})
                elif path == '/api/jobs/post':
                    from post_recipe import validate_post
                    data = validate_post(self.read_json())
                    folder = store.folder / 'uploads'
                    folder.mkdir(exist_ok=True)
                    source = folder / (uuid.uuid4().hex + '.json')
                    source.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                    self.send(202, {'id': store.create_job('post', str(source)), 'state': 'queued'})
                elif path == '/api/jobs/link':
                    from link_recipe import extract_url, validate_url
                    data = self.read_json()
                    share = data.get('share')
                    if not isinstance(share, str) or len(share) > 8000:
                        raise ValueError('分享文字格式不正确')
                    url = extract_url(share)
                    if not url:
                        raise ValueError('没有找到有效的小红书 HTTPS 链接')
                    validate_url(url)
                    self.send(202, {'id': store.create_job('link', url), 'state': 'queued'})
                elif path == '/api/recipes':
                    self.send(201, store.save_recipe(self.read_json()))
                elif path == '/api/feedback':
                    data = self.read_json()
                    self.send(201, store.report_recipe(data.get('recipe_id'), data.get('reason')))
                elif re.fullmatch(r'/api/jobs/[a-f0-9]{32}/retry',path):
                    self.read_json()
                    self.send(202,store.retry_job(path.split('/')[3]))
                else:
                    self.send(404, {'error': '找不到接口'})
            except OverflowError:
                self.send(413, {'error': '文件过大，视频上限 250MB；菜谱 JSON 上限 2MB'})
            except (ValueError, TypeError, UnicodeError):
                self.send(400, {'error': '提交内容无效、队列已满或上传中断，请检查后重试'})
            except OSError:
                self.send(503, {'error': '服务端存储或上传暂时不可用'})

        def do_PATCH(self):
            if not self.auth():
                return
            match = re.fullmatch(r'/api/recipes/([a-f0-9]{24})', urlsplit(self.path).path)
            if not match:
                self.send(404, {'error': '找不到菜谱'})
                return
            try:
                self.send(200, store.update_recipe(match[1], self.read_json()))
            except KeyError:
                self.send(404, {'error': '找不到菜谱'})
            except (ValueError, TypeError, OverflowError):
                self.send(400, {'error': '菜名、菜系或核对状态不正确'})
    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    token = os.environ.get('FRIDGE_ACCESS_TOKEN', '')
    store = Store(os.environ.get('FRIDGE_DATA_DIR', str(ROOT / 'work' / 'cloud-data')))
    server = make_server((os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8080'))), store, token)
    stop, worker = start_worker(store)
    print('Fridge Rescue 服务已启动；正式部署请使用 HTTPS，并保留数据卷。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
