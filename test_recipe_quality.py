import unittest
from recipe_quality import drawing_allowed

class QualityTests(unittest.TestCase):
    def test_no_api_success_no_drawing(self):
        for status in ('local', 'deepseek_failed_local_fallback', 'codex_grounded'):
            self.assertFalse(drawing_allowed({'analysis_status': status})[0])

    def test_uncertainties_block(self):
        r = {'analysis_status':'deepseek','deepseek':{'ingredients':[{'text':'面粉'}],'steps':[{'text':'混合'}],'uncertainties':['温度不清楚']}}
        self.assertFalse(drawing_allowed(r)[0])
        r['deepseek']['uncertainties'] = []
        self.assertTrue(drawing_allowed(r)[0])
