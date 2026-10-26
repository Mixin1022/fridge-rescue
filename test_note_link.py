import unittest
from note_link import parse_note,normalize_image_url
class Notes(unittest.TestCase):
    def test_image_platform_http_is_upgraded(self):
        self.assertEqual(normalize_image_url('http://sns-webpic-qc.xhscdn.com/a?token=x'),'https://sns-webpic-qc.xhscdn.com/a?token=x')
        self.assertEqual(normalize_image_url('https://a.xhscdn.net/a'),'https://a.xhscdn.net/a')
    def test_foreign_and_disguised_images_stay_blocked(self):
        for url in ('https://xhscdn.com.evil.test/a','https://evilxhscdn.com/a','http://127.0.0.1/a','file:///a','https://u:p@a.xhscdn.com/a','https://a.xhscdn.com:8080/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):normalize_image_url(url)
    def test_video(self): self.assertEqual(parse_note({'type':'video'})['kind'],'video')
    def test_post(self):
        result=parse_note({'type':'normal','title':'番茄','desc':'切块','imageList':[{'urlDefault':'https://a.xhscdn.com/1'},{'urlDefault':'https://a.xhscdn.com/1'}]})
        self.assertEqual(result['kind'],'post');self.assertEqual(result['text'],'番茄\n切块');self.assertEqual(len(result['urls']),1)
    def test_unknown(self):
        with self.assertRaises(ValueError):parse_note({})
