"""SNCF GTFS-RT trip updates (no token), decoded with a tiny protobuf reader.

Feed: https://transport.data.gouv.fr/resources/83583 (proxy URL below), about 0.7 MB, only trains
in roughly the next hour. Trip ids differ from the static GTFS ones, so trips are keyed by
(train number, service date) and stops by their 8-digit UIC code.
"""
import re
import urllib.request

RT_URL = "https://proxy.transport.data.gouv.fr/resource/sncf-gtfs-rt-trip-updates"
CANCELED = 3  # TripDescriptor.schedule_relationship
SKIPPED = 1   # StopTimeUpdate.schedule_relationship


def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return r, i


def _fields(b):
    i, out = 0, []
    while i < len(b):
        k, i = _varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif w == 1:
            v, i = b[i:i + 8], i + 8
        elif w == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"wire type {w}")
        out.append((f, v))
    return out


def _first(fs, num):
    for f, v in fs:
        if f == num:
            return v
    return None


def _event_time(raw):
    """StopTimeEvent bytes -> (epoch or None, delay_s or None)."""
    if raw is None:
        return None, None
    fs = _fields(raw)
    delay = _first(fs, 1)
    if delay is not None and delay >= 1 << 31:
        delay -= 1 << 32
    return _first(fs, 2) or None, delay


def parse(data: bytes):
    """-> {(number, date): {"canceled": bool, "stops": {uic: {"dep": epoch, "arr": epoch,
    "delay": s, "skipped": bool}}}}"""
    trips = {}
    for f, ent in _fields(data):
        if f != 2:
            continue
        raw = _first(_fields(ent), 3)
        if raw is None:
            continue
        tu = _fields(raw)
        trip = _fields(_first(tu, 1) or b"")
        trip_id = (_first(trip, 1) or b"").decode()
        day = (_first(trip, 3) or b"").decode()
        m = re.match(r"OCESN(\d{6})", trip_id)
        if not m:
            continue
        info = {"canceled": _first(trip, 4) == CANCELED, "stops": {}}
        for sf, sv in tu:
            if sf != 2:
                continue
            st = _fields(sv)
            sid = re.search(r"(\d{8})$", (_first(st, 4) or b"").decode())
            if not sid:
                continue
            arr, adl = _event_time(_first(st, 2))
            dep, ddl = _event_time(_first(st, 3))
            info["stops"][sid.group(1)] = {
                "arr": arr, "dep": dep,
                "delay": ddl if ddl is not None else adl,
                "skipped": _first(st, 5) == SKIPPED,
            }
        trips[(m.group(1), day)] = info
    return trips


def fetch(timeout=30):
    with urllib.request.urlopen(RT_URL, timeout=timeout) as r:
        return parse(r.read())
