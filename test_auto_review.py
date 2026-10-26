import tempfile
import unittest
from pathlib import Path
from recipe_auto_review import validate_review
from cloud_store import Store

class AutoReviewTests(unittest.TestCase):
    def test_old_uncollected_archived_once_collected_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            store=Store(tmp)
            pending=store.save_recipe({'recipe':{'steps':[{'text':'拌匀'}]}})
            kept=store.save_recipe({'recipe':{'steps':[{'text':'烘烤'}]},'reviewed':True})
            with store.connect() as db:
                db.execute('UPDATE recipes SET updated=0')
            self.assertEqual(store.archive_uncollected(now=8*86400),1)
            self.assertEqual(store.archive_uncollected(now=8*86400),0)
            self.assertEqual([r['id'] for r in store.recipes()],[kept['id']])
            self.assertEqual(store.feedback()[0]['snapshot']['id'],pending['id'])
    def test_pass_and_fail_contract(self):
        records=[{'text':'加入牛奶'}]
        self.assertTrue(validate_review({'passed':True,'issues':[]},records)['passed'])
        self.assertTrue(validate_review({'passed':True,'issues':[{'severity':'advisory','text':'建议标注材料用途','evidence_ids':[0]}]},records)['passed'])
        self.assertFalse(validate_review({'passed':True,'issues':[{'text':'遗漏','evidence_ids':[0]}]},records)['passed'])
        normalized=validate_review({'passed':False,'issues':[{'severity':'advisory','text':'建议标注用途','evidence_ids':[0]}]},records)
        self.assertTrue(normalized['passed'])
        self.assertTrue(normalized['verdict_normalized'])
        with self.assertRaises(ValueError):
            validate_review({'passed':False,'issues':[]},records)
        with self.assertRaises(ValueError):
            validate_review({'passed':False,'issues':[{'text':'遗漏','evidence_ids':[3]}]},records)

    def test_rejection_persists_and_learns_fixed_checks(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp:
            store=Store(tmp)
            entry=store.save_recipe({'recipe':{'steps':[{'text':'加入牛奶'}]}})
            store.report_recipe(entry['id'],'遗漏步骤，用量错误')
            restored=Store(tmp)
            self.assertTrue(restored.recipes()[0]['rejected'])
            self.assertEqual(len(restored.feedback()),1)
            self.assertIn('加强逐项核对用量原文',restored.learning_hints())
            self.assertEqual(restored.feedback()[0]['snapshot']['recipe']['steps'][0]['text'],'加入牛奶')
            with self.assertRaises(ValueError):
                store.report_recipe(entry['id'],' ')
