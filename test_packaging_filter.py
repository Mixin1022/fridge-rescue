import unittest
from content_classifier import classify_content

class PackagingTests(unittest.TestCase):
    def classify(self, text, kind='caption'):
        return classify_content({'text':text,'kind':kind,'source':'ocr','start':0,'end':0},[])[0]

    def test_warning_and_nutrition_not_food(self):
        for text in ('儿童青少年应避免过量摄入盐油糖。','儿童青少年应避免过量据入盐油糖。','儿量青少年应避免过量摄入盐油题。','每100g 营养素参考值%'):
            self.assertEqual(self.classify(text, 'ingredient_card'),'narration')

    def test_actual_ingredients_preserved(self):
        self.assertEqual(self.classify('中筋面粉250g、泡打粉5g、盐1g、白糖50g','ingredient_card'),'ingredient')

    def test_actual_corrupted_packaging(self):
        for text in ('净含量：化', '含量：1kg', '营州成分表', '每100营养表参语', '噪原汁添加量>23%，姜黄拍(香辛'):
            self.assertEqual(self.classify(text, 'ingredient_card'), 'narration')

    def test_cooking_instruction_preserved(self):
        self.assertEqual(self.classify('加入牛奶20g'),'operation')
