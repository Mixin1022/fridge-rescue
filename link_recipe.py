"""Experimental link-to-recipe text importer. No AI API calls."""
import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler


def extract_url(share):
    match = re.search(r'https://[^\s<>]+', share)
    if not match:
        raise ValueError('Share text contains no HTTPS URL')
    url = match.group().rstrip('。，,.')
    validate_url(url)
    return url


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'xhslink.cn', 'xhslink.com', 'www.xiaohongshu.com', 'xiaohongshu.com', 'v.douyin.com', 'www.douyin.com', 'douyin.com', 'www.iesdouyin.com', 'iesdouyin.com'} or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError('Only HTTPS Xiaohongshu or Douyin share/video URLs are accepted')


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            fields = dict(attrs)
            self.values[fields.get('property', fields.get('name', ''))] = fields.get('content', '')


def recipe_from_text(url, title, text, acquisition):
    ingredients = []
    if '食材：' in text:
        block = text.split('食材：', 1)[1].split('#', 1)[0]
        ingredients = [line.strip() for line in block.splitlines() if line.strip()]
    return {'source_url': url, 'title': title, 'acquisition': acquisition,
            'ingredients_source_lines': ingredients, 'source_text': text,
            'steps': [], 'cooking_time_minutes': None,
            'status': 'partial_recipe' if ingredients else 'needs_source_text',
            'missing': ['Video steps have not been transcribed', 'Cooking time is not verified'],
            'note': 'Source text only. No video recognition or inferred quantities/steps.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('share', nargs='?', help='URL or full copied share text')
    parser.add_argument('--source-text', type=Path, help='Browser-copied note text fallback')
    parser.add_argument('--title', default='')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        url = extract_url(args.share or input('Paste Xiaohongshu share text: '))
        if args.output.exists():
            raise ValueError('Output already exists; use a new filename')
        if args.source_text:
            title, text, acquisition = args.title, args.source_text.read_text(encoding='utf-8'), 'browser_text_fallback'
        else:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with build_opener(SafeRedirect()).open(request, timeout=20) as response:
                page = response.read(2_000_001)
                if len(page) > 2_000_000:
                    raise ValueError('Page exceeds size limit')
            meta = MetaParser()
            meta.feed(page.decode('utf-8', errors='replace'))
            title = meta.values.get('og:title', args.title)
            text = meta.values.get('og:description', meta.values.get('description', ''))
            if not text or '食材：' not in text:
                raise ValueError('Page metadata has no ingredient list; copy the note text and use --source-text. Login or browser rendering may be required.')
            acquisition = 'public_page_metadata'
        result = recipe_from_text(url, title, text, acquisition)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': result['status'], 'ingredient_lines': len(result['ingredients_source_lines']), 'output': str(args.output)}, ensure_ascii=False))
    except Exception as error:
        parser.exit(1, f'Import failed: {error}\n')


if __name__ == '__main__':
    main()
