import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from cloud_store import Store
from codex_recipe_art import attach, generate


class DrawingBridgeTests(unittest.TestCase):
    def test_timeout_preserves_images_and_resumes_verified_batches(self):
        import json
        from subprocess import CompletedProcess, TimeoutExpired
        recipe={'ingredients':[{'name':str(i)} for i in range(4)],'steps':[]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as temp:
            folder=Path(temp)/'art-task';calls=[]
            def run(command,**kwargs):
                if command[1:3]==['login','status']:return CompletedProcess([],0,'Logged in using ChatGPT','')
                cells=json.loads((folder/'active-art-batch.json').read_text())['cells'];calls.append([c['file'] for c in cells])
                self.assertEqual(kwargs['timeout'],900)
                if len(calls)==2:raise TimeoutExpired(command,900)
                for cell in cells:Image.new('RGB',(100,100),'white').save(folder/cell['file'])
                (folder/'art-review.json').write_text('{"rejected":false,"issues":[]}',encoding='utf-8')
                return CompletedProcess([],0)
            with patch('codex_recipe_art.executable',return_value='codex'),patch('codex_recipe_art.subprocess.run',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'超时'):generate(recipe,temp)
                self.assertTrue((folder/'cell-000.png').exists())
                generate(recipe,temp)
            self.assertEqual(calls,[['cell-000.png','cell-001.png','cell-002.png'],['cell-003.png'],['cell-003.png']])

    def test_redraws_failed_cell_then_contains_whole_image(self):
        import json
        from subprocess import CompletedProcess
        recipe={'ingredients':[{'name':'牛奶'}],'steps':[{'text':'倒入牛奶'}]}
        attempts=[]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as temp:
            folder=Path(temp)/'art-task'
            def run(command, **kwargs):
                if command[1:3]==['login','status']:return CompletedProcess([],0,'Logged in using ChatGPT','')
                attempts.append(kwargs['input'])
                if len(attempts)==1:
                    Image.new('RGB',(200,100),'red').save(folder/'cell-000.png')
                Image.new('RGB',(100,200),'blue').save(folder/'cell-001.png')
                issues=[{'field':'steps','index':0,'text':'动作不符'}] if len(attempts)==1 else []
                (folder/'art-review.json').write_text(json.dumps({'rejected':False,'issues':issues}),encoding='utf-8-sig')
                return CompletedProcess([],0)
            with patch('codex_recipe_art.executable',return_value='codex'),patch('codex_recipe_art.subprocess.run',side_effect=run):
                generate(recipe,temp)
            self.assertEqual(len(attempts),2)
            self.assertIn('ONLY cells in active-art-batch.json',attempts[1])
            self.assertEqual(recipe['art_masks'],[])
            with Image.open(folder/'recipe-art.png') as pic:
                self.assertEqual(pic.getpixel((24,192)),(255,0,0))
                self.assertEqual(pic.getpixel((359,192)),(255,0,0))
                self.assertEqual(pic.getpixel((0,192)),(252,250,246))

    def test_windows_bom_review_and_layout(self):
        import json
        from subprocess import CompletedProcess
        from codex_recipe_art import layout_for
        recipe = {'ingredients': [], 'steps': [{'instruction': '切半'}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as temp:
            def run(command, **kwargs):
                if command[1:3] == ['login', 'status']:
                    return CompletedProcess([], 0, 'Logged in using ChatGPT', '')
                folder = Path(temp) / 'art-task'
                Image.new('RGB', (120, 120), 'white').save(folder / 'cell-000.png')
                (folder / 'art-review.json').write_text(json.dumps({'rejected': False, 'issues': [{'field': 'steps', 'index': 0, 'text': '中心面团未切半'}]}), encoding='utf-8-sig')
                return CompletedProcess([], 0)
            with patch('codex_recipe_art.executable', return_value='codex'), patch('codex_recipe_art.subprocess.run', side_effect=run):
                self.assertTrue(generate(recipe, temp).startswith('data:image/png;base64,'))
            self.assertTrue(recipe['art_masks'])
            self.assertTrue((Path(temp)/'art-task'/'art-review-batch-1-round-3.json').exists())
            layout = Path(temp) / 'art-task' / 'art-layout.json'
            layout.write_text(layout.read_text(encoding='utf-8'), encoding='utf-8-sig')
            self.assertEqual(layout_for(recipe, temp)['mode'], 'tiles-v1')

    def test_image_survives_save_and_restart(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as temp:
            stream = io.BytesIO()
            Image.new('RGB', (4, 4), 'white').save(stream, format='PNG')
            art = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()
            recipe = {'steps': [{'instruction': '加入牛奶'}], 'recipe_art': art, 'art_status': 'completed'}
            Store(temp).save_recipe({'recipe': recipe})
            self.assertEqual(Store(temp).recipes()[0]['recipe']['recipe_art'], art)

    def test_invalid_image_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as temp:
            with self.assertRaises(ValueError):
                Store(temp).save_recipe({'recipe': {'steps': [{'instruction': '搅拌'}], 'recipe_art': 'data:image/png;base64,bad'}})

    def test_drawing_failure_preserves_recipe(self):
        recipe = {'steps': [{'instruction': '加入珍珠'}]}
        with patch.dict('os.environ', {'FRIDGE_CODEX_ART': '1'}), patch('codex_recipe_art.generate', side_effect=RuntimeError('额度不足')):
            attach(recipe, Path('.'))
        self.assertEqual(recipe['art_status'], 'failed')
        self.assertEqual(recipe['steps'][0]['instruction'], '加入珍珠')

    def test_no_image_is_not_success(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as temp, patch('codex_recipe_art.executable', return_value='codex'), patch('codex_recipe_art.subprocess.run', side_effect=[CompletedProcess([], 0, 'Logged in using ChatGPT', ''), CompletedProcess([], 0)]):
            with self.assertRaises(RuntimeError):
                generate({'steps': [{'instruction': '搅拌'}]}, temp)


if __name__ == '__main__':
    unittest.main()
