"""A scripted stand-in for the agent the coach starts: it follows one cycle
of the briefing with no model behind it, so the loop can be tested.

    python fake_agent.py MCP_CONFIG PROMPT

Two environment variables script how it "plays":

FAKE_DEPTH   JSON, e.g. {"S1": 0}: strategies mapped to 0 stay in town;
             every other strategy goes down to dungeon level 1.
FAKE_IDEAS   strategy changes separated by "|", proposed one at a time
             whenever the briefing asks for a new idea.  Without it, the
             agent proposes one idea of its own after its first game.
FAKE_NO_NOTES  if set, it skips the strategy's field notes after a game.

Given the coach's editor prompt instead, it tidies: see edit().
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


def edit(c, prompt):
    """The editor's pass: write the field notes asked for, and fold the
    whole playbook into one lesson if it is over its budget."""
    for sid in re.findall(r"^- (S\d+) .* no field notes", prompt, re.M):
        report = c.call("get_strategy", strategy=sid)
        assert "## Its games" in report
        c.call("note_strategy", strategy=sid, text="Editor's notes on %s." % sid)
    for sid in re.findall(r"^- (S\d+) .* has no recipe", prompt, re.M):
        c.call("write_recipe", strategy=sid, text="Editor's recipe for %s." % sid)
    if "its budget is" in prompt or "have no topic" in prompt:
        ids = re.findall(r"^- (L\d+) ", c.call("get_lessons"), re.M)
        c.call("merge_lessons", lesson_ids=ids, text="Everything, in one line.", topic="town")
    print("Tidied.")
    c.proc.stdin.close()
    c.proc.wait(10)


def main():
    config, prompt = sys.argv[1], sys.argv[2]
    if "editor of a learning campaign" in prompt:
        return edit(Client(config), prompt)
    assert "get_briefing" in prompt
    ideas = [i for i in os.environ.get("FAKE_IDEAS", "").split("|") if i]
    c = Client(config)
    briefing = c.call("get_briefing")
    if "## First: propose a strategy" in briefing:
        n = len(re.findall(r"[*][*]S[0-9]+ Idea", briefing))
        text = c.call("propose_strategy", title="Idea %d" % (n + 1), change=ideas[n])
        sid = re.search(r"Strategy (S\d+) added", text).group(1)
    else:
        sid = re.search(r"## Play this strategy: (S\d+)", briefing).group(1)
    text = c.call("new_game", strategy=sid, character_class="dwarf")
    run = re.search(r"as run (\S+)\.", text).group(1)
    if json.loads(os.environ.get("FAKE_DEPTH", "{}")).get(sid, 1):
        c.call("take_stairs", direction="down", thought="Following %s." % sid)
    text = c.call("send_keys", keys="Qy")
    for _ in range(8):
        if "Status: game over" in text:
            break
        text = c.call("send_keys", keys="<enter>")
    text = c.call("summarize_run", synopsis="Played %s and gave up." % sid,
                  takeaway="Gave up at once as %s." % sid,
                  went_wrong=["Gave up at once"], next_try=["Keep going"])
    assert "note_strategy" in text, text
    if not os.environ.get("FAKE_NO_NOTES"):
        c.call("note_strategy", strategy=sid, text="%s: give up less." % sid)
    c.call("add_lesson", text="The dungeon entrance is a short walk from the start.",
           topic="town", evidence=[run])
    if not ideas and sid == "S1" and "Buy armour" not in briefing:
        c.call("propose_strategy", title="Buy armour", change="Buy leather armor before the dungeon")
    print("Played %s as %s." % (run, sid))
    c.proc.stdin.close()
    c.proc.wait(10)


if __name__ == "__main__":
    main()
