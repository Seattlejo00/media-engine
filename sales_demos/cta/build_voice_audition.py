"""Package premium TTS samples as a blinded customer voice audition."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    ROOT
    / "output"
    / "cta-concept"
    / datetime.now().strftime("%Y-%m-%d")
    / "voice-audition"
)

AUDITION_SCRIPT = (
    "Colorado's technology economy is being built in satellites, water systems, "
    "and fiber. A Louisville company has secured a potential seven-hundred-ninety-"
    "eight-million-dollar role in America's next missile-tracking network. For "
    "Colorado leaders, the headline is only the beginning. The member watch item is "
    "hiring, supplier activity, and whether this investment compounds across the "
    "state's broader innovation economy. This is Colorado Tech Signal, a proposed "
    "weekly member briefing."
)

VOICE_DIRECTION = (
    "Warm, grounded, reassuring, and intelligent; a trusted female public-radio "
    "host. Calm confidence, conversational and inviting. Measured natural pacing "
    "with short, thoughtful pauses. Avoid hype, salesmanship, meditation cadence, "
    "or an exaggerated announcer voice."
)

CANDIDATES = (
    ("A", "marin"),
    ("B", "coral"),
    ("C", "nova"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marin", type=Path, required=True)
    parser.add_argument("--coral", type=Path, required=True)
    parser.add_argument("--nova", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def normalize_audio(source: Path, destination: Path, label: str) -> None:
    """Create a fair, delivery-ready MP3 with consistent perceived loudness."""
    if not source.is_file():
        raise FileNotFoundError(f"Missing Candidate {label} source: {source}")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            "-metadata",
            "title=Colorado Tech Signal - Candidate " + label,
            "-metadata",
            "artist=Distomos",
            "-metadata",
            "comment=AI-generated voice audition",
            str(destination),
        ],
        check=True,
    )


def build_page(output_dir: Path, durations: dict[str, float]) -> None:
    cards = "".join(
        f"""
        <article class="candidate">
          <p class="candidate-label">CANDIDATE {label}</p>
          <audio controls preload="metadata" src="candidate-{label.lower()}-ai-voice.mp3"></audio>
          <button type="button" data-choice="{label}">Choose Candidate {label}</button>
          <p class="duration">{durations[label]:.0f} seconds</p>
        </article>
        """
        for label, _voice in CANDIDATES
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Colorado Tech Signal — Voice Direction Audition</title>
  <style>
    :root{{--bg:#080b16;--panel:#12182a;--ink:#f4f6ff;--muted:#aeb8d3;--blue:#4c91ff;--gold:#f4c56f}}
    *{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 18% 0,#18315e 0,transparent 36%),var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
    main{{width:min(1080px,calc(100% - 32px));margin:auto;padding:54px 0 90px}}
    .eyebrow{{color:var(--blue);font-weight:800;letter-spacing:.16em;font-size:12px}}
    h1{{font-size:clamp(42px,7vw,78px);line-height:.96;letter-spacing:-.05em;max-width:860px;margin:16px 0}}
    .dek{{font-size:20px;color:var(--muted);max-width:760px}}
    .notice{{margin:34px 0;padding:14px 18px;border:1px solid #66552c;border-radius:12px;background:#211c10;color:#f6dda1}}
    .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:34px 0}}
    .candidate{{background:linear-gradient(155deg,#151d33,#0d1222);border:1px solid #2c3858;border-radius:18px;padding:24px}}
    .candidate-label{{font-weight:850;letter-spacing:.11em}} audio{{width:100%;margin:15px 0}}
    button{{width:100%;padding:12px;border:1px solid #4c91ff;border-radius:10px;background:#142547;color:#dce9ff;font-weight:750;cursor:pointer}}
    button.selected{{background:#4c91ff;color:#071020}} .duration{{color:var(--muted);font-size:13px;text-align:center}}
    .selection{{display:none;margin:22px 0;padding:20px;border-radius:14px;background:#12233f;border:1px solid #315890;font-size:18px}}
    .panel{{margin-top:46px;padding:26px;background:rgba(18,24,42,.88);border:1px solid #28324d;border-radius:18px}}
    blockquote{{margin:18px 0 0;padding-left:20px;border-left:4px solid var(--blue);color:#dce3f7}}
    li{{margin:.45rem 0}} small{{color:var(--muted)}}
    @media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body><main>
  <p class="eyebrow">PRIVATE CONCEPT • VOICE DIRECTION</p>
  <h1>Choose the voice of<br>Colorado Tech Signal</h1>
  <p class="dek">Three readings. Identical script, direction, and loudness. Listen for the voice that feels most credible, warm, and useful to Colorado technology leaders.</p>
  <div class="notice"><strong>AI voice disclosure:</strong> All three samples are generated by artificial intelligence and are not recordings of a human speaker.</div>
  <section class="grid">{cards}</section>
  <div class="selection" id="selection" aria-live="polite"></div>
  <section class="panel">
    <h2>What to listen for</h2>
    <ul>
      <li><strong>Trust:</strong> Does this sound credible enough for an executive member briefing?</li>
      <li><strong>Warmth:</strong> Is it comfortable to hear without becoming sleepy or sentimental?</li>
      <li><strong>Clarity:</strong> Are company names, numbers, and technical ideas easy to follow?</li>
      <li><strong>Repeatability:</strong> Would you choose to hear this voice every week?</li>
    </ul>
  </section>
  <section class="panel">
    <h2>Audition script</h2>
    <blockquote>{html.escape(AUDITION_SCRIPT)}</blockquote>
  </section>
  <p><small>Prepared by Distomos as an unofficial private concept. Not produced by or endorsed by the Colorado Technology Association. Please do not publish.</small></p>
</main>
<script>
  const buttons = [...document.querySelectorAll('[data-choice]')];
  const result = document.querySelector('#selection');
  buttons.forEach(button => button.addEventListener('click', () => {{
    buttons.forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
    result.style.display = 'block';
    result.textContent = `Your selection: Candidate ${{button.dataset.choice}}. Please send that letter to the Distomos team.`;
  }}));
</script>
</body></html>"""
    (output_dir / "index.html").write_text(page, encoding="utf-8")


def duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inputs = {"marin": args.marin, "coral": args.coral, "nova": args.nova}
    durations: dict[str, float] = {}
    for label, voice in CANDIDATES:
        destination = args.output_dir / f"candidate-{label.lower()}-ai-voice.mp3"
        normalize_audio(inputs[voice], destination, label)
        durations[label] = duration_seconds(destination)

    customer_manifest = {
        "title": "Colorado Tech Signal voice direction audition",
        "disclosure": "All candidates are AI-generated voices, not human recordings.",
        "candidates": [
            {
                "label": label,
                "file": f"candidate-{label.lower()}-ai-voice.mp3",
                "duration_seconds": round(durations[label], 3),
            }
            for label, _voice in CANDIDATES
        ],
    }
    (args.output_dir / "customer_manifest.json").write_text(
        json.dumps(customer_manifest, indent=2), encoding="utf-8"
    )
    (args.output_dir / "audition_script.txt").write_text(
        AUDITION_SCRIPT + "\n", encoding="utf-8"
    )
    (args.output_dir / "send_to_customer.md").write_text(
        """# Customer note

We prepared three voice directions for the proposed Colorado Tech Signal member briefing. Each candidate reads the same copy at matched loudness, so the comparison is about trust, warmth, clarity, and weekly listenability—not volume or script differences.

Please listen to Candidates A, B, and C and reply with the letter you would most want representing the briefing each week.

All samples use AI-generated voices and are not recordings of a human speaker. This is an unofficial private concept prepared by Distomos and is not produced by or endorsed by CTA.
""",
        encoding="utf-8",
    )
    build_page(args.output_dir, durations)

    print(json.dumps(customer_manifest, indent=2))


if __name__ == "__main__":
    main()
