import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_library


class LibraryTests(unittest.TestCase):
    def test_same_recipe_updates_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'work') as folder:
            root = Path(folder)
            recipe = {'steps': [{'instruction': '把番茄切成小块'}]}
            with patch.object(build_library, 'ROOT', root), patch.object(build_library, 'build_app') as render:
                build_library.add_recipe(recipe)
                build_library.add_recipe(dict(recipe, status='needs_review'))
            entries = json.loads((root / 'recipe-library.json').read_text(encoding='utf-8'))
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['recipe']['status'], 'needs_review')
            self.assertEqual(render.call_count, 2)

    def test_empty_steps_not_added(self):
        with patch.object(build_library, 'build_app') as render:
            build_library.add_recipe({'steps': []})
        render.assert_not_called()
