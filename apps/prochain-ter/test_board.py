import unittest

import board


def screens(theme):
    return [board.info(theme, "07:12"), board.info(theme, "07:17", delay_min=5), board.info(theme, "07:12", cancelled=True),
            board.identity(theme, "855634", "RENNES"), board.clock(theme, "06:44", "RENNES"),
            board.steps(theme, "wait", 700, 0.4, "06:49", "06:58"), board.steps(theme, "prep", 240, 0.8, "06:49", "06:58"),
            board.steps(theme, "go", 95, 0.5, "06:49", "06:58"), board.steps(theme, "go", 0, 0.0, "06:49", "06:58"),
            board.next_train(theme), board.next_train(theme, drive={"minutes": 52, "delay_min": 9}), board.steps(theme, "prep", 720, 1.0, "06:49", "06:58"), board.next_train(theme, "07:40", "07:31"), board.message(theme, "Pas de train", "dans la plage")]


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


if __name__ == "__main__":
    unittest.main()
