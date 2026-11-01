"""Calm engine rumble, synthesised (stdlib only): a soft six-cylinder idle that swells in and fades
out. Played when it is time to get in the car.

The bar's speaker is small and has no bass, so most of the energy sits in the 80-300 Hz
harmonics of the 40 Hz firing rate. Drop your own `engine.snd` next to this file to replace it.
"""
import math
import random
import struct
import wave

RATE = 22050


def _noise(rng, n, smooth=0.6):
    """Low-passed noise, -1..1."""
    out, y = [], 0.0
    for _ in range(n):
        y = smooth * y + (1 - smooth) * rng.uniform(-1, 1)
        out.append(y * 2.2)
    return out


def samples(volume=40):
    """A calm start: the engine is already running, a soft rumble swells in over ~0.9 s, purrs for
    about two seconds with a slow breathing in the idle, and fades out. No crank, no rev."""
    rng = random.Random(7)
    secs = 3.4
    n = int(RATE * secs)
    nz = _noise(rng, n, 0.9)                          # very low-passed noise: the road-rumble bed
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = 32 + 2.0 * min(1.0, t / 0.9) + 0.6 * math.sin(t * 1.7)   # settles from 32 Hz, hunts a little
        phase += 2 * math.pi * f / RATE
        lump = 0.9 + 0.1 * math.sin(phase * 0.5 + 0.8 * math.sin(t * 2.3))
        s_ = 0.0
        for h, a_ in ((1, 0.30), (2, 0.55), (3, 0.45), (4, 0.30), (5, 0.18), (6, 0.10)):
            s_ += a_ * math.sin(h * phase + 0.4 * h)
        s_ = math.tanh(1.1 * s_) * lump               # barely clipped: smooth, not growly
        swell = min(1.0, (t / 0.9) ** 1.6)
        fade = 1.0 if t < secs - 0.9 else max(0.0, (secs - t) / 0.9)
        breath = 0.92 + 0.08 * math.sin(2 * math.pi * 0.7 * t)
        out.append(swell * fade * breath * (0.8 * s_ + 0.10 * nz[i]))
    peak = max(abs(x) for x in out) or 1
    amp = 0.9 * max(0, min(100, volume)) / 100 * 1.3
    return [int(max(-1.0, min(1.0, x / peak * amp)) * 32767) for x in out]


def build_wav(path, volume=40):
    data = samples(volume)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(data)}h", *data))
