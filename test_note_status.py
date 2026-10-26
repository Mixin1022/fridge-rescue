import unittest
from recipe_note_status import annotate_recipe
from recipe_note_status import exclude_explicit_sides
from recipe_quality import drawing_allowed

class NoteStatusTests(unittest.TestCase):
    def test_only_explicit_side_drink_removed(self):
        m={'title':'司康','ingredients':[{'text':'牛奶20g'},{'name':'柠檬片（饮品）','text':'柠檬片2片'}],'steps':[{'text':'拌匀'},{'text':'饮品：加入红茶'}]}
        exclude_explicit_sides(m)
        self.assertEqual(len(m['ingredients']),1)
        self.assertEqual(len(m['steps']),1)
        self.assertIn('excluded_side_items',m)
        tea={'title':'抹茶奶茶','ingredients':[{'name':'牛奶（饮品）'}],'steps':[]}
        self.assertEqual(len(exclude_explicit_sides(tea)['ingredients']),1)
    def test_flags_local_issue_without_inventing_quantity(self):
        r={'analysis_status':'deepseek','deepseek':{'ingredients':[{'name':'干粉','quantity':'','text':'干粉','evidence_ids':[0]}],'steps':[{'text':'撒干粉擀平','evidence_ids':[0]}],'uncertainties':[]},'auto_review':{'passed':False,'issues':[{'text':'种类不明确','severity':'blocking','evidence_ids':[0]}]}}
        annotate_recipe(r)
        self.assertEqual(r['note_status'],'needs_confirmation')
        self.assertFalse(r['auto_review']['passed'])
        self.assertEqual(r['deepseek']['ingredients'][0]['quantity'],'')
        self.assertTrue(r['deepseek']['steps'][0]['question_notes'])
        self.assertTrue(drawing_allowed(r)[0])

    def test_unlocated_issue_and_empty_recipe(self):
        r={'deepseek':{'ingredients':[],'steps':[],'uncertainties':['内容缺失']},'auto_review':{'passed':False,'issues':[]}}
        annotate_recipe(r)
        self.assertEqual(r['note_status'],'insufficient')
        self.assertEqual(r['note_warnings'],['内容缺失'])
