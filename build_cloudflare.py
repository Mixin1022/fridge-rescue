"""Build a public-safe Pages upload ZIP; never include local recipes or secrets."""
import json
from pathlib import Path
import zipfile
from build_library import app_html

ROOT = Path(__file__).parent


def build():
    folder = ROOT / 'cloudflare-pages'
    folder.mkdir(exist_ok=True)
    html = app_html([], cloud=True)
    html = html.replace('</head>', '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#faf9f5"><meta name="apple-mobile-web-app-capable" content="yes"></head>', 1)
    html = html.replace('</body>', '<script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});</script></body>', 1)
    html = html.replace('待电脑程序识别，完成后导入菜谱 JSON。', '已收藏链接；此网页尚未接入视频识别后台。')
    html = html.replace('已记入待处理灵感。请在电脑端 start_recipe.cmd 中粘贴链接，识别后导入 recipe.json。', '已收藏链接。视频识别后台尚未接入；可以先导入已有食谱 JSON。')
    files = {
        'index.html': html,
        'manifest.webmanifest': json.dumps({'name': 'Fridge Rescue · 料理小本', 'short_name': '料理小本', 'start_url': '/', 'display': 'standalone', 'background_color': '#faf9f5', 'theme_color': '#faf9f5', 'icons': [{'src': '/app-icon.svg', 'sizes': 'any', 'type': 'image/svg+xml'}]}, ensure_ascii=False),
        'sw.js': (ROOT / 'pwa/sw.js').read_text(encoding='utf-8').replace('fridge-shell-v1', 'fridge-pages-autoconnect-v38'),
        'app-icon.svg': (ROOT / 'pwa/app-icon.svg').read_text(encoding='utf-8'),
        '_headers': '/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n/sw.js\n  Cache-Control: no-cache\n',
    }
    for name, content in files.items():
        (folder / name).write_text(content, encoding='utf-8')
    media = ['assets/home-hero-motion-v2.webp', 'assets/home-hero-silent-v3.mp4', 'assets/home-hero-poster-v3.jpg']
    import shutil
    for name in media:
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    archive = ROOT / 'fridge-rescue-cloudflare.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in list(files) + media:
            bundle.write(folder / name, name)
    return archive


if __name__ == '__main__':
    print(build())
