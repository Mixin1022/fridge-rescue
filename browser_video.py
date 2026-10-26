"""Dedicated persistent browser for user-assisted Xiaohongshu login."""
import http.cookiejar
import time
import json
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

from link_recipe import validate_url


def inspect_page(page):
    """An overlay or absent content triggers visible recovery, not proof of login."""
    videos = page.locator('video')
    video = videos.count() > 0
    ready = False
    if video:
        ready = videos.evaluate_all('(els) => els.some(v => v.readyState >= 1 && v.videoWidth > 0 && !v.error)')
    login = page.get_by_text('手机号登录', exact=True)
    blocked = any(login.nth(i).is_visible() for i in range(login.count()))
    # The player can exist without the old title/description IDs, especially on /discovery/item/.
    note_path = urlparse(page.url).path
    is_note = any(note_path.startswith(prefix) and len(note_path) > len(prefix)
                  for prefix in ('/explore/', '/discovery/item/'))
    return {'content': bool(is_note and ready), 'login_overlay': blocked}


def save_diagnostics(page):
    folder = Path(__file__).parent / 'work' / 'browser-diagnostics' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(folder / 'page.png'))
        location = urlparse(page.url)
        data = {'page': location.scheme + '://' + location.netloc + location.path,
                'title': page.title(), 'state': inspect_page(page),
                'videos': page.locator('video').evaluate_all('(els) => els.map(v => ({readyState:v.readyState,width:v.videoWidth,height:v.videoHeight,error:v.error?.code || null}))')}
        (folder / 'diagnostics.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'页面诊断已保存：{folder}（截图可能包含个人信息，仅保存在本机）', flush=True)
    except Exception:
        print('未能保存页面诊断。', flush=True)


def cookie_jar(cookies, platform='xiaohongshu'):
    jar = http.cookiejar.CookieJar()
    for c in cookies:
        domain = c['domain']
        host = domain.lstrip('.')
        suffix = 'douyin.com' if platform == 'douyin' else 'xiaohongshu.com'
        if host != suffix and not host.endswith('.' + suffix):
            continue
        expiry = c.get('expires', -1)
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=c['name'], value=c['value'], port=None, port_specified=False,
            domain=domain, domain_specified=True, domain_initial_dot=domain.startswith('.'),
            path=c.get('path', '/'), path_specified=True, secure=c.get('secure', True),
            expires=int(expiry) if expiry > 0 else None, discard=expiry <= 0,
            comment=None, comment_url=None, rest={'HttpOnly': c.get('httpOnly', False)}, rfc2109=False))
    return jar


def wait_for_content(context, page, url, timeout):
    deadline = time.monotonic() + timeout
    last_report = -float('inf')
    retried_note = False
    saw_login = False
    started = time.monotonic()
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError('浏览器页面已关闭，请重新运行。')
        # Login may open another tab or navigate the original tab to the home feed.
        pages = [p for p in context.pages if not p.is_closed()]
        for candidate in reversed(pages):
            state = inspect_page(candidate)
            if state['content'] and not state['login_overlay']:
                print('已检测到视频笔记，继续获取视频……', flush=True)
                return candidate
        state = inspect_page(page)
        saw_login = saw_login or state['login_overlay']
        elapsed = time.monotonic() - started
        if not state['login_overlay'] and not retried_note and (saw_login or elapsed >= 10):
            print('登录提示已消失或页面未回到笔记，正在重新打开原链接……', flush=True)
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            retried_note = True
            continue
        if time.monotonic() - last_report >= 5:
            remaining = max(0, int(deadline - time.monotonic()))
            detail = '等待完成登录' if state['login_overlay'] else '等待视频笔记加载'
            print(f'{detail}，剩余约 {remaining} 秒。', flush=True)
            last_report = time.monotonic()
        page.wait_for_timeout(1000)
    save_diagnostics(page)
    raise TimeoutError('等待超时：未发现已加载的视频播放器。诊断目录包含当时的网页截图，请查看是否为目标笔记、验证页或错误页。')


def launch_browser(chromium, profile, visible):
    failures = []
    # Each channel uses its own profile; never touch the user's everyday profile.
    for channel in ('msedge', 'chrome', None):
        folder = Path(profile) / (channel or 'chromium')
        folder.mkdir(parents=True, exist_ok=True)
        try:
            options = {'headless': not visible}
            if channel:
                options['channel'] = channel
            context = chromium.launch_persistent_context(str(folder.resolve()), **options)
            print(f'浏览器已启动：{channel or "Chromium"}')
            return context
        except Exception as error:
            failures.append(f'{channel or "Chromium"}: {type(error).__name__}')
    raise RuntimeError('Edge、Chrome 和 Chromium 均无法启动（' + '; '.join(failures) + '）。请从普通 Windows 终端启动 start_recipe.cmd；若仍失败，请检查系统安全软件或运行环境限制。')


def fetch_with_browser(url, root, profile, allow_login=True, timeout=180):
    """Try headless, relaunch visibly for login, then use that context's cookies."""
    validate_url(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError('缺少 Playwright；安装依赖后运行 python -m playwright install chromium') from error
    from video_recipe import download_video
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        for visible in (False, True):
            if visible and not allow_login:
                break
            context = launch_browser(playwright.chromium, profile, visible)
            try:
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                if visible:
                    page.wait_for_timeout(2000)
                    print('已显示专用浏览器。请在该窗口登录或扫码；程序会自动检查并继续。Ctrl+C 可取消。')
                    page = wait_for_content(context, page, url, timeout)
                else:
                    page.wait_for_timeout(2000)
                    state = inspect_page(page)
                    if not state['content'] or state['login_overlay']:
                        continue
                # Downloader extracts the actual stream; blob URLs are not download URLs.
                current = page.url
                validate_url(current)
                try:
                    print('开始解析并下载视频；网络请求可能需要一些时间……', flush=True)
                    return download_video(current, root, cookies=cookie_jar(context.cookies()))
                except Exception:
                    if visible or not allow_login:
                        raise RuntimeError('浏览器内容可访问，但仍未能下载视频；请使用本地 MP4。')
                    print('后台下载未成功，尝试显示浏览器以便登录或检查页面。')
            finally:
                context.close()
    raise RuntimeError('后台未取得视频；使用交互模式允许显示登录窗口，或指定本地 MP4。')
