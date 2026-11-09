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
        """Record finished games reaching the given dungeon depths, one per seed."""
        for seed, depth in zip(seeds or self.c["seeds"][which], depths):
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

    def test_rules_are_checked(self):
        for bad in ({"budget": 0}, {"margin": -1}, {"patience": 0}, {"holdout": -1}, {"luck": 1}):
            with self.assertRaises(learn.LearnError):
                learn.new_campaign(rules=bad)
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
        self.assertIn("L1 saved as tentative, citing 1 run.",
                      self.call("add_lesson", text="Level 1 monsters hit hard without armour.",
                                evidence=[first]))
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
        self.assertIn("- L1: Level 1 monsters hit hard without armour. (runs: %s)" % first, text)
        self.assertIn("- **S1 Baseline** [proven, the base]: 1 of 1 trial games, "
                      "average progress 0.03, best: never left town", text)
        self.assertIn("  - **S2 Armour first** [on trial]: not played yet ← play this next", text)
        self.assertIn("- %s (S1): Quit" % first, text)
        self.assertIn("  - went wrong: Had no armour", text)

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
        self.assertIn("L1 saved as confirmed, citing 2 runs.",
                      self.call("add_lesson", text="level 1 monsters hit hard without armour.",
                                evidence=[second], confidence="confirmed"))
        self.call("add_lesson", text="Never use the bank.")
        self.assertIn("L2 retracted", self.call("retract_lesson", lesson_id="L2",
                                                reason="Gold in the bank earns interest."))
        self.fails("retract_lesson", lesson_id="L9", reason="x")
        self.fails("retract_lesson", lesson_id="L1", reason=" ")
        text = self.call("get_briefing")
        self.assertIn("Confirmed, follow these:", text)
        self.assertNotIn("Never use the bank", text)

        doc = self.read("CAMPAIGN.md")
        self.assertIn("- L1: Level 1 monsters hit hard without armour. (runs: %s, %s)" % tuple(
            sorted([first, second])), doc)
        self.assertIn("- L2: ~~Never use the bank.~~ Gold in the bank earns interest.", doc)
        self.assertIn("    - **S3 And a shield** [abandoned]: 1 of 1 trial games", doc)
        self.assertIn("      Change: Also buy a shield", doc)
        self.assertIn("## Tried and failed", doc)
        self.assertIn("## Decisions", doc)
        self.assertIn("S2 Armour first proven: trial average 1.02; averaged 1.02 on 1 unseen "
                      "seeds, S1 averaged 0.03 on the trial seeds; it is the new base.", doc)
        self.assertIn("| Progress |", self.read("INDEX.md"))


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
