import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from pipeline_state import PipelineState,digest
from recipe_checks import prepare_local,apply_patch,normalize_findings,local_checks
from recipe_scope import scope_hints
from recipe_art_layout import layout_for_plan,validate_layout,art_content,validate_art_masks
from cloud_store import Store

class CheckpointTests(unittest.TestCase):
    def test_cache_binds_content_and_rules_and_reports_hits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            root=Path(tmp);callback=Mock(return_value={'text':'one'})
            p=PipelineState(root/'job1',root/'cache')
            p.run('ocr','OCR','video1','rules1',callback)
            p2=PipelineState(root/'job2',root/'cache')
            self.assertEqual(p2.run('ocr','OCR','video1','rules1',callback),{'text':'one'})
            self.assertEqual(callback.call_count,1)
            self.assertTrue(p2.timings[-1]['cache_hit'])
            p2.run('ocr','OCR','video2','rules1',callback)
            p2.run('ocr','OCR','video1','rules2',callback)
            self.assertEqual(callback.call_count,3)

    def test_failure_is_not_cached(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            p=PipelineState(Path(tmp)/'job',Path(tmp)/'cache')
            with self.assertRaises(ValueError):p.run('art','Art','a','v',Mock(side_effect=ValueError('bad')))
            cb=Mock(return_value={'ok':True});p.run('art','Art','a','v',cb)
            self.assertEqual(cb.call_count,1)
            self.assertEqual(p.timings[0]['state'],'failed')

    def test_corrupt_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            p=PipelineState(Path(tmp)/'job',Path(tmp)/'cache');cb=Mock(return_value={'ok':True})
            p.run('art','Art','a','v',cb)
            cache=next((Path(tmp)/'cache').rglob('*.json'));cache.write_text('{bad')
            p.run('art','Art','a','v',cb)
            self.assertEqual(cb.call_count,2)

class GroundedTests(unittest.TestCase):
    def test_same_number_wrong_measurement_unit_is_rejected(self):
        model={'ingredients':[{'text':'牛奶20ml','quantity':'20ml','evidence_ids':[0]}],'steps':[]}
        self.assertTrue(local_checks(model,[{'text':'牛奶20g'}]))
        model['ingredients'][0].update(text='牛奶20克',quantity='20克')
        self.assertFalse(local_checks(model,[{'text':'牛奶20g'}]))
    def test_local_missing_aid_before_ai_and_scopes(self):
        records=[{'text':'撒干粉擀平','start':0},{'text':'来做乳酪馅','start':1},{'text':'净含量：1kg','start':2},{'text':'闷好的红茶','start':3},{'text':'司康烤好后挤满馅','start':4}]
        model={'ingredients':[],'steps':[{'text':'撒干粉擀平','evidence_ids':[0]}]}
        fixed,changes=prepare_local(model,records)
        self.assertEqual(fixed['ingredients'][0]['quantity'],'')
        self.assertEqual(model['ingredients'],[])
        self.assertTrue(changes)
        self.assertEqual(list(scope_hints(records).values()),['main','filling','packaging','side_drink','main'])

    def test_patch_changes_only_target_and_rejects_stale_or_fabricated(self):
        model={'title':'Test','ingredients':[{'text':'牛奶20g','name':'牛奶','quantity':'20g','evidence_ids':[0]}],
               'steps':[{'text':'倒入牛奶','evidence_ids':[0]},{'text':'拌匀','evidence_ids':[1]}]}
        records=[{'text':'倒入牛奶20g'},{'text':'拌匀'}]
        change={'field':'steps','op':'replace','index':0,'expected_text':'倒入牛奶','item':{'text':'倒入牛奶20g','evidence_ids':[0]}}
        fixed=apply_patch(model,{'changes':[change]},records)
        self.assertEqual(fixed['steps'][1],model['steps'][1]);self.assertEqual(fixed['ingredients'],model['ingredients'])
        self.assertEqual(model['steps'][0]['text'],'倒入牛奶')
        change['expected_text']='wrong'
        with self.assertRaises(ValueError):apply_patch(model,{'changes':[change]},records)
        change.update(expected_text='倒入牛奶',item={'text':'倒入牛奶200g','evidence_ids':[0]})
        with self.assertRaises(ValueError):apply_patch(model,{'changes':[change]},records)

    def test_proven_false_missing_report_becomes_advisory(self):
        model={'ingredients':[{'name':'干粉（防粘）'}]}
        r=normalize_findings({'passed':False,'issues':[{'check_type':'missing_ingredient','subject':'干粉','text':'遗漏干粉','severity':'blocking'}]},model)
        self.assertTrue(r['passed'])

class ArtLayoutTests(unittest.TestCase):
    def test_only_localized_art_mismatches_can_be_masked(self):
        recipe={'steps':[{'text':'切一半'}],'ingredients':[]}
        issue={'field':'steps','index':0,'text':'误画成四份'}
        self.assertEqual(validate_art_masks(recipe,{'rejected':False,'issues':[issue]}),[issue])
        with self.assertRaises(ValueError):validate_art_masks(recipe,{'rejected':True,'issues':[]})
        with self.assertRaises(ValueError):validate_art_masks(recipe,{'issues':[dict(issue,index=4)]})
    def test_layout_covers_every_item_and_rejects_old_recipe(self):
        recipe={'deepseek':{'title':'Tea','ingredients':[{'name':'Matcha','quantity':'','text':'Matcha','evidence_ids':[99]}],
                           'steps':[{'text':'Whisk'},{'text':'Add milk'}]}}
        layout=layout_for_plan(recipe,1024,1024)
        self.assertEqual(len(layout['ingredients']),1);self.assertEqual(len(layout['steps']),2)
        self.assertEqual(validate_layout(recipe,layout),layout)
        self.assertNotIn('evidence_ids',art_content(recipe)['ingredients'][0])
        recipe['deepseek']['steps'][1]['text']='Bake'
        with self.assertRaises(ValueError):validate_layout(recipe,layout)

class StoreResumeTests(unittest.TestCase):
    def test_retry_and_source_identity(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            store=Store(tmp);job=store.create_job('link','https://xhslink.cn/o/test')
            with self.assertRaises(ValueError):store.retry_job(job)
            store.update_job(job,'failed','Download failed',error='bad')
            self.assertEqual(store.retry_job(job)['id'],job)
            self.assertIsNone(store.jobs()[0]['error'])
            recipe={'steps':[{'text':'Mix'}],'source_digest':'video-a','rule_revision':'rules1'}
            a=store.save_recipe({'recipe':recipe})
            b=store.save_recipe({'recipe':dict(recipe,source_digest='video-b')})
            c=store.save_recipe({'recipe':dict(recipe,rule_revision='rules2')})
            self.assertEqual(len({a['id'],b['id'],c['id']}),3)
