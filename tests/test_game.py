"""Headless game tests (run: python3 -m unittest)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fuzz  # noqa: E402
from harness import HeadlessGame  # noqa: E402

from pyularn import dungeon, player  # noqa: E402


class GameTest(unittest.TestCase):
    def test_start_and_move(self):
        g = HeadlessGame(seed=1)
        try:
            self.assertIn("what are ya", g.screen)
            g.send("e")
            self.assertIn("Press return", g.screen)
            g.send("\r")
            self.assertIn("HP:", g.screen)
            self.assertEqual(dungeon.level, 0)
            x0 = player.playerx
            g.send("l")
            self.assertIn(player.playerx, (x0, x0 + 1))
        finally:
            g.close()

    def test_reproducible_across_games(self):
        a = [fuzz.play_deep(s, 60)[0] for s in (11, 12)]
        b = [fuzz.play_deep(s, 60)[0] for s in (12, 11)]
        self.assertEqual(a, [b[1], b[0]])

    def test_fuzz_town(self):
        for seed in range(3):
            res, _ = fuzz.play(seed, 400)
            self.assertFalse(res.startswith(("CRASH", "HANG")), res)

    def test_fuzz_all_levels(self):
        for seed in range(2):
            res, _ = fuzz.play_deep(seed, 80)
            self.assertFalse(res.startswith(("CRASH", "HANG")), res)


if __name__ == "__main__":
    unittest.main()
