import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import core

TZ = ZoneInfo("Europe/Paris")


def trip(number, hh, mm=0, day="20261102"):
    dep = datetime(2026, 11, 2, hh, mm, tzinfo=TZ)
    return {"trip_id": "x", "number": number, "headsign": "Rennes", "date": day,
            "dep": dep, "arr": dep + timedelta(minutes=35)}


def feed(number, delay_s=0, canceled=False, uic="87473066", day="20261102", dep=None):
    return {(number, day): {"canceled": canceled, "stops": {
        uic: {"dep": dep, "arr": None, "delay": delay_s, "skipped": False}}}}


class Core(unittest.TestCase):
    def test_window(self):
        w = core.Window("m", core.parse_days("mon,tue"), core.parse_hhmm("06:00"), core.parse_hhmm("09:00"), "out")
        self.assertTrue(w.active(datetime(2026, 11, 2, 7, 0, tzinfo=TZ)))      # Monday
        self.assertFalse(w.active(datetime(2026, 11, 2, 9, 0, tzinfo=TZ)))     # end is exclusive
        self.assertFalse(w.active(datetime(2026, 11, 4, 7, 0, tzinfo=TZ)))     # Wednesday

    def test_merge_delay_and_cancel(self):
        s = [trip("1", 7, 12), trip("2", 7, 40)]
        late = int(datetime(2026, 11, 2, 7, 17, tzinfo=TZ).timestamp())
        f = {**feed("1", dep=late), **feed("2", canceled=True)}
        d = core.merge(s, f, "87473066", TZ)
        self.assertEqual(d[0]["delay_min"], 5)
        self.assertFalse(d[0]["cancelled"])
        self.assertTrue(d[1]["cancelled"])

    def test_pick_skips_cancelled_and_missed(self):
        s = core.merge([trip("1", 7, 12), trip("2", 7, 40), trip("3", 8, 10)],
                       feed("2", canceled=True), "87473066", TZ)
        now = datetime(2026, 11, 2, 7, 0, tzinfo=TZ)
        target, backup, missed = core.pick(s, now, 5, 15)  # 07:12 needs a 06:57 start: too late
        self.assertEqual(target["number"], "3")
        self.assertIsNone(backup)
        self.assertEqual(missed["number"], "1")

    def test_phases(self):
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]  # prepare 07:10, go 07:15
        at = lambda h, m, s=0: datetime(2026, 11, 2, h, m, s, tzinfo=TZ)
        self.assertEqual(core.phase(t, at(7, 0), 5, 15), ("wait", 10))
        self.assertEqual(core.phase(t, at(7, 9, 30), 5, 15), ("wait", 1))   # rounded up
        self.assertEqual(core.phase(t, at(7, 10), 5, 15), ("prep", 5))
        self.assertEqual(core.phase(t, at(7, 15), 5, 15), ("go", 0))
        self.assertEqual(core.phase(t, at(7, 17), 5, 15), ("go", 0))        # grace
        self.assertEqual(core.phase(t, at(7, 18), 5, 15)[0], "late")

    def test_progress(self):
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]  # prepare 07:10, go 07:15, slack to 07:17
        at = lambda h, m, s=0: datetime(2026, 11, 2, h, m, s, tzinfo=TZ)
        ph, left, frac = core.progress(t, at(7, 12, 30), 5, 15)
        self.assertEqual((ph, left, round(frac, 2)), ("prep", 150.0, 0.5))
        ph, left, frac = core.progress(t, at(7, 16), 5, 15)
        self.assertEqual((ph, left, round(frac, 2)), ("go", 60.0, 0.5))
        self.assertEqual(core.progress(t, at(7, 20), 5, 15)[0], "late")

    def test_visible_only_when_a_train_is_about_to_matter(self):
        import app
        deps = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)  # prepare 07:10 with prep 5 / car 15
        at = lambda h, m: datetime(2026, 11, 2, h, m, tzinfo=TZ)
        def shown(now, ahead=15):
            live = [d for d in deps if d["real_dep"] > now - timedelta(minutes=2)]  # what the app keeps
            target, _, missed = core.pick(live, now, 5, 15)
            return app.visible(target, None, missed, live, now, 5, 15, ahead)
        self.assertFalse(shown(at(6, 0)))      # hours before: the bar belongs to its other apps
        self.assertFalse(shown(at(6, 54)))
        self.assertTrue(shown(at(6, 55)))      # 15 min before you must start preparing
        self.assertTrue(shown(at(7, 20)))      # too late for it, but it has not left: still shown
        self.assertTrue(shown(at(7, 31)))      # just left, nothing else: the car screen for 2 minutes
        self.assertFalse(shown(at(7, 33)))     # then the bar is left alone

    def test_alert_sequence(self):
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]  # prepare 07:10, go 07:15
        al = core.Alerts()
        seen = []
        for minute in (0, 5, 9, 10, 11, 14, 15, 16, 20):
            now = datetime(2026, 11, 2, 7, 0, tzinfo=TZ) + timedelta(minutes=minute)
            seen += [k for k, _ in al.check(t, now, 5, 15)]
        self.assertEqual(seen, ["prepare", "go"])

    def test_late_start_does_not_replay(self):
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]
        al = core.Alerts()
        now = datetime(2026, 11, 2, 7, 16, tzinfo=TZ)  # already in the go phase
        self.assertEqual([k for k, _ in al.check(t, now, 5, 15)], ["go"])
        self.assertEqual(al.check(t, now, 5, 15), [])

    def test_delay_realert(self):
        al = core.Alerts()
        now = datetime(2026, 11, 2, 6, 0, tzinfo=TZ)
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]
        al.check(t, now, 5, 15)
        t2 = {**t, "delay_min": 7}
        self.assertEqual([k for k, _ in al.check(t2, now, 5, 15)], ["delay"])

    def test_evening_has_no_prepare(self):
        t = core.merge([trip("1", 18, 0)], {}, "87473066", TZ)[0]
        al = core.Alerts()
        seen = []
        for minute in (0, 40, 49, 50):  # go at 17:50 with no prep time
            now = datetime(2026, 11, 2, 17, 0, tzinfo=TZ) + timedelta(minutes=minute)
            seen += [k for k, _ in al.check(t, now, 0, 10)]
        self.assertEqual(seen, ["go"])


if __name__ == "__main__":
    unittest.main()
