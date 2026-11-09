"""The learning loop: progress scores, the playbook, the strategy tree, the
briefing and the coach (run: python3 -m unittest)."""

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


class CampaignTest(unittest.TestCase):
    """The learning tools, through the MCP server."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
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

    def play(self, depth=1, **args):
        """One short game: `depth` levels down, then quit."""
        text = self.call("new_game", seed=7, **args)
        run = re.search(r"as run (\S+)\.", text).group(1)
        if depth:
            self.call("take_stairs", direction="down")
        text = self.call("send_keys", keys="Qy")
        for _ in range(8):
            if "Status: game over" in text:
                break
            text = self.call("send_keys", keys="<enter>")
        return run

    def test_cycle(self):
        # The first briefing starts the campaign with a baseline to play.
        self.assertFalse(learn.exists(self.root))
        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S1 Baseline", text)
        self.assertIn("Game 1 under this strategy (not played yet)", text)
        self.assertIn("_Empty: this is one of the first games._", text)
        self.assertIn("## Your cycle", text)
        self.assertNotIn("## Latest games", text)
        self.assertTrue(learn.exists(self.root))

        first = self.play(strategy="S1", character_class="dwarf")
        meta = json.loads(self.read(first, "meta.json"))
        self.assertEqual(meta["strategy"], "S1")
        self.assertEqual(meta["hypotheses"], [learn.load(self.root)["strategies"]["S1"]["change"]])
        self.assertEqual(meta["progress"], {"score": 1.025, "milestone": "dungeon level 1"})
        self.assertIs(meta["outcome"]["has_cure"], False)
        self.assertIn("| Progress | dungeon level 1 (1.025) |", self.read(first, "summary.md"))
        self.call("summarize_run", synopsis="Quit on level 1.",
                  went_wrong=["Had no armour"], next_try=["Buy armour first"])

        # Lessons cite runs.
        self.assertIn("L1 saved as tentative, citing 1 run.",
                      self.call("add_lesson", text="Level 1 monsters hit hard without armour.",
                                evidence=[first]))
        self.assertIn("confirmed lesson must cite", self.fails(
            "add_lesson", text="Armour is good.", confidence="confirmed"))
        self.assertIn("no such run", self.fails("add_lesson", text="x", evidence=["nope"]))
        self.fails("add_lesson", text="  ")
        self.fails("add_lesson", text="x", confidence="certain")

        # A strategy is its parent plus one change, and is played next.
        text = self.call("propose_strategy", title="Armour first",
                         change="Buy leather armor before entering the dungeon",
                         character_class="Dwarf")
        self.assertIn("Strategy S2 added under S1", text)
        self.assertIn("already tests that change", self.fails(
            "propose_strategy", title="Again", parent="S1",
            change="buy leather armor before entering the dungeon"))
        self.fails("propose_strategy", title="No change")
        self.fails("propose_strategy", title="x", change="y", parent="S9")
        self.fails("propose_strategy", title="x", change="y", character_class="bard")

        text = self.call("get_briefing")
        self.assertIn("## Play this strategy: S2 Armour first", text)
        self.assertIn("Character class: dwarf.", text)
        self.assertIn("- Buy leather armor before entering the dungeon **(the change on trial)**", text)
        self.assertIn("Tentative, seen once:", text)
        self.assertIn("- L1: Level 1 monsters hit hard without armour. (runs: %s)" % first, text)
        self.assertIn("- **S1 Baseline**: 1 game, average progress 1.02, best: dungeon level 1", text)
        self.assertIn("  - **S2 Armour first**: not played yet ← play this next", text)
        self.assertIn("- %s (S1): Quit" % first, text)
        self.assertIn("  - went wrong: Had no armour", text)
        self.assertIn("  - next time: Buy armour first", text)

        # The game takes its hypotheses, class and difficulty from the strategy.
        second = self.play(depth=0, strategy="S2", character_class="wizard", difficulty=5,
                           hypotheses=["something else"])
        meta = json.loads(self.read(second, "meta.json"))
        self.assertEqual(meta["hypotheses"], ["Buy leather armor before entering the dungeon"])
        self.assertEqual((meta["character_class"], meta["difficulty"]), ("Dwarf", 0))
        self.assertEqual(meta["progress"]["milestone"], "never left town")

        # A third strategy on top of the second carries both changes.
        self.call("propose_strategy", title="And a shield", change="Also buy a shield")
        third = self.play(depth=0, strategy="S3")
        self.assertEqual(json.loads(self.read(third, "meta.json"))["hypotheses"],
                         ["Buy leather armor before entering the dungeon", "Also buy a shield"])
        # A strategy name the campaign does not know is just a label.
        other = self.play(depth=0, strategy="freestyle", hypotheses=["wing it"])
        self.assertEqual(json.loads(self.read(other, "meta.json"))["hypotheses"], ["wing it"])
        # A game that was abandoned says nothing about its strategy.
        self.call("new_game", strategy="S1", seed=3)
        self.call("end_game")

        campaign = learn.load(self.root)
        st = learn.stats(campaign, runs.list_runs(self.root))
        self.assertEqual({k: v["runs"] for k, v in st.items()}, {"S1": 1, "S2": 1, "S3": 1})
        self.assertEqual((st["S1"]["mean"], st["S1"]["best"]["milestone"], st["S1"]["run_ids"]),
                         (1.02, "dungeon level 1", [first]))
        self.assertEqual(st["S2"]["mean"], 0.03)
        self.assertEqual(learn.changes(campaign, "S1"), [])
        self.assertEqual([s["id"] for s in learn.lineage(campaign, "S3")], ["S1", "S2", "S3"])
        self.assertEqual(learn.character_class(campaign, "S3"), "dwarf")

        # A second run makes the lesson confirmed; a wrong one is retracted.
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
        self.assertIn("    - **S3 And a shield**: 1 game", doc)
        self.assertIn("      Change: Also buy a shield", doc)
        self.assertIn("5 games recorded.", doc)
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

    def setUp(self):
        self.root = os.path.join(tempfile.mkdtemp(), "campaign")
        self.agent = "%s %s {mcp_config} {prompt}" % (
            sys.executable, os.path.join(ROOT, "tests", "fake_agent.py"))
        self.old = {k: os.environ.get(k) for k in ("PYTHONPATH",)}
        os.environ["PYTHONPATH"] = ROOT

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def coach(self, *args):
        out, real = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            code = coach.main(["--dir", self.root, *args])
        finally:
            sys.stdout = real
        return code, out.getvalue()

    def test_two_cycles(self):
        code, text = self.coach("--status")
        self.assertEqual((code, text), (1, "No campaign in %s yet.\n" % self.root))

        code, text = self.coach("--cycles", "2", "--agent-cmd", self.agent)
        self.assertEqual(code, 0, text)
        self.assertIn("New campaign in %s, difficulty 0" % self.root, text)
        self.assertIn("Cycle 1 of 2: strategy S1 Baseline", text)
        self.assertIn("Cycle 2 of 2: strategy S2 Buy armour", text)   # proposed in cycle 1
        self.assertEqual(text.count("got to: dungeon level 1"), 2)
        self.assertNotIn("no post-mortem", text)

        played = runs.list_runs(self.root)
        self.assertEqual([m["strategy"] for m in played], ["S2", "S1"])
        self.assertEqual(played[0]["hypotheses"], ["Buy leather armor before the dungeon"])
        self.assertTrue(all(m["notes"] and m["outcome"]["result"] == "quit" for m in played))
        campaign = learn.load(self.root)
        (lesson,) = campaign["lessons"]                    # said twice, kept once
        self.assertEqual(sorted(lesson["evidence"]), sorted(m["run_id"] for m in played))
        with open(os.path.join(self.root, "coach-logs", "cycle-002.log"), encoding="utf-8") as f:
            self.assertIn("as S2.", f.read())
        # Its games have a scoreboard of their own.
        self.assertTrue(os.path.isdir(os.path.join(self.root, "home")))

        code, text = self.coach("--status")
        self.assertEqual(code, 0)
        self.assertIn("- **S1 Baseline**: 1 game", text)
        self.assertIn("  - **S2 Buy armour**: 1 game", text)

        # The campaign carries on where it left off, at its own difficulty.
        code, text = self.coach("--agent-cmd", self.agent)
        self.assertEqual(code, 0, text)
        self.assertIn("Continuing the campaign", text)
        self.assertIn("Cycle 1 of 1: strategy S2 Buy armour", text)
        self.assertEqual(len(runs.list_runs(self.root)), 3)
        with self.assertRaises(SystemExit):
            self.coach("--difficulty", "3", "--agent-cmd", self.agent)

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
                                "--max-budget-usd", "2.5", "--watch", "8765", "--difficulty", "1")
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
        self.assertEqual(learn.load(self.root)["difficulty"], 1)


if __name__ == "__main__":
    unittest.main()
