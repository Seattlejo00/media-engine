import tempfile
import unittest
from pathlib import Path

from scripts.send_build_in_public import load_env_file, render_email, validate_brief


def _brief():
    return {
        "work_date": "2026-07-17",
        "engineering_summary": (
            "Speech now sits on an overlay timeline while music crossfades "
            "beneath the opening and closing lines."
        ),
        "engineering_insight": (
            "Once audio overlaps, video timing must use the same timeline or "
            "cards and waveforms drift."
        ),
        "standalone_post": (
            "Making an AI podcast sound coherent became a timeline problem. "
            "I normalized voices to -20 dBFS, replaced concatenation with "
            "overlays, and made video share the mixer's timing."
        ),
        "thread_posts": [
            "The first fix was loudness: every generated voice is normalized to -20 dBFS before assembly.",
            "The harder fix was structural: audio and video now share overlap windows so transitions cannot drift.",
        ],
        "commits": [
            {"sha": "b3201a3", "subject": "Crossfaded audio bed with licensed music"},
        ],
    }


class BuildInPublicEmailTests(unittest.TestCase):
    def test_validates_and_normalizes_brief(self):
        brief = validate_brief(_brief())
        self.assertEqual(brief["work_date"], "2026-07-17")
        self.assertEqual(len(brief["thread_posts"]), 2)

    def test_rejects_post_over_280_characters(self):
        data = _brief()
        data["standalone_post"] = "x" * 281
        with self.assertRaisesRegex(ValueError, "281 characters"):
            validate_brief(data)

    def test_requires_two_or_three_thread_posts(self):
        data = _brief()
        data["thread_posts"] = ["Only one"]
        with self.assertRaisesRegex(ValueError, "2 or 3"):
            validate_brief(data)

    def test_email_contains_engineering_context_and_composer_links(self):
        brief = validate_brief(_brief())
        subject, text_body, html_body = render_email(brief)
        self.assertIn("Jul 17", subject)
        self.assertIn("overlay timeline", text_body)
        self.assertIn("timeline problem", html_body)
        self.assertGreaterEqual(text_body.count("twitter.com/intent/tweet"), 1)
        self.assertIn("Nothing was posted automatically", html_body)

    def test_env_file_does_not_override_existing_value(self):
        import os

        old = os.environ.get("RESEND_API_KEY")
        os.environ["RESEND_API_KEY"] = "existing"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "email.env"
                path.write_text("RESEND_API_KEY=from-file\nBUILD_IN_PUBLIC_TO_EMAIL=me@example.com\n")
                load_env_file(path)
            self.assertEqual(os.environ["RESEND_API_KEY"], "existing")
            self.assertEqual(os.environ["BUILD_IN_PUBLIC_TO_EMAIL"], "me@example.com")
            os.environ.pop("BUILD_IN_PUBLIC_TO_EMAIL", None)
        finally:
            if old is None:
                os.environ.pop("RESEND_API_KEY", None)
            else:
                os.environ["RESEND_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
