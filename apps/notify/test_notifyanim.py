"""Tests for notifyanim.py: which kind gets which picture, and that the writer produces .anim files.

Stdlib only, no bar.

    cd apps/notify && python -m unittest -v test_notifyanim
"""
import glob
import hashlib
import os
import struct
import tempfile
import unittest

import board
import notifyanim

# sha256 of every .anim that must not move when a sprite is redesigned. They are pinned here so an
# accidental change to the renderer breaks loudly; only a deliberate redraw of those pictures may
# update them.
UNCHANGED = {
    "package": "C0534C494C088AF0593B52733A2435AC1DE0A6D94A20032B46D91C26ABFBFAD4",
    "animal": "92342D916B2412A3EFC4D13236B2C0D970659D03F11B1AF28B893768C9B80643",
    "vehicle": "621D8F468057AEAF5A2F63B283D813E8B7AE81E8862793E42CC4806F644D8A70",
    "heatpump": "A5936FF757735DD410133BE87E6260B050E2F8581C25030E279DD7F437DFA6EA",
    "bc250": "678E4523E1BF9A9EC145A47FE2C39A6FACD9B4372A7C72A1ACF8E229F665C9E5",
    "generic": "44CDD53C06D082DFF24014C1DE05F0095770E13DF37EB0878EED953869477EFE",
}


class KindFor(unittest.TestCase):
    """The verdicts Home Assistant's automations actually send, in the README's `verdict.choice`."""

    def test_verdicts(self):
        for raw, expected in (("une personne", "person"),
                              ("plusieurs personnes", "person"),
                              ("livreur", "delivery"),
                              ("colis", "package"),
                              ("chat", "animal"),
                              ("chien", "animal"),
                              ("renard", "animal"),
                              ("oiseau", "animal"),
                              ("biche", "animal"),
                              ("vehicule", "vehicle"),
                              ("alarme_hp", "heatpump")):
            self.assertEqual(notifyanim.kind_for(raw), expected, raw)

    def test_leading_article(self):
        for raw, expected in (("un chat", "animal"),
                              ("une colis", "package"),
                              ("des personnes", "person"),
                              ("le chat", "animal"),
                              ("la biche", "animal"),
                              ("les colis", "package"),
                              ("le livreur", "delivery"),
                              ("l'oiseau", "animal"),
                              ("L'ALARME_HP", "heatpump")):
            self.assertEqual(notifyanim.kind_for(raw), expected, raw)

    def test_case_and_separators(self):
        self.assertEqual(notifyanim.kind_for("  Alarme-HP  "), "heatpump")
        self.assertEqual(notifyanim.kind_for("VEHICULE"), "vehicle")
        self.assertEqual(notifyanim.kind_for("colis "), "package")

    def test_bc250_aliases(self):
        """The BC-250 GPU temperature alerts: the kind, the model, the sensor, the symptom."""
        for raw in ("bc250", "bc 250", "bc_250", "BC-250", "BC-250 90°C", "BC-250 85 C !",
                    "gpu", "GPU", "gpu temperature", "gpu temp", "gpu chaud",
                    "temperature", "temp", "chaud", "surchauffe"):
            self.assertEqual(notifyanim.kind_for(raw), "bc250", raw)
        # the sentence must not become a picture: whole words only
        self.assertEqual(notifyanim.kind_for("chateau"), "generic")
        self.assertEqual(notifyanim.kind_for("chat"), "animal")  # and no regression on the others

    def test_unknown_and_empty(self):
        for raw in ("inconnu", "", None, "   ", "tornade"):
            self.assertEqual(notifyanim.kind_for(raw), "generic", repr(raw))

    def test_every_answer_is_a_picture(self):
        for raw in ("une personne", "un chat", "colis", "vehicule", "alarme_hp", "bc250",
                    "BC-250 90°C", "gpu", "temp", "tornade"):
            self.assertIn(notifyanim.kind_for(raw), notifyanim.KINDS)


class Alert(unittest.TestCase):
    """The picture, where it was detected, the time — in the readable small font, nothing else."""

    def test_source_and_clock_in_small(self):
        els = board.alert("day", "personne", "Terrasse Ouest · une personne", "long message",
                          "12:34", "notify-person.anim", source="TER OUEST")
        self.assertEqual([e["id"] for e in els], ["bg", "anim", "a", "now"])  # no "b": no message
        a = els[2]
        self.assertEqual((a["text"], a["font"]), ("TER OUEST", "small"))
        self.assertEqual((a["x"], a["y"]), (27, -1))
        for key in ("scroll_rate", "scroll_start_delay", "scroll_repeat_delay", "width"):
            self.assertNotIn(key, a)  # nothing scrolls
        now = els[3]
        self.assertEqual((now["text"], now["font"]), ("12:34", "small"))
        self.assertEqual((now["x"], now["y"], now["align"]), (71, 6, "top_right"))
        self.assertEqual(sum(1 for e in els if e["type"] == "text"), 2)  # the label and the clock
        self.assertEqual(els[1]["type"], "animation")

    def test_source_wins_and_the_title_is_the_fallback(self):
        self.assertEqual(board._label("TER OUEST", "Un titre"), "TER OUEST")
        self.assertEqual(board._label("", "PAC"), "PAC")  # fallback to the title, and it fits
        self.assertEqual(board._label("", "Terrasse Ouest"), "Terrass..")  # longer: cut with ".."
        els = board.alert("day", "bc250", "BC-250 — chauffage", "GPU 91 C", "07:05",
                          "notify-bc250.anim", source="BC250 82C")
        self.assertEqual([e["text"] for e in els if e["id"] == "a"], ["BC250 82C"])

    def test_long_source_is_truncated(self):
        text = board._fit("TERRASSE OUEST CAMERA 2")
        self.assertTrue(text.endswith(".."), text)
        self.assertLessEqual(len(text) * board.CHAR_W, board.LABEL_ROOM)
        self.assertEqual(board._fit("TER OUEST"), "TER OUEST")  # nine characters fit as they are

    def test_long_title_without_a_source_is_truncated(self):
        els = board.alert("day", "generic", "Une alarme tres longue qui ne rentre pas", "", "23:59", None)
        text = [e for e in els if e["id"] == "a"][0]["text"]
        self.assertTrue(text.endswith(".."), text)
        self.assertLessEqual(len(text) * board.CHAR_W, board.LABEL_ROOM)

    def test_fallback_block_keeps_the_bang(self):
        els = board.alert("day", "chat", "Chat", "", "23:59", None)
        self.assertEqual([e["id"] for e in els], ["bg", "lb", "bang", "a", "now"])

    def test_night_has_no_background(self):
        els = board.alert("night", "chat", "Chat", "", "23:59", "notify-animal.anim")
        self.assertNotIn("bg", [e["id"] for e in els])


class Sprites(unittest.TestCase):
    def grids(self):
        """Every sprite grid in the app: the single one of a motion kind, or each walk frame."""
        for key, spec in notifyanim.KINDS.items():
            for rows in spec.get("seq") or [spec["rows"]]:
                yield key, rows

    def test_rows_are_rectangular_and_fit_the_block(self):
        for key, rows in self.grids():
            self.assertEqual(len({len(r) for r in rows}), 1, key)
            self.assertLessEqual(len(rows[0]), notifyanim.W, key)
            self.assertLessEqual(len(rows), notifyanim.H, key)
            self.assertTrue(set("".join(rows)) <= set("IS."), key)

    def test_one_second_loop(self):
        self.assertEqual(notifyanim.FRAMES / notifyanim.FPS, 1.0)  # 60 s / 1 s is whole (gotcha 5)

    def test_walk_cycles(self):
        """person/delivery: 4 hard frames, one canvas, feet on the last row, 0.4 s."""
        for key in ("person", "delivery"):
            spec = notifyanim.KINDS[key]
            seq, fps = spec["seq"], notifyanim.fps_for(key)
            self.assertEqual(len(seq), 4, key)
            self.assertEqual(fps, 10, key)  # 100 ms a frame, from the pixel-art-animator skill
            self.assertEqual(60 * fps % len(seq), 0, key)  # the loop divides 60 s
            self.assertEqual(len({len(rows[0]) for rows in seq}), 1, key)  # one shared canvas
            for rows in seq:
                self.assertEqual(len(rows), notifyanim.H, key)  # 16 rows: _layer pins it at y=0
                self.assertIn("I", rows[-1], key)  # near foot on the ground line
                self.assertIn("S", rows[-1], key)  # far foot on the ground line too
            self.assertEqual(len({tuple(rows) for rows in seq}), 4, key)  # four distinct poses

    def test_walk_frames_are_hard_pixels(self):
        """No edge coverage, no anti-aliasing: only the block, the ink and one shade."""
        th = board.THEMES["day"]
        allowed = {th["block"][:7], th["on_block"][:7],
                   board._mix(th["on_block"], th["block"], notifyanim.SHADE)}
        for key in ("person", "delivery"):
            for frame in notifyanim.frames(key, th["block"], th["on_block"]):
                seen = {"#%02X%02X%02X" % (frame[i], frame[i + 1], frame[i + 2])
                        for i in range(0, len(frame), 4)}
                self.assertTrue(seen <= allowed, (key, seen - allowed))


class WriteAll(unittest.TestCase):
    def test_writes_every_kind_as_bicycle1(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = notifyanim.write_all(tmp, "day")
            self.assertEqual(set(paths), set(notifyanim.KINDS))
            self.assertIn("bc250", paths)
            self.assertTrue(paths["bc250"].endswith("bc250.anim"))
            self.assertEqual(len(glob.glob(os.path.join(tmp, "*.anim"))), len(notifyanim.KINDS))
            for key, path in paths.items():
                with open(path, "rb") as f:
                    data = f.read()
                self.assertEqual(data[:8], b"bicycle1", key)
                head = struct.unpack("<8s BBBB HHBB II II", data[:34])
                self.assertEqual((head[2], head[3]), (notifyanim.W, notifyanim.H), key)
                self.assertEqual(head[7], notifyanim.fps_for(key), key)
                self.assertEqual(head[12], notifyanim.frames_in(key), key)
                self.assertEqual(head[11], 1, key)  # one "default" section: no gotcha-8 rejection

    def test_unchanged_kinds_are_byte_identical(self):
        """The six kinds that were not redesigned still write exactly the same bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = notifyanim.write_all(tmp, "day")
            for key, digest in UNCHANGED.items():
                with open(paths[key], "rb") as f:
                    self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest.lower(), key)

    def test_themes_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = notifyanim.write_all(os.path.join(tmp, "day"), "day")
            night = notifyanim.write_all(os.path.join(tmp, "night"), "night")
            with open(day["person"], "rb") as f:
                a = f.read()
            with open(night["person"], "rb") as f:
                b = f.read()
            self.assertEqual(len(a), len(b))
            self.assertNotEqual(a, b)
            self.assertEqual(board.THEMES["night"]["bg"], None)  # black background, dimmest


if __name__ == "__main__":
    unittest.main()
