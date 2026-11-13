import unittest

import board


def screens(theme):
    now = "06:44"
    return [board.info(theme, "07:12", now=now), board.info(theme, "07:17", delay_min=5, now=now),
            board.info(theme, "07:12", cancelled=True, now=now),
            board.identity(theme, "855634", "RENNES", now=now), board.clock(theme, "06:44", "07:12", "RENNES"),
            board.steps(theme, "wait", 700, 0.4, "06:49", "06:58", now=now),
            board.steps(theme, "prep", 240, 0.8, "06:49", "06:58", now=now),
            board.steps(theme, "go", 95, 0.5, "06:49", "06:58", now=now),
            board.steps(theme, "go", 0, 0.0, "06:49", "06:58", now=now),
            board.next_train(theme, now=now), board.next_train(theme, drive={"minutes": 52, "delay_min": 9}, now=now),
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

    def test_clock_takes_the_free_row(self):
        wait = {e["id"]: e for e in board.steps("day", "wait", 700, 0.4, "06:49", "06:58", now="06:44")}
        prep = {e["id"]: e for e in board.steps("day", "prep", 240, 0.8, "06:49", "06:58", now="06:44")}
        self.assertEqual(wait["now"]["y"], -1)  # the departure time is short: the clock sits beside it
        self.assertEqual(prep["now"]["y"], 6)  # PREPARE-TOI... fills the top row: the clock drops under it

    def test_every_screen_carries_the_clock(self):
        for theme in board.THEMES:
            for els in screens(theme)[:-1]:  # all but the free-text message, which has no room
                found = {e["id"]: e for e in els}
                self.assertIn("now", found)
                self.assertEqual((found["now"]["text"], found["now"]["x"], found["now"]["align"]),
                                 ("06:44", 71, "top_right"))
                self.assertIn(found["now"]["y"], (-1, 6))
                self.assertEqual(found["now"]["color"], board.THEMES[theme]["sub"])  # muted, never the bright line
            self.assertNotIn("now", [e["id"] for e in board.message(theme, "Pas de train", "dans la plage")])

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


if __name__ == "__main__":
    unittest.main()
