"""Run many scripted bots at once, each playing its own game through its own
pyularn MCP server, on a random difficulty with a randomly drawn strategy.

    python examples/bot_swarm.py [--agents 50] [--max-actions 600]
                                 [--out DIR] [--seed N] [--max-difficulty 100]

No model is involved: each bot is a small rule-based player whose knobs
(how deep to go, when to fight or flee, when to rest, whether to shop, cast
or quaff, how often to do something random) are drawn at random when it
starts. Every game is recorded with --record, so the usual tools work on
the results (pyularn-runs --dir DIR/runs/agent-NN). A summary of all games
is written to DIR/results.json and DIR/RESULTS.md.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = {(0, -1): "k", (0, 1): "j", (-1, 0): "h", (1, 0): "l",
        (-1, -1): "y", (1, -1): "u", (-1, 1): "b", (1, 1): "n"}
CLASSES = "abcdefgh"
ARMOR_WORDS = ("armor", "mail", "plate")
WEAPON_WORDS = ("sword", "dagger", "axe", "mace", "spear", "flail", "hammer")
SHOP_LIKES = ("leather armor", "ring mail", "studded leather", "chain mail", "dagger",
              "spear", "mace", "battle axe", "longsword", "potion of healing",
              "scroll of enchant", "potion of restore", "shield", "scroll of teleport")


class Client:
    def __init__(self, home, record):
        env = dict(os.environ, PYTHONPATH=ROOT, PYULARN_HOME=home)
        env.pop("PYULARN_WATCH", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pyularn.mcp_server", "--record", record],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.n = 0
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "bot-swarm", "version": "0"}})

    def request(self, method, params):
        self.n += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n,
                                          "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server exited")
        return json.loads(line)

    def call(self, name, **args):
        r = self.request("tools/call", {"name": name, "arguments": args})["result"]
        return r["content"][0]["text"], r.get("isError", False)

    def skill(self, name, **args):
        text, err = self.call(name, **args)
        if err:
            return {"result": "error", "message": text[:200]}
        if text.startswith("Skill result:\n"):
            body = text[len("Skill result:\n"):].split("\n\nStatus:")[0]
            try:
                return json.loads(body)
            except ValueError:
                pass
        return {"result": "?"}

    def state(self):
        text, err = self.call("get_state")
        return None if err else json.loads(text)

    def close(self):
        try:
            self.call("end_game")
            self.proc.stdin.close()
            self.proc.wait(10)
        except Exception:
            self.proc.kill()


def draw_strategy(rng, max_difficulty):
    """An almost random strategy: random knobs, but each one sensible."""
    return {
        "class": rng.choice(CLASSES),
        # Skewed towards easier games, but the whole range can come up.
        "difficulty": int(round(rng.random() ** 2 * max_difficulty)),
        "target_depth": rng.choice([1, 2, 3, 4, 5, 6, 8, 10, 15]),
        "explore_first": rng.random(),          # chance to explore a level fully before going down
        "aggression": rng.random(),             # chance to fight rather than flee
        "fight_min_hp": round(rng.uniform(0.15, 0.6), 2),
        "rest_below": round(rng.uniform(0.3, 0.9), 2),
        "greed": rng.random(),                  # chance to pick up items after exploring
        "shop": rng.random() < 0.6,
        "cast": rng.random(),                   # chance to cast magic missile at a monster
        "quaff": rng.random(),                  # chance to drink a potion when in trouble
        "chaos": round(rng.uniform(0.0, 0.25), 2),   # chance of a purely random move
        "go_home": rng.random() < 0.3,          # head back to town at target depth
        "threat_radius": rng.randint(2, 7),     # monsters further away are walked past
        "flee_patience": rng.randint(1, 6),     # flees in a row before standing to fight
    }


def direction_to(pos, mon):
    dx = (mon["x"] > pos["x"]) - (mon["x"] < pos["x"])
    dy = (mon["y"] > pos["y"]) - (mon["y"] < pos["y"])
    return KEYS.get((dx, dy), "k")


def depth_of(st):
    idx = st.get("level_index", 0)
    return idx if isinstance(idx, int) else 0


class Bot:
    def __init__(self, n, args, rng):
        self.n = n
        self.rng = rng
        self.args = args
        self.strat = draw_strategy(rng, args.max_difficulty)
        self.home = os.path.join(args.out, "homes", "agent-%02d" % n)
        self.record = os.path.join(args.out, "runs", "agent-%02d" % n)
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.record, exist_ok=True)
        self.actions = 0
        self.log = []
        self.counts = {}
        self.result = None
        self.level_actions = 0
        self.last_level = None
        self.returning = False
        self.flees = 0
        self.ignore = False

    def act(self, name, **args):
        self.actions += 1
        self.level_actions += 1
        self.counts[name] = self.counts.get(name, 0) + 1
        if name in ("send_keys", "move"):
            text, _ = self.c.call(name, **args)
            return {"result": "sent", "text": text}
        return self.c.skill(name, **args)

    def run(self):
        s, rng = self.strat, self.rng
        t0 = time.time()
        try:
            self.c = Client(self.home, self.record)
            self.c.call("new_game", character_class=s["class"], difficulty=s["difficulty"],
                        seed=rng.randrange(1, 2**31), player_name="Bot%02d" % self.n,
                        strategy="swarm-random",
                        hypotheses=["%s=%s" % kv for kv in sorted(s.items())],
                        thought="Bot %d with a random strategy." % self.n)
            if s["shop"]:
                self.shop()
            while self.actions < self.args.max_actions:
                if time.time() - t0 > self.args.time_limit:
                    break
                st = self.c.state()
                if st is None or st.get("outcome"):
                    break
                self.turn(st)
            st = self.c.state() or {}
            self.result = self.summarize(st, time.time() - t0)
        except Exception as e:
            self.result = {"agent": self.n, "strategy": s, "error": repr(e),
                           "trace": traceback.format_exc()[-800:], "actions": self.actions}
        finally:
            if hasattr(self, "c"):
                self.c.close()
        return self.result

    # -- one decision -------------------------------------------------
    def turn(self, st):
        s, rng = self.strat, self.rng
        inp = st.get("input", {})
        if inp.get("kind") == "prompt":
            answers = inp.get("answers") or ["<esc>"]
            pick = "<esc>" if "<esc>" in answers and rng.random() < 0.7 else rng.choice(answers)
            self.act("send_keys", keys=pick, thought="answering a prompt")
            return
        if st.get("display") == "text" or inp.get("kind") == "other":
            self.act("send_keys", keys="<esc>")
            return

        if depth_of(st) != self.last_level:
            self.last_level = depth_of(st)
            self.level_actions = 0
        hp, hp_max = st["stats"]["hp"], max(1, st["stats"]["hp_max"])
        frac = hp / hp_max
        mons = st.get("monsters") or []
        pos = st["position"]

        if rng.random() < s["chaos"]:
            self.act("move", key=rng.choice("hjklyubn"), count=rng.randint(1, 4),
                     thought="a random step")
            return

        threats = [m for m in mons if m.get("distance", 99) <= s["threat_radius"]]
        self.ignore = bool(mons) and not threats
        if not threats:
            self.flees = 0
        if threats:
            near = threats[0]
            if frac < s["fight_min_hp"] and rng.random() < s["quaff"] and self.quaff(st):
                return
            if (st["stats"]["spells"] > 0 and rng.random() < s["cast"]
                    and any(k.startswith("mle") for k in st.get("known_spells", []))
                    and near.get("distance", 99) <= 6):
                self.act("send_keys", keys="cmle" + direction_to(pos, near),
                         thought="magic missile at %s" % near.get("name"))
                return
            if frac >= s["fight_min_hp"] and rng.random() < s["aggression"]:
                r = self.act("fight", min_hp=s["fight_min_hp"], thought="fight")
                if r.get("result") not in ("error", "unreachable"):
                    return
            if self.flees >= s["flee_patience"]:
                self.flees = 0
                self.act("fight", min_hp=0.05, thought="tired of running, fight it out")
                return
            self.flees += 1
            r = self.act("flee", thought="flee")
            if r.get("result") in ("cornered", "blocked", "error"):
                self.act("fight", min_hp=0.05, thought="cornered, fight it out")
            return

        if frac < s["rest_below"]:
            r = self.act("rest", thought="rest")
            if r.get("result") not in ("error", "blocked"):
                return

        depth = depth_of(st)
        if depth >= s["target_depth"] and s["go_home"]:
            self.returning = True
        if self.returning:
            if depth == 0:
                self.returning = False
                s["target_depth"] += rng.choice([1, 2, 3])
                if s["shop"]:
                    self.shop()
                return
            r = self.act("take_stairs", direction="up", ignore_monsters=self.ignore)
            if r.get("result") == "not_found":
                self.act("explore", until="stairs_up")
            return

        explore_more = rng.random() < s["explore_first"] and self.level_actions < 40
        if depth == 0:
            explore_more = False
        if explore_more or depth >= s["target_depth"]:
            r = self.act("explore", ignore_monsters=self.ignore)
            if r.get("result") == "explored":
                if rng.random() < s["greed"]:
                    self.act("pick_up")
                if depth < s["target_depth"]:
                    self.descend()
                else:
                    # Done with the target: wander one deeper with a small chance.
                    if rng.random() < 0.3:
                        s["target_depth"] += 1
                    else:
                        self.act("rest", turns=rng.randint(5, 30))
            elif r.get("result") in ("error", "no_path"):
                self.act("move", key=rng.choice("hjklyubn"), count=rng.randint(1, 3))
            return
        self.descend()

    def descend(self):
        r = self.act("take_stairs", direction="down", ignore_monsters=self.ignore)
        res = r.get("result")
        if res == "not_found":
            r = self.act("explore", until="stairs_down", ignore_monsters=self.ignore)
            if r.get("result") in ("explored", "error", "no_path"):
                self.act("move", key=self.rng.choice("hjklyubn"), count=self.rng.randint(1, 4))
        elif res in ("error", "refused", "blocked"):
            self.act("move", key=self.rng.choice("hjklyubn"), count=self.rng.randint(1, 3))

    def quaff(self, st):
        pots = [line for line in st.get("inventory", []) if "potion" in line.lower()]
        if not pots:
            return False
        healing = [p for p in pots if "heal" in p.lower()]
        line = (healing or [self.rng.choice(pots)])[0]
        letter = line.strip()[0]
        self.act("send_keys", keys="q" + letter, thought="quaff " + line.strip())
        return True

    def shop(self):
        rng = self.rng
        st = self.c.state()
        if not st or depth_of(st) != 0 or st["stats"]["gold"] < 20:
            return
        listing = self.act("buy", thought="price list")
        stock = listing.get("stock") or listing.get("items") or []
        gold = st["stats"]["gold"]
        wants = []
        for item in rng.sample(stock, len(stock)) if isinstance(stock, list) else []:
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            price = item.get("price", 10**9) if isinstance(item, dict) else 10**9
            liked = any(w in name.lower() for w in SHOP_LIKES)
            if price <= gold and (liked or rng.random() < 0.1):
                wants.append(name)
                gold -= price
        if wants:
            self.act("buy", items=wants[:4], thought="buy " + ", ".join(wants[:4]))
            self.equip()

    def equip(self):
        st = self.c.state() or {}
        for line in st.get("inventory", []):
            low, letter = line.lower(), line.strip()[:1]
            if "being worn" in low or "in hand" in low:
                continue
            if any(w in low for w in ARMOR_WORDS):
                self.act("send_keys", keys="W" + letter, thought="wear " + line)
            elif any(w in low for w in WEAPON_WORDS):
                self.act("send_keys", keys="w" + letter, thought="wield " + line)
            st2 = self.c.state() or {}
            if st2.get("input", {}).get("kind") == "prompt" or st2.get("display") == "text":
                self.act("send_keys", keys="<esc>")

    def summarize(self, st, secs):
        o = st.get("outcome") or {}
        return {
            "agent": self.n, "strategy": self.strat, "seed": st.get("seed"),
            "result": o.get("result") or ("unfinished" if st else "unknown"),
            "won": o.get("won", False), "reason": o.get("reason"),
            "killer": o.get("killer"),
            "deepest": st.get("deepest"), "level_now": st.get("dungeon_level"),
            "char_level": st.get("stats", {}).get("level"),
            "turns": st.get("turns"), "actions": self.actions,
            "calls": self.counts, "seconds": round(secs, 1),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=50)
    ap.add_argument("--max-actions", type=int, default=600)
    ap.add_argument("--time-limit", type=float, default=1800, help="seconds per agent")
    ap.add_argument("--max-difficulty", type=int, default=100)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="swarm-out")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    master = random.Random(a.seed)
    bots = [Bot(i + 1, a, random.Random(master.randrange(2**63))) for i in range(a.agents)]
    results = [None] * len(bots)
    done = [0]
    lock = threading.Lock()

    def go(i):
        results[i] = bots[i].run()
        with lock:
            done[0] += 1
            r = results[i]
            print("[%2d/%d] agent %02d d=%-3s %-10s deepest=%s actions=%s %s" % (
                done[0], len(bots), r["agent"], r["strategy"]["difficulty"],
                r.get("result", "ERROR"), (r.get("deepest") or {}).get("dungeon"),
                r.get("actions"), r.get("reason") or r.get("error") or ""), flush=True)

    t0 = time.time()
    threads = [threading.Thread(target=go, args=(i,)) for i in range(len(bots))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    write_report(results, os.path.join(a.out, "RESULTS.md"), time.time() - t0)
    print("Wrote", os.path.join(a.out, "RESULTS.md"))


def write_report(results, path, secs):
    ok = [r for r in results if "error" not in r]
    lines = ["# Bot swarm: %d agents" % len(results), "",
             "Wall time %.0f s. Errors: %d." % (secs, len(results) - len(ok)), ""]
    by = {}
    for r in ok:
        by[r["result"]] = by.get(r["result"], 0) + 1
    lines.append("Outcomes: " + ", ".join("%s %d" % kv for kv in sorted(by.items())))
    killers = {}
    for r in ok:
        if r.get("killer"):
            killers[r["killer"]] = killers.get(r["killer"], 0) + 1
    lines.append("Top killers: " + ", ".join("%s %d" % kv for kv in
                                             sorted(killers.items(), key=lambda kv: -kv[1])[:10]))
    lines += ["", "| Agent | Class | Diff | Target | Aggr | Shop | Result | Deepest | CL | Turns | Actions | Reason |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: r["agent"]):
        s = r["strategy"]
        lines.append("| %02d | %s | %d | %d | %.2f | %s | %s | %s | %s | %s | %s | %s |" % (
            r["agent"], s["class"], s["difficulty"], s["target_depth"], s["aggression"],
            "y" if s["shop"] else "n", r.get("result", "ERROR"),
            (r.get("deepest") or {}).get("dungeon", "-"), r.get("char_level", "-"),
            r.get("turns", "-"), r.get("actions", "-"),
            (r.get("reason") or r.get("error") or "").replace("|", "/")))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
