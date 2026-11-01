"""Four-note station chime, chiptune style: synthesised square waves (stdlib only), played on the bar.

C - G (long) then A - E (short). Drop your own sound file in as `chime.snd` next to this file to
replace it.
"""
import json
import struct
import urllib.parse
import urllib.request
import wave
from pathlib import Path

HERE =Path(__file__).resolve().parent
RATE = 22050
NOTES = [(261.63, 0.44), (392.00, 0.37), (440.00, 0.35), (329.63, 0.39)]  # C4 G4 A4 E4, tuned by ear
SLOW = 1.6  # 1.0 = the lengths tuned in the browser; bigger = slower
GAP = 0.02


def _square(freq, secs, duty=0.5):
    n = int(RATE * secs)
    out = []
    for i in range(n):
        t = i / RATE
        env = 1.0 - 0.3 * (t / secs)           # slight droop, like a chip channel
        env *= min(1.0, (secs - t) / 0.02)      # 20 ms release so notes do not click
        out.append((1.0 if (t * freq) % 1.0 < duty else -1.0) * env)
    return out


def samples(volume=40):
    pcm = []
    for f, d in NOTES:
        pcm += _square(f, d * SLOW) + [0.0] * int(RATE * GAP)
    amp = 0.6 * max(0, min(100, volume)) / 100  # volume 0-100 -> chime only, not the bar's master volume
    return [int(x * amp * 32767) for x in pcm]


def build_wav(path, volume=40):
    data = samples(volume)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(data)}h", *data))


def upload(base, app, local, remote, timeout=30):
    q = urllib.parse.urlencode({"application_name": app, "file": remote})
    req = urllib.request.Request(f"{base}/api/assets/upload?{q}", data=Path(local).read_bytes(), method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def play(base, app, remote, timeout=5):
    req = urllib.request.Request(f"{base}/api/audio/play", method="POST",
                                 data=json.dumps({"application_name": app, "path": remote}).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()
