"""Keep completed recipe results in a local library and rebuild the offline app."""
import json
from pathlib import Path
from illustration_assets import note_template as load_note_template

ROOT = Path(__file__).parent


def signature(recipe):
    model = recipe.get('deepseek') or recipe
    return '|'.join(s.get('text') or s.get('instruction', '') for s in model.get('steps', []))


def add_recipe(recipe):
    path = ROOT / 'recipe-library.json'
    entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    key = signature(recipe)
    if not key:
        return
    previous = next((e for e in entries if e['id'] == key), None)
    entry = {'id': key, 'recipe': recipe, 'cuisine': previous.get('cuisine', '') if previous else '',
             'title': previous.get('title', '') if previous else ''}
    entries = [e for e in entries if e['id'] != key] + [entry]
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    build_app(entries)


def build_app(entries):
    (ROOT / 'index.html').write_text(app_html(entries), encoding='utf-8')


def app_html(entries, cloud=False):
    template = (ROOT / 'app_template.html').read_text(encoding='utf-8')
    template = template.replace('__VISUAL_STYLE__', (ROOT / 'visual_style.css').read_text(encoding='utf-8'))
    template = template.replace('__MASCOT_STYLE__', (ROOT / 'mascot_style.css').read_text(encoding='utf-8') + (ROOT / 'bubble_flow.css').read_text(encoding='utf-8'))
    picture = '<div class="video-hero"><img class="hero-motion-fallback" src="assets/home-hero-poster-v3.jpg" data-motion="assets/home-hero-motion-v2.webp" alt="" aria-hidden="true" fetchpriority="high"><video id="home-video" autoplay muted loop playsinline preload="auto" poster="assets/home-hero-poster-v3.jpg" aria-label="水彩厨房首页动态视频"><source src="assets/home-hero-silent-v3.mp4" type="video/mp4"></video></div>'
    template = template.replace('__MASCOT_HERO__', picture)
    template = template.replace('</body>', '<script>' + (ROOT / 'hero_video.js').read_text(encoding='utf-8') + '</script></body>')
    for marker, filename, description in [('__FRIDGE_SCENE__', 'ingredient-portrait-v5.png', '水彩厨房中挑选食材的小伙伴'), ('__COLLECT_SCENE__', 'recipe-portrait-v4.png', '水彩厨房中记录菜谱的小伙伴')]:
        scene = ''
        asset = ROOT / 'assets' / filename
        if asset.exists():
            import base64
            encoded = base64.b64encode(asset.read_bytes()).decode('ascii')
            scene = f'<img class="inner-scene" alt="{description}" src="data:image/png;base64,{encoded}">'
        template = template.replace(marker, scene)
    note_template = load_note_template()
    # Reuse the same trusted, built-in watercolor icons across home and recipe views.
    icon_template = load_note_template(embed_library_icons=True)
    art = icon_template[icon_template.index('function art(type)'):icon_template.index('function show(data)')]
    payload = json.dumps({'entries': entries, 'note_template': note_template}, ensure_ascii=False)
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return (template.replace('__LIBRARY_DATA__', payload).replace('__ART_FUNCTION__', art)
            .replace('__CLOUD_MODE__', 'true' if cloud else 'false')
            .replace('__CLOUD_CLIENT__', (ROOT / 'cloud_client.js').read_text(encoding='utf-8') if cloud else '')
            .replace('__PWA_HEAD__', '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#faf9f5"><meta name="apple-mobile-web-app-capable" content="yes">' if cloud else ''))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('recipe', type=Path, nargs='?')
    args = parser.parse_args()
    if args.recipe:
        add_recipe(json.loads(args.recipe.read_text(encoding='utf-8-sig')))
    else:
        path = ROOT / 'recipe-library.json'
        build_app(json.loads(path.read_text(encoding='utf-8')) if path.exists() else [])
    print(ROOT / 'index.html')
