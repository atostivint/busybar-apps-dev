#!/usr/bin/env python3
"""Pre-render the pool scene (no toys: just the title or the logo) into a
seamless looping BUSY Bar .anim, using the firmware 1.2.4 encoder.

    python3 build.py octojam 6 15      # -> octojam_72x16.anim (6 s at 15 fps)
    python3 build.py stunfest 6 15
"""
import json, os, shutil, sys, types, zipfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "apps" / "jam-intro"))
# the encoder only needs flipper.rle; stub the CLI wrapper (colorlog not needed)
fa = types.ModuleType("flipper.app"); fa.App = object; sys.modules["flipper.app"] = fa
import flipper; flipper.app = fa
import seq2anim
import app
from PIL import Image

which = sys.argv[1] if len(sys.argv) > 1 else "octojam"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 6
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 15
XFADE = 1.0                                    # seconds blended across the loop seam
NAME = "%s_72x16" % which
n, xn = int(SECS * FPS), int(XFADE * FPS)

app.FLOTILLA = ()                              # no toys: only the lettering moves
frames = []
for i in range(n + xn):
    state = app.PoolState()
    state.shown = 1 if which == "stunfest" else 0
    frames.append(app.render(app.POOL, i / FPS, 6.0, "OCTOJAM", 0, state))

def mix(a, b, w):                              # w=0 -> a, w=1 -> b
    return [tuple(int(p * (1 - w) + q * w) for p, q in zip(pa, pb)) for pa, pb in zip(a, b)]

out = []
for i in range(n):
    # the first xn frames fade from the tail (which continues the last frame) into the head
    out.append(mix(frames[n + i], frames[i], i / xn) if i < xn else frames[i])

d = HERE / "build" / NAME
shutil.rmtree(d, ignore_errors=True)
d.mkdir(parents=True, exist_ok=True)
for i, buf in enumerate(out):
    img = Image.new("RGB", (72, 16)); img.putdata(buf); img.save(d / ("frame_%d.png" % i))
json.dump({"fps": FPS, "color_mode": "rgb888",
           "sections": [{"name": "whole", "start": 0, "end": n - 1}]}, open(d / "meta.json", "w"))
zpath = HERE / "build" / (NAME + ".zip")
with zipfile.ZipFile(zpath, "w") as z:
    for f in sorted(os.listdir(d)):
        z.write(d / f, "%s/%s" % (NAME, f))
dest = HERE / (NAME + ".anim")
seq2anim.BSBAnimConverter().convert_zip(zpath, dest)
print("%s: %d frames, %d bytes" % (dest.name, n, dest.stat().st_size))
