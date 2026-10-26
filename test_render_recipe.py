import json
import re
import tempfile
import unittest
from pathlib import Path
from render_recipe import render_recipe


class RenderTests(unittest.TestCase):
    def render(self, data):
        work = Path(__file__).parent / 'work'
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as folder:
            path = Path(folder) / 'recipe.html'
            render_recipe(data, path)
            return path.read_text(encoding='utf-8')

    def test_recipe_payload_roundtrip_and_script_escape(self):
        data = {'ingredients': [{'text': '番茄</script><script>alert(1)</script>'}], 'steps': []}
        html = self.render(data)
        payload = re.search(r'<script(?=[^>]*type="application/json")(?=[^>]*id="recipe-data")[^>]*>(.*?)</script>', html, re.S).group(1)
        rendered = json.loads(payload)
        self.assertEqual(rendered['ingredients'], data['ingredients'])
        self.assertEqual(rendered['steps'], data['steps'])
        self.assertNotIn('<script>', payload)

    def test_self_contained_assets(self):
        html = self.render({'steps': []})
        self.assertNotRegex(html, r'(?:src|href)=["\']https?://')
        self.assertNotIn('fetch(', html)
        self.assertNotIn('XMLHttpRequest', html)
        self.assertNotIn('__RECIPE_DATA__', html)

    def test_ai_and_original_evidence_preserved(self):
        data = {'steps': [], 'evidence': [{'text': '熟透的番茄'}],
                'deepseek': {'steps': [{'text': '切成小块', 'evidence_ids': [0]}]}}
        html = self.render(data)
        self.assertIn('熟透的番茄', html)
        self.assertIn('切成小块', html)

    def test_unfolded_route_and_local_illustrations(self):
        html = self.render({'steps': []})
        self.assertIn('illustrated-map', html)
        self.assertIn("data?.analysis_status!=='deepseek'", html)
        self.assertTrue('翻开 ↘' not in html)
        self.assertNotIn('feTurbulence', html)
        self.assertNotIn('radial-gradient', html)
        self.assertNotIn("node('button'", html)

    def test_illustrated_map_has_captions_and_no_extra_controls(self):
        html = self.render({'title': '抹茶珍珠奶茶', 'recipe_art': 'data:image/png;base64,AAAA',
            'ingredients': [{'text': '抹茶粉'}], 'steps': [{'instruction': '加入牛奶'}],
            'art_layout': {'ingredients': [{'x': .2, 'y': .3}], 'steps': [{'x': .5, 'y': .7}]}})
        self.assertIn('抹茶粉', html)
        self.assertIn('加入牛奶', html)
        self.assertNotIn('<button', html)
        self.assertNotIn('<details', html)
