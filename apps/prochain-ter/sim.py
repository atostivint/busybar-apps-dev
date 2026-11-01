"""Fake trains on a fast-forwarded clock, to see the whole sequence without waiting for a real train.

`python app.py --simulate` plays this story (simulated minutes since the start; 5 min to get ready,
9 min from the door to the platform):
  +0   a train (855600) leaves at +16 but is cancelled: red SUPPRIME screen + chime
  +0   train 855634 leaves at +34: PREPARER A +20 (counting down)
  +8   855634 gets a 4 min delay: chime, "+4 MIN", everything moves back 4 min
  +24  PREPARE (yellow, VOITURE): chime
  +29  GO (green, PARTEZ !): chime
  +31  too late for 855634: the screen now points at the next train 855640 (leaves at +52)
  +38  855634 has left
  +52  855640 leaves: nothing left, the car screen
  +62  end
"""
import time
from datetime import datetime, timedelta

DEP_A, DEP_B, DEP_CANCELLED, DELAY_AT, END = 34, 52, 16, 8, 62


class Clock:
    """Simulated time: starts at the current whole minute and runs `speed` times faster."""

    def __init__(self, speed, tz):
        self.speed = speed
        self.t0 = time.time()
        self.start = datetime.now(tz).replace(second=0, microsecond=0)

    def minutes(self):
        return (time.time() - self.t0) * self.speed / 60

    def now(self):
        return self.start + timedelta(minutes=self.minutes())

    def done(self):
        return self.minutes() >= END


def _train(number, dep, delay, cancelled):
    return {"trip_id": f"SIM{number}", "number": number, "headsign": "Rennes", "date": dep.strftime("%Y%m%d"),
            "dep": dep, "arr": dep + timedelta(minutes=37), "cancelled": cancelled, "delay_min": delay,
            "live": True, "real_dep": dep + timedelta(minutes=delay),
            "real_arr": dep + timedelta(minutes=37 + delay)}


def departures(clock):
    s = clock.start
    delay = 4 if clock.minutes() >= DELAY_AT else 0
    return [_train("855600", s + timedelta(minutes=DEP_CANCELLED), 0, True),
            _train("855634", s + timedelta(minutes=DEP_A), delay, False),
            _train("855640", s + timedelta(minutes=DEP_B), 0, False)]
