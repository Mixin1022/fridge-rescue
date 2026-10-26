import unittest
from unittest.mock import patch
from note_link import parse_note
from pipeline_acquisition import description_records
from deepseek_recipe import validate_result
from recipe_auto_review import review

class VideoBodyTests(unittest.TestCase):
    def test_video_preserves_body_as_separate_evidence(self):
        parsed=parse_note({'type':'video','title':'芒果冷麵','desc':'芒果100g\n面条煮熟后拌匀'})
        records=description_records(parsed['post_text'])
        self.assertEqual([r['text'] for r in records],['芒果冷麵','芒果100g','面条煮熟后拌匀'])
        self.assertTrue(all(r['kind']=='post_text' for r in records))
    def test_no_body_is_not_invented(self):
        self.assertEqual(description_records(parse_note({'type':'video'})['post_text']),[])
    def test_empty_recipe_reports_missing_body(self):
        with self.assertRaisesRegex(ValueError,'缺少帖子正文'):
            validate_result({'ingredients':[],'steps':[]},[{'text':'詳細食譜請參考內文'}],compact=True)
    def test_empty_recipe_cannot_spend_on_review_or_pass(self):
        with patch('recipe_auto_review.urlopen') as api:
            with self.assertRaisesRegex(ValueError,'空列表'):
                review({'ingredients':[],'steps':[]},[{'text':'芒果冷麵','kind':'post_text'}])
            api.assert_not_called()
