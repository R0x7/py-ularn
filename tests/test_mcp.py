"""End-to-end test of the MCP server over stdio (run: python3 -m unittest)."""

import json
import os
import subprocess
import sys
import tempfile
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
                                 "get_state", "key_reference", "end_game"})

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


class SpectatorTest(unittest.TestCase):
    def test_live_frames(self):
        import re
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
            c.call("send_keys", keys="i")
            f2 = frame()
            self.assertGreater(f2["seq"], f1["seq"])
            self.assertEqual(f2["key"], "i")
            screen = "\n".join("".join(r[0] for r in row) for row in f2["rows"])
            self.assertIn("a)", screen)

            # The event stream starts with the latest frame.
            with urllib.request.urlopen(url + "events", timeout=5) as es:
                line = es.readline().decode()
            self.assertTrue(line.startswith("data: {"), line)

            c.call("end_game")
            self.assertEqual(frame()["status"], "game over")
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
