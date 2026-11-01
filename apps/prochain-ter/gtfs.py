"""BreizhGo TER static timetable (GTFS) -> scheduled trips between two stations.

Stdlib only. The zip is cached next to the app and refreshed once a day.
"""
import csv
import io
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

GTFS_URL = "https://www.korrigo.bzh/ftp/OPENDATA/BREIZHGO_TER.gtfs.zip"
CACHE = Path(__file__).resolve().parent / "cache"
MAX_AGE_S = 24 * 3600

# UIC codes (GTFS stop_id) of the stations this app knows.
STATIONS = {
    "caulnes": ("87473066", "Caulnes"),
    "la-brohiniere": ("87471094", "La Brohiniere"),
    "quedillac": ("87473058", "Quedillac"),
    "rennes": ("87471003", "Rennes"),
}


def _open_zip():
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "breizhgo_ter.gtfs.zip"
    if not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE_S:
        try:
            with urllib.request.urlopen(GTFS_URL, timeout=60) as r:
                data = r.read()
            zipfile.ZipFile(io.BytesIO(data)).testzip()
            path.write_bytes(data)
        except Exception as e:  # keep an older copy if the download fails
            if not path.exists():
                raise
            print(f"gtfs refresh failed, using cached copy: {e}", flush=True)
    return zipfile.ZipFile(path)


def _rows(z, name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _secs(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def train_number(trip_id):
    """'OCESN855634F12775728' -> '855634' (the number real-time feeds also carry)."""
    t = trip_id
    return t[5:11] if t.startswith("OCESN") and len(t) >= 11 else t


class Timetable:
    def __init__(self):
        z = _open_zip()
        self.stop_names = {r["stop_id"]: r["stop_name"] for r in _rows(z, "stops.txt")}
        self.trips = {r["trip_id"]: r for r in _rows(z, "trips.txt")}
        self.calendar = {r["service_id"]: r for r in _rows(z, "calendar.txt")}
        self.exceptions = {}
        for r in _rows(z, "calendar_dates.txt"):
            self.exceptions.setdefault(r["service_id"], {})[r["date"]] = r["exception_type"]
        wanted = {uic for uic, _ in STATIONS.values()}
        self.calls = {}  # trip_id -> {stop_id: (seq, arr_s, dep_s)} (wanted stations only)
        for r in _rows(z, "stop_times.txt"):
            if r["stop_id"] in wanted:
                self.calls.setdefault(r["trip_id"], {})[r["stop_id"]] = (
                    int(r["stop_sequence"]), _secs(r["arrival_time"]), _secs(r["departure_time"]))

    def runs_on(self, service_id, day: date):
        key = day.strftime("%Y%m%d")
        exc = self.exceptions.get(service_id, {}).get(key)
        if exc == "1":
            return True
        if exc == "2":
            return False
        c = self.calendar.get(service_id)
        if not c or not (c["start_date"] <= key <= c["end_date"]):
            return False
        return c[day.strftime("%A").lower()] == "1"

    def between(self, origin, dest, day: date, tz):
        """Scheduled trips origin -> dest on `day`: list of dicts, sorted by departure."""
        out = []
        for trip_id, calls in self.calls.items():
            if origin not in calls or dest not in calls or calls[origin][0] >= calls[dest][0]:
                continue
            trip = self.trips[trip_id]
            if not self.runs_on(trip["service_id"], day):
                continue
            midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
            out.append({
                "trip_id": trip_id,
                "number": train_number(trip_id),
                "headsign": trip["trip_headsign"],
                "date": day.strftime("%Y%m%d"),
                "dep": midnight + timedelta(seconds=calls[origin][2]),
                "arr": midnight + timedelta(seconds=calls[dest][1]),
            })
        return sorted(out, key=lambda t: t["dep"])
