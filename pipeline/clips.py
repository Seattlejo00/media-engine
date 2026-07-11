"""
Clip extractor.
Identifies the most engaging segments and cuts short-form clips
for social media (TikTok, YouTube Shorts, X).
"""

import json
import logging
from pathlib import Path

from moviepy import AudioFileClip, CompositeVideoClip, concatenate_videoclips
from openai import OpenAI

import config
from pipeline.cost_tracker import tracker
from pipeline.video import PORTRAIT, _create_speaker_frame, _estimate_duration

logger = logging.getLogger(__name__)


def identify_clip_segments(script: dict) -> list[dict]:
    """
    Use AI to identify the most clip-worthy moments in the script.
    Returns segment indices and descriptions for the best 3-4 clips.
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    # Flatten all dialogue with indices
    all_lines = []
    global_idx = 0
    for seg_idx, segment in enumerate(script.get("segments", [])):
        for line_idx, line in enumerate(segment.get("dialogue", [])):
            all_lines.append(
                {
                    "global_index": global_idx,
                    "segment_index": seg_idx,
                    "segment_type": segment.get("type", ""),
                    "speaker": line["speaker"],
                    "text": line["text"],
                }
            )
            global_idx += 1

    lines_text = "\n".join(
        f"[{l['global_index']}] {l['speaker']}: {l['text']}" for l in all_lines
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a social media content editor. Identify the 3-4 best "
                    "moments from this podcast transcript that would make great "
                    "short-form clips (30-60 seconds each). Look for:\n"
                    "- Surprising takes or hot takes\n"
                    "- Disagreements between hosts\n"
                    "- Funny moments\n"
                    "- Highly quotable lines\n"
                    "- Moments with strong emotional resonance\n\n"
                    "Return JSON: {\"clips\": [{\"start_index\": N, \"end_index\": M, "
                    "\"title\": \"catchy clip title\", \"hook\": \"first line that "
                    "grabs attention\"}]}\n"
                    "Each clip should span 3-8 consecutive lines."
                ),
            },
            {"role": "user", "content": f"Transcript:\n{lines_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    # Track usage
    usage = response.usage
    if usage:
        tracker.record(
            step="clip_identification", model="gpt-4o-mini",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

    try:
        result = json.loads(response.choices[0].message.content)
        return result.get("clips", [])
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Failed to identify clips: {e}")
        return []


def extract_clips(
    clip_segments: list[dict],
    audio_manifest: list[dict],
    script: dict,
    output_dir: Path,
) -> list[Path]:
    """
    Extract short-form video clips in portrait mode.

    Returns list of paths to generated clip MP4s.
    """
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []

    for clip_idx, clip_info in enumerate(clip_segments):
        start = clip_info.get("start_index", 0)
        end = clip_info.get("end_index", start + 5)
        title = clip_info.get("title", f"clip_{clip_idx}")

        # Get the relevant audio segments
        relevant_entries = [
            e for e in audio_manifest if start <= e["index"] <= end
        ]

        if not relevant_entries:
            logger.warning(f"No audio segments found for clip {clip_idx}")
            continue

        try:
            clip_path = _render_clip(
                relevant_entries, title, clip_idx, clips_dir
            )
            clip_paths.append(clip_path)
            logger.info(f"Clip {clip_idx}: {title} -> {clip_path.name}")
        except Exception as e:
            logger.error(f"Failed to render clip {clip_idx}: {e}")
            continue

    logger.info(f"Generated {len(clip_paths)} clips")
    return clip_paths


def _render_clip(
    entries: list[dict],
    title: str,
    clip_idx: int,
    output_dir: Path,
) -> Path:
    """Render a single short-form clip as portrait video."""
    video_clips = []
    audio_clips = []

    for entry in entries:
        duration = _estimate_duration(entry["audio_path"])

        # Create portrait video frame (clip title doubles as the headline)
        frame = _create_speaker_frame(
            entry["speaker"], entry["text"], duration, PORTRAIT, topic=title
        )
        video_clips.append(frame)

        audio_clip = AudioFileClip(str(entry["audio_path"]))
        audio_clips.append(audio_clip)

    # Concatenate
    video = concatenate_videoclips(video_clips, method="compose")

    # Concatenate audio using CompositeAudioClip with sequential offsets
    from moviepy import CompositeAudioClip
    offset = 0
    positioned_audio = []
    for ac in audio_clips:
        positioned_audio.append(ac.with_start(offset))
        offset += ac.duration
    audio = CompositeAudioClip(positioned_audio)

    video = video.with_audio(audio)

    # Only hard-truncate if way over limit (let dialogue finish naturally)
    max_duration = config.CLIP_DURATION_SECONDS
    if video.duration > max_duration * 1.5:
        video = video.subclipped(0, max_duration)

    # Export
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:40]
    output_path = output_dir / f"clip_{clip_idx}_{safe_title}.mp4"

    video.write_videofile(
        str(output_path),
        fps=1,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger="bar",
    )

    video.close()
    for ac in audio_clips:
        ac.close()

    return output_path
