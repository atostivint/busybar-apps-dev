import tempfile
import unittest
from pathlib import Path

import anim
import board
import car


def screens(theme):
    now = "06:44"
    drive = {"minutes": 52, "delay_min": 9}
    return [board.info(theme, "07:12", now=now), board.info(theme, "07:17", delay_min=5, now=now),
            board.info(theme, "07:12", cancelled=True, now=now),
            board.identity(theme, "855634", "RENNES", now=now), board.clock(theme, "06:44", "07:12", "RENNES"),
            board.steps(theme, "wait", 700, 0.4, "06:49", "06:58", now=now),
            board.steps(theme, "prep", 240, 0.8, "06:49", "06:58", now=now),
            board.steps(theme, "go", 95, 0.5, "06:49", "06:58", now=now),
            board.steps(theme, "go", 0, 0.0, "06:49", "06:58", now=now),
            board.next_train(theme, now=now), board.next_train(theme, drive=drive, now=now),
            board.next_train(theme, now=now, car_path="car.anim"),
            board.next_train(theme, drive=drive, now=now, car_path="car.anim"),
            board.steps(theme, "prep", 720, 1.0, "06:49", "06:58", now=now),
            board.next_train(theme, "07:40", "07:31", now=now), board.message(theme, "Pas de train", "dans la plage")]


class Board(unittest.TestCase):
    def test_elements_are_valid(self):
        for theme in board.THEMES:
            for els in screens(theme):
                ids = [e["id"] for e in els]
                self.assertEqual(len(ids), len(set(ids)))
                for e in els:
                    if e["type"] == "text":
                        e["text"].encode("ascii")  # bar fonts have no accents
                    if e["type"] in ("rectangle", "xpmbitmap"):
                        self.assertLessEqual(e["x"] + e["width"], 72)
                        self.assertLessEqual(e["y"] + e["height"], 16)

    def test_night_has_no_background(self):
        self.assertNotIn("bg", [e["id"] for e in board.info("night", "07:12")])
        self.assertIn("bg", [e["id"] for e in board.info("day", "07:12")])

    def test_logo_or_timer_in_the_block(self):
        for theme in board.THEMES:
            for els in screens(theme)[:-1]:  # all but the plain "no train" message
                ids = [e["id"] for e in els]
                self.assertTrue("logo" in ids or "n" in ids or "car" in ids)  # the block shows the logo, or a timer

    def test_now_drops_to_the_free_row(self):
        """Safety net: if a screen's first line ever reaches into the corner, the clock takes the second
        row rather than running under the text."""
        els = {e["id"]: e for e in board._badge(board.THEMES["day"], "#FFFFFFFF", "#0A3D9CFF",
                                                "A VERY LONG FIRST LINE", "SHORT", "#FFFFFFFF", "#FFFFFFFF",
                                                now="06:44")}
        self.assertEqual(els["now"]["y"], 6)

    def test_every_screen_carries_the_clock(self):
        """The clock sits in the right corner of whichever row still has room; the line it shares that
        row with always stops before it (measured: it starts on column 54)."""
        for theme in board.THEMES:
            for els in screens(theme)[:-1]:  # all but the free-text message, which has no room
                found = {e["id"]: e for e in els}
                self.assertIn("now", found)
                row = -1 if found["now"]["y"] == -1 else 6
                self.assertIn(row, (-1, 6))
                self.assertEqual((found["now"]["text"], found["now"]["x"], found["now"]["align"]),
                                 ("06:44", 71, "top_right"))
                line = found["a" if row == -1 else "b"]["text"]
                self.assertLessEqual(board._w(line), board.NOW_FIT)  # it stops before the clock
                self.assertEqual(found["now"]["color"], board.THEMES[theme]["sub"])  # muted, never the bright line
            self.assertNotIn("now", [e["id"] for e in board.message(theme, "Pas de train", "dans la plage")])

    def test_the_car_screen_drives(self):
        """The car of the "no more train" screens is the uploaded animation when there is one, and the
        still bitmap otherwise; its two lines leave the top right corner to the clock."""
        for theme in board.THEMES:
            moving = {e["id"]: e for e in board.next_train(theme, now="06:44", car_path="car.anim")}
            still = {e["id"]: e for e in board.next_train(theme, now="06:44")}
            self.assertEqual((moving["car"]["type"], moving["car"]["path"], moving["car"]["loop"]),
                             ("animation", "car.anim", True))
            self.assertEqual(still["car"]["type"], "xpmbitmap")
            self.assertEqual((moving["a"]["text"], moving["b"]["text"]), ("PAS", "DE TRAIN"))
            self.assertEqual(moving["now"]["y"], -1)
            with_time = {e["id"]: e for e in board.next_train(theme, drive={"minutes": 52, "delay_min": 0},
                                                              now="06:44", car_path="car.anim")}
            self.assertEqual((with_time["a"]["text"], with_time["b"]["text"]), ("52 MIN", "EN VOITURE"))
            self.assertEqual(with_time["now"]["y"], -1)

    def test_clock_keeps_both_times_apart(self):
        """The desk clock shows the train (departure + destination) on the left, where every other
        screen puts the departure time, and the current time alone in the top right corner: two
        different places, so they can never be read one for the other."""
        for theme in board.THEMES:
            els = {e["id"]: e for e in board.clock(theme, "06:44", "07:12", "RENNES")}
            self.assertEqual((els["a"]["text"], els["a"]["x"], els["a"]["align"]), ("07:12", board.RX, "top_left"))
            self.assertEqual((els["b"]["text"], els["b"]["x"], els["b"]["y"]), ("RENNES", board.RX, 6))
            self.assertEqual((els["now"]["text"], els["now"]["x"], els["now"]["align"]), ("06:44", 71, "top_right"))
            self.assertEqual(els["now"]["color"], board.THEMES[theme]["sub"])  # muted: the train stays the bright line
            self.assertNotEqual(els["now"]["color"], els["a"]["color"])
            self.assertIn("logo", els)  # the block on the left stays, like every other screen


class Car(unittest.TestCase):
    def test_frames_are_a_loop_the_firmware_can_play(self):
        th = board.THEMES["day"]
        frames = car.frames(th["block"], th["on_block"])
        self.assertEqual(len(frames), car.FRAMES)
        self.assertTrue(all(len(f) == car.W * car.H * 4 for f in frames))
        self.assertNotEqual(frames[0], frames[car.ROAD_STEP])  # the road moves under the car
        self.assertTrue(any(f[3::4].count(0) for f in frames))  # transparent background: the block shows

    def test_writes_a_busy_anim(self):
        th = board.THEMES["night"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "car_night.anim"
            car.write(path, th["block"], th["on_block"])
            data = path.read_bytes()
        self.assertEqual(data[:8], b"bicycle1")  # the format the bar plays
        self.assertEqual((data[9], data[10], data[16]), (car.W, car.H, car.FPS))  # width, height, fps
        self.assertEqual(int.from_bytes(data[30:34], "little"), car.FRAMES)


if __name__ == "__main__":
    unittest.main()
