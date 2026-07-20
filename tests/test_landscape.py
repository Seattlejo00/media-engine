import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import config
import main
from main import _episode_date, _validate_episode_date_override
import pipeline.landscape as landscape_module
import pipeline.topics as topics_module
from pipeline.landscape import (
    _normalize_snapshot,
    friday_review_profile,
    is_weekly_review,
)
from pipeline.script import _build_episode_prompt, _topics_block
from pipeline.topics import (
    TRACKED_PLAYERS,
    _force_priority_stories,
    audit_candidates,
    consolidate_topic_events,
    rank_topics,
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

    def test_malformed_ranking_fallback_preserves_late_must_cover_story(self):
        articles = audit_candidates([
            {
                "title": f"Routine AI item {index}",
                "description": "Routine product coverage.",
                "source": "News",
                "url": f"https://example.com/{index}",
            }
            for index in range(1, 6)
        ] + [{
            "title": "Moonshot launches Kimi K3 frontier model",
            "description": "Moonshot released its new flagship model.",
            "source": "Kimi",
            "url": "https://kimi.com/k3",
        }])
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{bad json"))],
            usage=None,
        )
        client = MagicMock()
        client.chat.completions.create.return_value = response
        with patch("openai.OpenAI", return_value=client):
            selected = rank_topics(articles)
        self.assertIn(6, [item["index"] for item in selected])
        kimi = next(item for item in selected if item["index"] == 6)
        self.assertTrue(kimi["must_cover"])
        self.assertEqual(kimi["url"], "https://kimi.com/k3")

    def test_no_newsapi_key_skips_official_source_request_cleanly(self):
        with patch.object(topics_module.config, "NEWS_API_KEY", ""):
            self.assertEqual(topics_module.fetch_official_updates(), [])

    def test_duplicate_launch_articles_collapse_to_one_editorial_event(self):
        events = consolidate_topic_events(audit_candidates([
            {
                "title": "Moonshot launches Kimi K3 frontier model",
                "description": "Moonshot released its new Kimi K3 flagship.",
                "source": "Kimi",
                "url": "https://kimi.com/k3",
            },
            {
                "title": "Kimi K3 release shakes up the model race",
                "description": "The Kimi K3 launch is Moonshot's new flagship.",
                "source": "AI News",
                "url": "https://news.example/kimi-k3",
            },
            {
                "title": "A closer look at Moonshot's Kimi K3 launch",
                "description": "Moonshot shipped Kimi K3 this week.",
                "source": "Tech Wire",
                "url": "https://wire.example/kimi-k3",
            },
        ]))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_article_count"], 3)
        self.assertEqual(len(events[0]["supporting_articles"]), 2)
        self.assertTrue(events[0]["must_cover"])
        rerun = consolidate_topic_events(events)
        self.assertEqual(rerun[0]["event_article_count"], 3)
        self.assertEqual(len(rerun[0]["supporting_articles"]), 2)

    def test_same_model_different_action_remains_a_separate_event(self):
        events = consolidate_topic_events(audit_candidates([
            {
                "title": "Moonshot launches Kimi K3 frontier model",
                "description": "Moonshot released its new flagship.",
                "source": "Kimi",
                "url": "https://kimi.com/k3",
            },
            {
                "title": "Moonshot changes Kimi K3 API pricing",
                "description": "New Kimi K3 prices take effect next month.",
                "source": "Kimi",
                "url": "https://kimi.com/k3-pricing",
            },
        ]))
        self.assertEqual(len(events), 2)

    def test_legacy_research_checkpoint_clusters_launch_analysis_across_lanes(self):
        events = consolidate_topic_events(audit_candidates([
            {
                "title": "Kimi K3 is now the most intelligent model",
                "summary": "Moonshot AI launched Kimi K3 and it leads benchmarks.",
                "source": "Analysis A",
                "url": "https://example.com/kimi-analysis",
                "editorial_lane": "research",
                "tracked_players": ["moonshot"],
            },
            {
                "title": "New Moonshot Kimi K3 challenges GPT-5.6",
                "summary": "Kimi K3 was unveiled by Moonshot AI this week.",
                "source": "Analysis B",
                "url": "https://example.com/kimi-comparison",
                "editorial_lane": "models_products",
                "tracked_players": ["moonshot", "openai"],
            },
            {
                "title": "Kimi K3 may impact Anthropic valuation",
                "summary": "Moonshot launched Kimi K3 with implications for rivals.",
                "source": "Analysis C",
                "url": "https://example.com/kimi-valuation",
                "editorial_lane": "models_products",
                "tracked_players": ["moonshot", "anthropic"],
            },
            {
                "title": "Moonshot releases Kimi K3 open-source model",
                "summary": "Moonshot's Kimi K3 release rattled global markets.",
                "source": "Analysis D",
                "url": "https://example.com/kimi-release",
                "editorial_lane": "models_products",
                "tracked_players": ["moonshot"],
            },
        ]))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_article_count"], 4)


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
        self.assertIn("hybrid daily AI briefing", prompt)
        self.assertIn("Never pad a quiet week", prompt)
        self.assertIn("weekly-review share: about 25%", prompt)
        self.assertIn("Add 1-2 daily_news segments", prompt)
        self.assertIn("frontier_board", prompt)
        self.assertIn("under_the_radar", prompt)
        self.assertIn("hype_check", prompt)

    def test_quiet_friday_is_short_with_one_compact_weekly_beat(self):
        profile = friday_review_profile(
            {
                "top_moves": [{
                    "player_ids": ["moonshot"],
                    "summary": "Moonshot launched Kimi K3.",
                    "evidence_url": "https://kimi.com/k3",
                }],
                "under_the_radar": [],
                "hype_check": [],
            },
            [{
                "title": "Moonshot launches Kimi K3 frontier model",
                "description": "Moonshot released its new Kimi K3 flagship.",
                "tracked_players": ["moonshot"],
                "editorial_lane": "models_products",
            }],
            max_duration=12,
        )
        self.assertEqual(profile["scale"], "quiet")
        self.assertEqual(profile["target_duration_minutes"], 6)
        self.assertEqual(profile["weekly_review_share"], 0.25)

    def test_standard_friday_balances_daily_and_weekly_coverage(self):
        profile = friday_review_profile({
            "top_moves": [
                {
                    "player_ids": ["moonshot"],
                    "summary": "Moonshot launched Kimi K3.",
                    "evidence_url": "https://kimi.com/k3",
                },
                {
                    "player_ids": ["openai"],
                    "summary": "OpenAI released a new agent product.",
                    "evidence_url": "https://openai.com/agent",
                },
            ],
            "under_the_radar": [{
                "summary": "AI labor protests spread to another studio.",
                "evidence_url": "https://news.example/protests",
            }, {
                "summary": "Kimi K3 may pressure incumbent valuations.",
                "evidence_url": "https://news.example/kimi-valuation",
            }],
            "hype_check": [{
                "summary": "Claims that Kimi K3 dominates every benchmark ran ahead of evidence.",
                "evidence_url": "https://news.example/kimi-hype",
            }],
        }, [{
            "title": "Moonshot launched Kimi K3",
            "summary": "Moonshot released a new flagship.",
            "url": "https://kimi.com/k3",
            "tracked_players": ["moonshot"],
            "editorial_lane": "models_products",
            "supporting_articles": [
                {"url": "https://news.example/kimi-valuation"},
                {"url": "https://news.example/kimi-hype"},
            ],
        }, {
            "title": "OpenAI released a new agent product",
            "url": "https://openai.com/agent",
            "tracked_players": ["openai"],
            "editorial_lane": "models_products",
        }, {
            "title": "AI labor protests spread",
            "url": "https://news.example/protests",
            "tracked_players": [],
            "editorial_lane": "models_products",
        }], max_duration=12)
        self.assertEqual(profile["scale"], "standard")
        self.assertEqual(profile["target_duration_minutes"], 8)
        self.assertEqual(profile["weekly_review_share"], 0.5)
        self.assertEqual(profile["distinct_weekly_events"], 3)

    def test_busy_friday_allows_weekly_review_to_dominate(self):
        events = [
            {
                "player_ids": [player],
                "summary": summary,
                "evidence_url": f"https://example.com/{index}",
            }
            for index, (player, summary) in enumerate([
                ("openai", "OpenAI released GPT-6."),
                ("anthropic", "Anthropic launched Claude 6."),
                ("google", "Google shipped Gemini 5."),
            ])
        ]
        profile = friday_review_profile({
            "top_moves": events,
            "under_the_radar": [
                {
                    "summary": "A major AI acquisition closed.",
                    "evidence_url": "https://example.com/acquisition",
                },
                {
                    "summary": "A new national AI law passed.",
                    "evidence_url": "https://example.com/law",
                },
            ],
            "hype_check": [
                {
                    "summary": "A disputed benchmark claim drew attention.",
                    "evidence_url": "https://example.com/benchmark",
                },
            ],
        }, max_duration=12)
        self.assertEqual(profile["scale"], "dominant")
        self.assertEqual(profile["target_duration_minutes"], 12)
        self.assertEqual(profile["weekly_review_share"], 0.75)

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
            allowed_evidence={
                "https://trusted.example/story": {
                    "url": "https://trusted.example/story",
                    "title": "Trusted story",
                    "date": "2026-07-17",
                    "players": ["moonshot"],
                }
            },
        )
        moonshot = next(
            player for player in snapshot["players"] if player["id"] == "moonshot"
        )
        self.assertFalse(moonshot["changed"])
        self.assertEqual(moonshot["trajectory"], "unclear")
        self.assertEqual(moonshot["evidence"], [])
        self.assertEqual(moonshot["current_flagship"], "Unknown")

    def test_recognized_evidence_for_another_player_cannot_support_movement(self):
        url = "https://trusted.example/kimi-launch"
        snapshot = _normalize_snapshot(
            {"players": [{
                "id": "openai",
                "current_flagship": "Invented Model X",
                "changed": True,
                "change_summary": "OpenAI shipped Invented Model X.",
                "trajectory": "rising",
                "confidence": "high",
                "evidence": [{
                    "claim": "OpenAI shipped Invented Model X.",
                    "source_title": "Invented source title",
                    "url": url,
                    "date": "2026-07-17",
                }],
            }]},
            previous=None,
            date_str="2026-07-17",
            allowed_evidence={
                url: {
                    "url": url,
                    "title": "Moonshot launches Kimi K3",
                    "date": "2026-07-17",
                    "players": ["moonshot"],
                }
            },
        )
        openai = next(
            player for player in snapshot["players"] if player["id"] == "openai"
        )
        self.assertFalse(openai["changed"])
        self.assertEqual(openai["trajectory"], "unclear")
        self.assertEqual(openai["evidence"], [])
        self.assertEqual(openai["current_flagship"], "Unknown")

    def test_top_move_drops_players_not_named_by_its_evidence(self):
        url = "https://trusted.example/kimi-launch"
        snapshot = _normalize_snapshot(
            {
                "top_moves": [{
                    "player_ids": ["openai"],
                    "summary": "OpenAI supposedly moved.",
                    "evidence_url": url,
                }],
                "players": [],
            },
            previous=None,
            date_str="2026-07-17",
            allowed_evidence={
                url: {
                    "url": url,
                    "title": "Moonshot launches Kimi K3",
                    "date": "2026-07-17",
                    "players": ["moonshot"],
                }
            },
        )
        self.assertEqual(snapshot["top_moves"], [])

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
