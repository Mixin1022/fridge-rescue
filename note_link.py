"""Read a single Xiaohongshu note using a dedicated persistent browser."""
import base64
from urllib.parse import urlparse
from link_recipe import validate_url


def normalize_image_url(url):
    """Only upgrade known platform hosts; never relax arbitrary-origin checks."""
    from urllib.parse import urlsplit, urlunsplit
    parsed=urlsplit(url)
    host=parsed.hostname or ''
    allowed=('xhscdn.com','xhscdn.net','xiaohongshu.com')
    if (parsed.scheme not in ('http','https') or parsed.username or parsed.password
            or parsed.port not in (None,80 if parsed.scheme=='http' else 443)
            or not any(host==s or host.endswith('.'+s) for s in allowed)):
        raise ValueError('图片来源不在允许的平台域名内（协议：'+parsed.scheme+'；域名：'+host+'）')
    return urlunsplit(('https',host,parsed.path,parsed.query,''))

def navigate_note(page, url):
    """Wait for navigation commit, then for actual note data separately."""
    from playwright.sync_api import TimeoutError as BrowserTimeout
    try:
        page.goto(url, wait_until='commit', timeout=60000)
    except BrowserTimeout:
        # A committed target can still be usable even if navigation timed out.
        try:
            validate_url(page.url)
            ready = page.evaluate('() => Object.values(window.__INITIAL_STATE__?.note?.noteDetailMap || {}).some(x=>x.note?.type)')
        except Exception:
            ready = False
        if not ready:
            raise ValueError('小红书页面连接超时（60秒），尚未取得帖子。请在专用登录浏览器中打开同一链接，检查能否访问或是否要求验证。') from None
    validate_url(page.url)

def acquire_douyin(url, profile):
    validate_url(url)
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(Path(profile).resolve()), headless=True)
        try:
            page = context.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            validate_url(page.url)
            page.wait_for_timeout(3000)
            return {'kind':'video', 'platform':'douyin', 'url':page.url, 'cookies':context.cookies()}
        finally:
            context.close()

def parse_note(note):
    if not isinstance(note,dict): raise ValueError('帖子数据不可用')
    kind=note.get('type')
    if kind=='video': return {'kind':'video','media_urls':video_urls(note),'post_text':'\n'.join(x for x in [note.get('title',''),note.get('desc','')] if isinstance(x,str) and x)}
    if kind not in ('normal','image'): raise ValueError('未识别帖子类型，可能需要登录')
    images=[]
    for item in note.get('imageList',[]):
        url=item.get('urlDefault') or item.get('urlPre')
        if url and url not in images: images.append(url)
    if len(images)>12: raise ValueError('帖子图片超过12张，请分批处理')
    text='\n'.join(x for x in [note.get('title',''),note.get('desc','')] if isinstance(x,str) and x)
    if not text and not images: raise ValueError('帖子正文与图片为空')
    return {'kind':'post','text':text,'urls':images}

def video_urls(note):
    urls=[]
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('masterUrl','backupUrls','url','videoUrl'):
                    for url in item if isinstance(item,list) else [item]:
                        if isinstance(url,str) and url.startswith(('https://','http://')):
                            # Platform state may advertise HTTP; use the same path over TLS.
                            url='https://'+url[len('http://'):] if url.startswith('http://') else url
                            if url not in urls: urls.append(url)
                elif isinstance(item,(dict,list)):
                    walk(item)
        elif isinstance(value,list):
            for item in value: walk(item)
    walk(note.get('video',{}))
    return urls[:8]

def acquire_note(url,profile):
    validate_url(url)
    from playwright.sync_api import sync_playwright
    from pathlib import Path
    Path(profile).mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(str(Path(profile).resolve()),headless=True)
        try:
            page=context.new_page()
            observed=[]
            def record_response(response):
                from browser_media_download import validate_media_url
                try:
                    if 'video/mp4' in response.headers.get('content-type',''):
                        validate_media_url(response.url)
                        if response.url not in observed: observed.append(response.url)
                except Exception: pass
            page.on('response',record_response)
            navigate_note(page, url)
            try: page.wait_for_function('() => Object.values(window.__INITIAL_STATE__?.note?.noteDetailMap || {}).some(x=>x.note?.type)',timeout=60000)
            except Exception: raise ValueError('页面已打开，但60秒内没有取得帖子数据。可能出现登录或验证页面，也可能页面结构已改变；请在专用登录浏览器检查同一链接。') from None
            note=page.evaluate('() => {const map=window.__INITIAL_STATE__?.note?.noteDetailMap || {}; const id=location.pathname.split("/").filter(Boolean).pop(); return map[id]?.note || (Object.keys(map).length===1?Object.values(map)[0]?.note:null)}')
            parsed=parse_note(note)
            if parsed['kind']=='video':
                page.locator('video').evaluate_all('(els)=>els.forEach(v=>{v.muted=true;v.play().catch(()=>{})})')
                page.wait_for_timeout(1500)
                current=page.locator('video').evaluate_all('(els)=>els.map(v=>v.currentSrc||v.src).filter(u=>u.startsWith("https://"))')
                parsed['media_urls']=list(dict.fromkeys(observed+current+parsed.get('media_urls',[])))[:8]
                parsed['media_diagnostic']={'state_urls':len(video_urls(note)), 'observed_mp4_responses':len(observed),'player_urls':len(current),'total_candidates':len(parsed['media_urls'])}
                parsed['cookies'] = context.cookies()
                parsed['url'] = page.url
                return parsed
            images=[]
            for image_url in parsed['urls']:
                image_url=normalize_image_url(image_url)
                response=context.request.get(image_url,timeout=20000,max_redirects=0)
                if not response.ok: raise ValueError('帖子图片读取失败')
                raw=response.body()
                if len(raw)>8*1024*1024: raise ValueError('单张图片超过8MB')
                images.append(base64.b64encode(raw).decode('ascii'))
            from post_recipe import validate_post
            return {'kind':'post','post':validate_post({'text':parsed['text'],'images':images})}
        finally: context.close()
