"""Deterministic local placeholder score: deep synth pad, 60 seconds.

No samples, no network, no randomness. Chords crossfade every 7.5s over a
slow 60 BPM sub pulse. Output is peak-normalised to about -7 dBFS.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SR = 48_000
DUR = 60.0
N = int(SR * DUR)
t = np.arange(N, dtype=np.float64) / SR

# Am(add9) -> Fmaj7 -> Cmaj7 -> G(add9), repeated twice.
CHORDS = [
    [55.00, 110.00, 164.81, 246.94, 261.63],
    [43.65, 87.31, 130.81, 220.00, 329.63],
    [65.41, 130.81, 196.00, 246.94, 329.63],
    [49.00, 98.00, 146.83, 246.94, 293.66],
] * 2
CHORD_LEN = DUR / len(CHORDS)

mono = np.zeros(N, dtype=np.float64)
for idx, freqs in enumerate(CHORDS):
    start = int(idx * CHORD_LEN * SR)
    end = int((idx + 1) * CHORD_LEN * SR)
    seg_t = t[start:end]
    seg = np.zeros(end - start, dtype=np.float64)
    for j, f in enumerate(freqs):
        amp = 0.20 / (1.0 + 0.35 * j)
        seg += amp * np.sin(2 * math.pi * f * seg_t + 0.35 * j)
        seg += (amp * 0.35) * np.sin(2 * math.pi * f * 2.001 * seg_t + 0.11 * j)
    fade = int(1.2 * SR)
    env = np.ones_like(seg)
    env[:fade] *= np.linspace(0.0, 1.0, fade)
    env[-fade:] *= np.linspace(1.0, 0.55, fade)
    mono[start:end] += seg * env

# Very soft 60 BPM pulse (sine burst at 55 Hz, one per second).
pulse = np.zeros(N, dtype=np.float64)
beat_len = int(0.22 * SR)
beat_env = np.exp(-np.arange(beat_len) / (0.055 * SR))
for beat in range(60):
    s = int(beat * SR)
    pulse[s : s + beat_len] += 0.16 * np.sin(2 * math.pi * 55.0 * np.arange(beat_len) / SR) * beat_env

# Slow brightness LFO by mixing a one-pole low-passed copy.
alpha = 0.055
lp = np.empty_like(mono)
acc = 0.0
for i, x in enumerate(mono):
    acc += alpha * (x - acc)
    lp[i] = acc
lfo = 0.72 + 0.28 * np.sin(2 * math.pi * 0.05 * t)
body = lp * 2.4 * lfo + mono * 0.22 + pulse

# Stereo width: tiny deterministic delay on the right channel.
delay = int(0.011 * SR)
left = body.copy()
right = np.roll(body, delay) * 0.96

fade_in = int(1.5 * SR)
fade_out = int(2.5 * SR)
env = np.ones(N, dtype=np.float64)
env[:fade_in] = np.linspace(0.0, 1.0, fade_in)
env[-fade_out:] = np.linspace(1.0, 0.0, fade_out)
left *= env
right *= env

stereo = np.column_stack([left, right])
peak = float(np.max(np.abs(stereo))) or 1.0
stereo *= (10 ** (-7 / 20)) / peak

out = Path(__file__).resolve().parents[1] / "assets" / "audio" / "synth-score.wav"
out.parent.mkdir(parents=True, exist_ok=True)
wavfile.write(out, SR, (stereo * 32767).astype(np.int16))
print(f"wrote {out} sr={SR} seconds={DUR} peak_dbfs=-7.0")
