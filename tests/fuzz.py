"""Random-key fuzzer: plays many games with random input and reports crashes.

usage: python3 tests/fuzz.py [games] [keys_per_game] [first_seed]
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import HeadlessGame  # noqa: E402

KEYS = list("hjklyubnhjklyubnhjklyubnHJKLYUBN.,sgiItTrqwWdDoOcCeEPvx?@^ ") + \
    list("abcdefghijklmnopqrstuvwxyz0123456789") + ["\r", "\x1b", "\x1b", "y", "n"]


def play(seed, nkeys, stop_on="Q"):
    rng = random.Random(seed)
    g = HeadlessGame(seed=seed)
    try:
        g.send(rng.choice("abcdefgh"))
        g.send("\r")
        for i in range(nkeys):
            if g.term.finished:
                return "ended", i
            k = rng.choice(KEYS)
            if not g.send(k, timeout=10):
                if g.term.finished:
                    return "ended", i
                return "HANG after %r\n%s" % (k, g.screen), i
        return "ok", nkeys
    except RuntimeError as e:
        return "CRASH: %s" % e, -1
    finally:
        g.close()


def play_deep(seed, nkeys):
    """Visit every dungeon and volcano level (wizard teleport) with a tough
    character, fuzzing keys on each one."""
    from pyularn import player, dungeon
    rng = random.Random(seed)
    g = HeadlessGame(seed=seed)
    try:
        g.send(rng.choice("abcdefgh"))
        g.send("\r")
        for lev in range(1, dungeon.VBOTTOM + 1):
            if g.term.finished:
                return "ended on level %d" % lev, lev
            # game thread is blocked in getkey(): safe to poke state
            player.wizard = 1
            player.c[player.HPMAX] = player.c[player.HP] = 3000
            player.c[player.SPELLMAX] = player.c[player.SPELLS] = 200
            g.send("\x1b")
            g.send("Z")
            g.send(str(lev) + "\r")
            for i in range(nkeys):
                if g.term.finished:
                    return "ended on level %d" % lev, lev
                k = rng.choice(KEYS)
                if not g.send(k, timeout=10):
                    if g.term.finished:
                        return "ended on level %d" % lev, lev
                    return "HANG on level %d after %r\n%s" % (lev, k, g.screen), lev
        return "ok", dungeon.VBOTTOM
    except RuntimeError as e:
        return "CRASH: %s" % e, -1
    finally:
        g.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "deep":
        sys.argv.pop(1)
        play = play_deep  # noqa: F811
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    nkeys = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    bad = 0
    for seed in range(first, first + games):
        res, n = play(seed, nkeys)
        if res.startswith(("CRASH", "HANG")):
            bad += 1
            print("seed %d: %s" % (seed, res))
        else:
            print("seed %d: %s (%d keys)" % (seed, res, n))
    print("failures:", bad)
    sys.exit(1 if bad else 0)
