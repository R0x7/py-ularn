"""End-to-end test of the MCP server over stdio (run: python3 -m unittest)."""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class McpClient:
    def __init__(self, extra_args=()):
        env = dict(os.environ, PYTHONPATH=ROOT, PYULARN_HOME=tempfile.mkdtemp())
        env.pop("PYULARN_WATCH", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pyularn.mcp_server", *extra_args], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")
        self.next_id = 1

    def request(self, method, params=None):
        mid = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server died: " + self.proc.stderr.read())
        msg = json.loads(line)
        assert msg["id"] == mid, msg
        return msg

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def call(self, name, **args):
        msg = self.request("tools/call", {"name": name, "arguments": args})
        res = msg["result"]
        return res["content"][0]["text"], res["isError"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(10)
        self.proc.stdout.close()
        self.proc.stderr.close()


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.c = McpClient()
        init = self.c.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.c.notify("notifications/initialized")

    def tearDown(self):
        self.c.close()

    def test_tools_listed(self):
        tools = {t["name"] for t in self.c.request("tools/list")["result"]["tools"]}
        self.assertEqual(tools, {"new_game", "send_keys", "move", "get_screen",
                                 "get_state", "key_reference", "end_game",
                                 "summarize_run", "list_runs", "get_run",
                                 "explore", "travel_to", "take_stairs", "fight", "flee", "buy"})
        new_game = next(t for t in self.c.request("tools/list")["result"]["tools"]
                        if t["name"] == "new_game")
        self.assertIn("difficulty", new_game["inputSchema"]["properties"])

    def test_play(self):
        text, err = self.c.call("send_keys", keys="h")
        self.assertTrue(err)  # no game yet

        text, err = self.c.call("new_game", character_class="rogue", seed=42)
        self.assertFalse(err, text)
        self.assertIn("HP:", text)
        state = json.loads(text.split("State:\n", 1)[1])
        self.assertEqual(state["dungeon_level"], "H")
        self.assertTrue(state["inventory"])
        start = state["position"]

        text, err = self.c.call("move", direction="e", count=2, include_state=True)
        self.assertFalse(err, text)

        text, err = self.c.call("send_keys", keys="i")
        self.assertFalse(err, text)
        self.assertIn(")", text)
        self.c.call("send_keys", keys="<esc>")

        st = json.loads(self.c.call("get_state")[0])
        self.assertIn("hp", st["stats"])
        self.assertIsInstance(st["position"]["x"], int)
        self.assertNotEqual(st["turns"], None)
        del start

        # Same seed -> same starting state.
        a = json.loads(self.c.call("new_game", character_class="e", seed=7)[0].split("State:\n", 1)[1])
        b = json.loads(self.c.call("new_game", character_class="e", seed=7)[0].split("State:\n", 1)[1])
        self.assertEqual(a["position"], b["position"])
        self.assertEqual(a["stats"], b["stats"])

        text, err = self.c.call("end_game")
        self.assertFalse(err)

    def test_unknown_method(self):
        self.assertEqual(self.c.request("nope/nope")["error"]["code"], -32601)

    def new_game(self, **args):
        text, err = self.c.call("new_game", **args)
        self.assertFalse(err, text)
        return json.loads(text.split("State:\n", 1)[1])

    def test_state_for_agents(self):
        st = self.new_game(character_class="rogue", seed=42)
        self.assertEqual(st["seed"], 42)
        self.assertEqual(st["character_class"], "Rogue")
        self.assertEqual(st["difficulty"], 0)
        self.assertEqual(st["deepest"], {"dungeon": 0, "volcano": 0})
        self.assertEqual(st["time"], {"turn_limit": 40000, "mobuls_left": 399})
        self.assertEqual(st["monsters"], [])
        self.assertNotIn("outcome", st)

        # Without a seed one is picked and reported, so the game can be replayed.
        a = self.new_game(character_class="rogue")
        self.assertIsInstance(a["seed"], int)
        b = self.new_game(character_class="rogue", seed=a["seed"])
        self.assertEqual(a["position"], b["position"])
        self.assertEqual(a["stats"], b["stats"])

    def test_difficulty(self):
        self.assertEqual(self.new_game(character_class="dwarf", seed=5, difficulty=3)["difficulty"], 3)
        self.assertEqual(self.new_game(character_class="dwarf", seed=5)["difficulty"], 0)
        for bad in (-1, 101, "hard", 2.5, True):
            text, err = self.c.call("new_game", difficulty=bad)
            self.assertTrue(err, text)
            self.assertIn("difficulty", text)

    def quit_game(self):
        """Quit and page through the score screens until the game is over."""
        text, _ = self.c.call("send_keys", keys="Q")
        self.assertIn("quit", text.lower())
        text, _ = self.c.call("send_keys", keys="y")
        for _ in range(8):
            if "Status: game over" in text:
                break
            text, err = self.c.call("send_keys", keys="<enter>")
            self.assertFalse(err, text)
        self.assertIn("Status: game over", text)
        return text

    def test_outcome(self):
        self.new_game(character_class="elf", seed=11, difficulty=2)
        self.c.call("move", direction="e", count=3)
        text = self.quit_game()
        out = json.loads(text.split("Outcome:\n", 1)[1])
        self.assertEqual(out["result"], "quit")
        self.assertFalse(out["won"])
        self.assertEqual(out["reason"], "quit")
        self.assertIsNone(out["killer"])
        self.assertIsInstance(out["score"], int)
        self.assertEqual((out["seed"], out["difficulty"], out["character_class"]), (11, 2, "Elf"))
        self.assertEqual(out["dungeon_level"], "H")
        self.assertEqual(json.loads(self.c.call("get_state")[0])["outcome"], out)

        # A game the agent abandons has an outcome too.
        self.new_game(character_class="elf", seed=11)
        self.c.call("end_game")
        st = json.loads(self.c.call("get_state")[0])
        self.assertEqual(st["outcome"]["result"], "stopped")

    def test_skill_tools(self):
        text, err = self.c.call("explore")
        self.assertTrue(err)  # no game yet
        self.new_game(character_class="dwarf", seed=7)

        def skill(name, **args):
            text, err = self.c.call(name, **args)
            self.assertFalse(err, text)
            self.assertIn("Screen:\n", text)
            body = text.split("Skill result:\n", 1)[1]
            return json.JSONDecoder().raw_decode(body)[0], text

        r, _ = skill("explore")
        self.assertEqual(r["result"], "explored")   # the town is all in view
        r, text = skill("travel_to", target="bank", include_state=True)
        self.assertEqual(r["result"], "arrived")
        state = json.loads(text.split("State:\n", 1)[1])
        self.assertEqual(state["input"], {"kind": "prompt", "answers": ["g", "i", "<esc>"]})
        self.assertIn("$", {o["symbol"] for o in state["objects"]})
        text, err = self.c.call("fight")
        self.assertTrue(err)
        self.assertIn("asking something", text)
        self.c.call("send_keys", keys="<esc>")

        r, _ = skill("buy")
        self.assertEqual(r["result"], "listed")
        self.assertTrue(r["stock"])
        r, _ = skill("fight")
        self.assertEqual(r["result"], "no_monsters")
        r, _ = skill("flee")
        self.assertEqual(r["result"], "safe")
        r, _ = skill("take_stairs", direction="down", thought="Into the dungeon.")
        self.assertEqual((r["result"], r["level"]), ("changed_level", "1"))

        for name, args in (("travel_to", {}), ("travel_to", {"target": "nowhere"}),
                           ("travel_to", {"x": 500, "y": 1}), ("fight", {"min_hp": 2}),
                           ("explore", {"max_steps": 0}), ("take_stairs", {"direction": "left"}),
                           ("buy", {"items": "sword"})):
            text, err = self.c.call(name, **args)
            self.assertTrue(err, (name, args, text))
            self.assertNotIn("Traceback", text)

    def test_run_tools_need_recording(self):
        for tool, args in (("list_runs", {}), ("get_run", {}),
                           ("summarize_run", {"synopsis": "x"})):
            text, err = self.c.call(tool, **args)
            self.assertTrue(err, text)
            self.assertIn("--record", text)


class DeathTest(unittest.TestCase):
    """Dying and what the agent can see, checked inside one process."""

    def setUp(self):
        from pyularn import mcp_server
        self.old_home = os.environ.get("PYULARN_HOME")
        os.environ["PYULARN_HOME"] = tempfile.mkdtemp()
        self.session = mcp_server.GameSession()
        self.session.start(seed=9)
        self.session.send("e")     # rogue
        self.session.send("\r")    # past the welcome text

    def tearDown(self):
        self.session.stop()
        if self.old_home is None:
            del os.environ["PYULARN_HOME"]
        else:
            os.environ["PYULARN_HOME"] = self.old_home

    def feed_until_over(self):
        for _ in range(8):
            if self.session.term.finished:
                return
            self.session.send("\r")
        self.fail("the game did not end:\n" + self.session.screen())

    def test_killed_by_monster(self):
        from pyularn import monster, scores
        import pyularn.ularn as ularn
        s = self.session
        # The engine reports deaths through scores.died(); do so on the game
        # thread, the way a monster's attack would.
        orig_parse = ularn.parse
        ularn.parse = lambda action: scores.died(scores.DIED_MONSTER, monster.JACKAL)
        try:
            s.send(".")
        finally:
            ularn.parse = orig_parse
        out = s.final_outcome()
        self.assertEqual(out["result"], "died")
        self.assertEqual(out["killer"], monster.monster[monster.JACKAL].name)
        self.assertEqual(out["reason"], "killed by a " + out["killer"])
        self.assertEqual(s.state()["outcome"], out)
        self.feed_until_over()
        self.assertEqual(s.final_outcome(), out)

    def test_life_protection_is_not_a_death(self):
        from pyularn import monster, player, scores
        import pyularn.ularn as ularn
        s = self.session
        player.c[player.LIFEPROT] = 1
        orig_parse = ularn.parse
        ularn.parse = lambda action: scores.died(scores.DIED_MONSTER, monster.JACKAL)
        try:
            s.send(".")
        finally:
            ularn.parse = orig_parse
        self.assertFalse(s.term.finished)
        self.assertIsNone(s.final_outcome())
        self.assertNotIn("outcome", s.state())

    def test_monsters_follow_the_screen(self):
        from pyularn import dungeon, itm, monster, mcp_server, player
        px, py = player.playerx, player.playery
        x = px + 2 if px + 2 < dungeon.MAXX else px - 2

        def place(mon, stealth, known=True):
            dungeon.mitem[x][py].mon = mon
            dungeon.stealth[x][py] = stealth
            dungeon.know[x][py] = itm.ONOTHING if known else itm.OUNKNOWN
            return mcp_server._visible_monsters()

        seen = place(monster.JACKAL, dungeon.STEALTH_SEEN)
        self.assertEqual(seen, [{"name": monster.monster[monster.JACKAL].name,
                                 "symbol": monster.monstnamelist[monster.JACKAL],
                                 "x": x, "y": py, "distance": 2}])
        self.assertEqual(len(place(monster.JACKAL, dungeon.STEALTH_AWAKE)), 1)
        self.assertEqual(place(monster.JACKAL, 0), [])                       # asleep, never seen
        self.assertEqual(place(monster.JACKAL, dungeon.STEALTH_SEEN, known=False), [])
        self.assertEqual(place(monster.INVISIBLESTALKER, dungeon.STEALTH_SEEN), [])
        self.assertEqual(place(monster.LUCIFER, dungeon.STEALTH_SEEN), [])  # no Eye of Larn
        player.c[player.BLINDCOUNT] = 5
        self.assertEqual(place(monster.JACKAL, dungeon.STEALTH_SEEN), [])


class RecordTest(unittest.TestCase):
    def test_run_is_written(self):
        root = tempfile.mkdtemp()
        c = McpClient(["--record", root])
        try:
            c.request("initialize", {"protocolVersion": "2025-06-18"})
            text, err = c.call("new_game", character_class="dwarf", seed=21, difficulty=1)
            self.assertFalse(err, text)
            self.assertIn("Recording this game to", text)
            (run,) = os.listdir(root)
            self.assertTrue(run.endswith("-s21"), run)

            def meta():
                with open(os.path.join(root, run, "meta.json"), encoding="utf-8") as f:
                    return json.load(f)

            def events():
                with open(os.path.join(root, run, "events.jsonl"), encoding="utf-8") as f:
                    return [json.loads(line) for line in f]

            m = meta()
            self.assertEqual((m["seed"], m["character_class"], m["difficulty"]), (21, "Dwarf", 1))
            self.assertIsNone(m["outcome"])

            c.call("move", direction="e", count=2, thought="Stretching my legs.")
            c.call("send_keys", keys="i")
            c.call("send_keys", keys="<esc>")
            c.call("get_state")  # looking is not an action
            ev = events()
            self.assertEqual([e["type"] for e in ev], ["start", "action", "action", "action"])
            self.assertNotIn("result", ev[1])
            self.assertEqual(ev[0]["state"]["seed"], 21)
            self.assertEqual(ev[1]["tool"], "move")
            self.assertEqual(ev[1]["args"], {"direction": "e", "count": 2, "run": False})
            self.assertEqual(ev[1]["thought"], "Stretching my legs.")
            self.assertEqual(ev[1]["s"]["lvl"], 0)
            self.assertEqual(ev[2]["args"], {"keys": "i"})
            self.assertNotIn("thought", ev[2])

            # A skill is one action, with why it stopped.
            c.call("travel_to", target="home", thought="Going home.")
            last = events()[-1]
            self.assertEqual((last["tool"], last["args"]), ("travel_to", {"target": "home"}))
            self.assertEqual(last["thought"], "Going home.")
            self.assertEqual(last["result"]["result"], "arrived")
            self.assertGreater(last["result"]["steps"], 0)
            self.assertNotIn("monsters", last["result"])

            c.call("end_game")
            m = meta()
            self.assertEqual(m["outcome"]["result"], "stopped")
            self.assertEqual(m["actions"], 4)
            end = events()[-1]
            self.assertEqual(end["type"], "end")
            self.assertEqual(end["outcome"], m["outcome"])
            self.assertEqual(len(end["last_screens"]), 5)
            self.assertIn("HP:", end["last_screens"][0]["screen"])

            # The next game gets a folder of its own.
            c.call("new_game", character_class="dwarf", seed=22)
            self.assertEqual(len([n for n in os.listdir(root) if n != "INDEX.md"]), 2)
        finally:
            c.close()


class RunStoreTest(unittest.TestCase):
    """Summaries, post-mortems and the index of recorded games."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.c = McpClient(["--record", self.root])
        init = self.c.request("initialize", {"protocolVersion": "2025-06-18"})
        self.assertIn("list_runs", init["result"]["instructions"])

    def tearDown(self):
        self.c.close()

    def call(self, name, **args):
        text, err = self.c.call(name, **args)
        self.assertFalse(err, text)
        return text

    def read(self, *parts):
        with open(os.path.join(self.root, *parts), encoding="utf-8") as f:
            return f.read()

    def play(self, seed, **args):
        text = self.call("new_game", character_class="rogue", seed=seed, **args)
        run = re.search(r"as run (\S+)\.", text).group(1)
        self.call("move", direction="e", count=2, thought="Looking around town.")
        return run

    def test_summary_and_post_mortem(self):
        text, err = self.c.call("list_runs")
        self.assertFalse(err, text)
        self.assertEqual(json.loads(text), {"total": 0, "runs": []})

        run = self.play(31, difficulty=1, strategy="bank-early",
                        hypotheses=["Bank gold before level 5", "Buy armour | first"])
        meta = json.loads(self.read(run, "meta.json"))
        self.assertEqual(meta["strategy"], "bank-early")
        self.assertEqual(meta["hypotheses"], ["Bank gold before level 5", "Buy armour | first"])

        # A post-mortem has to wait for the game to end.
        text, err = self.c.call("summarize_run", synopsis="Too early.")
        self.assertTrue(err, text)
        self.assertIn("in progress", text)
        self.assertEqual(json.loads(self.call("list_runs"))["runs"][0]["result"], "in progress")

        self.call("end_game")
        summary = self.read(run, "summary.md")
        self.assertIn("# Run " + run, summary)
        self.assertIn("**Stopped in town, turn", summary)
        self.assertIn("- Bank gold before level 5", summary)
        self.assertIn("Not written yet", summary)
        self.assertIn("- Route: H (turn 0)", summary)
        self.assertIn("Looking around town.", summary)
        self.assertIn("### Final inventory", summary)
        self.assertIn("HP:", summary)  # the final screen

        self.call("summarize_run", synopsis="Never left town.",
                  went_wrong=["Did not enter the dungeon"], worked=[],
                  next_try=["Go straight to the dungeon entrance", "Buy a | shield"])
        summary = self.read(run, "summary.md")
        self.assertNotIn("Not written yet", summary)
        self.assertIn("Never left town.", summary)
        self.assertIn("- Did not enter the dungeon", summary)
        self.assertIn("- Go straight to the dungeon entrance", summary)
        self.assertEqual(self.call("get_run"), summary)
        self.assertEqual(self.call("get_run", run_id=run), summary)

        second = self.play(32, strategy="rush")
        self.call("end_game")
        listed = json.loads(self.call("list_runs"))
        self.assertEqual(listed["total"], 2)
        self.assertEqual([r["run_id"] for r in listed["runs"]], [second, run])
        first = listed["runs"][1]
        self.assertEqual((first["strategy"], first["difficulty"], first["result"]),
                         ("bank-early", 1, "stopped"))
        self.assertEqual(first["synopsis"], "Never left town.")
        self.assertEqual(first["next_try"][0], "Go straight to the dungeon entrance")
        self.assertEqual(first["deepest"], "town")
        only = json.loads(self.call("list_runs", strategy="rush"))["runs"]
        self.assertEqual([r["run_id"] for r in only], [second])
        self.assertEqual(json.loads(self.call("list_runs", difficulty=1))["total"], 1)
        self.assertEqual(len(json.loads(self.call("list_runs", limit=1))["runs"]), 1)

        # The earlier run can still be written about by name.
        self.call("summarize_run", run_id=run, synopsis="Second thoughts.")
        self.assertIn("Second thoughts.", self.read(run, "summary.md"))

        index = self.read("INDEX.md")
        self.assertIn("[%s](%s/summary.md)" % (run, run), index)
        self.assertIn("[%s](%s/summary.md)" % (second, second), index)
        self.assertIn("| bank-early | Stopped in town", index)
        self.assertLess(index.index(second), index.index(run))  # newest first

        for bad in ("../" + run, "nope", "..", ""):
            text, err = self.c.call("get_run", run_id=bad)
            self.assertEqual(err, bad != "", (bad, text))
        text, err = self.c.call("summarize_run", synopsis="  ")
        self.assertTrue(err)
        text, err = self.c.call("new_game", hypotheses=[1, 2])
        self.assertTrue(err)

    def test_command_line(self):
        run = self.play(41, strategy="cli")
        self.call("end_game")
        self.call("summarize_run", synopsis="A short walk.", next_try=["Walk further"])

        def cli(*args):
            env = dict(os.environ, PYTHONPATH=ROOT)
            p = subprocess.run([sys.executable, "-m", "pyularn.runs", "--dir", self.root, *args],
                               cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
            return p.returncode, p.stdout, p.stderr

        code, out, _ = cli()
        self.assertEqual(code, 0)
        self.assertIn(run, out)
        self.assertIn("Stopped in town", out)
        code, out, _ = cli("show", run)
        self.assertEqual(code, 0)
        self.assertIn("A short walk.", out)
        code, _, errtext = cli("show", "missing")
        self.assertEqual(code, 1)
        self.assertIn("no run called missing", errtext)

        # Everything readable is rebuilt from meta.json and events.jsonl.
        os.remove(os.path.join(self.root, "INDEX.md"))
        os.remove(os.path.join(self.root, run, "summary.md"))
        code, out, _ = cli("reindex")
        self.assertEqual(code, 0)
        self.assertIn("A short walk.", self.read(run, "summary.md"))
        self.assertIn("Walk further", self.read("INDEX.md"))


class SpectatorTest(unittest.TestCase):
    def test_live_frames(self):
        import re
        import urllib.error
        import urllib.request

        c = McpClient(["--watch", "0"])  # port 0: any free port
        try:
            c.request("initialize", {"protocolVersion": "2025-06-18"})
            text, err = c.call("new_game", character_class="dwarf", seed=3)
            self.assertFalse(err, text)
            url = re.search(r"Live view for the user: (\S+)", text).group(1)

            page = urllib.request.urlopen(url, timeout=5).read().decode()
            self.assertIn("EventSource", page)

            def frame():
                return json.loads(urllib.request.urlopen(url + "frame", timeout=5).read())

            f1 = frame()
            self.assertEqual(f1["status"], "playing")
            self.assertEqual(f1["state"]["stats"]["level"], 1)

            # The map comes as sprite tiles, with the dwarf's sprite on the
            # player's square (female 171 / male 187).
            m = f1["map"]
            self.assertEqual((m["w"], m["h"]), (67, 17))
            self.assertEqual(len(m["tiles"]), 67 * 17)
            px, py = m["player"]
            self.assertIn(m["tiles"][py * 67 + px], (171, 187))
            png = urllib.request.urlopen(url + "ularn_gfx.png", timeout=5).read()
            self.assertTrue(png.startswith(b"\x89PNG"))

            # Watching is read-only.
            req = urllib.request.Request(url + "keys", data=b'{"keys":["j"]}', method="POST",
                                         headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(cm.exception.code, 404)
            c.call("send_keys", keys="i", thought="Checking my pack <first>.")
            f2 = frame()
            self.assertGreater(f2["seq"], f1["seq"])
            self.assertEqual(f2["key"], "i")
            screen = "\n".join("".join(r[0] for r in row) for row in f2["rows"])
            self.assertIn("a)", screen)

            # The event stream starts with the game's thoughts, then the
            # latest frame.
            with urllib.request.urlopen(url + "events", timeout=5) as es:
                msgs = []
                while len(msgs) < 2:
                    line = es.readline().decode()
                    if line.startswith("data: "):
                        msgs.append(json.loads(line[6:]))
            self.assertEqual(msgs[0]["type"], "thought")
            self.assertEqual(msgs[0]["text"], "Checking my pack <first>.")
            self.assertEqual(msgs[0]["action"], "keys i")
            self.assertEqual(msgs[1]["seq"], f2["seq"])
            self.assertLess(msgs[0]["seq"], f2["seq"])

            c.call("end_game")
            self.assertEqual(frame()["status"], "game over")
        finally:
            c.close()


class WebPlayTest(unittest.TestCase):
    """`pyularn --web`: the page is the game's keyboard."""

    def test_play_in_browser(self):
        import re
        import urllib.error
        import urllib.request

        home = tempfile.mkdtemp()
        env = dict(os.environ, PYULARN_HOME=home, USER="webtester", LOGNAME="webtester",
                   PYTHONPATH=ROOT)
        proc = subprocess.Popen(
            [sys.executable, "-m", "pyularn", "--web", "0", "--no-browser", "-n"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=env, cwd=ROOT, text=True)
        try:
            url = None
            for _ in range(5):
                m = re.search(r"play the game at (\S+)", proc.stderr.readline())
                if m:
                    url = m.group(1)
                    break
            self.assertIsNotNone(url)

            def frame():
                return json.loads(urllib.request.urlopen(url + "frame", timeout=5).read() or b"null")

            def post(body, ctype="application/json", origin=None):
                headers = {"Content-Type": ctype}
                if origin:
                    headers["Origin"] = origin
                req = urllib.request.Request(url + "keys", data=body, method="POST", headers=headers)
                return urllib.request.urlopen(req, timeout=5).status

            def wait_for(pred):
                for _ in range(100):
                    f = frame()
                    if f and pred(f):
                        return f
                    time.sleep(0.05)
                self.fail("timed out; last frame %r" % (f and f.get("rows"),))

            page = urllib.request.urlopen(url, timeout=5).read().decode()
            self.assertIn('"play": true', page)

            f = wait_for(lambda f: f["map"] is None)  # choosing a class
            self.assertEqual(post(b'{"keys": ["e"]}'), 200)  # rogue
            f = wait_for(lambda f: f["map"] is not None)
            seq = f["seq"]
            self.assertEqual(post(b'{"keys": ["KEY_DOWN"]}'), 200)
            f = wait_for(lambda f: f["seq"] > seq)
            self.assertEqual(f["key"], "Down")

            # Only the page itself may type.
            for args in ((b'{"keys":["j"]}', "text/plain"),
                         (b'{"keys":["j"]}', "application/json", "http://evil.example")):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    post(*args)
                self.assertEqual(cm.exception.code, 403)
        finally:
            proc.terminate()
            proc.wait(10)
            proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
