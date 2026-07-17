"""
Generate the show's sonic logo: intro, segment stinger, and outro.

Synthesized programmatically (no licensing baggage): a warm pluck motif
on a pentatonic scale with a soft sub layer — minimal, NPR-adjacent.
Outputs WAVs into assets/; audio assembly picks them up from there.
Swap in licensed tracks anytime by replacing the files (same names).

Run:  python scripts/make_stingers.py
"""

import math
import struct
import wave
from pathlib import Path

SR = 44100
ASSETS = Path(__file__).resolve().parent.parent / "assets"

# A warm minor-pentatonic palette (A3 root)
NOTES = {
    "A3": 220.00, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "G4": 392.00, "A4": 440.00, "C5": 523.25, "D5": 587.33, "E5": 659.26,
}


def _pluck(freq: float, dur: float, vol: float = 0.5) -> list[float]:
    """A soft synthetic pluck: sine + light harmonics, exponential decay."""
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 4.5) * min(1.0, t * 200)  # fast attack, gentle decay
        s = (
            math.sin(2 * math.pi * freq * t)
            + 0.35 * math.sin(2 * math.pi * freq * 2 * t)
            + 0.12 * math.sin(2 * math.pi * freq * 3 * t)
        )
        out.append(vol * env * s / 1.47)
    return out


def _pad(freq: float, dur: float, vol: float = 0.18) -> list[float]:
    """A soft sub/pad layer one octave down with slow swell."""
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        env = math.sin(math.pi * min(t / dur, 1.0)) ** 1.5  # swell in and out
        s = math.sin(2 * math.pi * (freq / 2) * t)
        out.append(vol * env * s)
    return out


def _mix(total_dur: float, events: list[tuple[float, list[float]]]) -> list[float]:
    """Mix (start_time, samples) events into one buffer."""
    buf = [0.0] * int(SR * total_dur)
    for start, samples in events:
        offset = int(SR * start)
        for i, s in enumerate(samples):
            j = offset + i
            if j < len(buf):
                buf[j] += s
    peak = max(1e-9, max(abs(s) for s in buf))
    scale = min(1.0, 0.85 / peak)
    return [s * scale for s in buf]


def _write(name: str, buf: list[float]) -> None:
    ASSETS.mkdir(exist_ok=True)
    path = ASSETS / name
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(
            b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in buf)
        )
    print(f"wrote {path} ({len(buf)/SR:.2f}s)")


def main() -> None:
    N = NOTES

    # INTRO (~4.2s): rising motif A3-C4-E4-A4, pad underneath, sparkle at top
    _write("intro.wav", _mix(4.2, [
        (0.0, _pad(N["A3"], 4.0)),
        (0.3, _pluck(N["A3"], 2.2, 0.42)),
        (0.75, _pluck(N["C4"], 2.2, 0.44)),
        (1.2, _pluck(N["E4"], 2.4, 0.46)),
        (1.65, _pluck(N["A4"], 2.8, 0.5)),
        (2.4, _pluck(N["E5"], 2.0, 0.28)),
    ]))

    # STINGER (~1.5s): quick two-note turn D4 -> G4 with a soft tail
    _write("stinger.wav", _mix(1.5, [
        (0.0, _pluck(N["D4"], 1.0, 0.42)),
        (0.22, _pluck(N["G4"], 1.3, 0.48)),
        (0.22, _pad(N["G4"], 1.2, 0.10)),
    ]))

    # OUTRO (~4.6s): descending resolution E4-D4-C4-A3, long pad
    _write("outro.wav", _mix(4.6, [
        (0.0, _pad(N["A3"], 4.4, 0.16)),
        (0.2, _pluck(N["E4"], 2.0, 0.42)),
        (0.7, _pluck(N["D4"], 2.0, 0.40)),
        (1.25, _pluck(N["C4"], 2.4, 0.42)),
        (1.9, _pluck(N["A3"], 3.0, 0.5)),
    ]))


if __name__ == "__main__":
    main()
