import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.clips import _flatten_dialogue, _normalize_clip_segments
from pipeline.episode_notes import resolve_episode_note
from pipeline.script import SIGNOFF_CTA, _enforce_signoff_cta, _turn_prompt
from pipeline.video import (
    FONT_BOLD,
    LANDSCAPE,
    SPOTIFY_OUTRO_URL,
    YOUTUBE_OUTRO_URL,
    _fit_wrapped_text,
    _render_transition_card,
)


class EpisodeNoteTests(unittest.TestCase):
    def test_date_keyed_note_applies_to_only_matching_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode_notes.json"
            path.write_text(json.dumps({"2026-07-18": "Hope you like it"}))
            self.assertEqual(
                resolve_episode_note("2026-07-18", notes_path=path),
                "Hope you like it",
            )
            self.assertEqual(resolve_episode_note("2026-07-19", notes_path=path), "")

    def test_explicit_note_overrides_scheduled_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode_notes.json"
            path.write_text(json.dumps({"2026-07-18": "Scheduled"}))
            self.assertEqual(
                resolve_episode_note("2026-07-18", "Manual", path),
                "Manual",
            )


class SpokenEditorialTests(unittest.TestCase):
    def _prompt(self, segment_type, turn_idx, special_note=""):
        return _turn_prompt(
            {"type": segment_type, "beats": []},
            None,
            [],
            [],
            "Claude",
            turn_idx,
            4,
            "July 18, 2026",
            ["Claude", "ChatGPT"],
            special_note,
        )

    def test_operator_note_is_forced_into_first_intro_turn(self):
        note = "We hope you like our new format!"
        self.assertIn(note, self._prompt("intro", 0, note))
        self.assertNotIn(note, self._prompt("intro", 1, note))

    def test_cta_is_inserted_exactly_once_even_if_models_repeat_it(self):
        script = {
            "segments": [{
                "type": "sign_off",
                "dialogue": [
                    {"speaker": "Claude", "text": "My prediction mentions YouTube."},
                    {"speaker": "ChatGPT", "text": "My prediction."},
                    {"speaker": "Claude", "text": "Subscribe on YouTube and follow on Spotify. Thanks for listening."},
                    {"speaker": "ChatGPT", "text": "Find us on YouTube and Spotify. See you tomorrow."},
                ],
            }]
        }
        _enforce_signoff_cta(script, ["Claude", "ChatGPT"])
        goodbye_text = " ".join(
            line["text"] for line in script["segments"][0]["dialogue"][2:]
        )
        self.assertEqual(goodbye_text.lower().count("youtube"), 1)
        self.assertEqual(goodbye_text.lower().count("spotify"), 1)
        self.assertIn(SIGNOFF_CTA, goodbye_text)
        self.assertIn("My prediction mentions YouTube.", script["segments"][0]["dialogue"][0]["text"])


class TransitionCardTests(unittest.TestCase):
    def test_long_up_next_headline_wraps_without_truncation(self):
        headline = (
            "DeepMind CEO lobbies Washington on AI model vetting plan "
            "modeled after Wall Street oversight"
        )
        canvas = Image.new("RGB", LANDSCAPE)
        draw = ImageDraw.Draw(canvas)
        font, lines = _fit_wrapped_text(
            draw, headline, FONT_BOLD, 56, int(LANDSCAPE[0] * 0.82), 3, 26
        )
        self.assertEqual(" ".join(lines), headline)
        self.assertLessEqual(len(lines), 3)
        self.assertNotIn("...", " ".join(lines))
        self.assertTrue(all(draw.textlength(line, font=font) <= LANDSCAPE[0] * 0.82
                            for line in lines))

    def test_outro_card_has_platform_destinations(self):
        self.assertIn("youtube.com/", YOUTUBE_OUTRO_URL)
        self.assertIn("open.spotify.com/", SPOTIFY_OUTRO_URL)
        self.assertEqual(_render_transition_card("outro", LANDSCAPE).size, LANDSCAPE)


class ClipSelectionTests(unittest.TestCase):
    def setUp(self):
        self.script = {
            "segments": [
                {
                    "type": "intro",
                    "dialogue": [{"speaker": "Claude", "text": "Welcome to the show today."}],
                },
                {
                    "type": "main_story",
                    "topic": "AI safety",
                    "dialogue": [
                        {"speaker": "Claude", "text": "This concrete warning changes the stakes for every lab and regulator watching closely today."},
                        {"speaker": "ChatGPT", "text": "The surprising number is seventy percent, which turns a niche concern into a mainstream demand for action."},
                        {"speaker": "Claude", "text": "That creates a real enforcement dilemma with no easy exit for the companies involved."},
                    ],
                },
                {
                    "type": "sign_off",
                    "dialogue": [{"speaker": "ChatGPT", "text": "Follow us and goodbye."}],
                },
            ]
        }

    def test_normalizer_filters_signoff_and_overlaps_and_keeps_metadata(self):
        lines = _flatten_dialogue(self.script)
        raw = [
            {"start_index": 1, "end_index": 2, "title": "High Stakes", "on_screen_hook": "THIS CHANGES EVERYTHING", "score": 96},
            {"start_index": 2, "end_index": 3, "title": "Overlap", "score": 90},
            {"start_index": 4, "end_index": 4, "title": "Goodbye", "score": 100},
        ]
        clips = _normalize_clip_segments(raw, lines)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]["title"], "High Stakes")
        self.assertEqual(clips[0]["on_screen_hook"], "THIS CHANGES EVERYTHING")
        self.assertGreater(clips[0]["estimated_duration_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
