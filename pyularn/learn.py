"""What a series of games has learned: a playbook and a tree of strategies.

A campaign lives beside the recorded runs (see `pyularn.runs`)::

    DIR/campaign.json   the playbook's lessons, the strategy tree, the rules
    DIR/CAMPAIGN.md     the same, for people to read

The playbook holds lessons, each citing the runs that support it.  The
strategy tree holds the experiments: every strategy is a proven strategy
plus one change, so the effect of that change can be judged by comparing
the two.  How well a strategy does is never stored: it is worked out from
the runs recorded under its id, which stay the source of truth.

Trying, keeping and backing out of strategies
---------------------------------------------
One game says little: a roguelike death is mostly luck.  So a new strategy
is on *trial* for a fixed number of games (`budget`), on a fixed list of
seeds that its parent played too, and is then judged by `advance()`:

* It is *proven*, and becomes the base that new ideas build on, if its
  average progress beats its parent's by `margin`, and then still matches
  the parent on seeds no strategy has played before (`holdout`).  The second
  test is there because fixed seeds can be learned by heart.
* Otherwise it is *abandoned*, with the numbers, and stays on record so it
  is not proposed again.  Play goes back to the base for the next idea.
* If `patience` ideas in a row fail on top of a proven strategy, that line
  has *stalled*: the base steps back to the strategy it grew from, and the
  next idea branches off from there instead.

The difficulty ladder
---------------------
A campaign plays one difficulty at a time.  When `wins` of its latest
`window` games there were won, it moves up one, until `top` is cleared.
The playbook, the tree and the base carry over; the results do not, since
games are only ever compared within one difficulty (see `_climb`).

Each cycle of the loop is: read the briefing, play one game under the
strategy it names, write the post-mortem, then record lessons and, if
there is a specific idea to test, propose a new strategy.

Nothing here touches the game engine.
"""

import json
import os
import random
import time

from . import runs

CAMPAIGN_FILE = "campaign.json"
COUNTED = ("died", "won", "quit")   # results that say something about a strategy
ROOT_ID = "S1"
SOLID = ("proven", "stalled")       # strategies a new idea may build on

DEFAULT_RULES = {
    "budget": 5,      # games in a trial
    "margin": 1.0,    # progress points a strategy must beat its parent by
    "holdout": 3,     # games on unseen seeds before a strategy is proven
    "patience": 3,    # failed ideas in a row before a line has stalled
    "window": 5,      # the ladder looks at this many of the latest games...
    "wins": 3,        # ...and moves up a difficulty when this many were won
    "top": 5,         # the difficulty at which the campaign is complete
}

GOAL = ("Win Ularn: find the potion of cure dianthroritis and bring it home "
        "before the time runs out.")


class LearnError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


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


def _check_rules(rules):
    out = dict(DEFAULT_RULES)
    for key, value in (rules or {}).items():
        if key not in DEFAULT_RULES:
            raise LearnError("unknown rule %r" % key)
        if value is not None:
            out[key] = value
    if out["budget"] < 1 or out["holdout"] < 0 or out["patience"] < 1 or out["margin"] < 0:
        raise LearnError("rules: budget and patience are at least 1; margin and holdout at least 0")
    if not 1 <= out["wins"] <= out["window"]:
        raise LearnError("rules: wins is at least 1 and at most window")
    if not 0 <= out["top"] <= 100:
        raise LearnError("rules: top is a difficulty, 0 to 100")
    return out


def _seeds(n, taken=()):
    rng = random.SystemRandom()
    seeds = []
    while len(seeds) < n:
        s = rng.randrange(1, 2 ** 31)
        if s not in seeds and s not in taken:
            seeds.append(s)
    return seeds


def new_campaign(difficulty=0, rules=None):
    rules = _check_rules(rules)
    if difficulty > rules["top"]:
        raise LearnError("the campaign starts at difficulty %d, above its top of %d"
                         % (difficulty, rules["top"]))
    trial = _seeds(rules["budget"])
    return {
        "version": 2, "goal": GOAL, "difficulty": difficulty, "created": _now(),
        "rules": rules,
        # Every strategy plays the same seeds, so two strategies are compared
        # on the same dungeons.  The hold-out seeds are played only by a
        # strategy that has passed its trial.
        "seeds": {"trial": trial, "holdout": _seeds(rules["holdout"], trial)},
        "strategies": {ROOT_ID: {
            "id": ROOT_ID, "parent": None, "title": "Baseline",
            "change": "No fixed plan yet: play sensibly and see how far it gets.",
            "character_class": None, "status": "proven", "note": None, "created": _now()}},
        "base": ROOT_ID, "next_strategy": 2,
        "lessons": [], "next_lesson": 1,
        "log": [],
        "cleared": [],        # one entry per difficulty the ladder has moved past
        "complete": False,    # True once the top difficulty is cleared
    }


def _upgrade(campaign):
    """Bring a campaign written before trials existed up to date."""
    if campaign.get("version", 1) >= 2:
        return False
    rules = _check_rules(None)
    trial = _seeds(rules["budget"])
    campaign.update(version=2, rules=rules, base=ROOT_ID, log=[],
                    seeds={"trial": trial, "holdout": _seeds(rules["holdout"], trial)})
    campaign.pop("current", None)
    for s in campaign["strategies"].values():
        s["status"] = "proven" if s["parent"] is None else "trial"
        if s["parent"] is not None:
            s["parent"] = ROOT_ID   # trials are judged against a proven strategy
    return True


def load(root, create=True, difficulty=0, rules=None, judge=True):
    """The campaign in `root`, with any strategy whose trial is complete
    judged first.  With `create`, a missing campaign is started."""
    try:
        with open(_path(root), encoding="utf-8") as f:
            campaign = json.load(f)
    except FileNotFoundError:
        if not create:
            raise LearnError("no campaign in %s yet" % root)
        os.makedirs(root, exist_ok=True)
        campaign = new_campaign(difficulty, rules)
        save(root, campaign)
        return campaign
    changed = _upgrade(campaign)
    for key, value in DEFAULT_RULES.items():       # rules added since it was written
        if key not in campaign["rules"]:
            campaign["rules"][key] = max(value, campaign["difficulty"]) if key == "top" else value
            changed = True
    if "cleared" not in campaign:
        campaign.update(cleared=[], complete=False)
        changed = True
    if judge and advance(campaign, runs.list_runs(root)):
        changed = True
    if changed:
        save(root, campaign)
    return campaign


def save(root, campaign):
    runs._write_text(_path(root), json.dumps(campaign, indent=1) + "\n")
    runs._write_text(os.path.join(root, "CAMPAIGN.md"), render(root, campaign))


def refresh(root):
    """Judge and rewrite CAMPAIGN.md after a run has been added or changed."""
    if exists(root):
        campaign = load(root)
        runs._write_text(os.path.join(root, "CAMPAIGN.md"), render(root, campaign))


# ====================================================================== strategies

def strategy(campaign, sid):
    try:
        return campaign["strategies"][sid]
    except (KeyError, TypeError):
        raise LearnError("no strategy called %r; the briefing lists them" % (sid,))


def _number(s):
    return int(s["id"][1:])


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
    return sorted((s for s in campaign["strategies"].values() if s["parent"] == sid), key=_number)


def propose(root, title, change, parent=None, character_class=None, retry_reason=None):
    """Put a new strategy on trial: a proven strategy (default: the current
    base) plus one change.  An idea that was already abandoned is refused
    unless `retry_reason` says what is different this time."""
    title, change = str(title or "").strip(), str(change or "").strip()
    retry_reason = str(retry_reason or "").strip()
    if not title or not change:
        raise LearnError("a strategy needs a title and the one change it makes")
    campaign = load(root)
    parent = parent or campaign["base"]
    p = strategy(campaign, parent)
    if p["status"] not in SOLID:
        raise LearnError("%s is %s, so nothing can be built on it yet; build on %s"
                         % (parent, "still on trial" if p["status"] != "abandoned" else "abandoned",
                            campaign["base"]))
    for s in campaign["strategies"].values():
        if s["change"].lower() != change.lower():
            continue
        if s["status"] == "abandoned" and not retry_reason:
            raise LearnError("%s already tried that and was abandoned: %s. Propose something "
                             "else, or give retry_reason if things have changed."
                             % (s["id"], s.get("note")))
        if s["status"] != "abandoned" and s["parent"] == parent:
            raise LearnError("%s already tests that change" % s["id"])
    sid = "S%d" % campaign["next_strategy"]
    campaign["next_strategy"] += 1
    campaign["strategies"][sid] = {
        "id": sid, "parent": parent, "title": title[:80], "change": change,
        "character_class": character_class or None, "status": "trial", "note": None,
        "retry_reason": retry_reason or None, "created": _now()}
    save(root, campaign)
    return campaign["strategies"][sid]


def stats(campaign, all_runs):
    """Results per strategy at the campaign's difficulty, from the runs.

    "trial" and "holdout" map a seed to the progress score of the first
    finished game the strategy played on it; those are what it is judged
    on.  "runs", "mean" and "best" cover every finished game.
    """
    trial_seeds = set(campaign["seeds"]["trial"])
    holdout_seeds = set(campaign["seeds"]["holdout"])
    out = {sid: {"runs": 0, "wins": 0, "scores": [], "best": None, "run_ids": [],
                 "trial": {}, "holdout": {}}
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
        seed = meta.get("seed")
        if seed in trial_seeds:
            st["trial"].setdefault(seed, p["score"])
        elif seed in holdout_seeds:
            st["holdout"].setdefault(seed, p["score"])
    for st in out.values():
        st["mean"] = _mean(st["scores"])
        st["trial_mean"] = _mean(st["trial"].values())
        st["holdout_mean"] = _mean(st["holdout"].values())
    return out


def _mean(values):
    values = list(values)
    return round(sum(values) / len(values), 2) if values else None


def next_seed(campaign, sid, strategy_stats):
    """The seed the strategy's next game should use, or None for any."""
    st = strategy_stats[sid]
    which = "holdout" if strategy(campaign, sid)["status"] == "holdout" else "trial"
    for seed in campaign["seeds"][which]:
        if seed not in st[which]:
            return seed
    return None


# ====================================================================== judging

def _log(campaign, text):
    campaign["log"].append({"when": _now(), "text": text})


def _abandon(campaign, s, why):
    s["status"] = "abandoned"
    s["note"] = why
    _log(campaign, "%s %s abandoned: %s." % (s["id"], s["title"], why))


def _prove(campaign, s, st, why):
    s["status"] = "proven"
    s["note"] = why
    base = campaign["base"]
    if s["parent"] == base or (st[s["id"]]["trial_mean"] or 0) >= (st[base]["trial_mean"] or 0):
        campaign["base"] = s["id"]
        why += "; it is the new base"
    _log(campaign, "%s %s proven: %s." % (s["id"], s["title"], why))


def advance(campaign, all_runs):
    """Judge every strategy whose games are in, and step back from a line
    that has stalled.  Changes `campaign`; returns True if anything changed."""
    rules = campaign["rules"]
    changed = False
    while True:
        st = stats(campaign, all_runs)
        step = False
        for s in sorted(campaign["strategies"].values(), key=_number):
            if s["status"] not in ("trial", "holdout"):
                continue
            parent = campaign["strategies"][s["parent"]]
            mine, theirs = st[s["id"]], st[parent["id"]]
            if parent["status"] == "abandoned":
                _abandon(campaign, s, "its parent %s was abandoned" % parent["id"])
                step = True
            elif len(theirs["trial"]) < rules["budget"]:
                continue                     # the parent has not been measured yet
            elif s["status"] == "trial":
                if len(mine["trial"]) < rules["budget"]:
                    continue
                need = round(theirs["trial_mean"] + rules["margin"], 2)
                numbers = "averaged %s over %d games, %s averaged %s" % (
                    mine["trial_mean"], len(mine["trial"]), parent["id"], theirs["trial_mean"])
                if mine["trial_mean"] < need:
                    _abandon(campaign, s, "%s and it needed %s" % (numbers, need))
                elif rules["holdout"]:
                    s["status"] = "holdout"
                    _log(campaign, "%s %s passed its trial (%s). Checking it on %d unseen seeds."
                         % (s["id"], s["title"], numbers, rules["holdout"]))
                else:
                    _prove(campaign, s, st, numbers)
                step = True
            elif len(mine["holdout"]) >= rules["holdout"]:
                numbers = "averaged %s on %d unseen seeds, %s averaged %s on the trial seeds" % (
                    mine["holdout_mean"], len(mine["holdout"]), parent["id"], theirs["trial_mean"])
                if mine["holdout_mean"] >= theirs["trial_mean"]:
                    _prove(campaign, s, st, "trial average %s; %s" % (mine["trial_mean"], numbers))
                else:
                    _abandon(campaign, s, "passed its trial but did not hold up: " + numbers)
                step = True
        if not step:
            step = _step_back(campaign)
        if not step:
            step = _climb(campaign, all_runs)
        if not step:
            return changed
        changed = True


def ladder(campaign, all_runs):
    """Where the campaign stands on its current difficulty: the latest
    `window` finished games there, and how many of them were won."""
    rules = campaign["rules"]
    here = [m for m in all_runs
            if (m.get("outcome") or {}).get("result") in COUNTED
            and m.get("difficulty") == campaign["difficulty"]
            and m.get("strategy") in campaign["strategies"]]
    recent = here[:rules["window"]]
    return {"difficulty": campaign["difficulty"], "top": rules["top"],
            "games": len(here), "total_wins": sum(1 for m in here if m["outcome"].get("won")),
            "recent_wins": sum(1 for m in recent if m["outcome"].get("won")),
            "wins": rules["wins"], "window": rules["window"]}


def _climb(campaign, all_runs):
    """Move up a difficulty once enough of the latest games here were won.

    Everything learned carries over: the playbook, the strategy tree and
    the base.  What does not carry over is the evidence.  Results are only
    ever compared within one difficulty, so the base is measured again on
    fresh seeds, strategies that were mid-trial start their trials again,
    and a stalled line gets another chance.  Ideas abandoned at the easier
    difficulty stay abandoned unless proposed again with a reason.
    """
    if campaign["complete"]:
        return False
    rung = ladder(campaign, all_runs)
    if rung["recent_wins"] < rung["wins"]:
        return False
    rules, d = campaign["rules"], campaign["difficulty"]
    campaign["cleared"].append({
        "difficulty": d, "when": _now(), "base": campaign["base"],
        "games": rung["games"], "wins": rung["total_wins"], "seeds": campaign["seeds"]})
    won = "%d of the last %d games were won" % (rung["recent_wins"], min(rung["games"], rung["window"]))
    if d >= rules["top"]:
        campaign["complete"] = True
        _log(campaign, "Difficulty %d cleared: %s. That was the top of the ladder: the campaign "
             "is complete." % (d, won))
        return True
    campaign["difficulty"] = d + 1
    used = [s for c in campaign["cleared"] for group in c["seeds"].values() for s in group]
    trial = _seeds(rules["budget"], used)
    campaign["seeds"] = {"trial": trial, "holdout": _seeds(rules["holdout"], used + trial)}
    for s in campaign["strategies"].values():
        if s["status"] == "holdout":
            s["status"] = "trial"
        elif s["status"] == "stalled":
            s["status"] = "proven"
    _log(campaign, "Difficulty %d cleared: %s. Moving up to difficulty %d with %s as the base, "
         "to be measured again there on new seeds." % (d, won, d + 1, campaign["base"]))
    return True


def _step_back(campaign):
    """If the latest `patience` ideas built on the base all failed, the base
    has stalled: go back to the proven strategy it grew from."""
    base = campaign["strategies"][campaign["base"]]
    if base["parent"] is None:
        return False                          # nothing to go back to from the baseline
    kids = children(campaign, base["id"])
    recent = kids[-campaign["rules"]["patience"]:]
    if len(recent) < campaign["rules"]["patience"] or any(k["status"] != "abandoned" for k in recent):
        return False
    older = [s for s in lineage(campaign, base["id"])[:-1] if s["status"] == "proven"]
    if not older:
        return False
    base["status"] = "stalled"
    campaign["base"] = older[-1]["id"]
    _log(campaign, "%s %s has stalled: the last %d ideas built on it failed (%s). Stepping back "
         "to %s to branch off in another direction." % (
             base["id"], base["title"], len(recent), ", ".join(k["id"] for k in recent),
             campaign["base"]))
    return True


def choose_next(campaign, strategy_stats):
    """The strategy the next game should play: (id, reason, needs_proposal).

    Order: measure the base if it has not played its trial games; finish a
    hold-out check; finish the trial that is furthest along; otherwise play
    the base, and ask for a new idea.
    """
    rules = campaign["rules"]
    base = campaign["base"]
    if len(strategy_stats[base]["trial"]) < rules["budget"]:
        return base, "measuring the base, so later ideas have something to beat", False
    live = sorted(campaign["strategies"].values(), key=_number)
    for s in live:
        if s["status"] == "holdout":
            return s["id"], "it passed its trial; this checks it on unseen seeds", False
    trials = [s for s in live if s["status"] == "trial"
              and len(strategy_stats[s["parent"]]["trial"]) >= rules["budget"]]
    if trials:
        s = max(trials, key=lambda t: (t["parent"] == base, len(strategy_stats[t["id"]]["trial"]),
                                       -_number(t)))
        return s["id"], "on trial against %s" % s["parent"], False
    return base, "no idea is waiting to be tried", True


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
              "status": confidence, "note": None, "added": _now(),
              "difficulty": campaign["difficulty"]}
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

def _stat_text(campaign, s, st):
    rules = campaign["rules"]
    if not st["runs"]:
        return "not played yet"
    if s["status"] == "holdout":
        text = "trial average %s; %d of %d games on unseen seeds, average %s" % (
            st["trial_mean"], len(st["holdout"]), rules["holdout"], st["holdout_mean"])
    elif st["trial"]:
        text = "%d of %d trial games, average progress %s" % (
            min(len(st["trial"]), rules["budget"]), rules["budget"], st["trial_mean"])
    else:
        text = "%d game%s, average progress %s" % (st["runs"], "" if st["runs"] == 1 else "s", st["mean"])
    text += ", best: %s" % st["best"]["milestone"]
    if st["wins"]:
        text += ", %d won" % st["wins"]
    return text


STATUS_WORDS = {"trial": "on trial", "holdout": "passed its trial, being checked",
                "proven": "proven", "stalled": "stalled", "abandoned": "abandoned"}


def _tree_lines(campaign, strategy_stats, mark):
    lines = []

    def walk(sid, depth):
        s = campaign["strategies"][sid]
        tags = [STATUS_WORDS[s["status"]]]
        if sid == campaign["base"]:
            tags.append("the base")
        line = "%s- **%s %s** [%s]: %s" % ("  " * depth, sid, s["title"], ", ".join(tags),
                                           _stat_text(campaign, s, strategy_stats[sid]))
        if sid == mark:
            line += " ← play this next"
        lines.append(line)
        if s["parent"] is not None:
            lines.append("%s  Change: %s" % ("  " * depth, s["change"]))
        if s.get("note") and s["status"] in ("abandoned", "proven"):
            lines.append("%s  Verdict: %s" % ("  " * depth, s["note"]))
        for child in children(campaign, sid):
            walk(child["id"], depth + 1)

    walk(ROOT_ID, 0)
    return lines


def _lesson_lines(campaign, status):
    def learned_at(lesson):
        d = lesson.get("difficulty", campaign["difficulty"])
        return "" if d == campaign["difficulty"] else " [learned at difficulty %d]" % d

    return ["- %s: %s%s%s" % (l["id"], l["text"], learned_at(l),
                             " (runs: %s)" % ", ".join(l["evidence"]) if l["evidence"] else "")
            for l in campaign["lessons"] if l["status"] == status]


def _failed_lines(campaign):
    return ["- %s (%s, on top of %s): %s. Verdict: %s" % (
        s["change"], s["id"], s["parent"], s["title"], s.get("note"))
        for s in sorted(campaign["strategies"].values(), key=_number) if s["status"] == "abandoned"]


def _rules_text(campaign):
    r = campaign["rules"]
    text = ("A new strategy plays %d games on the same seeds as the strategy it builds on. "
            "It is kept if its average progress is at least %s higher" % (r["budget"], r["margin"]))
    if r["holdout"]:
        text += (", and it then does no worse than its parent's average over %d games on seeds "
                 "nobody has played" % r["holdout"])
    text += (". Otherwise it is abandoned. After %d failed ideas in a row on top of a proven "
             "strategy, the search steps back to the one before it." % r["patience"])
    return text


def _ladder_lines(campaign, all_runs):
    rung = ladder(campaign, all_runs)
    if campaign["complete"]:
        lines = ["**The campaign is complete: difficulty %d, the top of its ladder, is cleared.**"
                 % rung["top"]]
    else:
        lines = ["Difficulty %d, on a ladder that ends at %d. %d games played here, %d won. "
                 "The ladder moves up when %d of the latest %d games are won; so far %d are."
                 % (rung["difficulty"], rung["top"], rung["games"], rung["total_wins"],
                    rung["wins"], rung["window"], rung["recent_wins"])]
    for c in campaign["cleared"]:
        lines.append("- Difficulty %d cleared %s: %d wins in %d games, with %s as the base."
                     % (c["difficulty"], c["when"][:10], c["wins"], c["games"], c["base"]))
    return lines


def render(root, campaign=None):
    """CAMPAIGN.md: the playbook, the strategy tree and the decisions, for people."""
    campaign = campaign or load(root)
    all_runs = runs.list_runs(root)
    st = stats(campaign, all_runs)
    lines = ["# Campaign", "", campaign["goal"], "",
             "%d games recorded." % len(all_runs), ""]
    lines += _ladder_lines(campaign, all_runs)
    lines += ["", "## Playbook", "", "### Confirmed", ""]
    lines += _lesson_lines(campaign, "confirmed") or ["_Nothing confirmed yet._"]
    lines += ["", "### Tentative", ""]
    lines += _lesson_lines(campaign, "tentative") or ["_None._"]
    retracted = [l for l in campaign["lessons"] if l["status"] == "retracted"]
    if retracted:
        lines += ["", "### Retracted", ""]
        lines += ["- %s: ~~%s~~ %s" % (l["id"], l["text"], l.get("note") or "") for l in retracted]
    lines += ["", "## Strategies", "",
              "Each strategy is its parent plus one change. Progress is scored as "
              "1 per dungeon level, 2 per volcano level, 10 for the cure, 30 for a win. "
              "The results shown are those at difficulty %d." % campaign["difficulty"], "",
              _rules_text(campaign), ""]
    lines += _tree_lines(campaign, st, choose_next(campaign, st)[0])
    failed = _failed_lines(campaign)
    if failed:
        lines += ["", "## Tried and failed", ""] + failed
    if campaign["log"]:
        lines += ["", "## Decisions", ""]
        lines += ["- %s: %s" % (e["when"][:16].replace("T", " "), e["text"])
                  for e in reversed(campaign["log"])]
    return "\n".join(lines) + "\n"


CYCLE_STEPS = """\
## Your cycle

1. Start the game: `new_game` with `strategy` set to the id above. The
   strategy's hypotheses, class, seed and the campaign's difficulty are
   filled in for you; do not override them.
2. Play to win, following the strategy and the playbook. Use the skill
   tools (`explore`, `travel_to`, `take_stairs`, `fight`, `flee`, `buy`) and
   `get_state`; use `send_keys` for spells, potions, scrolls and prompts.
   Keep playing until the game is over. Do not quit a game that can go on.
3. When it is over, call `summarize_run`. Be exact about what went wrong:
   name the monster, the level, the HP and the decision you would change.
4. Call `add_lesson` for anything this game showed. Cite the run. Use
   `confirmed` only when more than one run agrees; otherwise `tentative`.
   If a lesson in the playbook turned out wrong, call `retract_lesson`.
   Lessons must hold in any dungeon: the same seeds are played again, so
   never record where things are on a particular map.
5. If you have one specific change that should do better, call
   `propose_strategy` with it. One change at a time, so its effect can be
   seen. It waits its turn; you do not need to propose one every game.
"""

PROPOSE_FIRST = """\
## First: propose a strategy

Every idea so far has been judged, and none is waiting. Before you start a
game, call `propose_strategy` with ONE specific change to %s that the
playbook and the latest post-mortems suggest, then play the strategy it
creates. Do not repeat an idea from "Tried and failed" unless something has
changed, in which case say what in `retry_reason`.
"""


def briefing(root):
    """What an agent should read before a game: the strategy to play, the
    playbook, the tree, what failed and how the latest games went."""
    campaign = load(root)
    all_runs = runs.list_runs(root)
    st = stats(campaign, all_runs)
    sid, why, needs_proposal = choose_next(campaign, st)
    s = strategy(campaign, sid)
    lines = ["# Briefing", "", campaign["goal"], "",
             "%d games recorded so far." % len(all_runs), ""]
    lines += _ladder_lines(campaign, all_runs) + [""]
    if campaign["cleared"] and not st[campaign["base"]]["runs"]:
        lines += ["This difficulty is new. Monsters have more hit points, hit harder and are "
                  "harder to hit, and give less gold and experience. The playbook was learned "
                  "on easier games: expect some of it to stop working, and say so when it does.", ""]
    if needs_proposal:
        lines += [PROPOSE_FIRST % ("%s %s" % (sid, s["title"])),
                  "## Otherwise play: %s %s" % (sid, s["title"]), ""]
    else:
        lines += ["## Play this strategy: %s %s" % (sid, s["title"]), ""]
    lines += ["Why this one: %s. So far: %s." % (why, _stat_text(campaign, s, st[sid])), ""]
    cls = character_class(campaign, sid)
    lines.append("Character class: %s." % (cls or "your choice; say why in the post-mortem"))
    todo = changes(campaign, sid)
    if todo:
        lines += ["", "What it does differently from the baseline:", ""]
        lines += ["- " + c for c in todo[:-1]]
        lines.append("- %s%s" % (todo[-1], " **(the change on trial)**"
                                 if s["status"] in ("trial", "holdout") else ""))
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

    lines += ["## Strategies", "", _rules_text(campaign), ""] + _tree_lines(campaign, st, sid)
    failed = _failed_lines(campaign)
    if failed:
        lines += ["", "## Tried and failed", "", "Do not propose these again:", ""] + failed
    if campaign["log"]:
        lines += ["", "## Latest decisions", ""]
        lines += ["- " + e["text"] for e in campaign["log"][-4:]]

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
