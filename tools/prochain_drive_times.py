#!/usr/bin/env python3
"""Drive time from home to each station -> apps/prochain-ter/drive_times.json (git-ignored).

    python tools/prochain_drive_times.py "8 Ty Ariane, 22350 Saint-Jouan-de-l'Isle"

Geocodes the address with Nominatim (OpenStreetMap), then asks the public OSRM server for the car
route to each station. The address is sent to those two free services once; it is not stored in
the repo (the output file only keeps minutes and the resolved coordinates).
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

STATIONS = {  # lat, lon (BreizhGo GTFS stops.txt)
    "caulnes": (48.284426, -2.155593),
    "la-brohiniere": (48.213472, -2.110452),
    "quedillac": (48.24848, -2.14522),
}
UA = {"User-Agent": "busybar-apps-dev prochain-ter (personal use)"}
OUT = Path(__file__).resolve().parent.parent / "apps" / "prochain-ter" / "drive_times.json"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def geocode(address):
    q = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1, "countrycodes": "fr"})
    hits = get("https://nominatim.openstreetmap.org/search?" + q)
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0]["display_name"]


def main():
    address = sys.argv[1]
    tried = [address]
    # fall back to the street without the house number, then to the commune
    parts = address.split(",")
    if len(parts) > 1:
        tried.append(",".join(parts[1:]).strip())
    found = None
    for a in tried:
        found = geocode(a)
        if found:
            break
    if not found:
        sys.exit("address not found")
    lat, lon, label = found
    print("resolved to:", label)
    result = {"home": {"lat": lat, "lon": lon, "resolved": label}, "drive_min": {}}
    for name, (slat, slon) in STATIONS.items():
        route = get(f"https://router.project-osrm.org/route/v1/driving/{lon},{lat};{slon},{slat}?overview=false")
        sec = route["routes"][0]["duration"]
        km = route["routes"][0]["distance"] / 1000
        result["drive_min"][name] = round(sec / 60)
        print(f"{name}: {sec / 60:.1f} min, {km:.1f} km")
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
