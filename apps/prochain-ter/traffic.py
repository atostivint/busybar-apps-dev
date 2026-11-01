"""Live car travel time home -> work, from the TomTom Routing API (free key, no credit card).

The key is read from the TOMTOM_KEY environment variable or from `tomtom.key` next to this file
(git-ignored). The work address is geocoded once with Nominatim (OpenStreetMap) and cached.
Results are cached for `ttl` seconds so the bar never hammers the API (free tier: 2500 requests/day).
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "busybar-apps-dev prochain-ter (personal use)"}


def load_key():
    key = os.environ.get("TOMTOM_KEY", "").strip()
    f = HERE / "tomtom.key"
    if not key and f.exists():
        key = f.read_text(encoding="utf-8").strip()
    return key or None


def _get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def geocode(address):
    """-> (lat, lon) or None. Cached in cache/geocode.json (the address stays on this machine)."""
    cache = HERE / "cache" / "geocode.json"
    known = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if address in known:
        return tuple(known[address])
    q = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1, "countrycodes": "fr"})
    hits = _get("https://nominatim.openstreetmap.org/search?" + q)
    if not hits:
        return None
    known[address] = [float(hits[0]["lat"]), float(hits[0]["lon"])]
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(known), encoding="utf-8")
    return tuple(known[address])


def parse_route(data):
    """TomTom calculateRoute JSON -> {"minutes": door-to-door with traffic, "delay_min": jam delay}."""
    s = data["routes"][0]["summary"]
    return {"minutes": round(s["travelTimeInSeconds"] / 60), "delay_min": round(s.get("trafficDelayInSeconds", 0) / 60)}


class Traffic:
    def __init__(self, key, home, work_address, ttl=300):
        self.key, self.home, self.work_address, self.ttl = key, home, work_address, ttl
        self.work, self.last, self.at = None, None, 0.0

    def get(self):
        """-> {"minutes", "delay_min"} or None. Keeps the last value if the API is unreachable."""
        if time.time() - self.at < self.ttl:
            return self.last
        self.at = time.time()  # also rate-limits retries after a failure
        try:
            if self.work is None:
                self.work = geocode(self.work_address)
            if self.work is None:
                return self.last
            loc = f"{self.home[0]},{self.home[1]}:{self.work[0]},{self.work[1]}"
            q = urllib.parse.urlencode({"key": self.key, "traffic": "true", "travelMode": "car"})
            self.last = parse_route(_get(f"https://api.tomtom.com/routing/1/calculateRoute/{loc}/json?{q}"))
        except Exception as e:  # network, quota, bad key: keep going without it
            print(f"traffic unavailable: {e}", flush=True)
        return self.last
