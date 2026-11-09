"""What a series of games has learned: a playbook and a tree of strategies.

A campaign lives beside the recorded runs (see `pyularn.runs`)::

    DIR/campaign.json   the playbook's lessons and the strategy tree
    DIR/CAMPAIGN.md     the same, for people to read

The playbook holds lessons, each citing the runs that support it.  The
strategy tree holds the experiments: every strategy is its parent plus one
change, so the effect of that change can be judged by comparing the two.
How well a strategy does is never stored: it is worked out from the runs
recorded under its id, which stay the source of truth.

Each cycle of the loop is: read the briefing, play one game under the
strategy it names, write the post-mortem, then record lessons and, if
there is a specific idea to test, propose a new strategy.

Nothing here touches the game engine.
"""

import json
import os
import time

from . import runs

CAMPAIGN_FILE = "campaign.json"
COUNTED = ("died", "won", "quit")   # results that say something about a strategy
ROOT_ID = "S1"

GOAL = ("Win Ularn: find the potion of cure dianthroritis and bring it home "
        "before the time runs out.")


class LearnError(Exception):
    pass


# ====================================================================== progress

def progress(outcome):
    """How far a game got, as a number that can be compared between games.

    Wins are far too rare to learn from at first, so the score rewards the
    steps on the way: 1 point per dungeon level reached (15 at most), 2 per
    volcano level (10 at most), 10 for holding the cure and 30 for winning.
    The character's level adds up to half a point, to split ties.
    """
    out = outcome or {}
    deep = out.get("deepest") or {}
    d, v = deep.get("dungeon") or 0, deep.get("volcano") or 0
    score = d + 2 * v
    if out.get("has_cure") or out.get("won"):
        score += 10
    if out.get("won"):
        score += 30
    score += min(out.get("character_level") or 0, 20) / 40.0
    if out.get("won"):
        milestone = "won"
    elif out.get("has_cure"):
        milestone = "found the cure"
    elif v:
        milestone = "volcano level %d" % v
    elif d:
        milestone = "dungeon level %d" % d
    else:
        milestone = "never left town"
    return {"score": round(score, 3), "milestone": milestone}


# ====================================================================== storage

def _path(root):
    return os.path.join(root, CAMPAIGN_FILE)


def exists(root):
    return os.path.isfile(_path(root))


def new_campaign(difficulty=0):
    return {
        "version": 1, "goal": GOAL, "difficulty": difficulty,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "strategies": {ROOT_ID: {
            "id": ROOT_ID, "parent": None, "title": "Baseline",
            "change": "No fixed plan yet: play sensibly and see how far it gets.",
            "character_class": None, "status": "active", "note": None,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}},
        "current": ROOT_ID, "next_strategy": 2,
        "lessons": [], "next_lesson": 1,
    }


def load(root, create=True, difficulty=0):
    """The campaign in `root`.  With `create`, a missing one is started."""
    try:
        with open(_path(root), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if not create:
            raise LearnError("no campaign in %s yet" % root)
    os.makedirs(root, exist_ok=True)
    campaign = new_campaign(difficulty)
    save(root, campaign)
    return campaign


def save(root, campaign):
    runs._write_text(_path(root), json.dumps(campaign, indent=1) + "\n")
    runs._write_text(os.path.join(root, "CAMPAIGN.md"), render(root, campaign))


def refresh(root):
    """Rewrite CAMPAIGN.md after a run has been added or changed."""
    if exists(root):
        campaign = load(root)
        runs._write_text(os.path.join(root, "CAMPAIGN.md"), render(root, campaign))


# ====================================================================== strategies

def strategy(campaign, sid):
    try:
        return campaign["strategies"][sid]
    except (KeyError, TypeError):
        raise LearnError("no strategy called %r; the briefing lists them" % (sid,))


def lineage(campaign, sid):
    """The strategies from the root down to `sid`."""
    chain = []
    while sid is not None:
        s = strategy(campaign, sid)
        chain.append(s)
        sid = s["parent"]
    chain.reverse()
    return chain


def changes(campaign, sid):
    """Everything strategy `sid` does that the baseline does not, oldest
    first.  These are a game's hypotheses; the last one is the one on trial."""
    return [s["change"] for s in lineage(campaign, sid)[1:]]


def character_class(campaign, sid):
    for s in reversed(lineage(campaign, sid)):
        if s.get("character_class"):
            return s["character_class"]
    return None


def children(campaign, sid):
    return [s for s in campaign["strategies"].values() if s["parent"] == sid]


def propose(root, title, change, parent=None, character_class=None):
    """Add a strategy that is `parent` (default: the current one) plus one
    change, and make it the one to play next."""
    title, change = str(title or "").strip(), str(change or "").strip()
    if not title or not change:
        raise LearnError("a strategy needs a title and the one change it makes")
    campaign = load(root)
    parent = parent or campaign["current"]
    strategy(campaign, parent)
    for s in children(campaign, parent):
        if s["change"].lower() == change.lower():
            raise LearnError("%s already tests that change" % s["id"])
    sid = "S%d" % campaign["next_strategy"]
    campaign["next_strategy"] += 1
    campaign["strategies"][sid] = {
        "id": sid, "parent": parent, "title": title[:80], "change": change,
        "character_class": character_class or None, "status": "active", "note": None,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    campaign["current"] = sid
    save(root, campaign)
    return campaign["strategies"][sid]


def stats(campaign, all_runs):
    """Results per strategy at the campaign's difficulty, from the runs."""
    out = {sid: {"runs": 0, "wins": 0, "scores": [], "best": None, "run_ids": []}
           for sid in campaign["strategies"]}
    for meta in reversed(all_runs):                       # oldest first
        st = out.get(meta.get("strategy"))
        outcome = meta.get("outcome") or {}
        if st is None or outcome.get("result") not in COUNTED:
            continue
        if meta.get("difficulty") != campaign["difficulty"]:
            continue
        p = meta.get("progress") or progress(outcome)
        st["runs"] += 1
        st["wins"] += 1 if outcome.get("won") else 0
        st["scores"].append(p["score"])
        st["run_ids"].append(meta.get("run_id"))
        if st["best"] is None or p["score"] > st["best"]["score"]:
            st["best"] = p
    for st in out.values():
        st["mean"] = round(sum(st["scores"]) / len(st["scores"]), 2) if st["scores"] else None
    return out


def choose_next(campaign, strategy_stats):
    """The strategy the next game should play."""
    return campaign["current"]


# ====================================================================== lessons

CONFIDENCE = ("confirmed", "tentative")


def add_lesson(root, text, evidence=(), confidence="tentative"):
    text = str(text or "").strip()
    if not text:
        raise LearnError("the lesson is empty")
    if confidence not in CONFIDENCE:
        raise LearnError("confidence must be confirmed or tentative")
    evidence = [str(e) for e in evidence or ()]
    known = {m["run_id"] for m in runs.list_runs(root)}
    unknown = [e for e in evidence if e not in known]
    if unknown:
        raise LearnError("no such run: " + ", ".join(unknown))
    if confidence == "confirmed" and not evidence:
        raise LearnError("a confirmed lesson must cite the runs that showed it")
    campaign = load(root)
    for lesson in campaign["lessons"]:
        if lesson["status"] != "retracted" and lesson["text"].lower() == text.lower():
            # The same lesson again: add the new evidence to it.
            lesson["evidence"] = sorted(set(lesson["evidence"]) | set(evidence))
            if confidence == "confirmed":
                lesson["status"] = "confirmed"
            save(root, campaign)
            return lesson
    lesson = {"id": "L%d" % campaign["next_lesson"], "text": text, "evidence": evidence,
              "status": confidence, "note": None,
              "added": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    campaign["next_lesson"] += 1
    campaign["lessons"].append(lesson)
    save(root, campaign)
    return lesson


def retract_lesson(root, lesson_id, reason):
    reason = str(reason or "").strip()
    if not reason:
        raise LearnError("say why the lesson is wrong")
    campaign = load(root)
    for lesson in campaign["lessons"]:
        if lesson["id"] == lesson_id:
            lesson["status"] = "retracted"
            lesson["note"] = reason
            save(root, campaign)
            return lesson
    raise LearnError("no lesson called %r" % (lesson_id,))


# ====================================================================== reading

def _stat_text(st):
    if not st or not st["runs"]:
        return "not played yet"
    text = "%d game%s, average progress %s, best: %s" % (
        st["runs"], "" if st["runs"] == 1 else "s", st["mean"], st["best"]["milestone"])
    if st["wins"]:
        text += ", %d won" % st["wins"]
    return text


def _tree_lines(campaign, strategy_stats, mark):
    lines = []

    def walk(sid, depth):
        s = campaign["strategies"][sid]
        line = "%s- **%s %s**: %s" % ("  " * depth, sid, s["title"], _stat_text(strategy_stats.get(sid)))
        if s["status"] != "active":
            line += " [%s%s]" % (s["status"], ": " + s["note"] if s.get("note") else "")
        if sid == mark:
            line += " ← play this next"
        lines.append(line)
        if s["parent"] is not None:
            lines.append("%s  Change: %s" % ("  " * depth, s["change"]))
        for child in sorted(children(campaign, sid), key=lambda c: int(c["id"][1:])):
            walk(child["id"], depth + 1)

    walk(ROOT_ID, 0)
    return lines


def _lesson_lines(campaign, status):
    return ["- %s: %s%s" % (l["id"], l["text"],
                           " (runs: %s)" % ", ".join(l["evidence"]) if l["evidence"] else "")
            for l in campaign["lessons"] if l["status"] == status]


def render(root, campaign=None):
    """CAMPAIGN.md: the playbook and the strategy tree, for people."""
    campaign = campaign or load(root)
    all_runs = runs.list_runs(root)
    st = stats(campaign, all_runs)
    lines = ["# Campaign", "", campaign["goal"], "",
             "Difficulty %s. %d games recorded." % (campaign["difficulty"], len(all_runs)), "",
             "## Playbook", "", "### Confirmed", ""]
    lines += _lesson_lines(campaign, "confirmed") or ["_Nothing confirmed yet._"]
    lines += ["", "### Tentative", ""]
    lines += _lesson_lines(campaign, "tentative") or ["_None._"]
    retracted = [l for l in campaign["lessons"] if l["status"] == "retracted"]
    if retracted:
        lines += ["", "### Retracted", ""]
        lines += ["- %s: ~~%s~~ %s" % (l["id"], l["text"], l.get("note") or "") for l in retracted]
    lines += ["", "## Strategies", "",
              "Each strategy is its parent plus one change. Progress is scored as "
              "1 per dungeon level, 2 per volcano level, 10 for the cure, 30 for a win.", ""]
    lines += _tree_lines(campaign, st, choose_next(campaign, st))
    return "\n".join(lines) + "\n"


CYCLE_STEPS = """\
## Your cycle

1. Start the game: `new_game` with `strategy` set to the id above. The
   strategy's hypotheses, class and the campaign's difficulty are filled in
   for you; do not override them.
2. Play to win, following the strategy and the playbook. Use the skill
   tools (`explore`, `travel_to`, `take_stairs`, `fight`, `flee`, `buy`) and
   `get_state`; use `send_keys` for spells, potions, scrolls and prompts.
   Keep playing until the game is over. Do not quit a game that can go on.
3. When it is over, call `summarize_run`. Be exact about what went wrong:
   name the monster, the level, the HP and the decision you would change.
4. Call `add_lesson` for anything this game showed. Cite the run. Use
   `confirmed` only when more than one run agrees; otherwise `tentative`.
   If a lesson in the playbook turned out wrong, call `retract_lesson`.
5. If you have one specific change that should do better, call
   `propose_strategy` with it. One change at a time, so its effect can be
   seen. Otherwise leave the strategy as it is: it needs more games.
"""


def briefing(root):
    """What an agent should read before a game: the strategy to play, the
    playbook, the tree and how the latest games went."""
    campaign = load(root)
    all_runs = runs.list_runs(root)
    st = stats(campaign, all_runs)
    sid = choose_next(campaign, st)
    s = strategy(campaign, sid)
    lines = ["# Briefing", "", campaign["goal"], "",
             "Difficulty %s. %d games recorded so far." % (campaign["difficulty"], len(all_runs)),
             "", "## Play this strategy: %s %s" % (sid, s["title"]), "",
             "Game %d under this strategy (%s)." % (st[sid]["runs"] + 1, _stat_text(st[sid])), ""]
    cls = character_class(campaign, sid)
    lines.append("Character class: %s." % (cls or "your choice; say why in the post-mortem"))
    todo = changes(campaign, sid)
    if todo:
        lines += ["", "What it does differently from the baseline:", ""]
        lines += ["- " + c for c in todo[:-1]]
        lines.append("- %s **(the change on trial)**" % todo[-1])
    else:
        lines += ["", s["change"]]

    lines += ["", "## Playbook", ""]
    confirmed, tentative = _lesson_lines(campaign, "confirmed"), _lesson_lines(campaign, "tentative")
    if confirmed:
        lines += ["Confirmed, follow these:", ""] + confirmed + [""]
    if tentative:
        lines += ["Tentative, seen once:", ""] + tentative + [""]
    if not confirmed and not tentative:
        lines += ["_Empty: this is one of the first games._", ""]

    lines += ["## Strategies tried", ""] + _tree_lines(campaign, st, sid)

    done = [m for m in all_runs if m.get("outcome")][:5]
    if done:
        lines += ["", "## Latest games", ""]
        for m in done:
            b = runs.brief(m)
            lines.append("- %s (%s): %s; got to: %s" % (
                b["run_id"], b["strategy"] or "no strategy", b["headline"],
                (m.get("progress") or progress(m["outcome"]))["milestone"]))
            notes = m.get("notes") or {}
            for label, key in (("went wrong", "went_wrong"), ("next time", "next_try")):
                if notes.get(key):
                    lines.append("  - %s: %s" % (label, "; ".join(notes[key][:3])))
        lines.append("")
        lines.append("`get_run` gives any of these in full.")
    lines += ["", CYCLE_STEPS]
    return "\n".join(lines)
