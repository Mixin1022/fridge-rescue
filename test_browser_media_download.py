import unittest
import tempfile
from pathlib import Path
from io import BytesIO
from unittest.mock import patch,Mock
from browser_media_download import validate_media_url,download_observed
from note_link import video_urls

class MediaTests(unittest.TestCase):
    def test_observed_urls_only(self):
        note={'video':{'media':{'stream':{'h264':[{'masterUrl':'https://a.xhscdn.com/video.mp4','backupUrls':['https://b.xhscdn.com/video.mp4']}]}}}}
        self.assertEqual(len(video_urls(note)),2)
        self.assertEqual(video_urls({'video':{'url':'http://a.xhscdn.com/a.mp4'}}),['https://a.xhscdn.com/a.mp4'])
        for url in ('https://127.0.0.1/a','https://xhscdn.com.evil.test/a','http://a.xhscdn.com/a'):
            with self.assertRaises(ValueError):validate_media_url(url)

    def test_mp4_and_size_limit(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'work') as folder:
            raw=b'\x00\x00\x00\x18ftypisom'+b'0'*30
            def response():
                value=BytesIO(raw);value.url='https://a.xhscdn.com/video.mp4';return value
            opener=Mock();opener.open.side_effect=lambda *a,**k:response()
            with patch('browser_media_download.build_opener',return_value=opener):
                result=download_observed(['https://a.xhscdn.com/video.mp4'],folder,None,'https://www.xiaohongshu.com/')
                self.assertEqual(result.read_bytes(),raw)
                with self.assertRaises(ValueError):
                    download_observed(['https://a.xhscdn.com/video.mp4'],folder,None,'https://www.xiaohongshu.com/',limit=12)
                self.assertEqual(len(list(Path(folder).glob('*.mp4'))),1)
