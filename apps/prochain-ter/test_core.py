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
        target, backup, missed = core.pick(s, now, 20)  # 07:12 needs a 06:52 start: missed
        self.assertEqual(target["number"], "3")
        self.assertIsNone(backup)
        self.assertEqual(missed["number"], "1")

    def test_alert_sequence(self):
        deps = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)
        al = core.Alerts()
        t = deps[0]
        seen = []
        for minute in (0, 14, 16, 25, 26, 29, 31):   # leave-by = 07:10
            now = datetime(2026, 11, 2, 6, 50, tzinfo=TZ) + timedelta(minutes=minute)
            seen += [k for k, _ in al.check(t, now, 20)]
        self.assertEqual(seen, ["t15", "t5", "t0"])

    def test_late_start_does_not_replay(self):
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]
        al = core.Alerts()
        now = datetime(2026, 11, 2, 7, 9, tzinfo=TZ)  # 1 min before leave-by
        self.assertEqual([k for k, _ in al.check(t, now, 20)], ["t5"])
        self.assertEqual(al.check(t, now, 20), [])

    def test_delay_realert(self):
        al = core.Alerts()
        now = datetime(2026, 11, 2, 6, 0, tzinfo=TZ)
        t = core.merge([trip("1", 7, 30)], {}, "87473066", TZ)[0]
        al.check(t, now, 20)
        t2 = {**t, "delay_min": 7}
        self.assertEqual([k for k, _ in al.check(t2, now, 20)], ["delay"])


if __name__ == "__main__":
    unittest.main()
