import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import main
from main import _episode_date, _validate_episode_date_override
import pipeline.landscape as landscape_module
import pipeline.topics as topics_module
from pipeline.landscape import _normalize_snapshot, is_weekly_review
from pipeline.script import _build_episode_prompt, _topics_block
from pipeline.topics import (
    TRACKED_PLAYERS,
    _force_priority_stories,
    audit_candidates,
)


class CoverageAuditTests(unittest.TestCase):
    def test_kimi_model_launch_is_a_must_cover_moonshot_event(self):
        [candidate] = audit_candidates([{
            "title": "Moonshot launches Kimi K3 frontier model",
            "description": "The new flagship is available through Kimi and its API.",
            "source": "Moonshot AI",
            "url": "https://www.kimi.com/blog/kimi-k3",
        }])
        self.assertTrue(candidate["must_cover"])
        self.assertIn("moonshot", candidate["tracked_players"])
        self.assertEqual(candidate["source_priority"], 0)

    def test_priority_candidate_replaces_a_lower_ranked_story(self):
        articles = audit_candidates([
            {"title": "Routine AI survey", "description": "", "source": "News", "url": "https://example.com/1"},
            {"title": "Moonshot releases Kimi K3 flagship model", "description": "", "source": "Kimi", "url": "https://kimi.com/k3"},
        ])
        selected = _force_priority_stories(
            [{"index": 1, "title": articles[0]["title"], "category": "main"}],
            articles,
            [2],
            limit=1,
        )
        self.assertEqual(selected[0]["index"], 2)
        self.assertEqual(selected[0]["selection_reason"], "coverage_audit")

    def test_must_cover_marker_reaches_the_showrunner(self):
        block = _topics_block([{
            "title": "Moonshot releases Kimi K3",
            "category": "main",
            "must_cover": True,
            "summary": "A major launch.",
        }])
        self.assertIn("[MUST COVER]", block)

    def test_more_than_six_must_cover_events_respects_episode_ceiling(self):
        articles = audit_candidates([
            {
                "title": f"Moonshot launches Kimi model {index}",
                "description": "A new flagship model.",
                "source": "Kimi",
                "url": f"https://kimi.com/model-{index}",
            }
            for index in range(8)
        ])
        selected = _force_priority_stories([], articles, list(range(1, 9)), limit=6)
        self.assertEqual(len(selected), 6)
        self.assertEqual([item["index"] for item in selected], list(range(1, 7)))

    def test_no_newsapi_key_skips_official_source_request_cleanly(self):
        with patch.object(topics_module.config, "NEWS_API_KEY", ""):
            self.assertEqual(topics_module.fetch_official_updates(), [])


class WeeklyLandscapeTests(unittest.TestCase):
    def test_friday_switches_to_weekly_review(self):
        self.assertTrue(is_weekly_review("2026-07-17"))
        self.assertFalse(is_weekly_review("2026-07-19"))

    def test_date_override_can_force_friday_for_non_publishing_rehearsal(self):
        _validate_episode_date_override(
            "2026-07-17", no_upload=True, script_only=False, dry_run=False
        )
        self.assertEqual(_episode_date("2026-07-17"), "2026-07-17")
        self.assertTrue(is_weekly_review(_episode_date("2026-07-17")))

    def test_date_override_cannot_publish(self):
        with self.assertRaisesRegex(ValueError, "test-only"):
            _validate_episode_date_override(
                "2026-07-17", no_upload=False, script_only=False, dry_run=False
            )

    def test_weekly_mode_uses_landscape_run_of_show(self):
        prompt = _build_episode_prompt(
            [{"title": "A sourced model launch", "summary": "Launch details."}],
            "July 17, 2026",
            ["Claude", "ChatGPT"],
            episode_mode="weekly_landscape",
            landscape={
                "headline": "A launch changed the week",
                "week_end": "2026-07-17",
                "players": [],
            },
        )
        self.assertIn("Friday weekly AI-landscape review", prompt)
        self.assertIn("frontier_board", prompt)
        self.assertIn("under_the_radar", prompt)
        self.assertIn("hype_check", prompt)

    def test_missing_players_are_preserved_as_unclear_not_invented_movement(self):
        snapshot = _normalize_snapshot(
            {
                "headline": "One verified move",
                "players": [{
                    "id": "moonshot",
                    "current_flagship": "Kimi K3",
                    "changed": True,
                    "change_summary": "Released Kimi K3.",
                    "trajectory": "rising",
                    "confidence": "high",
                    "evidence": [],
                }],
            },
            previous=None,
            date_str="2026-07-17",
        )
        self.assertEqual(len(snapshot["players"]), len(TRACKED_PLAYERS))
        openai = next(player for player in snapshot["players"] if player["id"] == "openai")
        self.assertFalse(openai["changed"])
        self.assertEqual(openai["trajectory"], "unclear")
        self.assertEqual(openai["current_flagship"], "Unknown")

    def test_unrecognized_evidence_url_cannot_support_player_movement(self):
        snapshot = _normalize_snapshot(
            {"players": [{
                "id": "moonshot",
                "current_flagship": "Invented Kimi K9",
                "changed": True,
                "change_summary": "Claimed movement.",
                "trajectory": "rising",
                "confidence": "high",
                "evidence": [{
                    "claim": "Unsupported",
                    "source_title": "Invented",
                    "url": "https://invented.example/story",
                    "date": "2026-07-17",
                }],
            }]},
            previous=None,
            date_str="2026-07-17",
            allowed_urls={"https://trusted.example/story"},
        )
        moonshot = next(
            player for player in snapshot["players"] if player["id"] == "moonshot"
        )
        self.assertFalse(moonshot["changed"])
        self.assertEqual(moonshot["trajectory"], "unclear")
        self.assertEqual(moonshot["evidence"], [])
        self.assertEqual(moonshot["current_flagship"], "Unknown")

    def test_duplicate_player_rows_collapse_to_one_registry_entry(self):
        snapshot = _normalize_snapshot(
            {"players": [
                {"id": "moonshot", "current_flagship": "Old value"},
                {"id": "moonshot", "current_flagship": "Kimi K3"},
            ]},
            previous=None,
            date_str="2026-07-17",
        )
        moonshot_rows = [
            player for player in snapshot["players"] if player["id"] == "moonshot"
        ]
        self.assertEqual(len(moonshot_rows), 1)
        self.assertEqual(moonshot_rows[0]["current_flagship"], "Kimi K3")

    def test_r2_unavailable_returns_no_previous_snapshot(self):
        with patch.object(landscape_module, "hosting_configured", return_value=False):
            self.assertIsNone(landscape_module.load_landscape_snapshot())

    def test_corrupt_r2_snapshot_is_ignored(self):
        class CorruptClient:
            def download_fileobj(self, bucket, key, destination):
                destination.write(b"{not json")

        with (
            patch.object(landscape_module, "hosting_configured", return_value=True),
            patch.object(landscape_module, "_r2_client", return_value=CorruptClient()),
        ):
            self.assertIsNone(landscape_module.load_landscape_snapshot())

    def test_corrupt_local_audit_is_reconstructed_from_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            episode_dir = output_dir / "2026-07-17"
            episode_dir.mkdir()
            topics = [{
                "title": "Moonshot launches Kimi K3",
                "description": "A new flagship model.",
                "url": "https://kimi.com/k3",
                "source": "Kimi",
                "must_cover": True,
            }]
            (episode_dir / "topics.json").write_text(json.dumps(topics))
            (episode_dir / "editorial_audit.json").write_text("{not json")
            rebuilt = {
                "candidate_count": 1,
                "selected_count": 1,
                "candidates": [{"title": topics[0]["title"], "selected": True}],
            }

            with (
                patch.object(config, "OUTPUT_DIR", output_dir),
                patch.object(config, "get_episode_roster", return_value=["Claude", "ChatGPT"]),
                patch.object(main, "audit_existing_topics", return_value=rebuilt) as audit,
            ):
                summary = main.run_pipeline(
                    dry_run=True, episode_date="2026-07-17"
                )

            self.assertEqual(summary["status"], "dry_run_complete")
            audit.assert_called_once_with(topics)
            self.assertEqual(
                json.loads((episode_dir / "editorial_audit.json").read_text()),
                rebuilt,
            )


if __name__ == "__main__":
    unittest.main()
