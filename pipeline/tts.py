"""
Text-to-Speech pipeline.
Converts script dialogue into audio files using OpenAI TTS.
Supports swapping to ElevenLabs later.
"""

import logging
from pathlib import Path

from openai import OpenAI

import config
from pipeline.cost_tracker import tracker

logger = logging.getLogger(__name__)

# Bump whenever voice prompting or synthesis semantics change. Cached manifests
# without the current version are regenerated with all downstream media.
TTS_FORMAT_VERSION = 2

def synthesize_line(
    client: OpenAI, text: str, speaker: str, output_path: Path
) -> Path:
    """Convert a single line of dialogue to an MP3 file."""
    speaker_config = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])

    kwargs = {
        "model": config.TTS_MODEL,
        "voice": speaker_config["voice"],
        "input": text,
        "speed": speaker_config["tts_speed"],
        "response_format": "mp3",
    }
    # instructions steer delivery but are rejected by the legacy tts-1 models
    instructions = speaker_config.get("voice_instructions")
    if instructions and not config.TTS_MODEL.startswith("tts-1"):
        kwargs["instructions"] = instructions

    try:
        response = client.audio.speech.create(**kwargs)
    except Exception as e:
        if config.TTS_MODEL == "tts-1-hd":
            raise
        logger.warning(f"TTS with {config.TTS_MODEL} failed ({e}); retrying with tts-1-hd")
        kwargs.pop("instructions", None)
        kwargs["model"] = "tts-1-hd"
        response = client.audio.speech.create(**kwargs)

    response.stream_to_file(str(output_path))
    tracker.record_tts(len(text))
    logger.debug(f"TTS: {speaker} -> {output_path.name}")
    return output_path


def synthesize_script(script: dict, output_dir: Path) -> list[dict]:
    """
    Convert entire script to individual audio files.

    Returns a list of dicts:
    [{"speaker": "Claude", "text": "...", "audio_path": Path, "segment": "...", "index": 0}, ...]
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    audio_dir = output_dir / "audio_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)

    audio_manifest = []
    global_index = 0

    for seg_idx, segment in enumerate(script.get("segments", [])):
        segment_type = segment.get("type", "unknown")

        for line_idx, line in enumerate(segment.get("dialogue", [])):
            speaker = line["speaker"]
            text = line["text"]

            if not text.strip():
                continue

            filename = f"{global_index:03d}_{speaker.lower()}_{segment_type}.mp3"
            audio_path = audio_dir / filename

            try:
                synthesize_line(client, text, speaker, audio_path)
                audio_manifest.append(
                    {
                        "tts_format_version": TTS_FORMAT_VERSION,
                        "speaker": speaker,
                        "text": text,
                        "audio_path": audio_path,
                        "segment_type": segment_type,
                        "topic": segment.get("topic"),
                        "index": global_index,
                    }
                )
                global_index += 1
            except Exception as e:
                logger.error(f"TTS failed for line {global_index} ({speaker}): {e}")
                continue

    logger.info(f"Synthesized {len(audio_manifest)} audio segments")
    return audio_manifest
