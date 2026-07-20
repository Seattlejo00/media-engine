import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

import config
from pipeline.clips import (
    CTA_SECONDS,
    _fallback_finalists,
    _flatten_dialogue,
    _normalize_clip_segments,
    _resolve_finalist_numbers,
)
from pipeline.tts import TTS_FORMAT_VERSION
from pipeline.episode_notes import resolve_episode_note
from pipeline.script import (
    MAX_SENTENCE_WORDS,
    MAX_TURN_WORDS,
    SIGNOFF_CTA,
    _enforce_signoff_cta,
    _parse_plan_json,
    _repetition_issues,
    _run_conversation,
    _speech_shape_issues,
    _turn_prompt,
    _uncovered_beats,
)
from pipeline.video import (
    FONT_BOLD,
    LANDSCAPE,
    SPOTIFY_OUTRO_URL,
    YOUTUBE_OUTRO_URL,
    _fit_wrapped_text,
    _render_clip_cta_card,
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


class ShowrunnerPlanParsingTests(unittest.TestCase):
    def test_fenced_valid_json_parses(self):
        self.assertEqual(
            _parse_plan_json('```json\n{"title": "Test", "segments": []}\n```'),
            {"title": "Test", "segments": []},
        )

    def test_invalid_backslash_escape_is_repaired(self):
        plan = _parse_plan_json(
            '{"title": "AI\\policy update", "segments": []}'
        )
        self.assertEqual(plan["title"], "AI\\policy update")

    def test_non_escape_syntax_error_still_raises_for_model_retry(self):
        with self.assertRaises(json.JSONDecodeError):
            _parse_plan_json('{"title": "Missing comma" "segments": []}')


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

    def test_second_intro_host_cannot_repeat_welcome_date_or_rundown(self):
        prompt = self._prompt("intro", 1)
        self.assertIn("Do not welcome listeners again", prompt)
        self.assertIn("repeat the date", prompt)
        self.assertIn("repeat the episode rundown", prompt)

    def test_spoken_ledger_is_explicitly_non_repeating(self):
        prompt = _turn_prompt(
            {"type": "main_story", "beats": []},
            None,
            [{"speaker": "ChatGPT", "text": "The API costs three dollars."}],
            ["Moonshot launched Kimi K3 with 2.8 trillion parameters."],
            "Claude",
            1,
            4,
            "July 18, 2026",
            ["Claude", "ChatGPT"],
        )
        self.assertIn("ANTI-REPETITION LEDGER", prompt)
        self.assertIn("2.8 trillion parameters", prompt)
        self.assertIn("NON-REPETITION CONTRACT", prompt)

    def test_repetition_check_flags_reused_number_or_core_point(self):
        earlier = [
            "Moonshot launched Kimi K3 with 2.8 trillion parameters.",
            "The lack of pricing leaves solo founders unable to budget.",
        ]
        self.assertTrue(_repetition_issues(
            "Kimi K3's 2.8 trillion parameter count is unusually large.",
            earlier,
        ))
        self.assertTrue(_repetition_issues(
            "Independent testing matters. Kimi K3 still has 2.8 trillion parameters.",
            earlier,
        ))
        self.assertTrue(_repetition_issues(
            "Solo founders still cannot budget because pricing remains absent.",
            earlier,
        ))
        self.assertEqual(
            _repetition_issues(
                "The weight release creates a concrete test for independent labs.",
                earlier,
            ),
            [],
        )

    def test_covered_showrunner_beat_is_removed_from_later_turns(self):
        beats = [
            "Kimi K3 has 2.8 trillion parameters.",
            "API access costs three dollars per million input tokens.",
        ]
        remaining = _uncovered_beats(
            beats,
            ["Moonshot says Kimi K3 contains 2.8 trillion parameters."],
        )
        self.assertEqual(remaining, [beats[1]])

    def test_repetitive_generated_turn_is_rewritten_before_output(self):
        plan = {
            "title": "Test",
            "segments": [{
                "type": "cold_open",
                "lead": "Claude",
                "turns_per_speaker": 1,
                "beats": [],
            }],
        }
        drafts = [
            "Moonshot says Kimi K3 has 2.8 trillion parameters and will publish weights in July.",
            "Kimi K3 has 2.8 trillion parameters, a huge figure for Moonshot's model release.",
            "Independent access will let researchers test efficiency claims instead of trusting launch-day marketing.",
        ]
        with (
            patch("pipeline.script._load_personas", return_value={
                "Claude": "persona", "ChatGPT": "persona",
            }),
            patch("pipeline.script._get_api_clients", return_value={
                "Claude": object(), "ChatGPT": object(),
            }),
            patch("pipeline.script._speak", side_effect=drafts) as speak,
        ):
            script = _run_conversation(
                plan,
                [],
                ["Claude", "ChatGPT"],
                "July 18, 2026",
            )

        self.assertEqual(speak.call_count, 3)
        self.assertEqual(
            script["segments"][0]["dialogue"][1]["text"],
            drafts[2],
        )

    def test_cta_is_inserted_exactly_once_even_if_models_repeat_it(self):
        script = {
            "segments": [{
                "type": "sign_off",
                "dialogue": [
                    {"speaker": "Claude", "text": "My prediction mentions YouTube."},
                    {"speaker": "ChatGPT", "text": "My prediction. Subscribe on YouTube and follow on Spotify."},
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
        self.assertEqual(script["segments"][0]["dialogue"][1]["text"], "My prediction.")

    def test_planned_clip_moment_is_forced_into_designated_turn(self):
        segment = {
            "type": "main_story",
            "beats": [],
            "clip_moment": "Use the seventy-percent figure to expose the stakes.",
        }
        prompt = _turn_prompt(
            segment, None, [], [], "Claude", 2, 4, "July 18, 2026",
            ["Claude", "ChatGPT"], "",
        )
        self.assertIn("PLANNED CLIP MOMENT", prompt)
        self.assertIn("Open with a decisive, standalone sentence", prompt)

    def test_structured_clip_moment_is_normalized_for_the_turn_prompt(self):
        segment = {
            "type": "frontier_board",
            "topic": "Weekly model movement",
            "beats": [],
            "clip_moment": {
                "hook": "Contrast the launch claim with independent evidence.",
                "format": "challenge and response",
            },
        }
        prompt = _turn_prompt(
            segment, None, [], [], "Claude", 0, 2, "July 17, 2026",
            ["Claude", "ChatGPT"], "",
        )
        self.assertIn("PLANNED CLIP MOMENT", prompt)
        self.assertIn("Contrast the launch claim", prompt)

    def test_turn_prompt_requires_short_syntax_bound_sentences(self):
        prompt = self._prompt("main_story", 1)
        self.assertIn("24-48 words", prompt)
        self.assertIn(f"no sentence over {MAX_SENTENCE_WORDS} words", prompt)
        self.assertIn("without a mid-clause breath", prompt)

    def test_speech_shape_flags_long_turns_and_sentences(self):
        long_sentence = " ".join(["word"] * (MAX_SENTENCE_WORDS + 1)) + "."
        self.assertTrue(_speech_shape_issues(long_sentence))
        short_sentences = " ".join(["One short sentence."] * 17)
        self.assertGreater(len(short_sentences.split()), MAX_TURN_WORDS)
        self.assertTrue(_speech_shape_issues(short_sentences))

    def test_speech_shape_flags_unmatched_quotation_mark(self):
        self.assertEqual(
            _speech_shape_issues('That cuts against "bigger means bloated.'),
            ["turn has an unmatched quotation mark"],
        )


class TtsCadenceTests(unittest.TestCase):
    def test_every_speaker_requires_continuous_syntax_bound_delivery(self):
        for speaker, settings in config.SPEAKERS.items():
            instructions = settings["voice_instructions"]
            self.assertIn("continuous, syntax-bound", instructions, speaker)
            self.assertIn("inside a clause", instructions, speaker)

    def test_tts_cache_format_is_versioned(self):
        self.assertGreaterEqual(TTS_FORMAT_VERSION, 2)


class TransitionCardTests(unittest.TestCase):
    def test_clip_cta_has_time_to_be_read(self):
        self.assertGreaterEqual(CTA_SECONDS, 3.0)

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

    def test_clip_cta_cards_are_portrait_and_platform_specific(self):
        from pipeline.video import PORTRAIT

        youtube = _render_clip_cta_card("youtube")
        social = _render_clip_cta_card("social")
        self.assertEqual(youtube.size, PORTRAIT)
        self.assertEqual(social.size, PORTRAIT)
        self.assertNotEqual(youtube.tobytes(), social.tobytes())


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

    def test_final_editor_can_choose_fewer_without_filling_a_quota(self):
        candidates = [
            {"title": "A", "score": 96},
            {"title": "B", "score": 91},
            {"title": "C", "score": 79},
        ]
        finalists = _resolve_finalist_numbers(
            [{"candidate_number": 2}, {"candidate_number": 2}, {"candidate_number": 99}],
            candidates,
        )
        self.assertEqual([c["title"] for c in finalists], ["B"])

    def test_finalist_resolution_has_no_arbitrary_upper_bound(self):
        candidates = [{"title": str(i), "score": 90} for i in range(12)]
        finalists = _resolve_finalist_numbers(
            [{"candidate_number": i} for i in range(1, 13)], candidates
        )
        self.assertEqual(len(finalists), 12)

    def test_fallback_drops_weak_candidates(self):
        candidates = [
            {"title": "Strong", "score": 94},
            {"title": "Weak", "score": 70},
        ]
        self.assertEqual(
            [c["title"] for c in _fallback_finalists(candidates)], ["Strong"]
        )

    def test_fallback_keeps_best_candidate_when_all_scores_are_weak(self):
        candidates = [
            {"title": "Best available", "score": 79},
            {"title": "Runner up", "score": 70},
        ]
        self.assertEqual(
            [c["title"] for c in _fallback_finalists(candidates)],
            ["Best available"],
        )


if __name__ == "__main__":
    unittest.main()
