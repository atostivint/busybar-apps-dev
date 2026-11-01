import unittest

import board


def screens(theme):
    return [board.panel(theme, "07:12 RNS", "2"), board.panel(theme, "07:17 RNS", "2", delay_min=5),
            board.panel(theme, "07:12 RNS", "2", cancelled=True), board.panel(theme, "07:12 RNS"),
            board.identity(theme, "855634", "RENNES"), board.leave(theme, 14, "06:58"),
            board.leave(theme, 5, "06:58"), board.leave(theme, 120, "06:58"), board.leave(theme, 0, "06:58"),
            board.message(theme, "Pas de train", "dans la plage")]


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
        self.assertNotIn("bg", [e["id"] for e in board.panel("night", "07:12 RNS", "2")])
        self.assertIn("bg", [e["id"] for e in board.panel("day", "07:12 RNS", "2")])


if __name__ == "__main__":
    unittest.main()
