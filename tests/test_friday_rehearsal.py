import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import main
import publish_site
from pipeline.script import SCRIPT_FORMAT_VERSION


def kimi_topic() -> dict:
    return {
        "rank": 1,
        "index": 1,
        "title": "Moonshot launches Kimi K3 frontier model",
        "summary": "Moonshot released a new flagship model.",
        "description": "Moonshot released a new flagship model.",
        "angle": "A major competitive landscape change.",
        "category": "main",
        "url": "https://www.kimi.com/blog/kimi-k3",
        "source": "Kimi",
        "tracked_players": ["moonshot"],
        "editorial_lane": "models_products",
        "must_cover": True,
        "must_cover_reason": "Major tracked-player event: Moonshot/Kimi",
    }


def kimi_audit() -> dict:
    return {
        "generated_at": "2026-07-17T03:00:00-07:00",
        "candidate_count": 1,
        "selected_count": 1,
        "candidates": [{
            "index": 1,
            "title": "Moonshot launches Kimi K3 frontier model",
            "description": "Moonshot released a new flagship model.",
            "source": "Kimi",
            "url": "https://www.kimi.com/blog/kimi-k3",
            "published": "2026-07-16T20:00:00Z",
            "tracked_players": ["moonshot"],
            "editorial_lane": "models_products",
            "must_cover": True,
            "must_cover_reason": "Major tracked-player event: Moonshot/Kimi",
            "selected": True,
            "selection_reason": "coverage_audit",
        }],
        "unresolved_must_cover": [],
        "model_high_impact_omissions": [],
        "priority_indexes": [1],
    }


def kimi_landscape() -> dict:
    return {
        "schema_version": 1,
        "week_start": "2026-07-11",
        "week_end": "2026-07-17",
        "headline": "Kimi K3 changed the frontier-model week",
        "summary": "Moonshot shipped a sourced flagship update.",
        "top_moves": [{
            "player_ids": ["moonshot"],
            "summary": "Moonshot launched Kimi K3.",
            "evidence_url": "https://www.kimi.com/blog/kimi-k3",
        }],
        "under_the_radar": [],
        "hype_check": [],
        "next_week": ["Watch independent Kimi K3 evaluations."],
        "players": [{
            "id": "moonshot",
            "name": "Moonshot/Kimi",
            "current_flagship": "Kimi K3",
            "changed": True,
            "change_summary": "Released Kimi K3.",
            "trajectory": "rising",
            "confidence": "high",
            "evidence": [{
                "claim": "Moonshot released Kimi K3.",
                "source_title": "Kimi launch post",
                "url": "https://www.kimi.com/blog/kimi-k3",
                "date": "2026-07-17",
            }],
            "last_covered": "2026-07-17",
            "watch_next": "Independent evaluations.",
        }],
        "coverage_metrics": {
            "days_audited": 7,
            "candidate_count": 80,
            "must_cover_count": 1,
            "must_cover_selected": 1,
            "must_cover_recall_percent": 100.0,
            "tracked_players_seen": ["moonshot"],
            "tracked_players_covered": ["moonshot"],
            "unresolved_must_cover": [],
        },
    }


class FridayPipelineRehearsalTests(unittest.TestCase):
    def test_kimi_fixture_flows_through_friday_and_reuses_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            script_calls = []

            def research(topics):
                enriched = []
                for topic in topics:
                    enriched.append({**topic, "brief": {
                        "key_facts": ["Moonshot released Kimi K3."],
                        "numbers_and_quotes": [],
                        "context": "A tracked frontier-model launch.",
                        "open_questions": ["How will independent tests compare it?"],
                        "sources": ["Kimi"],
                    }})
                return enriched

            def generate_script(topics, **kwargs):
                script_calls.append(kwargs)
                return {
                    "title": "Kimi K3 and the State of AI",
                    "description": "A Friday landscape review.",
                    "youtube_title": "Kimi K3 Changes the AI Model Race",
                    "roster": ["Claude", "ChatGPT"],
                    "special_note": "",
                    "episode_mode": kwargs["episode_mode"],
                    "landscape_week_end": kwargs["landscape"]["week_end"],
                    "script_format_version": SCRIPT_FORMAT_VERSION,
                    "segments": [{
                        "type": "week_in_review",
                        "topic": topics[0]["title"],
                        "dialogue": [
                            {"speaker": "Claude", "text": "Kimi K3 changed the week."},
                            {"speaker": "ChatGPT", "text": "The evidence puts Moonshot on the board."},
                        ],
                    }],
                }

            def synthesize(script, episode_dir):
                audio = episode_dir / "line.mp3"
                audio.write_bytes(b"mock mp3")
                return [{
                    "speaker": "Claude",
                    "text": "Kimi K3 changed the week.",
                    "audio_path": audio,
                    "segment_type": "week_in_review",
                    "topic": kimi_topic()["title"],
                    "index": 0,
                }]

            def create_file(path: Path, content: bytes = b"fixture") -> Path:
                path.write_bytes(content)
                return path

            patches = [
                patch.object(config, "OUTPUT_DIR", output_dir),
                patch.object(config, "get_episode_roster", return_value=["Claude", "ChatGPT"]),
                patch.object(main, "discover_topics_with_audit", return_value=([kimi_topic()], kimi_audit())),
                patch.object(main, "_generate_signal_scores", return_value={"overall": 9, "label": "Model launch", "categories": {"Models": 9}}),
                patch("pipeline.research.research_topics", side_effect=research),
                patch("pipeline.landscape.generate_landscape_snapshot", return_value=kimi_landscape()),
                patch("pipeline.memory.enrich_with_memory", return_value=None),
                patch.object(main, "generate_script", side_effect=generate_script),
                patch.object(main, "synthesize_script", side_effect=synthesize),
                patch.object(main, "assemble_episode", side_effect=lambda manifest, episode_dir, roster=None: create_file(episode_dir / "episode.mp3")),
                patch.object(main, "get_episode_duration", return_value=60.0),
                patch.object(main, "generate_landscape_video", side_effect=lambda manifest, audio, script, episode_dir: create_file(episode_dir / "episode_landscape.mp4")),
                patch.object(main, "generate_thumbnail", side_effect=lambda script, topics, episode_dir, roster=None: create_file(episode_dir / "thumbnail.png")),
                patch.object(main, "identify_clip_segments", return_value=[]),
                patch.object(main, "extract_clips", return_value={"youtube": [], "social": []}),
                patch.object(main.tracker, "save_report", return_value={"total_cost_usd": 0.0}),
            ]
            for active_patch in patches:
                active_patch.start()
                self.addCleanup(active_patch.stop)

            first = main.run_pipeline(no_upload=True, episode_date="2026-07-17")
            second = main.run_pipeline(no_upload=True, episode_date="2026-07-17")

            episode_dir = output_dir / "2026-07-17"
            audit = json.loads((episode_dir / "editorial_audit.json").read_text())
            landscape = json.loads((episode_dir / "landscape.json").read_text())
            script = json.loads((episode_dir / "script.json").read_text())

            self.assertEqual(first["status"], "complete_no_upload")
            self.assertEqual(second["status"], "complete_no_upload")
            self.assertTrue(audit["candidates"][0]["must_cover"])
            self.assertTrue(audit["candidates"][0]["selected"])
            self.assertEqual(landscape["players"][0]["current_flagship"], "Kimi K3")
            self.assertEqual(script["episode_mode"], "weekly_landscape")
            self.assertEqual(len(script_calls), 1)
            self.assertEqual(script_calls[0]["episode_mode"], "weekly_landscape")

            site_dir = Path(tmp) / "site"
            (site_dir / "static" / "articles").mkdir(parents=True)
            (site_dir / "static" / "articles.json").write_text("[]")
            publish_site.publish(episode_dir, site_dir)
            published_landscape = json.loads(
                (site_dir / "static" / "landscape.json").read_text()
            )
            self.assertEqual(published_landscape["week_end"], "2026-07-17")
            entries = json.loads((site_dir / "static" / "articles.json").read_text())
            self.assertEqual(entries[0]["episode_mode"], "weekly_landscape")

    def test_mid_pipeline_failure_resumes_from_completed_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            calls = {
                "discover": 0,
                "research": 0,
                "landscape": 0,
                "script": 0,
                "tts": 0,
            }

            def discover():
                calls["discover"] += 1
                return [kimi_topic()], kimi_audit()

            def research(topics):
                calls["research"] += 1
                return [{**topics[0], "brief": {"key_facts": ["Kimi K3 launched."]}}]

            def landscape(*args):
                calls["landscape"] += 1
                return kimi_landscape()

            def generate_script(topics, **kwargs):
                calls["script"] += 1
                return {
                    "title": "Kimi K3 and the State of AI",
                    "description": "A Friday landscape review.",
                    "roster": ["Claude", "ChatGPT"],
                    "special_note": "",
                    "episode_mode": "weekly_landscape",
                    "landscape_week_end": "2026-07-17",
                    "script_format_version": SCRIPT_FORMAT_VERSION,
                    "segments": [{
                        "type": "week_in_review",
                        "topic": topics[0]["title"],
                        "dialogue": [{"speaker": "Claude", "text": "Kimi K3 launched."}],
                    }],
                }

            def synthesize(script, episode_dir):
                calls["tts"] += 1
                if calls["tts"] == 1:
                    raise RuntimeError("simulated TTS outage")
                audio = episode_dir / "line.mp3"
                audio.write_bytes(b"mock mp3")
                return [{
                    "speaker": "Claude",
                    "text": "Kimi K3 launched.",
                    "audio_path": audio,
                    "segment_type": "week_in_review",
                    "topic": kimi_topic()["title"],
                    "index": 0,
                }]

            def create_file(path: Path) -> Path:
                path.write_bytes(b"fixture")
                return path

            patches = [
                patch.object(config, "OUTPUT_DIR", output_dir),
                patch.object(config, "get_episode_roster", return_value=["Claude", "ChatGPT"]),
                patch.object(main, "discover_topics_with_audit", side_effect=discover),
                patch.object(main, "_generate_signal_scores", return_value=None),
                patch("pipeline.research.research_topics", side_effect=research),
                patch("pipeline.landscape.generate_landscape_snapshot", side_effect=landscape),
                patch("pipeline.memory.enrich_with_memory", return_value=None),
                patch.object(main, "generate_script", side_effect=generate_script),
                patch.object(main, "synthesize_script", side_effect=synthesize),
                patch.object(main, "assemble_episode", side_effect=lambda *args, **kwargs: create_file(output_dir / "2026-07-17" / "episode.mp3")),
                patch.object(main, "get_episode_duration", return_value=60.0),
                patch.object(main, "generate_landscape_video", side_effect=lambda *args, **kwargs: create_file(output_dir / "2026-07-17" / "episode_landscape.mp4")),
                patch.object(main, "generate_thumbnail", side_effect=lambda *args, **kwargs: create_file(output_dir / "2026-07-17" / "thumbnail.png")),
                patch.object(main, "identify_clip_segments", return_value=[]),
                patch.object(main, "extract_clips", return_value={"youtube": [], "social": []}),
                patch.object(main.tracker, "save_report", return_value={"total_cost_usd": 0.0}),
            ]
            for active_patch in patches:
                active_patch.start()
                self.addCleanup(active_patch.stop)

            with self.assertRaisesRegex(RuntimeError, "simulated TTS outage"):
                main.run_pipeline(no_upload=True, episode_date="2026-07-17")

            result = main.run_pipeline(no_upload=True, episode_date="2026-07-17")

            self.assertEqual(result["status"], "complete_no_upload")
            self.assertEqual(calls, {
                "discover": 1,
                "research": 1,
                "landscape": 1,
                "script": 1,
                "tts": 2,
            })


if __name__ == "__main__":
    unittest.main()
