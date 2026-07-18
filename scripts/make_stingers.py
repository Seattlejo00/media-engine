"""
Generate the show's sonic logo: intro, segment stinger, and outro.

v2 — prettier: detuned dual oscillators (analog warmth), chord pads,
a ping-pong echo, gentle vibrato, stereo image. Still fully synthesized
(no licensing baggage) and swappable for licensed tracks by replacing
the files in assets/ (same names).

Run:  python scripts/make_stingers.py
"""

import math
import struct
import wave
from pathlib import Path

SR = 44100
ASSETS = Path(__file__).resolve().parent.parent / "assets"

# A-minor pentatonic palette
NOTES = {
    "A2": 110.00, "A3": 220.00, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "G4": 392.00, "A4": 440.00, "C5": 523.25, "D5": 587.33, "E5": 659.26,
    "G5": 783.99, "A5": 880.00,
}
DETUNE = 1.003  # ~5 cents — two slightly detuned voices = warmth


def _pluck(freq: float, dur: float, vol: float = 0.5, pan: float = 0.0) -> tuple:
    """Warm dual-oscillator pluck with vibrato. Returns (left, right) samples."""
    n = int(SR * dur)
    left, right = [], []
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 3.2) * min(1.0, t * 150)
        vib = 1.0 + 0.004 * math.sin(2 * math.pi * 5.2 * t) * min(1.0, t * 2)
        f1, f2 = freq * vib, freq * vib * DETUNE
        s = (
            math.sin(2 * math.pi * f1 * t)
            + 0.9 * math.sin(2 * math.pi * f2 * t)
            + 0.30 * math.sin(2 * math.pi * f1 * 2 * t)
            + 0.10 * math.sin(2 * math.pi * f1 * 3 * t)
        ) / 2.3
        s *= vol * env
        lg = math.cos((pan + 1) * math.pi / 4)  # constant-power pan
        rg = math.sin((pan + 1) * math.pi / 4)
        left.append(s * lg)
        right.append(s * rg)
    return left, right


def _chord_pad(freqs: list[float], dur: float, vol: float = 0.14) -> tuple:
    """Slow-swelling stereo chord pad."""
    n = int(SR * dur)
    left, right = [], []
    for i in range(n):
        t = i / SR
        env = math.sin(math.pi * min(t / dur, 1.0)) ** 1.6
        sl = sr_ = 0.0
        for j, f in enumerate(freqs):
            ph = j * 0.7
            sl += math.sin(2 * math.pi * f * t + ph)
            sr_ += math.sin(2 * math.pi * f * DETUNE * t + ph + 0.15)
        k = vol * env / max(len(freqs), 1)
        left.append(sl * k)
        right.append(sr_ * k)
    return left, right


def _mix(total_dur: float, events: list) -> tuple:
    """Mix (start, (left, right)) events into stereo buffers."""
    n = int(SR * total_dur)
    L, R = [0.0] * n, [0.0] * n
    for start, (el, er) in events:
        off = int(SR * start)
        for i in range(len(el)):
            j = off + i
            if j < n:
                L[j] += el[i]
                R[j] += er[i]
    return L, R


def _echo(L: list, R: list, delay_s: float = 0.28, fb: float = 0.30) -> tuple:
    """Ping-pong echo: left repeats land right and vice versa."""
    d = int(SR * delay_s)
    for i in range(d, len(L)):
        L[i] += fb * R[i - d]
        R[i] += fb * L[i - d]
    return L, R


def _write(name: str, L: list, R: list) -> None:
    peak = max(1e-9, max(max(abs(s) for s in L), max(abs(s) for s in R)))
    k = min(1.0, 0.82 / peak)
    ASSETS.mkdir(exist_ok=True)
    path = ASSETS / name
    frames = b"".join(
        struct.pack("<hh", int(max(-1, min(1, l * k)) * 32767),
                    int(max(-1, min(1, r * k)) * 32767))
        for l, r in zip(L, R)
    )
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    print(f"wrote {path} ({len(L)/SR:.2f}s stereo)")


def main() -> None:
    N = NOTES

    # INTRO (~7.5s): pad swell, ascending phrase with echo, answering high
    # figure, closing chord — room for the title card to breathe.
    L, R = _mix(7.5, [
        (0.0, _chord_pad([N["A2"], N["E4"], N["A3"]], 7.2, 0.12)),
        (0.4, _pluck(N["A3"], 2.6, 0.40, -0.4)),
        (0.95, _pluck(N["C4"], 2.6, 0.42, 0.3)),
        (1.5, _pluck(N["E4"], 2.8, 0.44, -0.2)),
        (2.05, _pluck(N["A4"], 3.2, 0.48, 0.25)),
        (3.1, _pluck(N["G4"], 2.4, 0.34, -0.35)),
        (3.65, _pluck(N["E5"], 2.8, 0.30, 0.4)),
        (4.4, _pluck(N["A5"], 2.6, 0.20, -0.15)),
        (4.4, _chord_pad([N["A3"], N["E4"], N["A4"], N["C5"]], 3.0, 0.10)),
        (5.2, _pluck(N["E4"], 2.2, 0.26, 0.1)),
        (5.55, _pluck(N["A4"], 1.9, 0.24, -0.1)),
    ])
    _write("intro.wav", *_echo(L, R))

    # STINGER (~2.2s): three-note turn with echo tail — reads as a beat,
    # long enough for the UP NEXT card to be read.
    L, R = _mix(2.2, [
        (0.0, _pluck(N["D4"], 1.2, 0.40, -0.3)),
        (0.22, _pluck(N["G4"], 1.4, 0.44, 0.3)),
        (0.5, _pluck(N["A4"], 1.7, 0.46, 0.0)),
        (0.5, _chord_pad([N["D4"], N["A4"]], 1.6, 0.08)),
    ])
    _write("stinger.wav", *_echo(L, R, delay_s=0.22, fb=0.26))

    # OUTRO (~6s): descending resolution with a long warm chord fade.
    L, R = _mix(6.0, [
        (0.0, _chord_pad([N["A2"], N["A3"], N["E4"]], 5.8, 0.13)),
        (0.3, _pluck(N["E4"], 2.4, 0.40, 0.3)),
        (0.9, _pluck(N["D4"], 2.4, 0.38, -0.3)),
        (1.5, _pluck(N["C4"], 2.6, 0.40, 0.25)),
        (2.2, _pluck(N["A3"], 3.4, 0.46, 0.0)),
        (3.4, _pluck(N["E4"], 2.4, 0.22, -0.2)),
        (3.4, _chord_pad([N["A3"], N["C4"], N["E4"]], 2.5, 0.10)),
    ])
    _write("outro.wav", *_echo(L, R))


if __name__ == "__main__":
    main()
