import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recipe_review_cycle import run_review_cycle

class ReviewCycleTests(unittest.TestCase):
    def test_correct_missing_material_once(self):
        original={'ingredients':[],'steps':[{'text':'撒点干粉擀平','evidence_ids':[0]}]}
        fixed={'ingredients':[{'name':'干粉（防粘）','quantity':'','text':'干粉（防粘）','evidence_ids':[0]}],'steps':original['steps']}
        rejected={'passed':False,'issues':[{'text':'步骤已写干粉，材料表遗漏','severity':'blocking','evidence_ids':[0]}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp, patch('recipe_review_cycle.review',return_value={'passed':True,'issues':[]}) as check, patch('recipe_review_cycle.revise',return_value=fixed) as correction:
            model,result=run_review_cycle(original,[{'text':'撒点干粉擀平'}],tmp)
            self.assertTrue(result['passed'])
            self.assertEqual(model['ingredients'][0]['quantity'],'')
            self.assertEqual(check.call_count,1)
            self.assertEqual(correction.call_count,0)
            self.assertTrue((Path(tmp)/'review-history.json').exists())

    def test_never_retry_indefinitely(self):
        issues=[{'passed':False,'issues':[{'text':str(i)+'顺序矛盾','evidence_ids':[0]}]} for i in range(3)]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp, patch('recipe_review_cycle.review',side_effect=issues) as check, patch('recipe_review_cycle.revise',side_effect=[{'title':'revision1'},{'title':'revision2'}]) as correction:
            _,result=run_review_cycle({},[{'text':'原文'}],tmp)
            self.assertFalse(result['passed'])
            self.assertEqual(check.call_count,3)
            self.assertEqual(correction.call_count,2)

    def test_service_error_returns_markable_draft(self):
        original={'ingredients':[{'text':'干粉','evidence_ids':[0]}],'steps':[{'text':'擀平','evidence_ids':[0]}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as tmp, patch('recipe_review_cycle.review',side_effect=ValueError('invalid')):
            model,result=run_review_cycle(original,[{'text':'干粉擀平'}],tmp)
            self.assertEqual(model,original)
            self.assertFalse(result['passed'])
            self.assertTrue(result['issues'])
