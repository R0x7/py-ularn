"""The item book: measuring items from play, notes, and the tools (run: python3 -m unittest)."""

import json
import os
import re
import shutil
import tempfile
import unittest

from pyularn import items, runs
from tests.test_mcp import McpClient


def snap(level=1, money=100, wc=0, ac=0, inv=(), wield=None, wear=None, shield=None, floor=()):
    return {"level": level, "level_name": runs.level_name(level), "money": money,
            "wc": wc, "ac": ac, "inv": [list(i) for i in inv],
            "wield": list(wield) if wield else None, "wear": list(wear) if wear else None,
            "shield": list(shield) if shield else None, "floor": sorted(floor)}


DAGGER = ("dagger", 0)
AXE = ("battle axe", 2)
LEATHER = ("leather armor", 0)


class DiffTest(unittest.TestCase):
    """What one action shows about items, worked out from two snapshots."""

    def record(self, before, after, book=None, **kw):
        book = book or items.new_book()
        items.record(book, items.diff(before, after, **kw), run_id="r1")
        return book

    def test_wielding_from_bare_hands_measures_the_weapon(self):
        book = self.record(snap(inv=[DAGGER]), snap(inv=[DAGGER], wc=3, wield=DAGGER))
        self.assertEqual(items.known_base(book["items"]["dagger"], "wc"), 3)

    def test_unwielding_and_taking_off_measure_too(self):
        book = self.record(snap(inv=[AXE, LEATHER], wc=19, ac=2, wield=AXE, wear=LEATHER),
                           snap(inv=[AXE, LEATHER]))
        # +2 axe gave 19, so its base is 17; the leather gave 2.
        self.assertEqual(items.known_base(book["items"]["battle axe"], "wc"), 17)
        self.assertEqual(items.known_base(book["items"]["leather armor"], "ac"), 2)

    def test_swap_uses_what_the_book_knows(self):
        before = snap(inv=[DAGGER, AXE], wc=3, wield=DAGGER)
        after = snap(inv=[DAGGER, AXE], wc=19, wield=AXE)
        unknown = self.record(before, after)
        self.assertNotIn("battle axe", unknown["items"], "dagger unknown: nothing to go on")
        book = self.record(snap(inv=[DAGGER]), snap(inv=[DAGGER], wc=3, wield=DAGGER))
        book = self.record(before, after, book=book)
        self.assertEqual(items.known_base(book["items"]["battle axe"], "wc"), 17)

    def test_no_measurement_when_the_pack_changed(self):
        book = self.record(snap(inv=[]), snap(inv=[DAGGER], wc=3, wield=DAGGER))
        self.assertEqual(book["items"], {})

    def test_two_armour_changes_at_once_are_not_split(self):
        shield = ("shield", 0)
        book = self.record(snap(inv=[LEATHER, shield]),
                           snap(inv=[LEATHER, shield], ac=4, wear=LEATHER, shield=shield))
        self.assertEqual(book["items"], {})

    def test_prices_in_town(self):
        bought = self.record(snap(level=0, money=500), snap(level=0, money=480, inv=[DAGGER]))
        self.assertEqual(bought["items"]["dagger"]["prices"]["bought"][0]["price"], 20)
        sold = self.record(snap(level=0, money=0, inv=[AXE]), snap(level=0, money=1200))
        self.assertEqual(sold["items"]["battle axe"]["prices"]["sold"][0],
                         {"price": 1200, "plus": 2, "run": "r1"})
        self.assertIn("sold for 1,200 (enchanted)", items.summary(sold["items"]["battle axe"]))
        # Not in the dungeon, and not when buy prices come from the buy skill instead.
        self.assertEqual(self.record(snap(money=500), snap(money=480, inv=[DAGGER]))["items"], {})
        self.assertEqual(self.record(snap(level=0, money=500),
                                     snap(level=0, money=480, inv=[DAGGER]),
                                     prices=False)["items"], {})

    def test_found_on_levels(self):
        book = self.record(snap(level=2), snap(level=2, floor=["spear", "ruby"]))
        book = self.record(snap(level=2, floor=["spear"]), snap(level=2, floor=["spear"]), book=book)
        book = self.record(snap(level=2, floor=["spear"]), snap(level=16, floor=["spear"]), book=book)
        self.assertEqual(book["items"]["spear"]["found_on"], ["2", "V1"])
        self.assertEqual(book["items"]["ruby"]["found_on"], ["2"])

    def test_most_common_measurement_wins(self):
        book = items.new_book()
        for gives in (3, 3, 1):
            items.record(book, [{"type": "stat", "item": "dagger", "plus": 0,
                                 "stat": "wc", "gives": gives}])
        e = book["items"]["dagger"]
        self.assertEqual(items.known_base(e, "wc"), 3)
        self.assertIn("also seen: 1 x1", items.summary(e))


class NoteTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for run_id in ("run-a", "run-b"):
            os.makedirs(os.path.join(self.root, run_id))
            runs.save_meta(os.path.join(self.root, run_id), {"run_id": run_id, "seed": 1})

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_names(self):
        self.assertEqual(items.canonical("A Battle Axe"), "battle axe")
        self.assertEqual(items.canonical("instant healing"), "potion of instant healing")
        with self.assertRaisesRegex(items.ItemError, "did you mean"):
            items.canonical("healing")      # potion of healing and of instant healing
        with self.assertRaisesRegex(items.ItemError, "no item"):
            items.canonical("bazooka")
        self.assertNotIn("arrow trap", items.all_kinds())
        self.assertNotIn("bank of larn", items.all_kinds())

    def test_add_confirm_retract(self):
        name, note = items.add_note(self.root, "leather", "Rust monsters cannot rust it.",
                                    evidence=["run-a"])
        self.assertEqual((name, note["id"], note["status"]), ("leather armor", "I1", "tentative"))
        with self.assertRaisesRegex(items.ItemError, "two runs"):
            items.add_note(self.root, "leather armor", "x", evidence=["run-a"], confidence="confirmed")
        with self.assertRaisesRegex(items.ItemError, "no such run"):
            items.add_note(self.root, "leather armor", "x", evidence=["nope"])
        _, again = items.add_note(self.root, "leather armor", "rust monsters cannot rust it.",
                                  evidence=["run-a", "run-b"], confidence="confirmed")
        self.assertEqual((again["id"], again["status"], again["evidence"]),
                         ("I1", "confirmed", ["run-a", "run-b"]))
        with open(os.path.join(self.root, "ITEMS.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("I1: Rust monsters cannot rust it. (runs: run-a, run-b)", text)

        items.retract_note(self.root, "I1", "A rust monster rusted it.")
        book = items.load(self.root)
        self.assertEqual(items.facts(book, ["leather armor"]), {})
        self.assertIn("~~Rust monsters", items.lookup(book, "leather"))
        with self.assertRaises(items.ItemError):
            items.retract_note(self.root, "I9", "why")


class ItemBookToolsTest(unittest.TestCase):
    """The server measures items as an agent plays, and the tools read and
    write the book."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.c = McpClient(["--record", self.root])
        self.c.request("initialize", {"protocolVersion": "2025-06-18"})

    def tearDown(self):
        self.c.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def call(self, name, **args):
        text, err = self.c.call(name, **args)
        self.assertFalse(err, text)
        return text

    def state(self):
        return json.loads(self.call("get_state").split("State:\n", 1)[-1])

    def test_measured_while_playing(self):
        text = self.call("new_game", character_class="rogue", seed=5)
        run = re.search(r"as run (\S+)\.", text).group(1)
        self.assertIn("item book is empty", self.call("get_items"))
        self.assertNotIn("item_book", self.state())

        self.call("send_keys", keys="w")    # Rogue: leather armour worn, dagger in hand
        self.call("send_keys", keys="-")    # unwield: WC 3 -> 0
        self.call("send_keys", keys="T")    # take off: AC 2 -> 0
        self.call("send_keys", keys="W")
        self.call("send_keys", keys="a")    # wear again: AC 0 -> 2
        book = items.load(self.root)
        self.assertEqual(book["items"]["dagger"]["measured"], {"wc": {"3": 1}})
        self.assertEqual(book["items"]["leather armor"]["measured"], {"ac": {"2": 2}})

        self.call("note_item", item="dagger", text="Weak; replace it first.", evidence=[run])
        st = self.state()
        self.assertIn("WC 3 base", st["item_book"]["dagger"])
        self.assertIn("I1: Weak; replace it first.", st["item_book"]["dagger"])
        self.assertIn("AC 2 base", st["item_book"]["leather armor"])
        self.assertIn("I1", self.call("get_items", item="dag"))

        text, err = self.c.call("note_item", item="bazooka", text="x")
        self.assertTrue(err)
        self.assertIn("no item called", text)
        self.assertIn("Note I1 on dagger retracted",
                      self.call("retract_item_note", note_id="I1", reason="test"))
        self.assertIn("## Item book", self.call("get_briefing"))
        self.assertIn("dagger", self.call("get_briefing"))


if __name__ == "__main__":
    unittest.main()
