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

Keeping it short
----------------
Every agent starts from the briefing alone, so the briefing must not grow
with the number of games.  Three things are distilled as play goes on:

* A game has a one-line takeaway (see `runs.takeaway`).
* A strategy has a digest: numbers worked out from its recordings
  (`digest`), and field notes that each agent rewrites whole after its game
  (`note_strategy`), so they stay one short text.  `strategy_report` puts
  both in one place with a line per game.
* The playbook has a budget (`playbook_budget`).  A lesson is short and has
  a topic; `merge_lessons` folds overlapping ones into one that carries
  their evidence.  Over its budget, the briefing lists once-seen lessons by
  topic instead of carrying their text (`_playbook_lines`), and `upkeep`
  names the tidying to be done, which the coach hands to an editor.

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
    "playbook_budget": 12000,   # characters of lessons the briefing carries; see playbook_size
}

LESSON_MAX = 300     # characters in one lesson
TOPIC_MAX = 30       # characters in a lesson's topic
NOTES_MAX = 1200     # characters in a strategy's field notes
NOTES_KEPT = 10      # earlier versions of a strategy's field notes (or recipe) kept on record
RECIPE_MAX = 2500    # characters in the recipe of a winning line
LINE = "line"        # the `kind` of a strategy made from a win; see _new_lines
LIVE = ("confirmed", "tentative")   # lessons in force (not retracted, not merged away)

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
    if out["playbook_budget"] < 1000:
        raise LearnError("rules: playbook_budget is at least 1000 characters")
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


def repeat_wins(all_runs):
    """The run ids of wins that do not count: wins on a seed that an
    earlier game had already won at that difficulty.  Games are
    deterministic, so a seed that has been won can be won again by playing
    the same keys, which shows nothing about the strategy."""
    won, repeats = set(), set()
    for meta in reversed(all_runs):                       # oldest first
        if not (meta.get("outcome") or {}).get("won"):
            continue
        key = (meta.get("difficulty"), meta.get("seed"))
        if key in won:
            repeats.add(meta.get("run_id"))
        won.add(key)
    return repeats


def _counted_progress(meta, repeats):
    """A game's progress for judging strategies.  A repeat win is scored as
    a game that held the cure: what it adds to the first win is not news."""
    outcome = meta.get("outcome") or {}
    if meta.get("run_id") in repeats:
        p = progress(dict(outcome, won=False, has_cure=True))
        return dict(p, milestone="won again on a seed already won (not counted as a win)")
    return meta.get("progress") or progress(outcome)


def stats(campaign, all_runs):
    """Results per strategy at the campaign's difficulty, from the runs.

    "trial" and "holdout" map a seed to the progress score of the first
    finished game the strategy played on it; those are what it is judged
    on.  "line" does the same for the seeds of a winning line, and
    "line_wins" lists those of them it won.  "runs", "mean" and "best" cover
    every finished game.  A win on a seed already won is not a win here.
    """
    trial_seeds = set(campaign["seeds"]["trial"])
    holdout_seeds = set(campaign["seeds"]["holdout"])
    repeats = repeat_wins(all_runs)
    out = {sid: {"runs": 0, "wins": 0, "scores": [], "best": None, "run_ids": [],
                 "trial": {}, "holdout": {}, "line": {}, "line_wins": []}
           for sid in campaign["strategies"]}
    for meta in reversed(all_runs):                       # oldest first
        st = out.get(meta.get("strategy"))
        outcome = meta.get("outcome") or {}
        if st is None or outcome.get("result") not in COUNTED:
            continue
        if meta.get("difficulty") != campaign["difficulty"]:
            continue
        p = _counted_progress(meta, repeats)
        won = bool(outcome.get("won")) and meta.get("run_id") not in repeats
        st["runs"] += 1
        st["wins"] += 1 if won else 0
        st["scores"].append(p["score"])
        st["run_ids"].append(meta.get("run_id"))
        if st["best"] is None or p["score"] > st["best"]["score"]:
            st["best"] = p
        seed = meta.get("seed")
        if seed in (campaign["strategies"][meta["strategy"]].get("seeds") or ()):
            if seed not in st["line"]:
                st["line"][seed] = p["score"]
                if won:
                    st["line_wins"].append(seed)
        elif seed in trial_seeds:
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
    s = strategy(campaign, sid)
    if s["status"] == LINE:
        return next((seed for seed in s["seeds"] if seed not in st["line"]), None)
    which = "holdout" if s["status"] == "holdout" else "trial"
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


def _new_lines(campaign, all_runs):
    """Turn a win into a strategy of its own: a winning line.

    A game won under an ordinary strategy shows that strategy can win, but
    not how: that is in the one game.  So the win gets a strategy that
    follows it, a child of the strategy it was played under, holding the
    win as its model and (once an agent has written it) a recipe.  It is
    played next, on seeds nobody has played, and judged on whether it wins
    there (`_judge_lines`), not on average progress.

    A second win under the same strategy while its line is still being
    tried is added to that line as another model.  A win under a line is
    the line working, and makes nothing new.  Wins on a seed already won
    are ignored throughout.
    """
    repeats = repeat_wins(all_runs)
    known = {run for s in campaign["strategies"].values() for run in s.get("models") or ()}
    made = False
    for meta in reversed(all_runs):                       # oldest first
        outcome = meta.get("outcome") or {}
        run, sid = meta.get("run_id"), meta.get("strategy")
        if not outcome.get("won") or run in repeats or run in known:
            continue
        if meta.get("difficulty") != campaign["difficulty"] or sid not in campaign["strategies"]:
            continue
        parent = campaign["strategies"][sid]
        if parent.get("kind") == LINE:
            continue
        known.add(run)
        made = True
        live = [s for s in children(campaign, sid) if s.get("kind") == LINE and s["status"] == LINE]
        if live:
            live[-1]["models"].append(run)
            _log(campaign, "%s won again (%s). It is added to %s as another game to follow."
                 % (sid, run, live[-1]["id"]))
            continue
        used = {m.get("seed") for m in all_runs}
        used |= {s for group in campaign["seeds"].values() for s in group}
        used |= {s for c in campaign["cleared"] for group in c["seeds"].values() for s in group}
        used |= {s for other in campaign["strategies"].values() for s in other.get("seeds") or ()}
        new = "S%d" % campaign["next_strategy"]
        campaign["next_strategy"] += 1
        campaign["strategies"][new] = {
            "id": new, "parent": sid, "kind": LINE, "status": LINE,
            "title": ("Winning line: " + parent["title"])[:80],
            "change": "Follow the recipe distilled from the won game %s, stage by stage, "
                      "building up to what the winner was at each level before going on." % run,
            "character_class": (meta.get("character_class") or "").lower() or None,
            "models": [run], "seeds": _seeds(campaign["rules"]["budget"], used),
            "recipe": None, "note": None, "created": _now()}
        _log(campaign, "%s %s won a game (%s). %s is made to follow that win; it is played next, "
             "on seeds nobody has played, and kept if it wins there."
             % (sid, parent["title"], run, new))
    return made


def _judge_lines(campaign, st):
    """A winning line is proven, and becomes the base, as soon as it wins
    on one of its unseen seeds.  If it has played them all and won none,
    the win it follows was not something it could repeat: it is abandoned."""
    judged = False
    for s in sorted(campaign["strategies"].values(), key=_number):
        if s["status"] != LINE:
            continue
        mine = st[s["id"]]
        played = "%d game%s on seeds nobody had played" % (
            len(mine["line"]), "" if len(mine["line"]) == 1 else "s")
        if mine["line_wins"]:
            s["status"] = "proven"
            s["note"] = "won %d of its first %s" % (len(mine["line_wins"]), played)
            campaign["base"] = s["id"]
            _log(campaign, "%s %s proven: %s; it is the new base." % (s["id"], s["title"], s["note"]))
            judged = True
        elif len(mine["line"]) >= len(s["seeds"]):
            _abandon(campaign, s, "won none of its %s (average progress %s, best: %s)" % (
                played, _mean(mine["line"].values()), mine["best"]["milestone"]))
            judged = True
    return judged


def advance(campaign, all_runs):
    """Judge every strategy whose games are in, and step back from a line
    that has stalled.  Changes `campaign`; returns True if anything changed."""
    rules = campaign["rules"]
    changed = False
    while True:
        step = _new_lines(campaign, all_runs)
        st = stats(campaign, all_runs)
        step = _judge_lines(campaign, st) or step
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
    repeats = repeat_wins(all_runs)       # a seed already won does not count again

    def wins(games):
        return sum(1 for m in games if m["outcome"].get("won") and m.get("run_id") not in repeats)

    return {"difficulty": campaign["difficulty"], "top": rules["top"],
            "games": len(here), "total_wins": wins(here), "recent_wins": wins(recent),
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
    live = sorted(campaign["strategies"].values(), key=_number)
    for s in live:
        if s["status"] == LINE:
            return (s["id"], "it follows the won game %s; this tries its recipe on a seed nobody "
                             "has played" % s["models"][0], False)
    if len(strategy_stats[base]["trial"]) < rules["budget"]:
        return base, "measuring the base, so later ideas have something to beat", False
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


def live_lessons(campaign):
    return [l for l in campaign["lessons"] if l["status"] in LIVE]


def playbook_size(campaign):
    """Characters of lesson text in force: what every briefing has to carry."""
    return sum(len(l["text"]) for l in live_lessons(campaign))


def topics(campaign):
    """The topics in use, most lessons first."""
    count = {}
    for l in live_lessons(campaign):
        if l.get("topic"):
            count[l["topic"]] = count.get(l["topic"], 0) + 1
    return sorted(count, key=lambda t: (-count[t], t))


def _lesson_text(text):
    text = " ".join(str(text or "").split())
    if not text:
        raise LearnError("the lesson is empty")
    if len(text) > LESSON_MAX:
        raise LearnError(
            "a lesson is at most %d characters and this is %d. Say the one thing a later game "
            "should do, and the number that matters; the story of how you found out belongs in "
            "the post-mortem." % (LESSON_MAX, len(text)))
    return text


def _topic(campaign, topic, default=None):
    topic = " ".join(str(topic or "").lower().split()) or default
    if not topic:
        used = topics(campaign)
        raise LearnError(
            "a lesson needs a topic: a word or two for what it is about (a monster, a place, an "
            "item, a tool), so that lessons on one subject can be found and merged. %s"
            % ("Topics in use: %s." % ", ".join(used[:25]) if used
               else "For example: dragons, volcano, town, traps."))
    if len(topic) > TOPIC_MAX:
        raise LearnError("a topic is a word or two, at most %d characters" % TOPIC_MAX)
    return topic


def _check_evidence(root, evidence):
    evidence = [str(e) for e in evidence or ()]
    known = {m["run_id"] for m in runs.list_runs(root)}
    unknown = [e for e in evidence if e not in known]
    if unknown:
        raise LearnError("no such run: " + ", ".join(unknown))
    return evidence


def add_lesson(root, text, evidence=(), confidence="tentative", topic=None):
    text = _lesson_text(text)
    if confidence not in CONFIDENCE:
        raise LearnError("confidence must be confirmed or tentative")
    evidence = _check_evidence(root, evidence)
    if confidence == "confirmed" and not evidence:
        raise LearnError("a confirmed lesson must cite the runs that showed it")
    campaign = load(root)
    for lesson in campaign["lessons"]:
        if lesson["status"] in LIVE and lesson["text"].lower() == text.lower():
            # The same lesson again: add the new evidence to it.
            lesson["evidence"] = sorted(set(lesson["evidence"]) | set(evidence))
            if confidence == "confirmed":
                lesson["status"] = "confirmed"
            if topic and not lesson.get("topic"):
                lesson["topic"] = _topic(campaign, topic)
            save(root, campaign)
            return lesson
    lesson = {"id": "L%d" % campaign["next_lesson"], "text": text,
              "topic": _topic(campaign, topic), "evidence": evidence,
              "status": confidence, "note": None, "added": _now(),
              "difficulty": campaign["difficulty"]}
    campaign["next_lesson"] += 1
    campaign["lessons"].append(lesson)
    save(root, campaign)
    return lesson


def merge_lessons(root, lesson_ids, text, topic=None):
    """Fold lessons into one: the new lesson takes their place and pools
    their evidence.  With a single id it is a rewrite, to shorten a lesson
    or give it a topic.  The old ones stay on record as merged.  Returns
    (the new lesson, characters the playbook shrank by)."""
    ids = [str(i).strip() for i in lesson_ids or () if str(i).strip()]
    if not ids:
        raise LearnError("name the lessons to merge, by id (L3, L8, ...)")
    if len(set(ids)) != len(ids):
        raise LearnError("a lesson is named twice")
    text = _lesson_text(text)
    campaign = load(root)
    by_id = {l["id"]: l for l in campaign["lessons"]}
    old = []
    for i in ids:
        lesson = by_id.get(i)
        if lesson is None:
            raise LearnError("no lesson called %r" % i)
        if lesson["status"] not in LIVE:
            raise LearnError("%s is %s%s" % (i, lesson["status"],
                                             ": " + lesson["note"] if lesson.get("note") else ""))
        old.append(lesson)
    used = [l["topic"] for l in old if l.get("topic")]
    topic = _topic(campaign, topic, max(used, key=used.count) if used else None)
    evidence = sorted({e for l in old for e in l["evidence"]})
    # More than one run behind it, or a part that was already confirmed.
    confirmed = len(evidence) > 1 or any(l["status"] == "confirmed" for l in old)
    new = {"id": "L%d" % campaign["next_lesson"], "text": text, "topic": topic,
           "evidence": evidence, "status": "confirmed" if confirmed else "tentative",
           "note": None, "added": _now(), "merged_from": ids,
           "difficulty": max(l.get("difficulty", campaign["difficulty"]) for l in old)}
    campaign["next_lesson"] += 1
    saved = sum(len(l["text"]) for l in old) - len(text)
    for l in old:
        l["status"] = "merged"
        l["note"] = "merged into " + new["id"]
    campaign["lessons"].append(new)
    save(root, campaign)
    return new, saved


def lessons_text(root, about=None):
    """The playbook in full, for looking a subject up or for tidying it:
    one lesson per line with its id, topic, standing and evidence.  `about`
    keeps the lessons whose topic or text mentions it."""
    campaign = load(root)
    word = " ".join(str(about or "").lower().split())
    found = [l for l in live_lessons(campaign)
             if not word or word in (l.get("topic") or "") or word in l["text"].lower()]
    budget = campaign["rules"]["playbook_budget"]
    lines = ["%d lesson%s%s. The whole playbook is %d characters; its budget is %d."
             % (len(found), "" if len(found) == 1 else "s", " about %r" % word if word else "",
                playbook_size(campaign), budget), ""]
    found.sort(key=lambda l: (l.get("topic") or "~", _lesson_number(l)))
    for l in found:
        lines.append("- %s [%s] (%s, %d run%s, %d chars): %s" % (
            l["id"], l.get("topic") or "no topic", l["status"], len(l["evidence"]),
            "" if len(l["evidence"]) == 1 else "s", len(l["text"]), l["text"]))
    if not found:
        lines.append("_Nothing%s._" % (" on that; topics in use: " + ", ".join(topics(campaign))
                                       if word else " yet"))
    return "\n".join(lines)


def _lesson_number(lesson):
    return int(lesson["id"][1:])


# ====================================================================== digests

def digest(campaign, sid, all_runs):
    """What the recordings say about a strategy: the games that count for
    it (finished, at the campaign's difficulty), how far they got and what
    ended them.  Worked out from the runs each time, never stored."""
    strategy(campaign, sid)
    games = [m for m in all_runs
             if m.get("strategy") == sid and m.get("difficulty") == campaign["difficulty"]
             and (m.get("outcome") or {}).get("result") in COUNTED]
    outs = [m["outcome"] for m in games]
    lost = [o for o in outs if not o.get("won")]

    def tally(values):
        count = {}
        for v in values:
            count[v] = count.get(v, 0) + 1
        return sorted(count.items(), key=lambda kv: (-kv[1], str(kv[0])))

    turns = sorted(o.get("turns") or 0 for o in outs)
    scores = [(m.get("progress") or progress(m["outcome"])) for m in games]
    return {
        "games": len(games), "wins": sum(1 for o in outs if o.get("won")),
        "cure": sum(1 for o in outs if o.get("has_cure") or o.get("won")),
        "mean": _mean(p["score"] for p in scores),
        "best": max(scores, key=lambda p: p["score"])["milestone"] if scores else None,
        "ended_by": tally(o.get("killer") or o.get("reason") or o.get("result") for o in lost),
        "ended_on": tally("town" if o.get("dungeon_level") == "H" else str(o.get("dungeon_level"))
                          for o in lost),
        "median_turns": turns[len(turns) // 2] if turns else None,
        "runs": games,                     # newest first
    }


def _counts(pairs, limit=6):
    text = ", ".join("%s%s" % (name, " ×%d" % n if n > 1 else "") for name, n in pairs[:limit])
    return text + (", and %d more" % (len(pairs) - limit) if len(pairs) > limit else "")


def _digest_lines(d):
    if not d["games"]:
        return ["No finished game yet."]
    lines = ["%d game%s: %d won, %d held the cure. Average progress %s; best: %s."
             % (d["games"], "" if d["games"] == 1 else "s", d["wins"], d["cure"], d["mean"],
                d["best"])]
    if d["ended_by"]:
        lines.append("Ended by: %s." % _counts(d["ended_by"]))
        lines.append("Ended on level: %s. A game lasted about %s turns."
                     % (_counts(d["ended_on"]), d["median_turns"]))
    return lines


def note_strategy(root, sid, text, run_id=None):
    """Replace a strategy's field notes: the one short account of how it
    plays, how it dies and what to do differently, which every agent that
    plays it brings up to date.  Earlier versions stay on record."""
    text = "\n".join(line.rstrip() for line in str(text or "").strip().splitlines())
    if not text:
        raise LearnError("the notes are empty")
    if len(text) > NOTES_MAX:
        raise LearnError(
            "field notes are at most %d characters and these are %d. They are rewritten whole "
            "each time, not added to: keep what still holds, drop what one game showed and no "
            "other did, and leave single events to the post-mortems." % (NOTES_MAX, len(text)))
    campaign = load(root)
    s = strategy(campaign, sid)
    if s.get("kind") == LINE:
        raise LearnError("%s is a winning line: its account is its recipe. Rewrite that with "
                         "write_recipe." % sid)
    all_runs = runs.list_runs(root)
    if run_id is not None and run_id not in {m["run_id"] for m in all_runs}:
        raise LearnError("no such run: %s" % run_id)
    if s.get("notes"):
        s["notes_history"] = ([s["notes"]] + (s.get("notes_history") or []))[:NOTES_KEPT]
    s["notes"] = {"text": text, "when": _now(), "run": run_id,
                  "games": digest(campaign, sid, all_runs)["games"]}
    save(root, campaign)
    return s


RECIPE_GUIDE = (
    "Write it as stages in the order they are played (for example: town and level 1; down "
    "to the level where the build-up is done; the volcano; taking the cure; the way home). "
    "For each stage say what to do, what to buy or learn, and what you must have before "
    "going on, in numbers: character level, HP, AC, WC, and the scrolls and potions in the "
    "pack. Then list the killers met and the answer to each. Take the numbers from the run "
    "sheet. Leave out anything about where things lay on the map: the next game is in "
    "another dungeon.")


def recipe_prompt(root, campaign, line, meta):
    """What to tell the agent that has just written up a game belonging to
    a winning line: write the recipe (the game was the win), or revise it
    (the game followed the line), with the facts to do it from."""
    sid, run = line["id"], meta.get("run_id")
    recipe = line.get("recipe")
    try:
        mine = runs.run_sheet(runs.read_events(runs.run_dir(root, run)))
    except runs.RunError:
        mine = None
    lines = [""]
    if run in line["models"]:
        lines += ["This game was WON. %s %s has been made to follow it: it is played next, on "
                  "seeds nobody has played, and kept if it wins there. %s its recipe now with "
                  "write_recipe (strategy \"%s\", at most %d characters). It is what the next "
                  "agent plays from." % (sid, line["title"], "Revise" if recipe else "Write",
                                         sid, RECIPE_MAX), "", RECIPE_GUIDE]
        if mine:
            lines += ["", "The run sheet of your game:", ""] + runs.sheet_lines(mine)
    else:
        won = (meta.get("outcome") or {}).get("won")
        lines += ["This game followed the winning line %s. Now rewrite its recipe with "
                  "write_recipe (strategy \"%s\", at most %d characters, the whole of it): keep "
                  "the stages that held, and change the stage where this game %s."
                  % (sid, sid, RECIPE_MAX,
                     "did better than the recipe asked" if won else "went wrong")]
        model = model_sheet(root, line)
        if model and mine:
            lines += ["", "Your game beside the game that won:", ""]
            lines += runs.compare_sheets(model, mine)
        if not recipe:
            lines += ["", "There is no recipe yet: yours will be the first.", "", RECIPE_GUIDE]
    if recipe:
        lines += ["", "The recipe as it stands:", ""] + recipe["text"].splitlines()
    return "\n".join(lines)


def write_recipe(root, sid, text, run_id=None):
    """Write, or rewrite whole, the recipe of a winning line: the staged
    plan drawn from the game that won, which each later game under the line
    revises with what it found.  Earlier versions stay on record."""
    text = "\n".join(line.rstrip() for line in str(text or "").strip().splitlines())
    if not text:
        raise LearnError("the recipe is empty")
    if len(text) > RECIPE_MAX:
        raise LearnError(
            "a recipe is at most %d characters and this is %d. It is rewritten whole each "
            "time: stages in order, each with what to have before going on, and the killers "
            "with the answer to each. Leave the story to the post-mortem."
            % (RECIPE_MAX, len(text)))
    campaign = load(root)
    s = strategy(campaign, sid)
    if s.get("kind") != LINE:
        raise LearnError("%s is not a winning line, so it has no recipe; its account is its "
                         "field notes (note_strategy). A winning line is made by the campaign "
                         "when a game is won." % sid)
    all_runs = runs.list_runs(root)
    if run_id is not None and run_id not in {m["run_id"] for m in all_runs}:
        raise LearnError("no such run: %s" % run_id)
    if s.get("recipe"):
        s["recipe_history"] = ([s["recipe"]] + (s.get("recipe_history") or []))[:NOTES_KEPT]
    s["recipe"] = {"text": text, "when": _now(), "run": run_id,
                   "games": digest(campaign, sid, all_runs)["games"]}
    save(root, campaign)
    return s


def line_of(campaign, meta):
    """The winning line a game belongs to: the one made from it if it was
    the win, or the one it was played under.  None for any other game."""
    for s in campaign["strategies"].values():
        if meta.get("run_id") in (s.get("models") or ()):
            return s
    s = campaign["strategies"].get(meta.get("strategy"))
    return s if s and s.get("kind") == LINE else None


def model_sheet(root, s):
    """The run sheet of the game a winning line follows (its first model)."""
    try:
        return runs.run_sheet(runs.read_events(runs.run_dir(root, s["models"][0])))
    except runs.RunError:
        return None


def _recipe_lines(root, campaign, s, all_runs):
    """A winning line for the agent about to play it: the recipe, and what
    the winner was on reaching each level, to measure oneself against."""
    recipe = s.get("recipe")
    lines = []
    if recipe:
        played = digest(campaign, s["id"], all_runs)["games"]
        lines += ["The recipe (as rewritten after %d of this line's %d games):"
                  % (min(recipe.get("games") or 0, played), played), ""]
        lines += recipe["text"].splitlines()
    else:
        lines += ["_No recipe has been written yet. Work from the run sheet below and from "
                  "`get_run` of the won game, and write the recipe after your game._"]
    sheet = model_sheet(root, s)
    if sheet:
        lines += ["", "The game that won, %s. Measure yourself against it on reaching each "
                  "level: where you are behind, build up before going deeper." % s["models"][0], ""]
        lines += runs.sheet_lines(sheet)
    if len(s["models"]) > 1:
        lines += ["", "Also won under the same strategy (`get_run` shows each): "
                  + ", ".join(s["models"][1:]) + "."]
    return lines


def _notes_lines(campaign, sid, all_runs, own=True):
    """A strategy's field notes, with how many of its games they cover."""
    s = strategy(campaign, sid)
    notes = s.get("notes")
    if not notes:
        return ["_No field notes yet._"] if own else []
    played = digest(campaign, sid, all_runs)["games"]
    behind = played - (notes.get("games") or 0)
    head = "Field notes" if own else "Field notes of %s %s, which this builds on" % (sid, s["title"])
    head += " (written after %d of its %d games%s):" % (
        min(notes.get("games") or 0, played), played,
        "; %d newer game%s not in them yet" % (behind, "" if behind == 1 else "s") if behind > 0
        else "")
    return [head, ""] + notes["text"].splitlines()


def strategy_report(root, sid):
    """Everything about one strategy in one place: what it is, its numbers,
    its field notes and a line for each of its games."""
    campaign = load(root)
    s = strategy(campaign, sid)
    all_runs = runs.list_runs(root)
    d = digest(campaign, sid, all_runs)
    tags = [STATUS_WORDS[s["status"]]] + (["the base"] if sid == campaign["base"] else [])
    chain = lineage(campaign, sid)
    lines = ["# %s %s [%s]" % (sid, s["title"], ", ".join(tags)), ""]
    if len(chain) > 1:
        lines += ["Builds on: " + " → ".join("%s %s" % (p["id"], p["title"]) for p in chain), "",
                  "What it does differently from the baseline:", ""]
        lines += ["- " + c for c in changes(campaign, sid)]
    else:
        lines.append(s["change"])
    cls = character_class(campaign, sid)
    if cls:
        lines += ["", "Character class: %s." % cls]
    if s.get("note"):
        lines += ["", "Verdict: %s." % s["note"]]
    lines += ["", "## Numbers", "", "From the recordings, at difficulty %d." % campaign["difficulty"],
              ""] + _digest_lines(d)
    if s.get("kind") == LINE:
        lines += ["", "## Recipe", ""] + _recipe_lines(root, campaign, s, all_runs)
    else:
        lines += ["", "## Field notes", ""] + _notes_lines(campaign, sid, all_runs)
    for p in reversed(chain[:-1]):
        inherited = _notes_lines(campaign, p["id"], all_runs, own=False)
        if inherited:
            lines += [""] + inherited
    if d["runs"]:
        lines += ["", "## Its games, newest first", ""]
        for m in d["runs"]:
            lines.append("- %s: %s; got to: %s. %s" % (
                m["run_id"], runs.headline(m),
                (m.get("progress") or progress(m["outcome"]))["milestone"], runs.takeaway(m)))
        lines += ["", "`get_run` gives any of these in full."]
    return "\n".join(lines)


def upkeep(root):
    """What needs tidying before more games are played, as a list of jobs
    for an editor: a playbook over its budget or with lessons that have no
    topic, and strategies that have been played but have no field notes."""
    campaign = load(root)
    all_runs = runs.list_runs(root)
    jobs = []
    size, budget = playbook_size(campaign), campaign["rules"]["playbook_budget"]
    untagged = [l for l in live_lessons(campaign) if not l.get("topic")]
    if size > budget:
        jobs.append("The playbook is %d characters in %d lessons, and its budget is %d: merge "
                    "and shorten lessons until it fits." % (size, len(live_lessons(campaign)), budget))
    elif untagged:
        jobs.append("%d lessons have no topic: give each one (merge_lessons with its own id)."
                    % len(untagged))
    for s in sorted(campaign["strategies"].values(), key=_number):
        played = digest(campaign, s["id"], all_runs)["games"]
        if s.get("kind") == LINE:
            if not s.get("recipe") and s["status"] != "abandoned":
                jobs.append("%s %s follows the won game %s and has no recipe: write it "
                            "(write_recipe) from that game." % (s["id"], s["title"], s["models"][0]))
        elif played and not s.get("notes"):
            jobs.append("%s %s has %d game%s and no field notes: write them."
                        % (s["id"], s["title"], played, "" if played == 1 else "s"))
    return jobs


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
    if s["status"] == LINE:
        text = "%d of %d games on unseen seeds, %d won, average progress %s" % (
            len(st["line"]), len(s["seeds"]), len(st["line_wins"]), _mean(st["line"].values()))
    elif s["status"] == "holdout":
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
                "proven": "proven", "stalled": "stalled", "abandoned": "abandoned",
                LINE: "following a win"}


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

    return ["- %s%s: %s%s%s" % (l["id"], " [%s]" % l["topic"] if l.get("topic") else "",
                               l["text"], learned_at(l),
                               " (runs: %s)" % ", ".join(l["evidence"]) if l["evidence"] else "")
            for l in campaign["lessons"] if l["status"] == status]


def _playbook_lines(campaign):
    """The playbook as the briefing carries it.  Within its budget, every
    lesson in full, by topic.  Over it, the lessons seen once that have a
    topic are only listed under it, to be looked up when the subject comes
    up; confirmed lessons, and any not yet given a topic, stay in full."""
    live = live_lessons(campaign)
    if not live:
        return ["_Empty: this is one of the first games._", ""]
    size, budget = playbook_size(campaign), campaign["rules"]["playbook_budget"]
    over = size > budget

    def line(l):
        d = l.get("difficulty", campaign["difficulty"])
        runs_ = len(l["evidence"])
        return "- %s%s: %s%s%s" % (
            l["id"], " [%s]" % l["topic"] if l.get("topic") else "", l["text"],
            "" if d == campaign["difficulty"] else " [learned at difficulty %d]" % d,
            " (%d runs)" % runs_ if runs_ > 1 else "")

    def ordered(lessons):
        return sorted(lessons, key=lambda l: (l.get("topic") or "~", _lesson_number(l)))

    confirmed = ordered(l for l in live if l["status"] == "confirmed")
    tentative = ordered(l for l in live if l["status"] == "tentative")
    listed = [l for l in tentative if over and l.get("topic")]
    shown = [l for l in tentative if l not in listed]
    lines = []
    if over:
        lines += ["The playbook has outgrown its budget (%d characters in %d lessons; the budget "
                  "is %d). Do not add to the pile: when what you learned overlaps a lesson "
                  "here, fold the two into one with `merge_lessons`." % (size, len(live), budget),
                  ""]
    if confirmed:
        lines += ["Confirmed, follow these:", ""] + [line(l) for l in confirmed] + [""]
    if shown:
        lines += ["Tentative, seen once:", ""] + [line(l) for l in shown] + [""]
    if listed:
        by_topic = {}
        for l in listed:
            by_topic.setdefault(l["topic"], []).append(l["id"])
        lines += ["Tentative, by topic. Read them when the subject comes up: "
                  "`get_lessons` with `about` set to the topic.", ""]
        lines += ["- %s: %s" % (t, ", ".join(ids)) for t, ids in sorted(by_topic.items())] + [""]
    return lines


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
    merged = [l for l in campaign["lessons"] if l.get("merged_from")]
    if merged:
        lines += ["", "### Merged", "",
                  "Lessons folded into one, which carries their evidence. The originals are in "
                  "`campaign.json`.", ""]
        lines += ["- %s ← %s" % (l["id"], ", ".join(l["merged_from"])) for l in merged]
    lines += ["", "The playbook is %d characters in %d lessons; its budget is %d."
              % (playbook_size(campaign), len(live_lessons(campaign)),
                 campaign["rules"]["playbook_budget"])]
    lines += ["", "## Strategies", "",
              "Each strategy is its parent plus one change. Progress is scored as "
              "1 per dungeon level, 2 per volcano level, 10 for the cure, 30 for a win. "
              "The results shown are those at difficulty %d." % campaign["difficulty"], "",
              _rules_text(campaign), ""]
    lines += _tree_lines(campaign, st, choose_next(campaign, st)[0])
    failed = _failed_lines(campaign)
    if failed:
        lines += ["", "## Tried and failed", ""] + failed
    played = [s for s in sorted(campaign["strategies"].values(), key=_number)
              if st[s["id"]]["runs"] or s.get("kind") == LINE]
    if played:
        lines += ["", "## How each strategy has gone", "",
                  "The numbers come from the recordings. The field notes are the agents' own "
                  "account, rewritten after each game."]
        for s in played:
            lines += ["", "### %s %s" % (s["id"], s["title"]), ""]
            lines += _digest_lines(digest(campaign, s["id"], all_runs))
            if s.get("kind") == LINE:
                lines += [""] + _recipe_lines(root, campaign, s, all_runs)
            else:
                lines += [""] + _notes_lines(campaign, s["id"], all_runs)
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
   tools (`explore`, `travel_to`, `pick_up`, `take_stairs`, `fight`, `flee`,
   `rest`, `buy`) and `get_state`; use `send_keys` for spells, potions,
   scrolls and prompts. Rest with `rest`, not with a row of `.` keys.
   Keep playing until the game is over. Do not quit a game that can go on.
3. When it is over, call `summarize_run`. Be exact about what went wrong:
   name the monster, the level, the HP and the decision you would change.
   Give a `takeaway`: the one sentence a later reader needs from this game.
   Then bring the strategy's field notes up to date with `note_strategy`.
   They are what the next agent reads in place of every game: rewrite them
   whole, keeping what still holds and adding what this game showed.
   If you WON, or the strategy is a winning line, `summarize_run` asks for
   its recipe instead (`write_recipe`): the staged plan the next agent
   plays from. That is the most useful thing a win leaves behind.
4. Call `add_lesson` for anything this game showed that the playbook does
   not already say. Cite the run and give a `topic`. A lesson is one short
   instruction, not the story of the game. Use `confirmed` only when more
   than one run agrees; otherwise `tentative`. If it overlaps a lesson
   already there, fold the two together with `merge_lessons`, which pools
   their evidence. If a lesson turned out wrong, call `retract_lesson`.
   Lessons must hold in any dungeon: the same seeds are played again, so
   never record where things are on a particular map.
   What you found out about a particular item (what it does, whether it
   was worth the gold, how it went wrong) goes in the item book instead:
   call `note_item`. Its WC/AC, prices and where it turns up are measured
   for you; to measure an item, wield or wear it.
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

    # How the strategy has gone so far, so that nobody has to read its
    # games one by one: the numbers, then what the agents who played it
    # (and the strategies it builds on) wrote down.
    lines += ["", "### How it has gone", ""] + _digest_lines(digest(campaign, sid, all_runs))
    if s.get("kind") == LINE:
        lines += ["", "### The recipe to follow", "",
                  "This strategy follows a game that was won. Its recipe is the plan; the "
                  "table is what the winner was on reaching each level. After your game you "
                  "rewrite the recipe with `write_recipe`, so say in the post-mortem where "
                  "the recipe held and where it did not.", ""]
        lines += _recipe_lines(root, campaign, s, all_runs)
    else:
        lines += [""] + _notes_lines(campaign, sid, all_runs)
    for p in reversed(lineage(campaign, sid)[:-1]):
        inherited = _notes_lines(campaign, p["id"], all_runs, own=False)
        if inherited:
            lines += [""] + inherited
    lines += ["", "`get_strategy` gives this for any strategy, with a line for each of its games."]

    lines += ["", "## Playbook", ""]
    lines += _playbook_lines(campaign)
    from . import items
    lines += items.briefing_lines(items.load(root))

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
            lines.append("- %s (%s): %s; got to: %s. %s" % (
                b["run_id"], b["strategy"] or "no strategy", b["headline"],
                (m.get("progress") or progress(m["outcome"]))["milestone"], runs.takeaway(m)))
        lines.append("")
        lines.append("`get_run` gives any of these in full.")
    lines += ["", CYCLE_STEPS]
    return "\n".join(lines)
