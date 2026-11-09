"""A scripted stand-in for the agent the coach starts: it follows one cycle
of the briefing with no model behind it, so the loop can be tested.

    python fake_agent.py MCP_CONFIG PROMPT
"""

import json
import os
import re
import subprocess
import sys


class Client:
    def __init__(self, config_path):
        with open(config_path, encoding="utf-8") as f:
            server = json.load(f)["mcpServers"]["pyularn"]
        self.proc = subprocess.Popen(
            [server["command"], *server["args"]], env=dict(os.environ, **server.get("env", {})),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.n = 0
        self.request("initialize", {"protocolVersion": "2025-06-18"})

    def request(self, method, params):
        self.n += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method,
                                          "params": params}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())["result"]

    def call(self, name, **args):
        res = self.request("tools/call", {"name": name, "arguments": args})
        text = res["content"][0]["text"]
        if res["isError"]:
            raise RuntimeError("%s failed: %s" % (name, text))
        return text


def main():
    config, prompt = sys.argv[1], sys.argv[2]
    assert "get_briefing" in prompt
    c = Client(config)
    briefing = c.call("get_briefing")
    sid = re.search(r"## Play this strategy: (S\d+)", briefing).group(1)
    text = c.call("new_game", strategy=sid, character_class="dwarf")
    run = re.search(r"as run (\S+)\.", text).group(1)
    c.call("take_stairs", direction="down", thought="Following %s." % sid)
    text = c.call("send_keys", keys="Qy")
    for _ in range(8):
        if "Status: game over" in text:
            break
        text = c.call("send_keys", keys="<enter>")
    c.call("summarize_run", synopsis="Went down one level under %s and gave up." % sid,
           went_wrong=["Gave up at once"], next_try=["Keep going"])
    c.call("add_lesson", text="The dungeon entrance is a short walk from the start.", evidence=[run])
    if sid == "S1":
        c.call("propose_strategy", title="Buy armour", change="Buy leather armor before the dungeon")
    print("Played %s as %s." % (run, sid))
    c.proc.stdin.close()
    c.proc.wait(10)


if __name__ == "__main__":
    main()
