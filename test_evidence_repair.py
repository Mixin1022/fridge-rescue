import unittest,json,tempfile
from pathlib import Path
from copy import deepcopy
from deepseek_recipe import repair_missing_ingredient_refs,recover_reference_failure

class EvidenceRepairTests(unittest.TestCase):
    def test_literal_name_and_quantity_only(self):
        records=[{'text':'还有一枚大蒜'},{'text':'隔夜的酸面包'},{'text':'加一点盐'}]
        result={'ingredients':[{'name':'大蒜','quantity':'一枚'},{'name':'隔夜酸面包','quantity':''},{'name':'盐','quantity':'一点'}]}
        self.assertEqual(len(repair_missing_ingredient_refs(result,records)),3)
        self.assertEqual(result['ingredients'][0]['evidence_ids'],[0])
    def test_no_guessing_or_packaging_or_negation(self):
        result={'ingredients':[{'name':'黄油','quantity':'50g'},{'name':'盐','quantity':''},{'name':'牛奶','quantity':''}]}
        records=[{'text':'黄油20g，白糖50g'},{'text':'海盐'},{'text':'不要加牛奶'},{'text':'牛奶净含量1kg'}]
        self.assertEqual(repair_missing_ingredient_refs(result,records),[])
    def test_invalid_supplied_reference_and_steps_untouched(self):
        result={'ingredients':[{'name':'黄瓜','evidence_ids':[999]}],'steps':[{'text':'切黄瓜'}]};before=deepcopy(result)
        self.assertEqual(repair_missing_ingredient_refs(result,[{'text':'黄瓜'}]),[]);self.assertEqual(result,before)
    def test_saved_payload_requires_exact_evidence_and_complete_response(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as root:
            p=Path(root);records=[{'text':'黄瓜','start':0,'end':1}]
            result={'ingredients':[{'name':'黄瓜','text':'黄瓜','quantity':''}],'steps':[{'text':'黄瓜','evidence_ids':[0]}],'uncertainties':[]}
            payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
            for name,data in [('analysis-diagnostic.json',{'message':'API 食谱缺少有效原文依据'}),('recognition-draft.json',{'evidence':records}),('deepseek-response.json',payload)]:
                (p/name).write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(recover_reference_failure(records,records,p/'candidate.json'),payload)
            self.assertIsNone(recover_reference_failure([dict(records[0],text='番茄')],records,p/'candidate.json'))
            payload['choices'][0]['finish_reason']='length';(p/'deepseek-response.json').write_text(json.dumps(payload))
            self.assertIsNone(recover_reference_failure(records,records,p/'candidate.json'))
