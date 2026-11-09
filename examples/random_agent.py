"""A toy MCP client: starts the pyularn MCP server with the spectator page
on, then wanders around at random so you can watch it in a browser.

    python examples/random_agent.py [--port 8765] [--steps 300] [--delay 0.3]

Open http://localhost:8765/ while it runs.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Client:
    def __init__(self, port):
        env = dict(os.environ, PYTHONPATH=ROOT)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pyularn.mcp_server", "--watch", str(port)],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8")
        self.n = 0
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "random-agent", "version": "0"}})

    def request(self, method, params):
        self.n += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n,
                                          "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, name, **args):
        r = self.request("tools/call", {"name": name, "arguments": args})["result"]
        return r["content"][0]["text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    c = Client(a.port)
    text = c.call("new_game", character_class=random.choice("abcdefg"), seed=a.seed)
    print(text.splitlines()[0])
    for _ in range(a.steps):
        time.sleep(a.delay)
        if "Status: game over" in c.call("get_screen"):
            print("game over")
            break
        screen = c.call("get_screen")
        if "?" in screen.splitlines()[-1] or "(y/n)" in screen or "--more--" in screen.lower():
            c.call("send_keys", keys=random.choice(["y", "n", "<esc>", "<space>"]))
        else:
            c.call("move", direction=random.choice(["n", "s", "e", "w", "ne", "nw", "se", "sw"]),
                   count=random.randint(1, 4))
    time.sleep(2)
    c.call("end_game")
    c.proc.stdin.close()
    c.proc.wait(10)


if __name__ == "__main__":
    main()
