import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import main


class ClipOnlyRecoveryTests(unittest.TestCase):
    def test_recovery_reuses_legacy_speech_and_uploads_every_selected_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "output"
            episode_dir = output_root / "2026-07-19"
            audio_dir = episode_dir / "audio_segments"
            audio_dir.mkdir(parents=True)

            script = {
                "title": "Recovered episode",
                "roster": ["Claude", "ChatGPT"],
                "segments": [],
            }
            (episode_dir / "script.json").write_text(json.dumps(script))
            audio_path = audio_dir / "000_claude_main_story.mp3"
            audio_path.touch()
            # July 19 predates TTS_FORMAT_VERSION in the manifest. Clip-only
            # recovery intentionally accepts it without regenerating speech.
            (episode_dir / "audio_manifest.json").write_text(json.dumps([{
                "speaker": "Claude",
                "text": "Existing speech",
                "audio_path": str(audio_path),
                "segment_type": "main_story",
                "topic": "Test",
                "index": 0,
            }]))
            (episode_dir / "episode.mp3").touch()
            (episode_dir / "episode_landscape.mp4").touch()
            (episode_dir / "clip_segments.json").write_text("[]")
            (episode_dir / "distribution_state.json").write_text(json.dumps({
                "youtube_episode_id": "episode123",
                "youtube_clip_ids": {},
                "podcast_audio_url": "https://example.com/episode.mp3",
            }))

            selected = [
                {"start_index": 0, "end_index": 0, "title": "First"},
                {"start_index": 0, "end_index": 0, "title": "Second"},
            ]
            youtube_paths = [
                episode_dir / "clips" / "youtube" / "clip_0.mp4",
                episode_dir / "clips" / "youtube" / "clip_1.mp4",
            ]
            for path in youtube_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            with (
                patch.object(config, "OUTPUT_DIR", output_root),
                patch("main._episode_date", return_value="2026-07-19"),
                patch("main.identify_clip_segments", return_value=selected),
                patch("main.extract_clips", return_value={
                    "youtube": youtube_paths,
                    "social": [],
                }),
                patch("main.upload_clip", side_effect=["short1", "short2"]) as upload,
            ):
                summary = main.run_clips_only()

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["youtube_clip_ids"], ["short1", "short2"])
            self.assertEqual(upload.call_count, 2)
            self.assertTrue(audio_path.exists())
            self.assertTrue((episode_dir / "episode.mp3").exists())
            self.assertTrue((episode_dir / "episode_landscape.mp4").exists())
            self.assertEqual(
                json.loads((episode_dir / "script.json").read_text()), script
            )
            ledger = json.loads(
                (episode_dir / "distribution_state.json").read_text()
            )
            self.assertEqual(
                ledger["youtube_clip_ids"], {"0": "short1", "1": "short2"}
            )
            self.assertEqual(
                ledger["podcast_audio_url"], "https://example.com/episode.mp3"
            )


class TtsCacheInvalidationTests(unittest.TestCase):
    def test_tts_clear_preserves_script_research_and_upload_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode_dir = Path(tmp)
            for directory in ("audio_segments", "clips"):
                (episode_dir / directory).mkdir()
            for filename in (
                "audio_manifest.json",
                "episode.mp3",
                "chapters.json",
                "episode_landscape.mp4",
                "clip_segments.json",
                "summary.json",
                "script.json",
                "research.json",
                "distribution_state.json",
            ):
                (episode_dir / filename).touch()

            main._clear_tts_outputs(episode_dir)

            self.assertFalse((episode_dir / "audio_segments").exists())
            self.assertFalse((episode_dir / "episode.mp3").exists())
            self.assertFalse((episode_dir / "episode_landscape.mp4").exists())
            self.assertTrue((episode_dir / "script.json").exists())
            self.assertTrue((episode_dir / "research.json").exists())
            self.assertTrue((episode_dir / "distribution_state.json").exists())


if __name__ == "__main__":
    unittest.main()
