import unittest
from copy import deepcopy
from deepseek_recipe import validate_result
from unittest.mock import patch
from io import BytesIO
import json
from deepseek_recipe import analyze
from deepseek_recipe import missing_numbers


class ValidationTests(unittest.TestCase):
    def test_equivalent_duration_and_decimal(self):
        self.assertFalse(missing_numbers('冷冻30分钟','冷冻半小时'))
        self.assertFalse(missing_numbers('厚1.50cm','厚1.5cm'))
        self.assertTrue(missing_numbers('加入30g糖','冷冻半小时'))
        self.assertTrue(missing_numbers('烤30分钟','烤18分钟'))
    def setUp(self):
        self.records = [{'start': 5, 'end': 6, 'text': '熟透的番茄'}, {'start': 7, 'end': 8, 'text': '切成小块'}]
        self.result = {'ingredients': [{'text': '熟透的番茄', 'evidence_ids': [0]}],
                       'steps': [{'text': '切成小块', 'evidence_ids': [1]}],
                       'classification': [{'id': 0, 'category': 'ingredient', 'reason': '材料'},
                                          {'id': 1, 'category': 'operation', 'reason': '操作'}], 'uncertainties': []}

    def test_complete_sources_pass(self):
        self.assertEqual(validate_result(self.result, self.records)['steps'][0]['start'], 7)

    def test_compact_response_local_index(self):
        del self.result['classification']
        checked=validate_result(self.result,self.records,compact=True)
        self.assertEqual(len(checked['classification']),2)
        self.assertEqual(checked['steps'][0]['evidence_ids'],[1])

    def test_length_response_never_accepted(self):
        payload={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}
        with patch('deepseek_recipe.load_config',return_value=('test','test')), patch('deepseek_recipe.urlopen',return_value=BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(ValueError,'截断'):
                analyze([dict(self.records[0],source='ocr')])

    def test_missing_choices_has_explicit_error(self):
        with patch('deepseek_recipe.load_config',return_value=('test','test')), patch('deepseek_recipe.urlopen',return_value=BytesIO(b'{}')):
            with self.assertRaisesRegex(ValueError,'结果列表'):
                analyze([dict(self.records[0],source='ocr')])

    def test_missing_quantity_is_not_invented(self):
        self.result['ingredients'][0].update(name='番茄', quantity='')
        self.assertEqual(validate_result(self.result, self.records)['ingredients'][0]['quantity'], '')

    def test_invented_quantity_rejected(self):
        self.result['ingredients'][0].update(name='番茄', quantity='200g')
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_invented_baking_number_rejected(self):
        self.result['steps'][0]['text'] = '180度烤18分钟'
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_packaging_only_evidence_rejected(self):
        self.records[0]['text'] = '净含量：1kg'
        self.result['ingredients'][0]['text'] = '果酱1kg'
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_packaging_issues_retained_off_note(self):
        self.result['uncertainties'] = ['净含量：化疑似OCR错误', '蛋黄液刷面用量未明确。', '关键步骤顺序有冲突']
        checked = validate_result(self.result, self.records)
        self.assertEqual(checked['uncertainties'], ['关键步骤顺序有冲突'])
        self.assertEqual(len(checked['excluded_notes']), 2)

    def test_omitted_ingredient_fails(self):
        self.result['ingredients'] = []
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_fabricated_reference_fails(self):
        self.result['steps'][0]['evidence_ids'] = [99]
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_duplicate_classification_fails(self):
        self.result['classification'][1]['id'] = 0
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_missing_classification_fails(self):
        self.result['classification'].pop()
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)

    def test_packaging_warning_not_ingredient(self):
        self.result['ingredients'][0]['text'] = '儿童青少年应避免过量摄入盐油糖'
        with self.assertRaises(ValueError):
            validate_result(self.result, self.records)
