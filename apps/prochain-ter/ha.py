"""Home Assistant as the data source: next train, phase and times, read over the REST API.

Stdlib only. URL and token come from the HA_URL / HA_TOKEN environment variables (or the
--ha-url / --ha-token flags, which default to them); nothing is stored in a file.

Entity contract (all read with GET {HA_URL}/api/states/<entity_id>):
    sensor.ter_prochain_train                 state = minutes until departure, or "off";
                                              attributes: train (number), trip_id
    sensor.ter_phase                          wait | annonce | prepare | go | late | off
    sensor.ter_heure_de_depart                timestamp of the train's departure
    sensor.ter_heure_de_depart_de_la_maison   timestamp you leave home; attributes drive_minutes,
                                              station_minutes, walk_minutes, total_minutes
    sensor.ter_heure_de_preparation           timestamp you start getting ready

`fetch()` never raises: it returns None when HA is unreachable, rejects the token or answers
something unexpected, and {"active": False} when there is no train ("off").
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

TIMEOUT_S = 12  # HA's event loop can stall for several seconds: a 5 s budget lost whole polls
E_TRAIN = "sensor.ter_prochain_train"
E_PHASE = "sensor.ter_phase"
E_DEPART = "sensor.ter_heure_de_depart"
E_HOME = "sensor.ter_heure_de_depart_de_la_maison"
E_PREPARE = "sensor.ter_heure_de_preparation"

# HA phase -> the phase names core.py uses. "annonce" is the heads-up before you must get ready.
PHASES = {"wait": "wait", "annonce": "wait", "prepare": "prep", "go": "go", "late": "late"}


def config(url=None, token=None):
    """-> (url, token) from the arguments, else HA_URL / HA_TOKEN; None unless both are set."""
    url = (url or os.environ.get("HA_URL", "")).strip().rstrip("/")
    token = (token or os.environ.get("HA_TOKEN", "")).strip()
    return (url, token) if url and token else None


def _get(url, token, entity):
    """-> parsed state dict, or None. One retry on a network error; HTTP errors are not retried."""
    req = urllib.request.Request(f"{url}/api/states/{entity}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data if isinstance(data, dict) and "state" in data else None
        except urllib.error.HTTPError:  # 401 bad token, 404 unknown entity...: retrying will not help
            return None
        except (urllib.error.URLError, OSError):  # includes timeouts
            if attempt:
                return None
        except (ValueError, UnicodeDecodeError):  # not JSON
            return None
    return None


def _time(state, tz):
    """HA timestamp state -> aware datetime in `tz`, or None."""
    try:
        d = datetime.fromisoformat(str(state).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(tz) if d.tzinfo else d.replace(tzinfo=tz)


def fetch(url, token, tz):
    """-> {"active": False} (no train), a dict describing the train, or None (HA unusable).

    Active dict: number, trip_id, minutes, ha_phase, phase (core.py name), depart, leave, prepare
    (aware datetimes in `tz`), drive_min, station_min, walk_min, total_min (numbers or None)."""
    train = _get(url, token, E_TRAIN)
    if train is None:
        return None
    if str(train["state"]).lower() == "off":
        return {"active": False}
    try:
        minutes = float(train["state"])
    except (TypeError, ValueError):
        return None
    attrs = train.get("attributes") or {}
    if not attrs.get("train"):
        return None
    got = {e: _get(url, token, e) for e in (E_PHASE, E_DEPART, E_HOME, E_PREPARE)}
    if any(v is None for v in got.values()):
        return None
    ha_phase = str(got[E_PHASE]["state"]).lower()
    if ha_phase == "off":
        return {"active": False}
    if ha_phase not in PHASES:
        return None
    depart, leave, prepare = (_time(got[e]["state"], tz) for e in (E_DEPART, E_HOME, E_PREPARE))
    if not (depart and leave and prepare) or not (prepare <= leave <= depart):
        return None
    home = got[E_HOME].get("attributes") or {}

    def num(k):
        v = home.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    return {"active": True, "number": str(attrs["train"]), "trip_id": str(attrs.get("trip_id") or ""),
            "minutes": minutes, "ha_phase": ha_phase, "phase": PHASES[ha_phase],
            "depart": depart, "leave": leave, "prepare": prepare,
            "drive_min": num("drive_minutes"), "station_min": num("station_minutes"),
            "walk_min": num("walk_minutes"), "total_min": num("total_minutes")}


def timings(state):
    """-> (prep_min, car_min) in the terms of core.times(): car_min = leaving home -> departure,
    prep_min = starting to get ready -> leaving home. Taken from the timestamps so that core's
    go / prepare instants match Home Assistant's."""
    return ((state["leave"] - state["prepare"]).total_seconds() / 60,
            (state["depart"] - state["leave"]).total_seconds() / 60)


def departures(state):
    """HA state -> list of departures in the model core.merge() produces (empty when no train).
    Delay and cancellation are already in HA's departure time, so delay_min is 0 here."""
    if not state or not state.get("active"):
        return []
    dep = state["depart"]
    return [{"trip_id": state["trip_id"], "number": state["number"], "headsign": "Rennes",
             "date": dep.strftime("%Y%m%d"), "dep": dep, "arr": dep,
             "cancelled": False, "delay_min": 0, "live": True, "real_dep": dep, "real_arr": dep}]


E_LIEU = "sensor.ter_lieu"
# where you are -> direction of the trip: "back" = Rennes -> home station, "out" = home station -> Rennes
PLACE_DIRECTION = {"bureau": "back", "gare_rennes": "back", "maison": "out", "gare_caulnes": "out"}


def location(url, token):
    """-> {"place", "direction", "stale", "age_minutes", "activity", "source_state"}, or None when the
    entity is missing / HA unusable. `direction` is None unless the fix is trustworthy: the place is one
    of PLACE_DIRECTION and `stale` is explicitly false (a missing flag is not trusted)."""
    d = _get(url, token, E_LIEU)
    if d is None:
        return None
    a = d.get("attributes") or {}
    place = str(d["state"]).lower()
    stale = a.get("stale")
    return {"place": place, "stale": stale, "age_minutes": a.get("age_minutes"),
            "activity": a.get("activity"), "source_state": a.get("source_state"),
            "direction": PLACE_DIRECTION.get(place) if stale is False else None}


def resolve_direction(loc, clock_direction):
    """Direction to serve: the location's when it is trustworthy, else the clock window's."""
    return (loc or {}).get("direction") or clock_direction


def active_window(now, windows, loc=None):
    """The window the app serves now. The --morning / --evening windows come first, exactly as before;
    outside them a trustworthy location (fresh fix on a known place) opens an all-day window named
    "location" for its direction. Unknown / stale / ailleurs / zone / missing -> None, as before."""
    import core
    win = core.active_window(now, windows)
    if win is not None:
        return win
    direction = (loc or {}).get("direction")
    return core.Window("location", frozenset(range(7)), 0, 1440, direction) if direction else None


def _cli():
    import argparse
    from zoneinfo import ZoneInfo
    p = argparse.ArgumentParser(description="Print what Home Assistant says about the next TER")
    p.add_argument("--ha-url", default=None, help="default: $HA_URL")
    p.add_argument("--ha-token", default=None, help="default: $HA_TOKEN (prefer the variable: flags show in ps)")
    a = p.parse_args()
    cfg = config(a.ha_url, a.ha_token)
    if not cfg:
        raise SystemExit("set HA_URL and HA_TOKEN (or --ha-url / --ha-token)")
    state = fetch(*cfg, ZoneInfo("Europe/Paris"))
    print("unreachable, unauthorised or unexpected payload" if state is None
          else json.dumps(state, default=str, indent=2))


if __name__ == "__main__":
    _cli()
