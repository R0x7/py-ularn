"""Replays of recorded runs (run: python3 -m unittest tests.test_replay)."""

import gzip
import json
import os
import shutil
import tempfile
import unittest

from pyularn import replay


def decode(entries):
    """What the player page does with a replay file, in Python."""
    out, rows, mp, state = [], [], None, None
    for e in entries:
        if "th" in e:
            out.append(("thought", e["th"]))
            continue
        if "r" in e:
            rows = e["r"]
        elif "d" in e:
            rows = list(rows)
            for i, r in e["d"]:
                rows[i] = r
        if e.get("m") == 0:
            mp = None
        elif e.get("m"):
            mp = e["m"]
        elif "md" in e:
            tiles = list(mp["tiles"])
            t = e["md"]["t"]
            for i in range(0, len(t), 2):
                tiles[t[i]] = t[i + 1]
            mp = {"w": mp["w"], "h": mp["h"], "tiles": tiles,
                  "player": e["md"]["p"], "cursor": e["md"]["c"]}
        if "s" in e:
            changes = dict(e["s"])
            st = changes.pop("st", None)
            state = dict(state or {}, **changes)
            if st:
                state["stats"] = dict(state["stats"], **st)
        out.append(("frame", rows, mp, state))
    return out


class ReplayTest(unittest.TestCase):
    def setUp(self):
        from pyularn import mcp_server
        self.m = mcp_server
        self.root = tempfile.mkdtemp()
        self.site = tempfile.mkdtemp()
        self.old_home = os.environ.get("PYULARN_HOME")
        os.environ["PYULARN_HOME"] = tempfile.mkdtemp()
        self.old_dir = mcp_server.SESSION.record_dir
        mcp_server.SESSION.record_dir = self.root
        del mcp_server._OWN_HOME[:]

    def tearDown(self):
        self.m.SESSION.stop()
        self.m.SESSION.record_dir = self.old_dir
        del self.m._OWN_HOME[:]
        if self.old_home is None:
            os.environ.pop("PYULARN_HOME", None)
        else:
            os.environ["PYULARN_HOME"] = self.old_home
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.site, ignore_errors=True)

    def record_game(self):
        m = self.m
        m.tool_new_game({"seed": 4242, "character_class": "rogue", "thought": "start"})
        m.TOOLS_BY_NAME["take_stairs"]["handler"]({"thought": "down we go"})
        m.TOOLS_BY_NAME["explore"]["handler"]({"max_steps": 40})
        m.tool_move({"direction": "north", "count": 2})
        m.tool_send_keys({"keys": "s", "thought": "search"})
        m.tool_end_game({})
        (run,) = [d for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))]
        return os.path.join(self.root, run)

    def test_rebuild_matches_the_recording(self):
        run = self.record_game()
        messages, report = replay.rebuild(run)
        self.assertIsNone(report["mismatch"])
        self.assertEqual(report["replayed"], report["actions"])
        self.assertEqual(report["actions"], 4)
        thoughts = [m["text"] for m in messages if m.get("type") == "thought"]
        self.assertEqual(thoughts, ["down we go", "search"])
        frames = [m for m in messages if "rows" in m]
        self.assertGreater(len(frames), 10)

        # The compact entries decode back to every frame.
        decoded = [d for d in decode(replay.encode(messages)) if d[0] == "frame"]
        last = None
        want = []
        for f in frames:
            state = {k: f["state"].get(k) for k in replay.PAGE_STATE}
            item = ("frame", f["rows"], f["map"], state)
            if item != last:
                want.append(item)
            last = item
        self.assertEqual([d[1:] for d in decoded][-1], want[-1][1:])
        for got in decoded:
            self.assertIn(got, want)

    def test_export_writes_a_site(self):
        run = self.record_game()
        self.assertTrue(replay.export(self.site, [run], log=lambda *_: None))
        with open(os.path.join(self.site, "runs", "index.json")) as f:
            (entry,) = json.load(f)
        self.assertTrue(entry["complete"])
        self.assertEqual(entry["class"], "Rogue")
        with gzip.open(os.path.join(self.site, "runs", entry["id"] + ".json.gz"), "rt") as f:
            data = json.load(f)
        self.assertEqual(data["run"]["id"], entry["id"])
        user = os.environ.get("USER")
        if user and len(user) > 3:
            self.assertNotIn(user, json.dumps(data))
        with open(os.path.join(self.site, "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("DecompressionStream", page)
        self.assertNotIn("new EventSource", page)
        self.assertTrue(os.path.getsize(os.path.join(self.site, "ularn_gfx.png")) > 1000)


if __name__ == "__main__":
    unittest.main()
