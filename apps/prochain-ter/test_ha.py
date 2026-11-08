import io
import json
import os
import unittest
import urllib.error
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import core
import ha

TZ = ZoneInfo("Europe/Paris")
URL, TOKEN = "http://ha.test:8123", "test-token"


class FakeResponse(io.BytesIO):
    """What urlopen returns: a context manager with read()."""

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def entity(state, **attrs):
    return {"state": state, "attributes": attrs}


def payloads(**override):
    base = {
        ha.E_TRAIN: entity("42", train="855634", trip_id="OCESN855634F12775728"),
        ha.E_PHASE: entity("prepare"),
        ha.E_DEPART: entity("2026-11-05T06:58:00+01:00"),
        ha.E_HOME: entity("2026-11-05T06:44:00+01:00", drive_minutes=9, station_minutes=3,
                          walk_minutes=2, total_minutes=14),
        ha.E_PREPARE: entity("2026-11-05T06:39:00+01:00"),
    }
    base.update(override)
    return base


def fake_urlopen(data, seen=None):
    def urlopen(req, timeout=None):
        if seen is not None:
            seen.append((req, timeout))
        return FakeResponse(data[req.full_url.rsplit("/api/states/", 1)[1]])
    return urlopen


class HomeAssistant(unittest.TestCase):
    def test_normal_payload(self):
        seen = []
        with mock.patch("urllib.request.urlopen", fake_urlopen(payloads(), seen)):
            s = ha.fetch(URL, TOKEN, TZ)
        self.assertTrue(s["active"])
        self.assertEqual((s["number"], s["trip_id"], s["minutes"]), ("855634", "OCESN855634F12775728", 42))
        self.assertEqual((s["ha_phase"], s["phase"]), ("prepare", "prep"))
        self.assertEqual(s["depart"], datetime(2026, 11, 5, 6, 58, tzinfo=TZ))
        self.assertEqual((s["drive_min"], s["station_min"], s["walk_min"], s["total_min"]), (9, 3, 2, 14))
        self.assertEqual(ha.timings(s), (5, 14))
        req, timeout = seen[0]
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(timeout, ha.TIMEOUT_S)

    def test_maps_onto_the_internal_model(self):
        with mock.patch("urllib.request.urlopen", fake_urlopen(payloads())):
            s = ha.fetch(URL, TOKEN, TZ)
        deps = ha.departures(s)
        prep_min, car = ha.timings(s)
        now = datetime(2026, 11, 5, 6, 40, tzinfo=TZ)
        self.assertEqual(deps[0]["number"], "855634")
        self.assertEqual(core.times(deps[0], prep_min, car)[0], datetime(2026, 11, 5, 6, 39, tzinfo=TZ))
        self.assertEqual(core.phase(deps[0], now, prep_min, car)[0], "prep")

    def test_state_off(self):
        data = payloads(**{ha.E_TRAIN: entity("off")})
        with mock.patch("urllib.request.urlopen", fake_urlopen(data)):
            s = ha.fetch(URL, TOKEN, TZ)
        self.assertEqual(s, {"active": False})
        self.assertEqual(ha.departures(s), [])

    def test_http_401_returns_none(self):
        err = urllib.error.HTTPError(URL, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", side_effect=err) as m:
            self.assertIsNone(ha.fetch(URL, TOKEN, TZ))
        self.assertEqual(m.call_count, 1)  # a rejected token is not retried

    def test_network_timeout_returns_none_after_one_retry(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")) as m:
            self.assertIsNone(ha.fetch(URL, TOKEN, TZ))
        self.assertEqual(m.call_count, 2)

    def test_one_retry_recovers(self):
        ok = fake_urlopen(payloads())
        calls = []

        def flaky(req, timeout=None):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.URLError("connection reset")
            return ok(req, timeout)
        with mock.patch("urllib.request.urlopen", flaky):
            self.assertTrue(ha.fetch(URL, TOKEN, TZ)["active"])

    def test_unexpected_payloads_return_none(self):
        for bad in (payloads(**{ha.E_TRAIN: entity("soon", train="1")}),               # minutes not a number
                    payloads(**{ha.E_TRAIN: entity("5")}),                              # no train attribute
                    payloads(**{ha.E_PHASE: entity("bogus")}),
                    payloads(**{ha.E_DEPART: entity("unavailable")}),
                    payloads(**{ha.E_PREPARE: entity("2026-11-05T07:30:00+01:00")})):   # prepare after departure
            with mock.patch("urllib.request.urlopen", fake_urlopen(bad)):
                self.assertIsNone(ha.fetch(URL, TOKEN, TZ))
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(["not", "a", "state"])):
            self.assertIsNone(ha.fetch(URL, TOKEN, TZ))

    def test_config_needs_both_values(self):
        with mock.patch.dict(os.environ, {"HA_URL": "", "HA_TOKEN": ""}):
            self.assertIsNone(ha.config())
            self.assertIsNone(ha.config(URL, None))
            self.assertEqual(ha.config(URL + "/", TOKEN), (URL, TOKEN))
        with mock.patch.dict(os.environ, {"HA_URL": URL, "HA_TOKEN": TOKEN}):
            self.assertEqual(ha.config(), (URL, TOKEN))


def lieu(place, stale=False, **extra):
    return entity(place, age_minutes=3, stale=stale, source_state="home", activity="Stationary", **extra)


def read_location(place, stale=False):
    with mock.patch("urllib.request.urlopen", fake_urlopen({ha.E_LIEU: lieu(place, stale)})):
        return ha.location(URL, TOKEN)


class Location(unittest.TestCase):
    def test_places_map_to_a_direction(self):
        for place, want in (("bureau", "back"), ("gare_rennes", "back"),
                            ("maison", "out"), ("gare_caulnes", "out")):
            loc = read_location(place)
            self.assertEqual(loc["direction"], want, place)
            self.assertEqual((loc["activity"], loc["age_minutes"]), ("Stationary", 3))

    def test_untrusted_fixes_give_no_direction(self):
        for place in ("bureau", "maison", "gare_rennes", "gare_caulnes"):  # stale beats a good place
            self.assertIsNone(read_location(place, stale=True)["direction"], place)
        for place in ("inconnu", "ailleurs", "zone"):
            self.assertIsNone(read_location(place)["direction"], place)
        no_flag = entity("maison", age_minutes=3)  # no `stale` attribute: not trusted
        with mock.patch("urllib.request.urlopen", fake_urlopen({ha.E_LIEU: no_flag})):
            self.assertIsNone(ha.location(URL, TOKEN)["direction"])

    def test_missing_entity_is_none(self):
        err = urllib.error.HTTPError(URL, 404, "Not Found", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertIsNone(ha.location(URL, TOKEN))

    def test_location_beats_the_clock_but_a_stale_fix_does_not(self):
        # 15:00, still inside the morning window: the clock says "out"
        self.assertEqual(ha.resolve_direction(read_location("bureau"), "out"), "back")
        self.assertEqual(ha.resolve_direction(read_location("maison"), "back"), "out")
        # the same fix, stale: the clock window decides
        self.assertEqual(ha.resolve_direction(read_location("bureau", stale=True), "out"), "out")
        # unusable places and a missing entity: the clock window decides too
        self.assertEqual(ha.resolve_direction(read_location("ailleurs"), "back"), "back")
        self.assertEqual(ha.resolve_direction(None, "out"), "out")


class LocationWakesTheApp(unittest.TestCase):
    """Outside --morning / --evening a trustworthy location keeps the app active; nothing else does."""

    WINDOWS = [core.Window("morning", core.parse_days("mon,tue,wed,thu,fri"), core.parse_hhmm("06:00"),
                           core.parse_hhmm("09:00"), "out"),
               core.Window("evening", core.parse_days("mon,tue,wed,thu,fri"), core.parse_hhmm("16:30"),
                           core.parse_hhmm("19:30"), "back")]
    NIGHT = datetime(2026, 11, 5, 21, 0, tzinfo=TZ)   # Thursday, outside both windows
    NOON = datetime(2026, 11, 5, 11, 0, tzinfo=TZ)

    def win(self, now, place, stale=False):
        return ha.active_window(now, self.WINDOWS, read_location(place, stale))

    def test_fresh_bureau_outside_windows_is_active_return_trip(self):
        w = self.win(self.NIGHT, "bureau")
        self.assertEqual((w.name, w.direction), ("location", "back"))

    def test_fresh_maison_outside_windows_is_active_outbound(self):
        w = self.win(self.NOON, "maison")
        self.assertEqual((w.name, w.direction), ("location", "out"))

    def test_stale_bureau_outside_windows_is_inactive_as_today(self):
        self.assertIsNone(self.win(self.NIGHT, "bureau", stale=True))

    def test_fresh_ailleurs_outside_windows_is_inactive(self):
        for place in ("ailleurs", "zone", "inconnu"):
            self.assertIsNone(self.win(self.NIGHT, place), place)

    def test_missing_entity_and_no_location_change_nothing(self):
        self.assertIsNone(ha.active_window(self.NIGHT, self.WINDOWS, None))
        inside = datetime(2026, 11, 5, 7, 0, tzinfo=TZ)
        self.assertEqual(ha.active_window(inside, self.WINDOWS, None).name, "morning")

    def test_clock_window_keeps_priority_inside_its_hours(self):
        # 07:00 at the office: the window stays "morning"; the direction is resolved separately
        w = self.win(datetime(2026, 11, 5, 7, 0, tzinfo=TZ), "bureau")
        self.assertEqual(w.name, "morning")
        self.assertEqual(ha.resolve_direction(read_location("bureau"), w.direction), "back")


if __name__ == "__main__":
    unittest.main()
