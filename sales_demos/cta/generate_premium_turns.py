"""Generate resumable premium Marin narration for the CTA concept episode."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from sales_demos.cta.build import SCRIPT  # noqa: E402


MODEL = "gpt-4o-mini-tts"
VOICE = "marin"
VOICE_DIRECTION = """Voice affect: Warm, grounded, reassuring, and intelligent. Use the presence of a trusted female public-radio host.
Tone: Calm confidence, conversational and inviting. Avoid hype, salesmanship, a meditation cadence, or an exaggerated announcer voice.
Pacing: Measured and natural, around 150 words per minute. Use short, thoughtful pauses between ideas.
Emotion: Genuine interest and steady optimism.
Pronunciation: Say Colorado naturally. Pronounce Louisville as LOO-iss-vill. Keep technical phrases crisp."""


def parse_args() -> argparse.Namespace:
    default_output = (
        ROOT
        / "output"
        / "cta-concept"
        / dt.date.today().isoformat()
        / "premium-marin"
        / "raw_segments"
    )
    parser = argparse.ArgumentParser(
        description="Generate missing Marin narration turns for the CTA concept."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help="Directory containing numbered MP3 turns.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate turns that already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not config.OPENAI_API_KEY:
        raise SystemExit(
            "OPENAI_API_KEY is not configured. Add it to the local environment or "
            ".env, then rerun this command; do not paste the key into chat."
        )

    lines = [
        line["text"]
        for segment in SCRIPT["segments"]
        for line in segment["dialogue"]
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    generated = 0
    skipped = 0

    for index, line in enumerate(lines):
        destination = args.output_dir / f"{index:03d}.mp3"
        if destination.exists() and not args.force:
            print(f"Skipping existing turn {index:03d}: {destination}")
            skipped += 1
            continue

        print(f"Generating turn {index:03d}: {destination}")
        with client.audio.speech.with_streaming_response.create(
            model=MODEL,
            voice=VOICE,
            input=line,
            instructions=VOICE_DIRECTION,
            response_format="mp3",
        ) as response:
            response.stream_to_file(destination)
        generated += 1

    print(f"Complete: generated {generated}, skipped {skipped}.")


if __name__ == "__main__":
    main()
