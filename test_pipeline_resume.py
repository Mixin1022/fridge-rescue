import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from cloud_store import Store
from cloud_worker import process_job
from recipe_art_layout import layout_for_plan

class ResumeIntegrationTests(unittest.TestCase):
    def test_art_retry_does_not_redo_source_recognition_or_ai_text(self):
        self.exercise({'passed':True,'issues':[]})

    def test_art_retry_keeps_a_marked_draft_without_repeating_failed_review(self):
        self.exercise({'passed':False,'review_error':'TimeoutError','issues':[{'text':'步骤遗漏需核对','severity':'blocking','evidence_ids':[1]}]})

    def exercise(self,review_result):
        from make_test_video import generate
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            folder=Path(tmp);store=Store(folder)
            video=generate(folder/'test.mp4');identifier=store.create_job('video',str(video))
            evidence=[{'text':'加入牛奶20g','source':'ocr','start':0,'end':1},{'text':'拌匀','source':'ocr','start':1,'end':2}]
            model={'title':'Milk','ingredients':[{'name':'牛奶','quantity':'20g','text':'牛奶20g','evidence_ids':[0]}],
                   'steps':[{'text':'加入牛奶20g','evidence_ids':[0]},{'text':'拌匀','evidence_ids':[1]}],'uncertainties':[]}
            calls=[]
            def draw(recipe,*args):
                calls.append(1)
                if len(calls)==1:recipe.update(art_status='failed',art_warning='fixture failure');return
                stream=io.BytesIO();Image.new('RGB',(768,256),'white').save(stream,format='PNG')
                recipe.update(art_status='completed',recipe_art='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode(),art_layout=layout_for_plan(recipe,768,256))
            with patch('video_recipe.ocr_video',return_value=evidence) as ocr, patch('video_recipe.transcribe',return_value=[]) as speech, patch('deepseek_recipe.load_config',return_value=('test','test')), patch('deepseek_recipe.analyze',return_value=model) as organizer, patch('recipe_review_cycle.review',return_value=review_result) as reviewer, patch('codex_recipe_art.attach',side_effect=draw):
                process_job(store,store.claim())
                self.assertTrue(store.jobs()[0]['retryable'])
                store.retry_job(identifier);process_job(store,store.claim())
                self.assertEqual(ocr.call_count,1);self.assertEqual(speech.call_count,1)
                self.assertEqual(organizer.call_count,1);self.assertEqual(reviewer.call_count,1)
            self.assertEqual(len(calls),2)
            result=json.loads((folder/'jobs'/identifier/'recipe.json').read_text(encoding='utf-8'))
            if not review_result['passed']:self.assertEqual(len([r for r in store.feedback() if r['kind']=='auto_review_failure']),1)
            self.assertEqual(result['art_status'],'completed')
            self.assertTrue(result['source_snapshot_reused'])
            self.assertTrue(any(t['stage']=='ocr' and t['cache_hit'] for t in result['pipeline']['stages']))
            self.assertEqual(result['art_layout']['mode'],'tiles-v1')
