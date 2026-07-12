import tempfile
import unittest
from pathlib import Path
import sys
import types

from PIL import Image

# Keep this unit test independent from the pipeline's optional env loader.
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda **_kwargs: None
sys.modules.setdefault("dotenv", dotenv)

from pipeline.thumbnail import THUMB_SIZE, _thumbnail_hook, generate_thumbnail


class ThumbnailTests(unittest.TestCase):
    def test_hook_prefers_youtube_title_and_removes_brand(self):
        script = {
            "title": "A long episode title",
            "youtube_title": "Apple Sues OpenAI Over Stolen Secrets | Context Window",
        }
        hook = _thumbnail_hook(script, [], max_words=7)
        self.assertEqual(hook, "Apple Sues OpenAI Over Stolen Secrets")
        self.assertNotIn("Context Window", hook)

    def test_hook_caps_article_headline(self):
        topics = [{
            "category": "main",
            "title": "Apple Sues OpenAI Alleging Former Employees Stole Confidential Hardware Trade Secrets",
        }]
        hook = _thumbnail_hook({}, topics, max_words=7)
        self.assertEqual(len(hook.split()), 7)

    def test_generator_emits_youtube_sized_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_thumbnail(
                {"youtube_title": "Apple vs OpenAI: Trade Secret War"},
                [{"category": "main", "title": "Apple sues OpenAI"}],
                Path(tmp),
                roster=["Claude", "ChatGPT"],
            )
            self.assertTrue(path.exists())
            with Image.open(path) as image:
                self.assertEqual(image.size, THUMB_SIZE)
                self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
