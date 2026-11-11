"""The learning loop: progress scores, the playbook, the strategy tree, the
judging of strategies, the briefing and the coach (run: python3 -m unittest)."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

from pyularn import coach, learn, runs
from tests.test_mcp import McpClient, ROOT


class ProgressTest(unittest.TestCase):
    def test_ladder(self):
        def score(**outcome):
            return learn.progress(outcome)

        self.assertEqual(score(), {"score": 0.0, "milestone": "never left town"})
        self.assertEqual(learn.progress(None)["score"], 0.0)
        self.assertEqual(score(deepest={"dungeon": 3, "volcano": 0}, character_level=4),
                         {"score": 3.1, "milestone": "dungeon level 3"})
        deep = score(deepest={"dungeon": 15, "volcano": 2}, character_level=20)
        self.assertEqual(deep, {"score": 19.5, "milestone": "volcano level 2"})
        cure = score(deepest={"dungeon": 15, "volcano": 5}, has_cure=True)
        self.assertEqual(cure, {"score": 35.0, "milestone": "found the cure"})
        won = score(deepest={"dungeon": 15, "volcano": 5}, has_cure=False, won=True)
        self.assertEqual(won, {"score": 65.0, "milestone": "won"})
        # Each step up the ladder beats any amount of the step below.
        self.assertLess(score(deepest={"dungeon": 4}, character_level=20)["score"],
                        score(deepest={"dungeon": 5}, character_level=1)["score"])
        self.assertLess(deep["score"], cure["score"])
        self.assertLess(cure["score"], won["score"])


class JudgingTest(unittest.TestCase):
    """advance() and choose_next() on made-up results: no game is played."""

    def setUp(self):
        self.c = learn.new_campaign(rules={"budget": 3, "margin": 1.0, "holdout": 2, "patience": 2})
        self.games = []          # newest first, as runs.list_runs returns them

    def add(self, title, parent=None, status="trial"):
        sid = "S%d" % self.c["next_strategy"]
        self.c["next_strategy"] += 1
        self.c["strategies"][sid] = {
            "id": sid, "parent": parent or self.c["base"], "title": title, "change": title,
            "character_class": None, "status": status, "note": None}
        return sid

    def play(self, sid, depths, which="trial", result="died", difficulty=0, seeds=None):
        """Record finished games reaching the given dungeon depths, one per
        seed.  A depth of "win" is a game that was won."""
        for seed, depth in zip(seeds or self.c["seeds"][which], depths):
            if depth == "win":
                outcome = {"result": "won", "won": True, "deepest": {"dungeon": 15, "volcano": 5}}
            else:
                outcome = {"result": result, "deepest": {"dungeon": depth, "volcano": 0}}
            self.games.insert(0, {"run_id": "r%d" % len(self.games), "strategy": sid, "seed": seed,
                                  "difficulty": difficulty, "outcome": outcome,
                                  "progress": learn.progress(outcome)})

    def advance(self):
        return learn.advance(self.c, self.games)

    def next(self):
        return learn.choose_next(self.c, learn.stats(self.c, self.games))

    def status(self, sid):
        return self.c["strategies"][sid]["status"]

    def test_seeds_are_fixed_and_separate(self):
        seeds = self.c["seeds"]
        self.assertEqual((len(seeds["trial"]), len(seeds["holdout"])), (3, 2))
        self.assertEqual(len(set(seeds["trial"]) | set(seeds["holdout"])), 5)
        st = learn.stats(self.c, self.games)
        self.assertEqual(learn.next_seed(self.c, "S1", st), seeds["trial"][0])
        self.play("S1", [2])
        self.play("S1", [0], result="stopped", seeds=seeds["trial"][1:])   # abandoned: replayed
        st = learn.stats(self.c, self.games)
        self.assertEqual(learn.next_seed(self.c, "S1", st), seeds["trial"][1])
        self.play("S1", [2, 2], seeds=seeds["trial"][1:])
        self.assertIsNone(learn.next_seed(self.c, "S1", learn.stats(self.c, self.games)))

    def test_trial_then_holdout_then_proven(self):
        self.assertEqual(self.next(), ("S1", "measuring the base, so later ideas have something to beat", False))
        s2 = self.add("armour")
        self.play(s2, [5, 5, 5])
        self.assertFalse(self.advance())             # the base is not measured: no verdict yet
        self.assertEqual(self.next()[0], "S1")
        self.play("S1", [2, 2, 2])
        self.assertTrue(self.advance())
        self.assertEqual(self.status(s2), "holdout")
        self.assertEqual(self.c["base"], "S1")       # not the base until it is proven
        self.assertEqual(self.next()[:1] + self.next()[2:], (s2, False))
        st = learn.stats(self.c, self.games)
        self.assertEqual(learn.next_seed(self.c, s2, st), self.c["seeds"]["holdout"][0])

        self.play(s2, [3], which="holdout")
        self.assertFalse(self.advance())             # one of two unseen seeds played
        self.play(s2, [1], which="holdout", seeds=self.c["seeds"]["holdout"][1:])
        self.assertTrue(self.advance())              # averages 2 there: as good as S1's 2
        self.assertEqual((self.status(s2), self.c["base"]), ("proven", s2))
        self.assertIn("it is the new base", self.c["log"][-1]["text"])
        self.assertEqual(self.next(), (s2, "no idea is waiting to be tried", True))
        self.assertFalse(self.advance())             # nothing more to decide

    def test_no_better_is_abandoned(self):
        self.play("S1", [2, 2, 2])
        s2, s3 = self.add("a"), self.add("b")
        self.play(s2, [2, 3, 3])                     # +0.67: short of the margin of 1
        self.play(s3, [3, 3])                        # trial not finished
        self.assertTrue(self.advance())
        self.assertEqual((self.status(s2), self.status(s3)), ("abandoned", "trial"))
        note = self.c["strategies"][s2]["note"]
        self.assertEqual(note, "averaged 2.67 over 3 games, S1 averaged 2.0 and it needed 3.0")
        self.assertEqual(self.c["base"], "S1")
        self.assertEqual(self.next()[0], s3)         # on with the next idea
        self.play(s3, [3], seeds=self.c["seeds"]["trial"][2:])
        self.advance()
        self.assertEqual(self.status(s3), "holdout")  # exactly +1 passes

    def test_luck_on_known_seeds_does_not_pass(self):
        self.play("S1", [2, 2, 2])
        s2 = self.add("lucky")
        self.play(s2, [6, 6, 6])
        self.play(s2, [1, 2], which="holdout")       # 1.5 on unseen seeds, below S1's 2
        self.advance()
        self.assertEqual(self.status(s2), "abandoned")
        self.assertIn("passed its trial but did not hold up", self.c["strategies"][s2]["note"])
        self.assertEqual(self.c["base"], "S1")

    def test_only_fair_games_count(self):
        self.play("S1", [2, 2, 2])
        s2 = self.add("x")
        self.play(s2, [9, 9, 9], difficulty=1)                         # another difficulty
        self.play(s2, [9, 9, 9], result="stopped")                     # abandoned games
        self.play(s2, [9, 9, 9], seeds=[111, 222, 333])                # not the trial's seeds
        self.assertFalse(self.advance())
        self.assertEqual(self.status(s2), "trial")
        self.play(s2, [1, 1, 1])
        self.play(s2, [9, 9, 9])                                       # replays: the first counts
        self.advance()
        self.assertEqual(self.status(s2), "abandoned")
        st = learn.stats(self.c, self.games)[s2]
        self.assertEqual((st["runs"], st["trial_mean"]), (9, 1.02))

    def test_without_holdout(self):
        self.c["rules"]["holdout"] = 0
        self.play("S1", [1, 1, 1])
        s2 = self.add("x")
        self.play(s2, [4, 4, 4])
        self.advance()
        self.assertEqual((self.status(s2), self.c["base"]), ("proven", s2))

    def prove(self, title, depth):
        sid = self.add(title)
        self.play(sid, [depth] * 3)
        self.play(sid, [depth] * 2, which="holdout")
        self.advance()
        self.assertEqual((self.status(sid), self.c["base"]), ("proven", sid))
        return sid

    def fail(self, title, parent=None):
        sid = self.add(title, parent)
        self.play(sid, [0, 0, 0])
        self.advance()
        return sid

    def test_stepping_back_from_a_stalled_line(self):
        self.play("S1", [1, 1, 1])
        s2 = self.prove("armour", 3)
        s3 = self.prove("armour + shield", 5)

        f1 = self.fail("idea a")
        self.assertEqual(self.c["base"], s3)         # one failure is not a stall
        ok = self.add("pending")                     # an idea still on trial holds the line
        self.assertEqual(self.c["base"], s3)
        self.c["strategies"][ok]["status"] = "abandoned"
        self.assertTrue(self.advance())              # now the last two ideas on S3 failed
        self.assertEqual((self.status(s3), self.c["base"]), ("stalled", s2))
        self.assertIn("%s armour + shield has stalled" % s3, self.c["log"][-1]["text"])
        self.assertIn("Stepping back to %s" % s2, self.c["log"][-1]["text"])
        self.assertEqual(self.next(), (s2, "no idea is waiting to be tried", True))

        # From S2 another direction is tried; if those fail too, back to S1.
        self.fail("idea b")
        self.assertEqual(self.c["base"], s2)         # S3 was a success under S2, so one failure
        self.fail("idea c")
        self.assertEqual((self.status(s2), self.c["base"]), ("stalled", "S1"))
        # The baseline has nowhere to step back to, however often ideas fail.
        self.fail("idea d")
        self.fail("idea e")
        self.fail("idea f")
        self.assertEqual((self.status("S1"), self.c["base"]), ("proven", "S1"))
        # A stalled strategy is still the best so far and can be built on.
        self.assertEqual(self.status(f1), "abandoned")
        self.assertIn(self.status(s3), learn.SOLID)

    def test_a_success_resets_patience(self):
        self.play("S1", [1, 1, 1])
        s2 = self.prove("armour", 3)
        self.fail("idea a")
        s4 = self.prove("better", 6)                 # proven on top of S2
        self.assertEqual(self.c["base"], s4)
        self.fail("idea b", parent=s2)               # an old branch failing does not stall S4
        self.assertEqual((self.c["base"], self.status(s2)), (s4, "proven"))

    def test_the_difficulty_ladder(self):
        self.c = learn.new_campaign(rules={"budget": 3, "margin": 1.0, "holdout": 2, "patience": 2,
                                           "window": 3, "wins": 2, "top": 1})
        first_seeds = self.c["seeds"]
        self.play("S1", [2, 2, 2])
        s2 = self.prove("armour", 4)                      # proven: the base
        on_trial = self.add("mid-trial")
        checking = self.add("being checked", status="holdout")
        stalled = self.add("old line", parent="S1", status="stalled")
        failed = self.add("bad idea", status="abandoned")
        extra = [9001, 9002, 9003, 9004]

        self.play(s2, ["win"], seeds=extra)
        self.assertTrue(self.advance())                   # one win of the last three: stay...
        line = self.c["strategies"]["S7"]                 # ...but the win gets a line to follow it
        self.assertEqual((line["kind"], line["parent"], self.c["difficulty"]), ("line", s2, 0))
        rung = learn.ladder(self.c, self.games)
        self.assertEqual((rung["difficulty"], rung["recent_wins"], rung["wins"], rung["window"]),
                         (0, 1, 2, 3))
        self.play(s2, [3, 3, 3], seeds=extra[1:])
        self.play("freestyle", ["win", "win", "win"], seeds=[1, 2, 3])   # not this campaign's
        self.assertFalse(self.advance())                  # the win has left the window
        self.assertEqual(learn.ladder(self.c, self.games)["recent_wins"], 0)

        self.play(s2, ["win", 3, "win"], seeds=[9005, 9006, 9007])
        self.assertTrue(self.advance())                   # two of the latest three
        self.assertEqual((self.c["difficulty"], self.c["complete"], self.c["base"]), (1, False, s2))
        (cleared,) = self.c["cleared"]
        self.assertEqual((cleared["difficulty"], cleared["base"], cleared["wins"], cleared["seeds"]),
                         (0, s2, 3, first_seeds))
        self.assertIn("Difficulty 0 cleared: 2 of the last 3 games were won. Moving up to "
                      "difficulty 1 with %s as the base" % s2, self.c["log"][-1]["text"])

        # The tree carries over; the results do not.
        self.assertFalse(set(self.c["seeds"]["trial"] + self.c["seeds"]["holdout"])
                         & set(first_seeds["trial"] + first_seeds["holdout"]))
        st = learn.stats(self.c, self.games)
        self.assertEqual((st[s2]["runs"], st["S1"]["runs"]), (0, 0))
        self.assertEqual([self.status(s) for s in (s2, on_trial, checking, stalled, failed)],
                         ["proven", "trial", "trial", "proven", "abandoned"])
        # The line made from the wins below was never tried, so it still comes first;
        # after it, the base is measured again.
        self.assertEqual((line["status"], len(line["models"]), self.next()[0]), ("line", 3, "S7"))
        line["status"] = "abandoned"
        self.assertEqual(self.next()[:2], (s2, "measuring the base, so later ideas have something to beat"))
        line["status"] = "line"
        self.assertEqual(learn.next_seed(self.c, s2, st), self.c["seeds"]["trial"][0])
        self.assertEqual(learn.ladder(self.c, self.games)["games"], 0)

        # Winning at the top completes the campaign, once.
        self.play(s2, ["win", "win", 2], difficulty=1)
        self.assertTrue(self.advance())
        self.assertEqual((self.c["difficulty"], self.c["complete"]), (1, True))
        self.assertEqual([c["difficulty"] for c in self.c["cleared"]], [0, 1])
        self.assertIn("the campaign is complete", self.c["log"][-1]["text"])
        self.assertFalse(self.advance())

    def test_upgrading_an_older_campaign(self):
        old = {"version": 1, "goal": "g", "difficulty": 0, "current": "S3", "next_strategy": 4,
               "lessons": [], "next_lesson": 1,
               "strategies": {
                   "S1": {"id": "S1", "parent": None, "title": "Baseline", "change": "-",
                          "character_class": None, "status": "active", "note": None},
                   "S2": {"id": "S2", "parent": "S1", "title": "a", "change": "a",
                          "character_class": None, "status": "active", "note": None},
                   "S3": {"id": "S3", "parent": "S2", "title": "b", "change": "b",
                          "character_class": None, "status": "active", "note": None}}}
        root = tempfile.mkdtemp()
        with open(os.path.join(root, "campaign.json"), "w", encoding="utf-8") as f:
            json.dump(old, f)
        c = learn.load(root)
        self.assertEqual((c["version"], c["base"], c["rules"]), (2, "S1", learn.DEFAULT_RULES))
        self.assertEqual([s["status"] for s in c["strategies"].values()], ["proven", "trial", "trial"])
        self.assertEqual(c["strategies"]["S3"]["parent"], "S1")
        self.assertNotIn("current", c)
        self.assertEqual(len(c["seeds"]["trial"]), 5)
        self.assertEqual(learn.load(root), c)        # and it is saved that way

    def test_a_win_becomes_a_line_to_follow(self):
        self.play("S1", [3, 3, 3])
        idea = self.add("Armour")
        self.play(idea, ["win"])                       # game r3 wins its first trial seed
        self.assertTrue(self.advance())
        line = self.c["strategies"]["S3"]
        self.assertEqual((line["kind"], line["status"], line["parent"], line["models"]),
                         ("line", "line", idea, ["r3"]))
        self.assertEqual(line["title"], "Winning line: Armour")
        self.assertIn("won game r3", line["change"])
        # It gets seeds of its own that nobody has played.
        taken = set(self.c["seeds"]["trial"]) | set(self.c["seeds"]["holdout"])
        self.assertEqual((len(line["seeds"]), len(set(line["seeds"]) & taken)), (3, 0))
        self.assertIn("S3 is made to follow that win", self.c["log"][-1]["text"])
        # It is played next, ahead of the trial in progress, on the first of them.
        sid, why, needs_proposal = self.next()
        self.assertEqual((sid, needs_proposal), ("S3", False))
        self.assertIn("follows the won game r3", why)
        st = learn.stats(self.c, self.games)
        self.assertEqual(learn.next_seed(self.c, "S3", st), line["seeds"][0])
        self.assertFalse(self.advance())               # nothing more to decide yet

        # Winning the same seed again shows nothing: it is not a win, and makes no line.
        self.play(idea, ["win"])                       # r4, the seed r3 won
        self.assertEqual(learn.repeat_wins(self.games), {"r4"})
        self.advance()
        self.assertEqual(sorted(self.c["strategies"]), ["S1", "S2", "S3"])
        self.assertEqual(learn.ladder(self.c, self.games)["total_wins"], 1)
        self.assertEqual(learn.stats(self.c, self.games)[idea]["wins"], 1)
        # A second win on another seed, while the line is being tried, is one more model.
        self.play(idea, ["win"], seeds=[777])          # r5
        self.advance()
        self.assertEqual((sorted(self.c["strategies"]), line["models"]),
                         (["S1", "S2", "S3"], ["r3", "r5"]))

        # The line is judged on wins on its own seeds: two losses decide nothing...
        self.play("S3", [2, 4], seeds=line["seeds"])
        self.advance()
        self.assertEqual((self.status("S3"), self.next()[0]), ("line", "S3"))
        st = learn.stats(self.c, self.games)
        self.assertEqual(learn.next_seed(self.c, "S3", st), line["seeds"][2])
        self.assertIn("2 of 3 games on unseen seeds, 0 won", learn._stat_text(self.c, line, st["S3"]))
        # ...and one win proves it and makes it the base.
        self.play("S3", ["win"], seeds=line["seeds"][2:])
        self.assertTrue(self.advance())
        self.assertEqual((self.status("S3"), self.c["base"]), ("proven", "S3"))
        self.assertEqual(line["note"], "won 1 of its first 3 games on seeds nobody had played")
        self.assertIn("S3 Winning line: Armour proven", self.c["log"][-1]["text"])
        # A win under a line is the line working: it makes no line of its own.
        self.assertEqual(sorted(self.c["strategies"]), ["S1", "S2", "S3"])

    def test_a_line_that_cannot_repeat_the_win_is_abandoned(self):
        self.play("S1", ["win", 3, 3])
        self.advance()
        line = self.c["strategies"]["S2"]
        self.assertEqual((line["parent"], line["status"]), ("S1", "line"))
        self.play("S2", [9, 9, 9], seeds=line["seeds"])
        self.advance()
        self.assertEqual(self.status("S2"), "abandoned")
        self.assertIn("won none of its 3 games on seeds nobody had played", line["note"])
        self.assertEqual(self.c["base"], "S1")
        self.assertEqual(self.next()[0], "S1")
        # The next win under the baseline gets a line of its own.
        self.play("S1", ["win"], seeds=[4242])
        self.advance()
        self.assertEqual((self.c["strategies"]["S3"]["kind"], self.next()[0]), ("line", "S3"))

    def test_digest_of_a_strategy(self):
        def game(n, sid="S1", level="V5", killer=None, result="died", difficulty=0, turns=100,
                 won=False, cure=False):
            outcome = {"result": result, "won": won, "has_cure": cure, "killer": killer,
                       "reason": "killed by a %s" % killer if killer else result,
                       "dungeon_level": level, "turns": turns,
                       "deepest": {"dungeon": 3, "volcano": 5 if level == "V5" else 0}}
            return {"run_id": "g%d" % n, "strategy": sid, "seed": n, "difficulty": difficulty,
                    "outcome": outcome, "progress": learn.progress(outcome)}

        games = [game(7, sid="S9"), game(6, difficulty=1), game(5, result="stopped"),
                 game(4, result="won", won=True, turns=900), game(3, level="H", result="quit", turns=5),
                 game(2, killer="white dragon", cure=True, turns=700),
                 game(1, killer="white dragon", turns=300)]          # newest first
        self.assertEqual(learn._digest_lines(learn.digest(self.c, "S1", [])), ["No finished game yet."])
        d = learn.digest(self.c, "S1", games)
        # Only finished games of this strategy at this difficulty count.
        self.assertEqual([m["run_id"] for m in d["runs"]], ["g4", "g3", "g2", "g1"])
        self.assertEqual((d["games"], d["wins"], d["cure"], d["median_turns"]), (4, 1, 2, 700))
        self.assertEqual(d["ended_by"], [("white dragon", 2), ("quit", 1)])
        self.assertEqual(learn._digest_lines(d), [
            "4 games: 1 won, 2 held the cure. Average progress %s; best: won." % d["mean"],
            "Ended by: white dragon ×2, quit.",
            "Ended on level: V5 ×2, town. A game lasted about 700 turns."])
        with self.assertRaises(learn.LearnError):
            learn.digest(self.c, "S9", games)

    def test_rules_are_checked(self):
        for bad in ({"budget": 0}, {"margin": -1}, {"patience": 0}, {"holdout": -1}, {"luck": 1},
                    {"wins": 0}, {"wins": 6}, {"window": 2}, {"top": 101}, {"top": -1},
                    {"playbook_budget": 10}):
            with self.assertRaises(learn.LearnError):
                learn.new_campaign(rules=bad)
        with self.assertRaises(learn.LearnError):
            learn.new_campaign(difficulty=6)                 # above the default top of 5
        self.assertEqual(learn.new_campaign(difficulty=6, rules={"top": 8})["difficulty"], 6)
        self.assertEqual(learn.new_campaign(rules={"budget": None})["rules"], learn.DEFAULT_RULES)


class CampaignTest(unittest.TestCase):
    """The learning tools, through the MCP server, on real (short) games."""

    RULES = {"budget": 1, "margin": 0.5, "holdout": 1, "patience": 2}

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.seeds = learn.load(self.root, rules=self.RULES)["seeds"]
        self.c = McpClient(["--record", self.root])
        init = self.c.request("initialize", {"protocolVersion": "2025-06-18"})
        self.assertIn("get_briefing", init["result"]["instructions"])

    def tearDown(self):
        self.c.close()

    def call(self, name, **args):
        text, err = self.c.call(name, **args)
        self.assertFalse(err, text)
        return text

    def fails(self, name, **args):
        text, err = self.c.call(name, **args)
        self.assertTrue(err, text)
        self.assertNotIn("Traceback", text)
        return text

    def read(self, *parts):
        with open(os.path.join(self.root, *parts), encoding="utf-8") as f:
            return f.read()

    def meta(self, run):
        return json.loads(self.read(run, "meta.json"))

    def play(self, sid, depth, **args):
        """One short game under a strategy: `depth` levels down, then quit."""
        text = self.call("new_game", strategy=sid, **args)
        run = re.search(r"as run (\S+)\.", text).group(1)
        if depth:
            self.call("take_stairs", direction="down")
        text = self.call("send_keys", keys="Qy")
        for _ in range(8):
            if "Status: game over" in text:
                break
            text = self.call("send_keys", keys="<enter>")
        return run

    def status(self, sid):
        return learn.load(self.root)["strategies"][sid]["status"]

    def test_campaign(self):
        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S1 Baseline", text)
        self.assertIn("Why this one: measuring the base, so later ideas have something to beat. "
                      "So far: not played yet.", text)
        self.assertIn("_Empty: this is one of the first games._", text)
        self.assertIn("A new strategy plays 1 games on the same seeds", text)
        self.assertIn("## Your cycle", text)
        self.assertNotIn("## Latest games", text)

        # --- the baseline is measured first, on the campaign's seed
        first = self.play("S1", 0, character_class="dwarf", seed=12345)
        meta = self.meta(first)
        self.assertEqual((meta["strategy"], meta["seed"]), ("S1", self.seeds["trial"][0]))
        self.assertEqual(meta["progress"], {"score": 0.025, "milestone": "never left town"})
        self.assertIs(meta["outcome"]["has_cure"], False)
        self.assertIn("| Progress | never left town (0.025) |", self.read(first, "summary.md"))
        self.call("summarize_run", synopsis="Never left town.",
                  went_wrong=["Had no armour"], next_try=["Buy armour first"])

        # --- lessons cite runs
        self.assertIn('L1 saved as tentative under "armour", citing 1 run.',
                      self.call("add_lesson", text="Level 1 monsters hit hard without armour.",
                                topic="Armour", evidence=[first]))
        self.assertIn("confirmed lesson must cite", self.fails(
            "add_lesson", text="Armour is good.", confidence="confirmed"))
        self.assertIn("no such run", self.fails("add_lesson", text="x", evidence=["nope"]))
        self.fails("add_lesson", text="  ")
        self.fails("add_lesson", text="x", confidence="certain")

        # --- an idea goes on trial against the base
        text = self.call("get_briefing")
        self.assertIn("## First: propose a strategy", text)
        self.assertIn("## Otherwise play: S1 Baseline", text)
        text = self.call("propose_strategy", title="Armour first",
                         change="Buy leather armor before entering the dungeon",
                         character_class="Dwarf")
        self.assertEqual(text, "Strategy S2 added, on trial against S1. It is the one to play "
                               "next: new_game(strategy=\"S2\").")
        self.assertIn("already tests that change", self.fails(
            "propose_strategy", title="Again",
            change="buy leather armor before entering the dungeon"))
        self.assertIn("S2 is still on trial, so nothing can be built on it yet; build on S1",
                      self.fails("propose_strategy", title="x", change="y", parent="S2"))
        self.fails("propose_strategy", title="No change")
        self.fails("propose_strategy", title="x", change="y", parent="S9")
        self.fails("propose_strategy", title="x", change="y", character_class="bard")

        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S2 Armour first", text)
        self.assertIn("Why this one: on trial against S1.", text)
        self.assertIn("Character class: dwarf.", text)
        self.assertIn("- Buy leather armor before entering the dungeon **(the change on trial)**", text)
        self.assertIn("- L1 [armour]: Level 1 monsters hit hard without armour.\n", text)
        self.assertIn("- **S1 Baseline** [proven, the base]: 1 of 1 trial games, "
                      "average progress 0.03, best: never left town", text)
        self.assertIn("  - **S2 Armour first** [on trial]: not played yet ← play this next", text)
        self.assertIn("- %s (S1): Quit" % first, text)
        self.assertIn("got to: never left town. Had no armour\n", text)   # no takeaway given

        # --- its games take everything from the strategy; a stopped game does not count
        self.call("new_game", strategy="S2")
        self.call("end_game")
        second = self.play("S2", 1, character_class="wizard", difficulty=5, seed=99,
                           hypotheses=["something else"])
        meta = self.meta(second)
        self.assertEqual(meta["hypotheses"], ["Buy leather armor before entering the dungeon"])
        self.assertEqual((meta["character_class"], meta["difficulty"], meta["seed"]),
                         ("Dwarf", 0, self.seeds["trial"][0]))          # the seed S1 played
        self.assertEqual(meta["progress"]["milestone"], "dungeon level 1")

        # --- it beat the base by the margin, so it is checked on an unseen seed
        self.assertEqual(self.status("S2"), "holdout")
        text = self.call("get_briefing")
        self.assertIn("Why this one: it passed its trial; this checks it on unseen seeds.", text)
        self.assertIn("S2 Armour first passed its trial (averaged 1.02 over 1 games, "
                      "S1 averaged 0.03). Checking it on 1 unseen seeds.", text)
        third = self.play("S2", 1)
        self.assertEqual(self.meta(third)["seed"], self.seeds["holdout"][0])
        campaign = learn.load(self.root)
        self.assertEqual((self.status("S2"), campaign["base"]), ("proven", "S2"))

        # --- the next idea builds on the new base, fails, and is remembered
        text = self.call("get_briefing")
        self.assertIn("## First: propose a strategy", text)
        self.assertIn("ONE specific change to S2 Armour first", text)
        self.assertIn("## Otherwise play: S2 Armour first", text)
        self.assertNotIn("the change on trial", text)
        self.assertIn("on trial against S2", self.call(
            "propose_strategy", title="And a shield", change="Also buy a shield"))
        fourth = self.play("S3", 0)
        self.assertEqual(self.meta(fourth)["hypotheses"],
                         ["Buy leather armor before entering the dungeon", "Also buy a shield"])
        self.assertEqual(self.status("S3"), "abandoned")
        text = self.call("get_briefing")
        self.assertIn("## Tried and failed", text)
        self.assertIn("- Also buy a shield (S3, on top of S2): And a shield. Verdict: averaged "
                      "0.03 over 1 games, S2 averaged 1.02 and it needed 1.52", text)
        refused = self.fails("propose_strategy", title="Shield again", change="also buy a shield")
        self.assertIn("S3 already tried that and was abandoned", refused)

        # --- a second failure in a row: the line has stalled, so step back to S1
        self.call("propose_strategy", title="Shield again", change="also buy a shield",
                  retry_reason="This time sell the spear to afford it")
        self.play("S4", 0)
        campaign = learn.load(self.root)
        self.assertEqual((self.status("S4"), self.status("S2"), campaign["base"]),
                         ("abandoned", "stalled", "S1"))
        text = self.call("get_briefing")
        self.assertIn("S2 Armour first has stalled: the last 2 ideas built on it failed "
                      "(S3, S4). Stepping back to S1", text)
        self.assertIn("ONE specific change to S1 Baseline", text)
        self.assertIn("- **S1 Baseline** [proven, the base]", text)
        self.assertIn("  - **S2 Armour first** [stalled]", text)
        self.assertIn("on trial against S1", self.call(
            "propose_strategy", title="Wizard", change="Play a wizard", character_class="wizard"))
        self.assertIn("on trial against S2", self.call(      # a stalled one can still be built on
            "propose_strategy", title="Helmet", change="Buy a helmet", parent="S2"))

        # --- a strategy name the campaign does not know is just a label
        other = self.play("freestyle", 0, hypotheses=["wing it"], seed=5)
        self.assertEqual((self.meta(other)["hypotheses"], self.meta(other)["seed"]), (["wing it"], 5))

        # --- lessons: confirmed by a second run, or retracted
        self.assertIn('L1 saved as confirmed under "armour", citing 2 runs.',
                      self.call("add_lesson", text="level 1 monsters hit hard without armour.",
                                evidence=[second], confidence="confirmed"))
        self.call("add_lesson", text="Never use the bank.", topic="town")
        self.assertIn("L2 retracted", self.call("retract_lesson", lesson_id="L2",
                                                reason="Gold in the bank earns interest."))
        self.fails("retract_lesson", lesson_id="L9", reason="x")
        self.fails("retract_lesson", lesson_id="L1", reason=" ")
        text = self.call("get_briefing")
        self.assertIn("Confirmed, follow these:", text)
        self.assertNotIn("Never use the bank", text)

        doc = self.read("CAMPAIGN.md")
        self.assertIn("- L1 [armour]: Level 1 monsters hit hard without armour. (runs: %s, %s)" % tuple(
            sorted([first, second])), doc)
        self.assertIn("- L2: ~~Never use the bank.~~ Gold in the bank earns interest.", doc)
        self.assertIn("    - **S3 And a shield** [abandoned]: 1 of 1 trial games", doc)
        self.assertIn("      Change: Also buy a shield", doc)
        self.assertIn("## Tried and failed", doc)
        self.assertIn("## Decisions", doc)
        self.assertIn("S2 Armour first proven: trial average 1.02; averaged 1.02 on 1 unseen "
                      "seeds, S1 averaged 0.03 on the trial seeds; it is the new base.", doc)
        self.assertIn("| Progress |", self.read("INDEX.md"))

    def test_strategy_digest_and_field_notes(self):
        # --- a game leaves a one-line takeaway, and is asked for the strategy's notes
        first = self.play("S1", 0, character_class="dwarf")
        text = self.call("summarize_run", takeaway="Quit in town with nothing tried.",
                         synopsis="Never left town.", went_wrong=["Had no armour"])
        self.assertIn("Now bring the field notes of S1 up to date with note_strategy", text)
        self.assertIn("There are none yet: yours will be the first.", text)
        self.assertNotIn("No takeaway was given", text)
        self.assertEqual(self.meta(first)["notes"]["takeaway"], "Quit in town with nothing tried.")
        self.assertIn("**In one line:** Quit in town with nothing tried.",
                      self.read(first, "summary.md"))
        self.assertIn("at most 200", self.fails("summarize_run", synopsis="x", takeaway="y" * 201))

        self.assertEqual(self.call("note_strategy", strategy="S1", text="Buy armour before level 1.\n"),
                         "Field notes of S1 Baseline saved (26 characters), covering 1 game.")
        notes = learn.load(self.root)["strategies"]["S1"]["notes"]
        self.assertEqual((notes["text"], notes["run"], notes["games"]),
                         ("Buy armour before level 1.", first, 1))
        self.assertIn("no strategy called 'S9'", self.fails("note_strategy", strategy="S9", text="x"))
        self.assertIn("the notes are empty", self.fails("note_strategy", strategy="S1", text="  "))
        self.assertIn("at most 1200 characters and these are 1201",
                      self.fails("note_strategy", strategy="S1", text="z" * 1201))
        self.assertIn("no such run", self.fails("note_strategy", strategy="S1", text="x", run_id="nope"))

        # --- one call gives the strategy whole: no reading its games one by one
        text = self.call("get_strategy", strategy="S1")
        self.assertIn("# S1 Baseline [proven, the base]", text)
        self.assertIn("1 game: 0 won, 0 held the cure. Average progress 0.03; best: never left town.",
                      text)
        self.assertIn("Ended by: quit.", text)
        self.assertRegex(text, r"Ended on level: town\. A game lasted about \d+ turns\.")
        self.assertIn("Field notes (written after 1 of its 1 games):\n\nBuy armour before level 1.", text)
        self.assertRegex(text, r"- %s: Quit.*; got to: never left town\. Quit in town with nothing "
                               r"tried\." % re.escape(first))
        self.fails("get_strategy", strategy="S9")
        self.fails("get_strategy")

        # --- the briefing carries it for the strategy to play, and for what it builds on
        self.call("propose_strategy", title="Armour first", change="Buy leather armor")
        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S2 Armour first", text)
        self.assertIn("### How it has gone\n\nNo finished game yet.\n\n_No field notes yet._", text)
        self.assertIn("Field notes of S1 Baseline, which this builds on (written after 1 of its 1 "
                      "games):\n\nBuy armour before level 1.", text)
        self.assertIn("got to: never left town. Quit in town with nothing tried.\n", text)
        self.assertNotIn("  - went wrong", text)        # the old three-line extract per game

        # --- notes fall behind as games are played, and are rewritten, not added to
        second = self.play("S1", 0, character_class="dwarf")
        text = self.call("summarize_run", synopsis="Again.")
        self.assertIn("No takeaway was given", text)
        self.assertIn("The notes as they stand:\n\nBuy armour before level 1.", text)
        self.assertIn("(written after 1 of its 2 games; 1 newer game not in them yet):",
                      self.call("get_strategy", strategy="S1"))
        self.call("note_strategy", strategy="S1", text="Buy armour. Do not quit.")
        s1 = learn.load(self.root)["strategies"]["S1"]
        self.assertEqual((s1["notes"]["text"], s1["notes"]["run"], s1["notes"]["games"]),
                         ("Buy armour. Do not quit.", second, 2))
        self.assertEqual([n["text"] for n in s1["notes_history"]], ["Buy armour before level 1."])
        doc = self.read("CAMPAIGN.md")
        self.assertIn("## How each strategy has gone", doc)
        self.assertIn("### S1 Baseline\n\n2 games: 0 won", doc)
        self.assertIn("Buy armour. Do not quit.", doc)
        self.assertNotIn("### S2 Armour first", doc)        # not played yet

        # --- lists of games are one line each unless the whole is asked for
        listed = json.loads(self.call("list_runs"))["runs"]
        self.assertEqual([r["takeaway"] for r in listed],
                         ["Again.", "Quit in town with nothing tried."])
        self.assertNotIn("synopsis", listed[1])
        self.assertEqual(json.loads(self.call("list_runs", full=True))["runs"][1]["synopsis"],
                         "Never left town.")

        # --- a slip in the strategy's name still counts for it; another name is flagged
        text = self.call("new_game", strategy="s1 baseline")
        run = re.search(r"as run (\S+)\.", text).group(1)
        self.assertNotIn("is not a strategy", text)
        self.call("end_game")
        self.assertEqual(self.meta(run)["strategy"], "S1")
        text = self.call("new_game", strategy="freestyle")
        self.assertIn('"freestyle" is not a strategy of the campaign (S1, S2), so this game '
                      'counts towards none of them.', text)
        self.call("end_game")

    def test_a_win_leaves_a_recipe(self):
        first = self.play("S1", 1, character_class="dwarf")
        # Make it a win on disk: a real one takes hours of play.
        meta = self.meta(first)
        meta["outcome"].update(result="won", won=True, has_cure=True)
        meta["progress"] = learn.progress(meta["outcome"])
        runs.save_meta(os.path.join(self.root, first), meta)

        # --- the campaign makes a strategy that follows the win, and plays it next
        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S2 Winning line: Baseline", text)
        self.assertIn("Why this one: it follows the won game %s; this tries its recipe on a seed "
                      "nobody has played." % first, text)
        self.assertIn("### The recipe to follow", text)
        self.assertIn("_No recipe has been written yet.", text)
        self.assertIn("The game that won, %s. Measure yourself against it" % first, text)
        self.assertRegex(text, r"\| First on \| Turn \| Char level \|[^\n]*\n\|[-|]+\n\| H \| 0 \|"
                               r"[^\n]*\n\| 1 \| \d+ \| 1 \|")
        self.assertIn("  - **S2 Winning line: Baseline** [following a win]: not played yet "
                      "← play this next", text)
        line = learn.load(self.root)["strategies"]["S2"]
        self.assertEqual((line["character_class"], line["models"]), ("dwarf", [first]))
        self.assertIn("S2 Winning line: Baseline follows the won game %s and has no recipe: "
                      "write it (write_recipe) from that game." % first, learn.upkeep(self.root))

        # --- writing the win up asks for the recipe, with the run sheet to write it from
        text = self.call("summarize_run", run_id=first, synopsis="Won.", takeaway="Won it.")
        self.assertIn("This game was WON. S2 Winning line: Baseline has been made to follow it", text)
        self.assertIn('Write its recipe now with write_recipe (strategy "S2", at most 2500 '
                      'characters)', text)
        self.assertIn("what you must have before going on, in numbers", text)
        self.assertIn("The run sheet of your game:\n\n| First on |", text)
        self.assertNotIn("note_strategy", text)
        self.assertIn("### Run sheet", self.read(first, "summary.md"))
        self.assertEqual(self.call("write_recipe", text="Stage 1: buy armour. Go on at AC 10."),
                         "Recipe of S2 Winning line: Baseline saved (36 characters). It is what "
                         "the next game under S2 plays from.")
        self.assertIn("S1 is not a winning line", self.fails("write_recipe", strategy="S1", text="x"))
        self.assertIn("at most 2500 characters and this is 2501",
                      self.fails("write_recipe", strategy="S2", text="r" * 2501))
        self.assertIn("the recipe is empty", self.fails("write_recipe", text=" "))
        self.assertIn("its account is its recipe",
                      self.fails("note_strategy", strategy="S2", text="x"))
        text = self.call("get_briefing")
        self.assertIn("The recipe (as rewritten after 0 of this line's 0 games):\n\n"
                      "Stage 1: buy armour. Go on at AC 10.", text)
        text = self.call("get_strategy", strategy="S2")
        self.assertIn("# S2 Winning line: Baseline [following a win]", text)
        self.assertIn("## Recipe\n\nThe recipe (as rewritten", text)
        self.assertEqual([j for j in learn.upkeep(self.root) if "recipe" in j], [])

        # --- a game under it: the winner's class, a seed nobody has played, and afterwards
        #     the game set beside the win, to revise the recipe from
        second = self.play("S2", 0)
        meta = self.meta(second)
        self.assertEqual((meta["character_class"], meta["seed"]), ("Dwarf", line["seeds"][0]))
        self.assertIn("Follow the recipe distilled from the won game", meta["hypotheses"][0])
        text = self.call("summarize_run", synopsis="Stayed in town.")
        self.assertIn("This game followed the winning line S2. Now rewrite its recipe with "
                      'write_recipe (strategy "S2", at most 2500 characters, the whole of it)', text)
        self.assertIn("change the stage where this game went wrong", text)
        self.assertIn("Your game beside the game that won:\n\n| First on | The game that won | "
                      "This game |", text)
        self.assertRegex(text, r"\| 1 \| turn \d+: level 1, \d+ HP, AC \d+, WC \d+ \| never reached \|")
        self.assertIn("It never reached level 1, which the winner entered on turn", text)
        self.assertIn("The recipe as it stands:\n\nStage 1: buy armour. Go on at AC 10.", text)
        self.call("write_recipe", text="Stage 1: buy armour, then go down at once.")
        line = learn.load(self.root)["strategies"]["S2"]
        self.assertEqual((line["recipe"]["text"], line["recipe"]["run"], line["recipe"]["games"]),
                         ("Stage 1: buy armour, then go down at once.", second, 1))
        self.assertEqual([r["text"] for r in line["recipe_history"]],
                         ["Stage 1: buy armour. Go on at AC 10."])
        # With one seed to its name (this campaign's budget) and no win on it, the line is dropped.
        self.assertEqual(line["status"], "abandoned")
        self.assertIn("won none of its 1 game on seeds nobody had played", line["note"])
        doc = self.read("CAMPAIGN.md")
        self.assertIn("### S2 Winning line: Baseline", doc)
        self.assertIn("Stage 1: buy armour, then go down at once.", doc)

        # --- the same seed won again is not a second win
        third = self.play("S1", 0, character_class="dwarf")
        meta = self.meta(third)
        meta["seed"] = self.meta(first)["seed"]
        meta["outcome"].update(result="won", won=True, has_cure=True)
        meta["progress"] = learn.progress(meta["outcome"])
        runs.save_meta(os.path.join(self.root, third), meta)
        text = self.call("get_briefing")
        self.assertIn("3 games played here, 1 won.", text)
        campaign = learn.load(self.root)
        self.assertEqual(sorted(campaign["strategies"]), ["S1", "S2"])     # no new line
        self.assertEqual(learn.repeat_wins(runs.list_runs(self.root)), {third})
        self.assertEqual(learn.ladder(campaign, runs.list_runs(self.root))["total_wins"], 1)

    def test_the_playbook_keeps_to_its_budget(self):
        first = self.play("S1", 0, character_class="dwarf")
        second = self.play("S1", 0, character_class="dwarf")

        # --- a lesson is short and has a topic
        self.assertIn("at most 300 characters and this is 301",
                      self.fails("add_lesson", text="x" * 301, topic="town"))
        self.assertIn("a lesson needs a topic", self.fails("add_lesson", text="Rest often."))
        self.assertIn("at most 30 characters", self.fails("add_lesson", text="y", topic="t" * 31))
        self.assertIn('L1 saved as tentative under "dragons", citing 1 run.', self.call(
            "add_lesson", topic=" Dragons ", evidence=[first],
            text="White dragons breathe for 15 to 30 a turn: do not fight one, leave by the stairs."))
        self.call("add_lesson", topic="dragons", evidence=[second],
                  text="Never melee a white dragon below 80 HP.")
        self.call("add_lesson", topic="town", text="Sell gems at the bank.")
        self.assertIn("Topics in use: dragons, town.", self.fails("add_lesson", text="Rest often."))

        # --- a subject can be looked up
        text = self.call("get_lessons", about="Dragon")
        self.assertIn("2 lessons about 'dragon'. The whole playbook is", text)
        self.assertIn("- L1 [dragons] (tentative, 1 run, 81 chars): White dragons breathe", text)
        self.assertNotIn("Sell gems", text)
        self.assertIn("- L3 [town] (tentative, 0 runs, 22 chars): Sell gems at the bank.",
                      self.call("get_lessons"))
        self.assertIn("_Nothing on that; topics in use: dragons, town._",
                      self.call("get_lessons", about="lemmings"))

        # --- overlapping lessons fold into one, which keeps their evidence
        size = learn.playbook_size(learn.load(self.root))
        merged = "Do not fight a white dragon: it breathes for 15 to 30 a turn. Leave by the stairs."
        text = self.call("merge_lessons", lesson_ids=["L1", "L2"], text=merged)
        self.assertEqual(text, 'Lesson L4 (confirmed, under "dragons", citing 2 runs) replaces L1, L2. '
                               'The playbook is %d characters shorter.' % (81 + 39 - len(merged)))
        campaign = learn.load(self.root)
        by_id = {l["id"]: l for l in campaign["lessons"]}
        self.assertEqual((by_id["L1"]["status"], by_id["L1"]["note"]), ("merged", "merged into L4"))
        self.assertEqual((by_id["L4"]["merged_from"], by_id["L4"]["evidence"]),
                         (["L1", "L2"], sorted([first, second])))
        self.assertEqual(learn.playbook_size(campaign), size - (81 + 39 - len(merged)))
        self.assertIn("L1 is merged: merged into L4",
                      self.fails("merge_lessons", lesson_ids=["L1", "L3"], text="x"))
        self.assertIn("no lesson called 'L9'", self.fails("merge_lessons", lesson_ids=["L9"], text="x"))
        self.assertIn("named twice", self.fails("merge_lessons", lesson_ids=["L3", "L3"], text="x"))
        self.assertIn("at most 300", self.fails("merge_lessons", lesson_ids=["L3"], text="x" * 301))
        self.fails("merge_lessons", lesson_ids=[], text="x")
        # One id rewrites a lesson; with nothing new behind it, it stays tentative.
        self.assertIn('Lesson L5 (tentative, under "town", citing 0 runs) replaces L3.', self.call(
            "merge_lessons", lesson_ids="L3", text="Sell gems at the bank, not the trading post."))

        text = self.call("get_briefing")
        self.assertIn("Confirmed, follow these:\n\n- L4 [dragons]: %s (2 runs)\n" % merged, text)
        self.assertIn("Tentative, seen once:\n\n- L5 [town]: Sell gems at the bank, not", text)
        self.assertNotIn("Never melee", text)
        self.assertNotIn("outgrown its budget", text)
        doc = self.read("CAMPAIGN.md")
        self.assertIn("### Merged", doc)
        self.assertIn("- L4 ← L1, L2", doc)
        self.assertIn("- L4 [dragons]: %s (runs: %s, %s)" % ((merged,) + tuple(sorted([first, second]))),
                      doc)

        # --- over its budget, the briefing lists what was seen once instead of carrying it
        campaign = learn.load(self.root)
        campaign["rules"]["playbook_budget"] = 100
        learn.save(self.root, campaign)
        learn.add_lesson(self.root, "An old lesson, from before lessons had topics.", topic="x")
        campaign = learn.load(self.root)
        del campaign["lessons"][-1]["topic"]
        learn.save(self.root, campaign)
        text = self.call("get_briefing")
        self.assertIn("The playbook has outgrown its budget", text)
        self.assertIn("- L4 [dragons]: %s (2 runs)" % merged, text)             # confirmed: in full
        self.assertIn("Tentative, seen once:\n\n- L6: An old lesson, from before", text)   # no topic yet
        self.assertIn("Tentative, by topic. Read them when the subject comes up", text)
        self.assertIn("- town: L5\n", text)
        self.assertNotIn("not the trading post", text)
        self.assertIn("over its budget of 100", self.call(
            "add_lesson", text="Lemmings breed.", topic="lemmings"))
        jobs = learn.upkeep(self.root)
        self.assertRegex(jobs[0], r"^The playbook is \d+ characters in 4 lessons, and its budget is 100")
        self.assertEqual(jobs[1:], ["S1 Baseline has 2 games and no field notes: write them."])
        campaign = learn.load(self.root)
        campaign["rules"]["playbook_budget"] = 12000
        learn.save(self.root, campaign)
        self.assertEqual(learn.upkeep(self.root)[0],
                         "1 lessons have no topic: give each one (merge_lessons with its own id).")


class LadderGameTest(unittest.TestCase):
    """Real wins, produced through the game engine, inside one process."""

    def setUp(self):
        from pyularn import mcp_server
        self.m = mcp_server
        self.root = tempfile.mkdtemp()
        self.own_home = tempfile.mkdtemp()
        self.old_home = os.environ.get("PYULARN_HOME")
        os.environ["PYULARN_HOME"] = self.own_home
        self.old_dir = mcp_server.SESSION.record_dir
        mcp_server.SESSION.record_dir = self.root
        del mcp_server._OWN_HOME[:]
        learn.load(self.root, rules={"budget": 1, "holdout": 0, "window": 2, "wins": 2, "top": 1})

    def tearDown(self):
        self.m.SESSION.stop()
        self.m.SESSION.record_dir = self.old_dir
        del self.m._OWN_HOME[:]
        if self.old_home is None:
            del os.environ["PYULARN_HOME"]
        else:
            os.environ["PYULARN_HOME"] = self.old_home

    def state(self, text):
        return json.loads(text.split("State:\n", 1)[1])

    def win(self):
        """Start a campaign game and win it the way the game does: by
        reporting DIED_WINNER, then paging through the score screens."""
        from pyularn import scores
        import pyularn.ularn as ularn
        state = self.state(self.m.tool_new_game({"strategy": "S1", "character_class": "dwarf"}))
        parse = ularn.parse
        ularn.parse = lambda action: scores.died(scores.DIED_WINNER, 0)
        try:
            self.m.SESSION.send(".")
        finally:
            ularn.parse = parse
        for _ in range(12):
            if self.m.SESSION.term.finished:
                break
            self.m.tool_send_keys({"keys": "<enter>"})
        self.assertTrue(self.m.SESSION.term.finished, self.m.SESSION.screen())
        return state

    def test_wins_climb_the_ladder(self):
        first = self.win()
        self.assertEqual(first["difficulty"], 0)
        played = runs.list_runs(self.root)
        self.assertEqual(played[0]["outcome"]["result"], "won")
        self.assertEqual(played[0]["progress"]["milestone"], "won")
        campaign = learn.load(self.root)
        self.assertEqual((campaign["difficulty"], campaign["cleared"]), (0, []))   # one win of two

        # Ularn would start this player's next game one difficulty up, owing
        # taxes.  A campaign game has a scoreboard of its own, so it does not.
        second = self.win()
        self.assertEqual(second["difficulty"], 0)
        self.assertIn(os.path.join(self.root, "home"), os.environ["PYULARN_HOME"])

        campaign = learn.load(self.root)
        self.assertEqual((campaign["difficulty"], campaign["complete"]), (1, False))
        text = self.m.tool_get_briefing({})
        self.assertIn("Difficulty 1, on a ladder that ends at 1. 0 games played here, 0 won. "
                      "The ladder moves up when 2 of the latest 2 games are won; so far 0 are.", text)
        self.assertIn("- Difficulty 0 cleared", text)
        self.assertIn(": 2 wins in 2 games, with S1 as the base.", text)
        self.assertIn("This difficulty is new.", text)
        # Both wins were under S1: the first made a line to follow it, the second joined it.
        self.assertIn("## Play this strategy: S2 Winning line: Baseline", text)
        self.assertEqual(len(campaign["strategies"]["S2"]["models"]), 2)

        # The next games are played at the new difficulty; two wins finish it.
        self.assertEqual(self.win()["difficulty"], 1)
        self.assertEqual(self.win()["difficulty"], 1)
        campaign = learn.load(self.root)
        self.assertTrue(campaign["complete"])
        self.assertIn("The campaign is complete", self.m.tool_get_briefing({}))
        with open(os.path.join(self.root, "CAMPAIGN.md"), encoding="utf-8") as f:
            doc = f.read()
        self.assertIn("**The campaign is complete: difficulty 1, the top of its ladder, is cleared.**", doc)
        self.assertIn("- Difficulty 1 cleared", doc)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = coach.main(["--dir", self.root, "--cycles", "3", "--agent-cmd", "no-such-agent"])
        self.assertEqual(code, 0)
        self.assertIn("The campaign is complete: difficulty 1 is cleared.", out.getvalue())
        self.assertNotIn("Cycle 1", out.getvalue())

        # A game outside the campaign uses the server's own home again.
        self.m.tool_new_game({"character_class": "dwarf"})
        self.assertEqual(os.environ["PYULARN_HOME"], self.own_home)

    def test_lessons_remember_their_difficulty(self):
        learn.add_lesson(self.root, "Buy armour first.", topic="town")
        campaign = learn.load(self.root)
        self.assertEqual(campaign["lessons"][0]["difficulty"], 0)
        self.assertIn("- L1 [town]: Buy armour first.\n", learn.briefing(self.root) + "\n")
        campaign["difficulty"] = 1
        learn.save(self.root, campaign)
        self.assertIn("- L1 [town]: Buy armour first. [learned at difficulty 0]",
                      learn.briefing(self.root))


class RunSheetTest(unittest.TestCase):
    """The stage-by-stage sheet of a game, from made-up events."""

    @staticmethod
    def state(level, turn, cl, hp, ac, wc, pack=(), spells=()):
        return {"level_index": level, "turns": turn, "inventory": list(pack),
                "known_spells": list(spells),
                "stats": {"level": cl, "hp_max": hp, "ac": ac, "wc": wc, "gold": 10, "bank": 5}}

    def winner(self):
        st = self.state
        worn = ["a)   ring mail (being worn)", "b)   a spear +1 (weapon in hand)"]
        return [
            {"type": "start", "state": st(0, 0, 1, 12, 2, 3, ["a)   leather armor (being worn)"],
                                          ["pro (protection)"])},
            {"type": "action", "tool": "buy", "s": {"turn": 30, "lvl": 0},
             "result": {"result": "done", "bought": [{"name": "ring mail", "price": 400}]}},
            {"type": "action", "tool": "take_stairs", "s": {"turn": 40, "lvl": 1}},
            {"type": "state", "state": st(1, 40, 1, 12, 5, 3, worn, ["pro (protection)", "sle (sleep)"])},
            {"type": "action", "tool": "send_keys", "s": {"turn": 900, "lvl": 16}},
            {"type": "state", "state": st(16, 900, 10, 80, 12, 20, worn)},
            {"type": "state", "state": st(16, 920, 10, 80, 12, 20,
                                          worn + ["c)   a magic potion of cure dianthroritis"])},
            {"type": "action", "tool": "take_stairs", "s": {"turn": 950, "lvl": 0}},
            {"type": "state", "state": st(0, 950, 11, 85, 12, 20, worn)},     # town again: no new stage
        ]

    def test_sheet(self):
        sheet = runs.run_sheet(self.winner())
        self.assertEqual([s["level"] for s in sheet["stages"]], ["H", "1", "V1"])
        self.assertEqual(sheet["stages"][1], {"level": "1", "turn": 40, "cl": 1, "hp": 12, "ac": 5,
                                              "wc": 3, "gold": 15, "spells": 2,
                                              "kit": ["ring mail", "a spear +1"]})
        self.assertEqual(sheet["bought"], [{"name": "ring mail", "price": 400, "turn": 30}])
        self.assertEqual(sheet["spells"], [{"spell": "pro (protection)", "turn": 0},
                                           {"spell": "sle (sleep)", "turn": 40}])
        self.assertEqual((sheet["cure"], sheet["home"]),
                         ({"turn": 920, "level": "V1"}, [{"level": "H", "turn": 950}]))
        text = "\n".join(runs.sheet_lines(sheet))
        self.assertIn("| V1 | 900 | 10 | 80 | 12 | 20 | 15 | 0 | ring mail, a spear +1 |", text)
        self.assertIn("- Bought: turn 30: ring mail (400 gold)", text)
        self.assertIn("- Spells learned: sle (sleep) by turn 40", text)
        self.assertIn("- The cure was in the pack by turn 920, on level V1.", text)
        self.assertIn("- After that: H (turn 950)", text)
        self.assertEqual(runs.sheet_lines(runs.run_sheet([])), ["_Nothing recorded._"])

    def test_one_game_beside_another(self):
        st = self.state
        model = runs.run_sheet(self.winner())
        same = runs.compare_sheets(model, model)
        self.assertEqual(same[0], "| First on | The game that won | This game |")
        self.assertEqual(same[-1], "It kept pace with the winner on arriving at every level. It had "
                                   "the cure by turn 920 (the winner by turn 920).")
        # Went down in the armour it started with.
        weak = runs.run_sheet([{"type": "start", "state": st(0, 0, 1, 12, 2, 3)},
                               {"type": "state", "state": st(1, 25, 1, 12, 2, 3)}])
        lines = runs.compare_sheets(model, weak)
        self.assertIn("| 1 | turn 40: level 1, 12 HP, AC 5, WC 3 | turn 25: level 1, 12 HP, AC 2, WC 3 |",
                      lines)
        self.assertIn("| V1 | turn 900: level 10, 80 HP, AC 12, WC 20 | never reached |", lines)
        self.assertEqual(lines[-1], "It first fell behind the winner on arriving at level 1: "
                                    "AC 2 against 5.")
        home = runs.run_sheet([{"type": "start", "state": st(0, 0, 1, 12, 2, 3)}])
        self.assertEqual(runs.compare_sheets(model, home)[-1],
                         "It never reached level 1, which the winner entered on turn 40 at "
                         "character level 1 with 12 HP, AC 5 and WC 3.")

    def test_the_recording_marks_when_the_cure_is_taken(self):
        from pyularn import recorder
        root = tempfile.mkdtemp()
        full = dict(self.state(16, 5, 9, 70, 10, 15), turns=5)
        rec = recorder.RunRecorder(root, {"seed": 1}, full)
        rec.action("move", {}, None, full, "screen")
        with_cure = dict(full, inventory=["a)   a magic potion of cure dianthroritis"], turns=6)
        rec.action("send_keys", {"keys": "t"}, None, with_cure, "screen")
        rec.action("move", {}, None, with_cure, "screen")
        events = runs.read_events(rec.dir)
        self.assertEqual([e["type"] for e in events], ["start", "action", "action", "state", "action"])
        self.assertEqual(runs.run_sheet(events)["cure"], {"turn": 6, "level": "V1"})


class NoRecordingTest(unittest.TestCase):
    def test_learning_tools_need_recording(self):
        c = McpClient()
        try:
            c.request("initialize", {"protocolVersion": "2025-06-18"})
            for tool, args in (("get_briefing", {}), ("add_lesson", {"text": "x"}),
                               ("propose_strategy", {"title": "x", "change": "y"}),
                               ("retract_lesson", {"lesson_id": "L1", "reason": "x"})):
                text, err = c.call(tool, **args)
                self.assertTrue(err, text)
                self.assertIn("--record", text)
            # Without a campaign a strategy is only a label.
            text, err = c.call("new_game", strategy="S1", character_class="elf", difficulty=2)
            self.assertFalse(err, text)
            self.assertEqual(json.loads(text.split("State:\n", 1)[1])["difficulty"], 2)
        finally:
            c.close()


class CoachTest(unittest.TestCase):
    """The coach, with a scripted agent in place of a model."""

    FAKE = ("FAKE_DEPTH", "FAKE_IDEAS", "PYTHONPATH")

    def setUp(self):
        self.root = os.path.join(tempfile.mkdtemp(), "campaign")
        self.agent = "%s %s {mcp_config} {prompt}" % (
            sys.executable, os.path.join(ROOT, "tests", "fake_agent.py"))
        self.old = {k: os.environ.get(k) for k in self.FAKE}
        os.environ["PYTHONPATH"] = ROOT

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def coach(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = coach.main(["--dir", self.root, *args])
        return code, out.getvalue()

    def test_a_campaign_from_start_to_backtrack(self):
        code, text = self.coach("--status")
        self.assertEqual((code, text), (1, "No campaign in %s yet.\n" % self.root))

        # S1 stays in town; ideas 1 and 2 reach level 1; ideas 3 and 4 do not.
        os.environ["FAKE_DEPTH"] = json.dumps({"S1": 0, "S4": 0, "S5": 0, "S6": 0})
        os.environ["FAKE_IDEAS"] = "Buy armour|Buy a shield|Skip the store|Run past everything|Rest more|Dig"
        rules = ("--budget", "2", "--margin", "0.5", "--holdout", "1", "--patience", "2")
        code, text = self.coach("--cycles", "14", "--agent-cmd", self.agent, *rules)
        self.assertEqual(code, 0, text)
        self.assertIn("New campaign in %s, difficulty 0" % self.root, text)
        lines = [l for l in text.splitlines() if l.startswith(("Cycle", "  Decision"))]
        want = [
            "Cycle 1 of 14: strategy S1 Baseline (measuring the base",
            "Cycle 2 of 14: strategy S1 Baseline (measuring the base",
            "Cycle 3 of 14: a new idea is needed; the agent will propose one",
            "Cycle 4 of 14: strategy S2 Idea 1 (on trial against S1)",
            "  Decision: S2 Idea 1 passed its trial",
            "Cycle 5 of 14: strategy S2 Idea 1 (it passed its trial",
            "  Decision: S2 Idea 1 proven:",
            "Cycle 6 of 14: a new idea is needed",
            "Cycle 7 of 14: strategy S3 Idea 2 (on trial against S2)",
            "  Decision: S3 Idea 2 abandoned: averaged 1.02 over 2 games, S2 averaged 1.02 and it needed 1.52.",
            "Cycle 8 of 14: a new idea is needed",
            "Cycle 9 of 14: strategy S4 Idea 3 (on trial against S2)",
            "  Decision: S4 Idea 3 abandoned:",
            "  Decision: S2 Idea 1 has stalled: the last 2 ideas built on it failed (S3, S4). "
            "Stepping back to S1",
            "Cycle 10 of 14: a new idea is needed",
            "Cycle 11 of 14: strategy S5 Idea 4 (on trial against S1)",
            "  Decision: S5 Idea 4 abandoned:",
            "Cycle 12 of 14: a new idea is needed",
            "Cycle 13 of 14: strategy S6 Idea 5 (on trial against S1)",
            "  Decision: S6 Idea 5 abandoned:",
            "Cycle 14 of 14: a new idea is needed",
        ]
        self.assertEqual(len(lines), len(want), "\n".join(lines))
        for got, expected in zip(lines, want):
            self.assertTrue(got.startswith(expected), "%r\n does not start with\n%r" % (got, expected))
        self.assertNotIn("no post-mortem", text)

        campaign = learn.load(self.root)
        self.assertEqual({k: v["status"] for k, v in campaign["strategies"].items()},
                         {"S1": "proven", "S2": "stalled", "S3": "abandoned", "S4": "abandoned",
                          "S5": "abandoned", "S6": "abandoned", "S7": "trial"})
        self.assertEqual((campaign["base"], campaign["strategies"]["S5"]["parent"]), ("S1", "S1"))
        # Each strategy played the same seeds, in order; S2 also played the unseen one.
        seeds = campaign["seeds"]
        by = {}
        for m in reversed(runs.list_runs(self.root)):
            by.setdefault(m["strategy"], []).append(m["seed"])
        self.assertEqual(by["S1"], seeds["trial"])
        self.assertEqual(by["S2"], seeds["trial"] + seeds["holdout"])
        self.assertEqual(by["S3"], seeds["trial"])
        self.assertEqual(len(runs.list_runs(self.root)), 14)
        (lesson,) = campaign["lessons"]                    # said every game, kept once
        self.assertEqual(len(lesson["evidence"]), 14)
        with open(os.path.join(self.root, "coach-logs", "cycle-004.log"), encoding="utf-8") as f:
            self.assertIn("as S2.", f.read())
        self.assertTrue(os.path.isdir(os.path.join(self.root, "home")))   # its own scoreboard

        code, text = self.coach("--status")
        self.assertEqual(code, 0)
        self.assertIn("- **S1 Baseline** [proven, the base]: 2 of 2 trial games", text)
        self.assertIn("  - **S2 Idea 1** [stalled]", text)
        self.assertIn("## Tried and failed", text)

        # A campaign keeps its difficulty and its rules.
        for changed in (("--difficulty", "3"), ("--budget", "9")):
            with self.assertRaises(SystemExit):
                self.coach("--agent-cmd", self.agent, *changed)
        code, text = self.coach("--agent-cmd", self.agent, "--budget", "2")
        self.assertEqual(code, 0, text)
        self.assertIn("Continuing the campaign", text)
        self.assertIn("Cycle 1 of 1: strategy S7 Idea 6 (on trial against S1)", text)

    def test_the_editor_tidies_before_play(self):
        os.environ["FAKE_DEPTH"] = json.dumps({"S1": 0})
        os.environ["FAKE_NO_NOTES"] = "1"           # this agent skips the field notes
        try:
            code, text = self.coach("--agent-cmd", self.agent, "--playbook-budget", "1000")
        finally:
            del os.environ["FAKE_NO_NOTES"]
        self.assertEqual(code, 0, text)
        self.assertNotIn("Tidying", text)           # a new campaign has nothing to tidy
        self.assertEqual(learn.upkeep(self.root),
                         ["S1 Baseline has 1 game and no field notes: write them."])

        # --tidy sends the editor alone: no game is played.
        code, text = self.coach("--tidy", "--agent-cmd", self.agent)
        self.assertEqual(code, 0, text)
        self.assertIn("Tidying before play:\n  - S1 Baseline has 1 game and no field notes", text)
        self.assertNotIn("still to do", text)
        self.assertNotIn("Cycle", text)
        self.assertEqual(learn.load(self.root)["strategies"]["S1"]["notes"]["text"],
                         "Editor's notes on S1.")
        self.assertEqual(len(runs.list_runs(self.root)), 1)
        logs = os.listdir(os.path.join(self.root, "coach-logs"))
        self.assertEqual(len([n for n in logs if n.startswith("editor-")]), 1)
        code, text = self.coach("--tidy", "--agent-cmd", self.agent)
        self.assertEqual(code, 0, text)
        self.assertIn("Nothing to tidy", text)

        # A playbook over its budget is folded back before the next game...
        for i in range(5):
            learn.add_lesson(self.root, "Lesson %d. %s" % (i, "x" * 240), topic="topic %d" % i)
        self.assertGreater(learn.playbook_size(learn.load(self.root)), 1000)
        code, text = self.coach("--agent-cmd", self.agent, "--no-tidy", "--print-command")
        self.assertNotIn("Tidying", text)
        code, text = self.coach("--agent-cmd", self.agent)
        self.assertEqual(code, 0, text)
        self.assertIn("Tidying before play:\n  - The playbook is", text)
        self.assertRegex(text, r"playbook: 24 characters in 1 lessons, was \d+ in 6 \(budget 1000\)")
        self.assertLess(text.index("Tidying"), text.index("Cycle 1 of 1"))
        campaign = learn.load(self.root)
        self.assertLess(learn.playbook_size(campaign), 1000)
        # ...and the lesson the games keep teaching kept its evidence through the merge.
        merged = next(l for l in campaign["lessons"] if l.get("merged_from"))
        self.assertEqual((merged["status"], len(merged["evidence"])), ("tentative", 1))
        self.assertEqual(len(runs.list_runs(self.root)), 2)

        # An editor that fails leaves the jobs, says so, and play goes on.
        learn.add_lesson(self.root, "y" * 300, topic="a")
        for i in range(4):
            learn.add_lesson(self.root, "Another %d. %s" % (i, "x" * 240), topic="b")
        broken = "%s -c 'import sys; sys.exit(3)' {mcp_config}" % sys.executable
        code, text = self.coach("--tidy", "--agent-cmd", broken)
        self.assertEqual(code, 1, text)
        self.assertIn("still to do: The playbook is", text)

    def test_agents_that_fail(self):
        broken = "%s -c 'import sys; print(\"boom\"); sys.exit(3)' {mcp_config}" % sys.executable
        code, text = self.coach("--cycles", "5", "--agent-cmd", broken)
        self.assertEqual(code, 1, text)
        self.assertEqual(text.count("the agent exited with code 3"), 2)
        self.assertEqual(text.count("no game was played to its end this cycle"), 2)
        self.assertIn("Stopping: two cycles in a row went wrong.", text)
        self.assertNotIn("Cycle 3", text)

        code, text = self.coach("--agent-cmd", "no-such-agent-program {prompt}")
        self.assertIn("could not start the agent", text)

    def test_default_command(self):
        code, text = self.coach("--print-command", "--model", "some-model",
                                "--max-budget-usd", "2.5", "--watch", "8765", "--difficulty", "1",
                                "--budget", "4")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("claude -p "), text)
        config = os.path.join(self.root, "agent-mcp.json")
        self.assertIn("--mcp-config %s --strict-mcp-config --allowedTools mcp__pyularn "
                      "--model some-model --max-budget-usd 2.5" % config, text)
        self.assertIn("get_briefing", text)
        with open(config, encoding="utf-8") as f:
            server = json.load(f)["mcpServers"]["pyularn"]
        self.assertEqual(server["args"], ["-m", "pyularn.mcp_server", "--record", self.root,
                                          "--watch", "8765"])
        self.assertEqual(server["env"]["PYULARN_HOME"], os.path.join(self.root, "home"))
        campaign = learn.load(self.root)
        self.assertEqual((campaign["difficulty"], campaign["rules"]["budget"]), (1, 4))
        self.assertEqual(len(campaign["seeds"]["trial"]), 4)
        with self.assertRaises(SystemExit):
            self.coach("--print-command", "--dir", self.root + "-2", "--budget", "0")


if __name__ == "__main__":
    unittest.main()
