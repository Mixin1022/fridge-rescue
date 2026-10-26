import unittest
from diagnose_recognition import chinese_boxes


class DiagnosticTests(unittest.TestCase):
    def test_english_noise_rejected_but_chinese_quantity_retained(self):
        box = [[0, 0], [10, 0], [10, 10], [0, 10]]
        result = chinese_boxes([(box, '红葱头1个切丝', .8), (box, 'English subtitle', .9), (box, '@叩iefresh ingredients on screen', .4)])
        self.assertEqual([r['text'] for r in result], ['红葱头1个切丝'])

    def test_low_confidence_is_preserved_for_review(self):
        box = [[0, 0], [10, 0], [10, 10], [0, 10]]
        self.assertEqual(chinese_boxes([(box, '可疑文字', .1)])[0]['confidence'], .1)


if __name__ == '__main__':
    unittest.main()
