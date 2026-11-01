"""Scene -> looping frames -> .anim bytes."""
import hashlib
import json
from pathlib import Path

from anim import rgba_to_bgra, write_anim

from .canvas import RED, W, H, Canvas
from .scenes import OPTIONS, SCENES


def params_for(scene, given):
    """Defaults from OPTIONS, then the scene's own overrides, then the explicit values in `given`."""
    spec = SCENES[scene]
    p = {name: OPTIONS[name][1] for name in spec["opts"]}
    p.update(spec.get("defaults", {}))
    p.update({k: v for k, v in given.items() if k in p and v is not None})
    return p


def frames(scene, params, accent, loop_s, fps, min_alpha):
    """RGBA frames for one seamless loop. ph = f / n, so motion with whole cycles per loop wraps cleanly."""
    spec = SCENES[scene]
    colour = RED if spec.get("red") else accent
    canvas = Canvas(min_alpha)
    n = max(2, round(loop_s * fps))
    out = []
    for f in range(n):
        canvas.clear()
        spec["draw"](canvas, f / n, params, colour)
        out.append(canvas.rgba())
    return out


def cache_name(scene, params, accent, loop_s, fps, min_alpha):
    key = json.dumps([scene, params, accent, loop_s, fps, min_alpha], sort_keys=True)
    return f"fui_{scene}_{hashlib.sha1(key.encode()).hexdigest()[:8]}.anim"


def build(assets: Path, scene, given, accent, loop_s, fps, min_alpha):
    """Render (or reuse) the .anim for these parameters; returns the file name inside `assets`."""
    params = params_for(scene, given)
    loop_s = loop_s or SCENES[scene]["loop"]
    name = cache_name(scene, params, accent, loop_s, fps, min_alpha)
    path = assets / name
    if not path.exists():
        assets.mkdir(parents=True, exist_ok=True)
        rendered = frames(scene, params, accent, loop_s, fps, min_alpha)
        write_anim(path, [rgba_to_bgra(f) for f in rendered], W, H, fps)
    return name
