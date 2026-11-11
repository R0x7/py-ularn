"""The run store: read recorded games, summarise them, list them.

`pyularn.recorder` writes ``meta.json`` and ``events.jsonl`` for each game.
This module turns those into things to read:

``<run>/summary.md``  what happened (worked out from the event log) and the
                      agent's own post-mortem: synopsis, what went wrong and
                      what the next run will try
``INDEX.md``          a table of every run in the folder, newest first

Both are rebuilt from ``meta.json`` and ``events.jsonl``, which stay the
source of truth, so they can be regenerated at any time::

    pyularn-runs                 # list the runs in ./runs
    pyularn-runs show RUN_ID     # print one run's summary
    pyularn-runs reindex         # rebuild every summary.md and INDEX.md

Nothing here touches the game engine, so it is safe to use while a game runs.
"""

import json
import os
import re
import sys

RUN_ID_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*")
NOTE_LISTS = ("went_wrong", "worked", "next_try")
RESULT_WORDS = {"won": "Won", "died": "Died", "quit": "Quit", "saved": "Saved",
                "stopped": "Stopped", "crashed": "Crashed"}


class RunError(Exception):
    pass


# ====================================================================== reading

def level_name(index):
    """Name of a level index, as the game shows it: H, 1-15, V1-V5."""
    if index is None:
        return "?"
    if index == 0:
        return "H"
    return str(index) if index <= 15 else "V%d" % (index - 15)


def run_dir(root, run_id):
    """The folder of one run; raises RunError for a bad or unknown id."""
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        raise RunError("not a run id: %r" % (run_id,))
    path = os.path.join(root, run_id)
    if not os.path.isfile(os.path.join(path, "meta.json")):
        raise RunError("no run called %s in %s" % (run_id, root))
    return path


def load_meta(path):
    with open(os.path.join(path, "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def save_meta(path, meta):
    _write_text(os.path.join(path, "meta.json"), json.dumps(meta, indent=1) + "\n")


def _write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def list_runs(root):
    """The meta of every run in `root`, newest first."""
    runs = []
    try:
        names = os.listdir(root)
    except OSError:
        return runs
    for name in names:
        try:
            meta = load_meta(os.path.join(root, name))
        except (OSError, ValueError):
            continue  # not a run folder, or one being written right now
        meta.setdefault("run_id", name)
        runs.append(meta)
    runs.sort(key=lambda m: (m.get("started_ms") or 0, m["run_id"]), reverse=True)
    return runs


def read_events(path):
    """The events of a run.  A game still being played (or one cut short)
    may end in a half-written line, which is skipped."""
    events = []
    try:
        with open(os.path.join(path, "events.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return events


# ====================================================================== digest

def digest(events):
    """The facts of a run, worked out from its events alone."""
    d = {"levels": [], "level_ups": [], "lowest_hp": None, "thoughts": [],
         "final_state": None, "final_screen": None, "start_state": None,
         "errors": {}}      # (tool, message) -> times a call was refused or failed
    level = xl = None
    for ev in events:
        kind = ev.get("type")
        if kind == "start":
            st = d["start_state"] = ev.get("state") or {}
            level = st.get("level_index")
            xl = (st.get("stats") or {}).get("level")
            d["levels"].append({"turn": st.get("turns"), "level": level})
        elif kind == "action":
            s = ev.get("s") or {}
            if s.get("lvl") is not None and s["lvl"] != level:
                level = s["lvl"]
                d["levels"].append({"turn": s.get("turn"), "level": level})
            if s.get("xl") is not None and s["xl"] != xl:
                xl = s["xl"]
                d["level_ups"].append({"turn": s.get("turn"), "level": xl})
            hp, hpmax = s.get("hp"), s.get("hpmax")
            if hp is not None and hpmax:
                low = d["lowest_hp"]
                if low is None or hp * low["hpmax"] < low["hp"] * hpmax:
                    d["lowest_hp"] = {"hp": hp, "hpmax": hpmax, "turn": s.get("turn"),
                                      "level": s.get("lvl")}
            if ev.get("thought"):
                d["thoughts"].append({"turn": s.get("turn"), "text": ev["thought"]})
        elif kind == "error":
            key = (str(ev.get("tool")), str(ev.get("error") or "").split("\n")[0])
            d["errors"][key] = d["errors"].get(key, 0) + 1
        elif kind == "end":
            d["final_state"] = ev.get("state")
            screens = ev.get("last_screens") or []
            if screens:
                d["final_screen"] = screens[-1].get("screen")
    return d


# ====================================================================== run sheet

CURE = "cure dianthroritis"


def run_sheet(events):
    """How a game was built up, stage by stage, from its events alone.

    "stages" has one entry for the first arrival on each level, in the order
    they were reached: the turn, and what the character was by then (level,
    HP, AC, WC, gold, spells, what was worn and wielded).  "bought" is the
    shopping at the DND store, in order.  "spells" are in the order learned.
    "cure" says when the cure was first in the pack, and "home" lists the
    levels passed after that.  Turns come from the full states a recording
    keeps (one per level change, one when the cure is taken, one every so
    many actions), so a spell's turn is "by", not "at".
    """
    sheet = {"stages": [], "bought": [], "spells": [], "cure": None, "home": []}
    seen, known = set(), set()

    def look(state):
        level = state.get("level_index")
        stats = state.get("stats") or {}
        for spell in state.get("known_spells") or ():
            if spell not in known:
                known.add(spell)
                sheet["spells"].append({"spell": spell, "turn": state.get("turns")})
        pack = state.get("inventory") or ()
        if sheet["cure"] is None and any(CURE in line for line in pack):
            sheet["cure"] = {"turn": state.get("turns"), "level": level_name(level)}
        if level is None or level in seen:
            return
        seen.add(level)
        kit = [line.split(")", 1)[-1].strip() for line in pack
               if "(being worn)" in line or "(weapon in hand)" in line]
        kit = [k.replace(" (being worn)", "").replace(" (weapon in hand)", "") for k in kit]
        sheet["stages"].append({
            "level": level_name(level), "turn": state.get("turns"), "cl": stats.get("level"),
            "hp": stats.get("hp_max"), "ac": stats.get("ac"), "wc": stats.get("wc"),
            "gold": (stats.get("gold") or 0) + (stats.get("bank") or 0),
            "spells": len(state.get("known_spells") or ()), "kit": kit})

    level = None
    for ev in events:
        kind = ev.get("type")
        if kind in ("start", "state", "end") and ev.get("state"):
            look(ev["state"])
        elif kind == "action":
            s = ev.get("s") or {}
            result = ev.get("result")
            if ev.get("tool") == "buy" and isinstance(result, dict):
                for b in result.get("bought") or ():
                    sheet["bought"].append({"name": b.get("name"), "price": b.get("price"),
                                            "turn": s.get("turn")})
            if s.get("lvl") is not None and s["lvl"] != level:
                level = s["lvl"]
                if sheet["cure"] is not None:
                    sheet["home"].append({"level": level_name(level), "turn": s.get("turn")})
    return sheet


def sheet_lines(sheet):
    """A run sheet as Markdown: a table of stages, then the lists."""
    if not sheet["stages"]:
        return ["_Nothing recorded._"]
    lines = ["| First on | Turn | Char level | HP | AC | WC | Gold | Spells | Wearing and wielding |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in sheet["stages"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s["level"], s["turn"], s["cl"], s["hp"], s["ac"], s["wc"], s["gold"], s["spells"],
            _cell(", ".join(s["kit"]) or "nothing")))
    lines.append("")
    if sheet["bought"]:
        trips = []                        # one entry per visit to the store
        for b in sheet["bought"]:
            if not trips or trips[-1]["turn"] != b["turn"]:
                trips.append({"turn": b["turn"], "names": [], "gold": 0})
            trips[-1]["names"].append(b["name"])
            trips[-1]["gold"] += b["price"] or 0
        said = []
        for t in trips:
            names = []
            for name in dict.fromkeys(t["names"]):
                n = t["names"].count(name)
                names.append(name if n == 1 else "%d × %s" % (n, name))
            said.append("turn %s: %s (%s gold)" % (t["turn"], ", ".join(names), t["gold"]))
        lines.append("- Bought: " + "; ".join(said))
    learned = [s for s in sheet["spells"] if s["turn"]]
    if learned:
        lines.append("- Spells learned: " + "; ".join(
            "%s by turn %s" % (s["spell"], s["turn"]) for s in learned))
    if sheet["cure"]:
        lines.append("- The cure was in the pack by turn %s, on level %s." % (
            sheet["cure"]["turn"], sheet["cure"]["level"]))
        if sheet["home"]:
            lines.append("- After that: " + " → ".join(
                "%s (turn %s)" % (h["level"], h["turn"]) for h in sheet["home"]))
    return lines


def _behind(mine, model):
    """In what a stage falls short of the model's, as text; empty if it keeps pace."""
    short = []
    if (mine["cl"] or 0) < (model["cl"] or 0) - 1:
        short.append("character level %s against %s" % (mine["cl"], model["cl"]))
    if (mine["hp"] or 0) < 0.8 * (model["hp"] or 0):
        short.append("%s HP against %s" % (mine["hp"], model["hp"]))
    if (mine["ac"] or 0) < (model["ac"] or 0) - 2:
        short.append("AC %s against %s" % (mine["ac"], model["ac"]))
    if (mine["wc"] or 0) < (model["wc"] or 0) - 4:
        short.append("WC %s against %s" % (mine["wc"], model["wc"]))
    return ", ".join(short)


def compare_sheets(model, mine):
    """A game set beside the game it was meant to follow, level by level,
    and the first place it fell behind.  Returns lines of Markdown."""
    by_level = {s["level"]: s for s in mine["stages"]}

    def cell(s):
        return "turn %s: level %s, %s HP, AC %s, WC %s" % (
            s["turn"], s["cl"], s["hp"], s["ac"], s["wc"]) if s else "never reached"

    stages = [s for s in model["stages"] if s["level"] != "H"]
    lines = ["| First on | The game that won | This game |", "|---|---|---|"]
    lines += ["| %s | %s | %s |" % (s["level"], cell(s), cell(by_level.get(s["level"]))) for s in stages]
    verdict = None
    for s in stages:
        got = by_level.get(s["level"])
        if got is None:
            verdict = ("It never reached level %s, which the winner entered on turn %s at "
                       "character level %s with %s HP, AC %s and WC %s."
                       % (s["level"], s["turn"], s["cl"], s["hp"], s["ac"], s["wc"]))
            break
        short = _behind(got, s)
        if short:
            verdict = "It first fell behind the winner on arriving at level %s: %s." % (
                s["level"], short)
            break
    if verdict is None:
        verdict = "It kept pace with the winner on arriving at every level."
        if model["cure"] and not mine["cure"]:
            verdict += " It never held the cure, which the winner had by turn %s." % model["cure"]["turn"]
        elif model["cure"] and mine["cure"]:
            verdict += " It had the cure by turn %s (the winner by turn %s)." % (
                mine["cure"]["turn"], model["cure"]["turn"])
    return lines + ["", verdict]


def deepest_text(outcome):
    deep = (outcome or {}).get("deepest") or {}
    parts = []
    if deep.get("dungeon"):
        parts.append(str(deep["dungeon"]))
    if deep.get("volcano"):
        parts.append("V%d" % deep["volcano"])
    return " + ".join(parts) or "town"


def headline(meta):
    """One line saying how the run ended."""
    out = meta.get("outcome")
    if not out:
        return "In progress"
    text = RESULT_WORDS.get(out.get("result"), str(out.get("result")))
    if out.get("reason") and out.get("result") not in ("won", "stopped"):
        text += ": " + out["reason"]
    if out.get("result") != "won" and out.get("dungeon_level") is not None:
        where = out["dungeon_level"]
        text += " in town" if where == "H" else " on level %s" % where
    if out.get("turns") is not None:
        text += ", turn %s" % out["turns"]
    return text


# ====================================================================== summary

def _bullets(items, empty="_None recorded._"):
    items = [str(i).strip() for i in items or () if str(i).strip()]
    return "\n".join("- " + i for i in items) if items else empty


def render_summary(meta, events):
    d = digest(events)
    out = meta.get("outcome") or {}
    notes = meta.get("notes") or {}
    lines = ["# Run %s" % meta.get("run_id"), "", "**%s**" % headline(meta), ""]

    lines += ["| | |", "|---|---|"]
    rows = [("Class", meta.get("character_class")), ("Difficulty", meta.get("difficulty")),
            ("Seed", meta.get("seed")), ("Strategy", meta.get("strategy") or "none given"),
            ("Started", meta.get("started")), ("Actions", meta.get("actions"))]
    if out:
        prog = meta.get("progress") or {}
        rows += [("Progress", "%s (%s)" % (prog.get("milestone"), prog.get("score")) if prog else None),
                 ("Game score", out.get("score")), ("Deepest level", deepest_text(out)),
                 ("Character level", out.get("character_level")),
                 ("Time left", "%s mobuls" % out.get("mobuls_left"))]
    lines += ["| %s | %s |" % (k, "" if v is None else v) for k, v in rows]

    lines += ["", "## Hypotheses under test", "",
              _bullets(meta.get("hypotheses"), "_None given._")]

    lines += ["", "## Post-mortem", ""]
    if notes:
        if notes.get("takeaway"):
            lines += ["**In one line:** " + notes["takeaway"], ""]
        lines += [notes.get("synopsis") or "_No synopsis._", "",
                  "### What went wrong", "", _bullets(notes.get("went_wrong")), "",
                  "### What worked", "", _bullets(notes.get("worked")), "",
                  "### The next run will try", "", _bullets(notes.get("next_try"))]
    else:
        lines.append("_Not written yet: the agent adds it with the `summarize_run` tool._")

    lines += ["", "## What happened", "", "Worked out from the event log.", ""]
    if d["levels"]:
        lines.append("- Route: " + " → ".join(
            "%s (turn %s)" % (level_name(s["level"]), s["turn"]) for s in d["levels"]))
    if d["level_ups"]:
        last = d["level_ups"][-1]
        lines.append("- Character level: reached %s at turn %s" % (last["level"], last["turn"]))
    low = d["lowest_hp"]
    if low and low["hp"] < low["hpmax"]:
        lines.append("- Lowest HP: %s of %s at turn %s on level %s" % (
            low["hp"], low["hpmax"], low["turn"], level_name(low["level"])))
    final = d["final_state"] or {}
    stats = final.get("stats") or {}
    if stats:
        lines.append("- At the end: HP %s of %s, AC %s, WC %s, %s gold, %s in the bank" % (
            stats.get("hp"), stats.get("hp_max"), stats.get("ac"), stats.get("wc"),
            stats.get("gold"), stats.get("bank")))
    if final.get("monsters"):
        lines.append("- Monsters in view at the end: " + ", ".join(
            "%s (%s away)" % (m.get("name"), m.get("distance")) for m in final["monsters"][:8]))
    if final.get("effects"):
        lines.append("- Active effects at the end: " + ", ".join(final["effects"]))
    if final.get("known_spells"):
        lines.append("- Spells known: " + ", ".join(final["known_spells"]))
    sheet = run_sheet(events)
    if len(sheet["stages"]) > 1:
        lines += ["", "### Run sheet", "",
                  "What the character was on first reaching each level, for setting one game "
                  "beside another.", ""] + sheet_lines(sheet)
    if final.get("inventory"):
        lines += ["", "### Final inventory", "", _bullets(final["inventory"])]

    if d["errors"]:
        worst = sorted(d["errors"].items(), key=lambda kv: (-kv[1], kv[0]))
        lines += ["", "### Calls the server refused", "",
                  "%d in all; the game did not move for these." % sum(d["errors"].values()), "",
                  _bullets("%d× `%s`: %s" % (n, tool, text[:200]) for (tool, text), n in worst[:8])]

    if d["thoughts"]:
        lines += ["", "### Last thoughts", "",
                  _bullets("turn %s: %s" % (t["turn"], t["text"]) for t in d["thoughts"][-8:])]
    if d["final_screen"]:
        lines += ["", "### Final screen", "", "```", d["final_screen"].rstrip(), "```"]
    return "\n".join(lines) + "\n"


def write_summary(path):
    """(Re)write summary.md for the run in `path`; returns its text."""
    meta = load_meta(path)
    meta.setdefault("run_id", os.path.basename(path))
    text = render_summary(meta, read_events(path))
    _write_text(os.path.join(path, "summary.md"), text)
    return text


def set_notes(path, synopsis, went_wrong=(), worked=(), next_try=(), takeaway=None):
    """Store the agent's post-mortem in meta.json and rebuild summary.md."""
    meta = load_meta(path)
    meta["notes"] = {"takeaway": _clip(takeaway or "") or None,
                     "synopsis": str(synopsis).strip(),
                     "went_wrong": [str(i).strip() for i in went_wrong or ()],
                     "worked": [str(i).strip() for i in worked or ()],
                     "next_try": [str(i).strip() for i in next_try or ()]}
    save_meta(path, meta)
    return write_summary(path)


TAKEAWAY_MAX = 200   # characters in a game's one-line takeaway


def _clip(text, limit=TAKEAWAY_MAX):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def takeaway(meta):
    """A game in one line: the takeaway its post-mortem gave, or, for games
    written up before there was one, the first thing that went wrong."""
    notes = meta.get("notes") or {}
    if notes.get("takeaway"):
        return _clip(notes["takeaway"])
    wrong = notes.get("went_wrong") or []
    return _clip(wrong[0] if wrong else notes.get("synopsis") or "No post-mortem written.")


# ====================================================================== index

def brief(meta, full=True):
    """The few fields of a run worth showing in a list.  Without `full`,
    the post-mortem is cut down to its one-line takeaway."""
    out = meta.get("outcome") or {}
    notes = meta.get("notes") or {}
    b = {
        "run_id": meta.get("run_id"), "started": meta.get("started"),
        "character_class": meta.get("character_class"), "difficulty": meta.get("difficulty"),
        "seed": meta.get("seed"), "strategy": meta.get("strategy"),
        "result": out.get("result") or "in progress", "headline": headline(meta),
        "deepest": deepest_text(out) if out else None,
        "turns": out.get("turns"), "score": out.get("score"),
        "progress": meta.get("progress"),
        "takeaway": takeaway(meta) if notes else None,
    }
    if full:
        b.update(hypotheses=meta.get("hypotheses") or [], synopsis=notes.get("synopsis"),
                 next_try=notes.get("next_try") or [])
    return b


def _cell(value):
    return "" if value is None else str(value).replace("|", "/").replace("\n", " ")


def render_index(runs):
    lines = ["# Runs", ""]
    if not runs:
        return "\n".join(lines + ["No runs recorded yet."]) + "\n"

    by_diff = {}
    for m in runs:
        by_diff.setdefault(m.get("difficulty"), []).append(m)
    lines += ["| Difficulty | Runs | Wins | Deepest |", "|---|---|---|---|"]
    for diff in sorted(by_diff, key=lambda v: (v is None, v)):
        group = by_diff[diff]
        outs = [m.get("outcome") or {} for m in group]
        best = max(outs, key=lambda o: ((o.get("deepest") or {}).get("volcano", 0),
                                        (o.get("deepest") or {}).get("dungeon", 0)))
        lines.append("| %s | %d | %d | %s |" % (
            _cell(diff), len(group), sum(1 for o in outs if o.get("won")), deepest_text(best)))

    lines += ["", "Newest first.", "",
              "| Run | Class | Diff | Strategy | How it ended | Deepest | Progress | Next run will try |",
              "|---|---|---|---|---|---|---|---|"]
    for m in runs:
        b = brief(m)
        lines.append("| [%s](%s/summary.md) | %s | %s | %s | %s | %s | %s | %s |" % (
            b["run_id"], b["run_id"], _cell(b["character_class"]), _cell(b["difficulty"]),
            _cell(b["strategy"]), _cell(b["headline"]), _cell(b["deepest"]),
            _cell((b["progress"] or {}).get("score")), _cell("; ".join(b["next_try"]))))
    return "\n".join(lines) + "\n"


def write_index(root):
    """(Re)write INDEX.md for the runs in `root`."""
    _write_text(os.path.join(root, "INDEX.md"), render_index(list_runs(root)))


def finish_run(path):
    """Called when a recording closes: write its summary and refresh the index."""
    write_summary(path)
    write_index(os.path.dirname(path))


# ====================================================================== command

def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(prog="pyularn-runs",
                                 description="List and read the games recorded by pyularn-mcp --record.")
    ap.add_argument("--dir", default=os.environ.get("PYULARN_RECORD") or "runs",
                    help="the folder of recordings (default: $PYULARN_RECORD, else ./runs)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="list the runs, newest first (the default)")
    show = sub.add_parser("show", help="print one run's summary")
    show.add_argument("run_id")
    sub.add_parser("reindex", help="rebuild every summary.md and INDEX.md")
    args = ap.parse_args(argv)
    root = os.path.abspath(os.path.expanduser(args.dir))
    out = sys.stdout

    try:
        if args.cmd == "show":
            out.write(write_summary(run_dir(root, args.run_id)))
        elif args.cmd == "reindex":
            runs = list_runs(root)
            for m in runs:
                write_summary(os.path.join(root, m["run_id"]))
            write_index(root)
            out.write("Rebuilt %d summaries and %s\n" % (len(runs), os.path.join(root, "INDEX.md")))
        else:
            runs = list_runs(root)
            if not runs:
                out.write("No runs in %s\n" % root)
            for m in runs:
                b = brief(m)
                out.write("%-26s %-10s d%-3s %-18s %s\n" % (
                    b["run_id"], b["character_class"] or "?", _cell(b["difficulty"]),
                    (b["strategy"] or "-")[:18], b["headline"]))
    except RunError as e:
        sys.stderr.write("%s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
