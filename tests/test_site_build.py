import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "sites" / "ai-daily" / "scripts" / "build.py"
SPEC = importlib.util.spec_from_file_location("context_window_build", BUILD_PATH)
site_build = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(site_build)


class ContextWindowSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        site_build.main()
        cls.site = ROOT / "sites" / "ai-daily"
        cls.episodes = json.loads((cls.site / "static" / "articles.json").read_text())

    def test_homepage_has_daily_utility_and_measurement(self):
        homepage = (self.site / "index.html").read_text()
        self.assertIn("THE THREE THINGS TO KNOW", homepage)
        self.assertIn("WHY IT MATTERS", homepage)
        self.assertIn("Episode play", homepage)
        self.assertIn("View score history", homepage)
        self.assertIn("Methodology", homepage)

    def test_episode_has_schema_and_unique_social_image(self):
        latest = self.episodes[0]
        page = (self.site / "episodes" / f'{latest["date"]}.html').read_text()
        self.assertIn('"@type": "PodcastEpisode"', page)
        self.assertIn("i.ytimg.com/vi/", page)
        self.assertIn("SHARE THIS BRIEFING", page)

    def test_discovery_files_are_generated(self):
        self.assertIn("/sitemap.xml", (self.site / "robots.txt").read_text())
        sitemap = (self.site / "sitemap.xml").read_text()
        self.assertIn("<urlset", sitemap)
        self.assertIn(f'/episodes/{self.episodes[0]["date"]}.html', sitemap)

    def test_every_episode_score_is_logged(self):
        expected = [ep for ep in self.episodes if (ep.get("scores") or {}).get("overall") is not None]
        score_log = json.loads((self.site / "static" / "scores.json").read_text())
        self.assertEqual(len(expected), len(score_log))
        self.assertEqual(
            {ep["date"] for ep in expected},
            {entry["date"] for entry in score_log},
        )
        score_page = (self.site / "scores" / "index.html").read_text()
        self.assertIn("Every score", score_page)
        for episode in expected:
            self.assertIn(episode["date"], score_page)


if __name__ == "__main__":
    unittest.main()
