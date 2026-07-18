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
from pipeline.video import PORTRAIT, _create_speaker_frames, _estimate_duration

logger = logging.getLogger(__name__)

MIN_CLIP_SECONDS = 20
MAX_CLIP_SECONDS = 58
MAX_CLIPS = 4


def _estimated_seconds(text: str) -> float:
    """Estimate brisk podcast speech duration, including a short turn gap."""
    return max(1.0, len(text.split()) / 2.75 + 0.3)


def _flatten_dialogue(script: dict) -> list[dict]:
    """Flatten the script into the same global index space used by TTS."""
    all_lines = []
    global_idx = 0
    for seg_idx, segment in enumerate(script.get("segments", [])):
        for line in segment.get("dialogue", []):
            text = (line.get("text") or "").strip()
            if not text:
                continue
            all_lines.append(
                {
                    "global_index": global_idx,
                    "segment_index": seg_idx,
                    "segment_type": segment.get("type", ""),
                    "topic": segment.get("topic") or "",
                    "speaker": line["speaker"],
                    "text": text,
                    "estimated_seconds": _estimated_seconds(text),
                }
            )
            global_idx += 1
    return all_lines


def _score_value(clip: dict) -> float:
    try:
        return float(clip.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_clip_segments(raw_clips: list[dict], all_lines: list[dict]) -> list[dict]:
    """Validate, de-overlap, duration-fit, and rank model-selected clips."""
    by_index = {line["global_index"]: line for line in all_lines}
    normalized: list[dict] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start <= existing["end_index"] and end >= existing["start_index"]
                   for existing in normalized)

    ranked = sorted(
        (clip for clip in raw_clips if isinstance(clip, dict)),
        key=_score_value,
        reverse=True,
    )

    for clip in ranked:
        try:
            start = int(clip["start_index"])
            end = int(clip["end_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if start > end:
            start, end = end, start
        if start not in by_index or end not in by_index:
            continue

        segment_index = by_index[start]["segment_index"]
        segment_lines = [
            line for line in all_lines
            if line["segment_index"] == segment_index
            and line["segment_type"] not in ("intro", "sign_off")
        ]
        if not segment_lines or by_index[end]["segment_index"] != segment_index:
            continue

        segment_indices = [line["global_index"] for line in segment_lines]
        if start not in segment_indices or end not in segment_indices:
            continue

        # Extend short selections with complete turns from the same segment;
        # contract long ones from the tail. Never create a mid-sentence cut.
        selected = [line for line in segment_lines if start <= line["global_index"] <= end]
        duration = sum(line["estimated_seconds"] for line in selected)
        cursor = segment_indices.index(end) + 1
        while duration < MIN_CLIP_SECONDS and cursor < len(segment_lines):
            candidate = segment_lines[cursor]
            if duration + candidate["estimated_seconds"] > MAX_CLIP_SECONDS:
                break
            selected.append(candidate)
            end = candidate["global_index"]
            duration += candidate["estimated_seconds"]
            cursor += 1
        while duration > MAX_CLIP_SECONDS and len(selected) > 1:
            removed = selected.pop()
            duration -= removed["estimated_seconds"]
            end = selected[-1]["global_index"]

        if not selected or duration > MAX_CLIP_SECONDS or overlaps(start, end):
            continue

        title = str(clip.get("title") or "Must-See AI Moment").strip()[:70]
        hook = str(clip.get("on_screen_hook") or clip.get("hook") or title).strip()[:70]
        normalized.append(
            {
                "start_index": start,
                "end_index": end,
                "title": title,
                "on_screen_hook": hook,
                "hook": by_index[start]["text"],
                "selection_reason": str(clip.get("selection_reason") or "").strip(),
                "score": round(_score_value(clip), 1),
                "estimated_duration_seconds": round(duration, 1),
            }
        )
        if len(normalized) >= MAX_CLIPS:
            break

    return normalized


def identify_clip_segments(script: dict) -> list[dict]:
    """
    Use AI to identify the most clip-worthy moments in the script.
    Returns validated indices and metadata for the best 3-4 clips.
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    all_lines = _flatten_dialogue(script)

    lines_text = "\n".join(
        f"[{l['global_index']}] [{l['segment_type']}] "
        f"[{l['estimated_seconds']:.1f}s]"
        + (f" [{l['topic']}]" if l["topic"] else "")
        + f" {l['speaker']}: {l['text']}"
        for l in all_lines
    )

    try:
        response = client.chat.completions.create(
            model=config.CHATGPT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                    "You are the ruthless short-form editor for a smart AI-news show. "
                    "Choose the 3-4 moments most likely to stop a scroll and earn a "
                    "share. The first selected spoken line must itself be the hook; "
                    "the editor cannot reorder or rewrite the audio.\n\n"
                    "Rank candidates on:\n"
                    "- immediate stakes, surprise, tension, disagreement, or a bold claim\n"
                    "- concrete names, numbers, vivid analogies, or quotable language\n"
                    "- a complete idea that makes sense without the rest of the episode\n"
                    "- a strong opening that does not begin with agreement, a greeting, "
                    "a transition, or context-dependent words like 'that' or 'it'\n"
                    "- a satisfying payoff or counterpoint before the clip ends\n\n"
                    "Hard rules:\n"
                    "- use consecutive lines from ONE segment only\n"
                    "- target 20-58 seconds using the per-line duration estimates\n"
                    "- never use intro or sign_off lines\n"
                    "- clips may not overlap or repeat the same argument\n"
                    "- prefer fewer exceptional clips over filler\n"
                    "- title: specific, curiosity-driving, 4-9 words, no clickbait lie\n"
                    "- on_screen_hook: 3-8 punchy words that accurately frame the moment\n\n"
                    "Return JSON only: {\"clips\": [{\"start_index\": N, "
                    "\"end_index\": M, \"title\": \"...\", "
                    "\"on_screen_hook\": \"...\", "
                    "\"selection_reason\": \"one sentence\", "
                    "\"score\": 0-100}]}"
                    ),
                },
                {"role": "user", "content": f"Transcript:\n{lines_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
    except Exception as exc:
        logger.error("Clip selection failed; continuing without clips: %s", exc)
        return []

    # Track usage
    usage = response.usage
    if usage:
        tracker.record(
            step="clip_identification", model=config.CHATGPT_MODEL,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

    try:
        result = json.loads(response.choices[0].message.content)
        clips = _normalize_clip_segments(result.get("clips", []), all_lines)
        logger.info(
            "Selected %d high-hook clips: %s",
            len(clips),
            [f"{c['score']}: {c['title']}" for c in clips],
        )
        return clips
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
        on_screen_hook = clip_info.get("on_screen_hook") or title

        # Get the relevant audio segments
        relevant_entries = [
            e for e in audio_manifest if start <= e["index"] <= end
        ]

        if not relevant_entries:
            logger.warning(f"No audio segments found for clip {clip_idx}")
            continue

        try:
            clip_path = _render_clip(
                relevant_entries, title, on_screen_hook, clip_idx, clips_dir
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
    on_screen_hook: str,
    clip_idx: int,
    output_dir: Path,
) -> Path:
    """Render a single short-form clip as portrait video."""
    video_clips = []
    audio_clips = []

    for entry in entries:
        duration = _estimate_duration(entry["audio_path"])

        # The short hook is optimized for a phone screen; the longer title is
        # retained for filenames and distribution metadata.
        video_clips.extend(
            _create_speaker_frames(
                entry["speaker"], entry["text"], duration, PORTRAIT,
                topic=on_screen_hook,
            )
        )

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

    if video.duration > MAX_CLIP_SECONDS + 8:
        logger.warning(
            "Clip %d is %.1fs after TTS; keeping the complete final thought",
            clip_idx, video.duration,
        )

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
