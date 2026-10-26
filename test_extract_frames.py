import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from extract_frames import extract
from make_test_video import generate


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / 'work'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = generate(self.root / 'synthetic.mp4')

    def test_scene_changes_and_images(self):
        out = self.root / '场景'
        data = extract(self.video, out, interval=99)
        self.assertEqual(data['decoded_frame_count'], 60)
        self.assertEqual([f['frame_index'] for f in data['frames']], [0, 20, 40])
        self.assertEqual([f['reason'] for f in data['frames']], ['first', 'scene_change', 'scene_change'])
        for record in data['frames']:
            frame = cv2.imdecode(np.frombuffer((out / record['file']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(frame.shape, (240, 320, 3))
        self.assertEqual(json.loads((out / 'metadata.json').read_text(encoding='utf-8')), data)

    def test_interval_sampling(self):
        data = extract(self.video, self.root / 'interval', interval=1, scene_threshold=1)
        self.assertEqual([f['frame_index'] for f in data['frames']], [0, 10, 20, 30, 40, 50])
        self.assertEqual([f['timestamp_seconds'] for f in data['frames']], [0, 1, 2, 3, 4, 5])

    def test_limit(self):
        data = extract(self.video, self.root / 'limit', interval=.1, max_frames=2)
        self.assertEqual(data['saved_frame_count'], 2)
        self.assertEqual(data['decoded_frame_count'], 60)

    def test_invalid_inputs(self):
        for kwargs in [{'interval': 0}, {'interval': float('nan')}, {'scene_threshold': 0}, {'max_frames': 0}]:
            with self.assertRaises(ValueError):
                extract(self.video, self.root / 'invalid', **kwargs)
        with self.assertRaises(ValueError):
            extract(self.root / 'missing.mp4', self.root / 'missing')
        broken = self.root / 'broken.mp4'
        broken.write_bytes(b'not a video')
        with self.assertRaises(ValueError):
            extract(broken, self.root / 'broken')

    def test_no_overwrite(self):
        out = self.root / 'existing'
        out.mkdir()
        sentinel = out / 'keep.txt'
        sentinel.write_text('keep')
        with self.assertRaises(ValueError):
            extract(self.video, out)
        self.assertEqual(sentinel.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main(verbosity=2)
