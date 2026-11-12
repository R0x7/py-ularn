"""Skills: multi-step actions for agents, built on single key presses.

An agent that sends one key per tool call needs thousands of calls to play
a game.  A skill does a whole errand in one call (explore this level, walk
to the stairs, fight what is next to me) and stops as soon as something
needs a decision, saying why.

Rules every skill follows:

* It only presses keys.  The game engine is not modified or bypassed, so a
  skill can do nothing a player at the keyboard could not.
* It only uses what the player knows: `dungeon.know` (the map as drawn on
  the screen, with undiscovered traps hidden) and the monsters the screen
  shows.  It never reads `dungeon.item` or sleeping, unseen monsters.
* It never walks onto a known trap, pit or teleporter on the way, and it
  answers "ignore" to things it passes over.  Only a prompt at the place it
  was sent to is left for the agent (`pick_up` answers "take" there, which
  is what it was asked to do).
* It stops when a monster appears or comes adjacent, when HP drops, when
  the level changes, and when the game asks something it cannot answer.

A skill returns a dict whose "result" says why it stopped.  The skills run
on the caller's thread while the game thread waits for input, which is the
only time the engine's globals may be read.
"""

import heapq
import importlib

ESC = "\x1b"

# How the skills behave.  Runs record it, so a replay of an older run can
# ask for the behaviour it was recorded with (LEGACY): version 1 crossed
# express elevators, stayed on a trap that had just hurt, tried four times
# to step into something unseen, and let `fight` walk off after new
# targets until HP fell to min_hp.  Version 2 still stopped a walk for
# every monster in view, however far or walled off, and at every step
# taken next to one; it did not look for a forgotten building in town.
# Version 3 had `flee` look one step ahead only.  Version 4 took "In What
# Direction?" for the map waiting for a command, so a skill started there
# answered the question with its first key.  Version 5 walked over altars
# and answered their prompt "ignore", which can summon a monster and add
# Aggravate; version 6 routes round known altars and stops on one it finds
# underfoot, leaving the prompt to the agent.  Version 6 opened closed
# doors in the volcano, where a failed try can add Aggravate, which
# overrides stealth; version 7 routes round them there and leaves a door
# it is asked to cross to the agent.
VERSION = 7
BEHAVE = VERSION     # the version whose behaviour is in force; see behave_as
LEGACY = False       # behaving as a version before 3


def behave_as(version=None):
    """Behave as skills version `version` did, for replaying a run recorded
    with it.  None goes back to the current behaviour."""
    global BEHAVE, LEGACY
    BEHAVE = VERSION if version is None else max(1, min(int(version), VERSION))
    LEGACY = BEHAVE < 3


ALERT_DISTANCE = 6   # a walk stops for a new monster this near, if it can get to you
COST_UNKNOWN = 4     # walking into the unexplored, when asked to
COST_HAZARD = 1000   # a known trap, when asking what lies in the way
FAR = 1 << 30

# (dx, dy) -> movement key.  y grows downwards, as on the screen.
KEYS = {(0, -1): "k", (0, 1): "j", (1, 0): "l", (-1, 0): "h",
        (1, -1): "u", (-1, -1): "y", (1, 1): "n", (-1, 1): "b"}
STEPS = list(KEYS)

DOOR_PROMPT = "oi" + ESC          # "Do you (o) try to open it, or (i) ignore it?"
STORE_PROMPT = "abcdefghijklmnopqrstuvwxyz " + ESC

COST_FREE = 1      # empty floor, open doors, gold (picked up without asking)
COST_DOOR = 3      # a closed door: has to be opened, which can fail
COST_OBJECT = 6    # anything else: stepping on it raises a prompt to dismiss


class SkillError(Exception):
    """The skill cannot be used like this (bad argument, wrong place)."""


class _Engine:
    """The game modules, looked up when used.  They must not be imported
    when this module loads: the engine is set up (and reset) by the caller."""

    def __getattr__(self, name):
        return importlib.import_module("." + name, __package__)


E = _Engine()


# ====================================================================== the map

def _ids(*names):
    return frozenset(getattr(E.itm, n) for n in names)


def hidden_ids():
    """Traps the player has not found: `know` holds them, the screen does not."""
    return _ids("OTRAPARROWIV", "OIVDARTRAP", "OIVTRAPDOOR", "OIVTELETRAP")


def hazard_ids():
    """Known things a walk must not cross: traps, express elevators, which
    carry you off as soon as you step on them, and altars, whose prompt a
    walk could only answer "ignore" (a monster and Aggravate 30% of the time)."""
    traps = ("OPIT", "OTELEPORTER", "OTRAPARROW", "ODARTRAP", "OTRAPDOOR", "OANNIHILATION")
    if LEGACY:
        return _ids(*traps)
    if BEHAVE < 6:
        return _ids(*traps, "OELEVATORUP", "OELEVATORDOWN")
    return _ids(*traps, "OELEVATORUP", "OELEVATORDOWN", "OALTAR")


def trap_ids():
    """Known traps that hurt you again for every turn you stay on them."""
    return _ids("OTRAPARROW", "ODARTRAP")


def gold_ids():
    return _ids("OGOLDPILE", "ODGOLD", "OKGOLD", "OMAXGOLD")


def item_ids():
    """What can be picked up: everything that is not scenery.  Gold counts;
    walking onto it picks it up without a question."""
    return (frozenset(range(E.itm.OCOUNT)) - E.items.scenery_ids()) | gold_ids()


def captured(fn, *args):
    """Run one of the game's show.* functions and return what it would have
    printed on the screen."""
    import io

    win = E.ularn_win
    buf = io.StringIO()
    saved = win.Print, win.Printf, win.Printc, win.Standout

    def p(s):
        buf.write(str(s))

    def pf(fmt, *a):
        try:
            buf.write(fmt % a if a else fmt)
        except (TypeError, ValueError):
            buf.write(fmt)

    win.Print, win.Printf, win.Printc, win.Standout = p, pf, p, p
    try:
        fn(*args)
    finally:
        win.Print, win.Printf, win.Printc, win.Standout = saved
    return buf.getvalue()


def seen(x, y):
    """What the player knows to be at (x, y), as the screen shows it."""
    k = E.dungeon.know[x][y]
    return E.itm.ONOTHING if k in hidden_ids() else k


def in_bounds(x, y):
    return 0 <= x < E.dungeon.MAXX and 0 <= y < E.dungeon.MAXY


def in_volcano():
    """On a volcano level, where skills (version 7 on) leave closed doors
    alone: a failed try can add Aggravate, which wakes everything."""
    return BEHAVE >= 7 and E.dungeon.level > E.dungeon.DBOTTOM


def step_cost(x, y):
    """Cost of walking onto (x, y), or None if a skill will not go there."""
    itm = E.itm
    k = seen(x, y)
    if k in (itm.OUNKNOWN, itm.OWALL) or k in hazard_ids():
        return None
    if k in (itm.ONOTHING, itm.OOPENDOOR) or k in gold_ids():
        return COST_FREE
    if k == itm.OCLOSEDDOOR:
        return None if in_volcano() else COST_DOOR
    return COST_OBJECT


def hidden_kind(k):
    """Whether the screen would not show a monster of kind `k` even in
    plain view: the player is blind, it is an invisible stalker (without
    see invisible) or a demon (without the Eye of Larn)."""
    monster, player = E.monster, E.player
    c = player.c
    if c[player.BLINDCOUNT]:
        return True
    if k == monster.INVISIBLESTALKER and c[player.SEEINVISIBLE] == 0:
        return True
    return monster.DEMONLORD <= k <= monster.LUCIFER and c[player.EYEOFLARN] == 0


def visible_monsters():
    """The monsters drawn on the map right now, nearest first.

    This follows the display rules of ularn_win.GetTile, so it holds only
    what the screen already shows: a mimic is listed as what it looks like,
    and unseen sleepers, invisible stalkers and (without the Eye of Larn)
    demons are left out.
    """
    dungeon, itm, monster, player = E.dungeon, E.itm, E.monster, E.player
    c = player.c
    if c[player.BLINDCOUNT]:
        return []
    px, py = player.playerx, player.playery
    found = []
    for x in range(dungeon.MAXX):
        for y in range(dungeon.MAXY):
            k = dungeon.mitem[x][y].mon
            if k == 0 or dungeon.know[x][y] == itm.OUNKNOWN:
                continue
            if not dungeon.stealth[x][y] & (dungeon.STEALTH_SEEN | dungeon.STEALTH_AWAKE):
                continue
            if hidden_kind(k):
                continue
            if k == monster.MIMIC:
                k = E.ularn_win.mimicmonst or monster.MIMIC
            found.append({
                "name": monster.monster[k].name,
                "symbol": monster.monstnamelist[k],
                "x": x, "y": y,
                "distance": max(abs(x - px), abs(y - py)),
            })
    found.sort(key=lambda m: (m["distance"], m["y"], m["x"]))
    return found


MAP_UNKNOWN = " "
MAP_FLOOR = "."
MAP_WALL = "#"


def map_rows():
    """The level as the player knows it: MAXY strings of MAXX characters,
    row y, column x, matching the positions used everywhere else.

    It is the map drawn on the screen, cell for cell, with two differences
    that make it easier to read as text: every wall is "#" (the screen draws
    lines and corners), and explored floor is "." where the terminal shows a
    blank for both floor and the unexplored.  The graphical versions of the
    game make that distinction too.  Everything else uses the screen's own
    symbols: @ you, letters for visible monsters, D and O for doors, and the
    object symbols.
    """
    itm, player = E.itm, E.player
    grid = []
    for y in range(E.dungeon.MAXY):
        row = []
        for x in range(E.dungeon.MAXX):
            k = seen(x, y)
            if k == itm.OUNKNOWN:
                row.append(MAP_UNKNOWN)
            elif k == itm.ONOTHING:
                row.append(MAP_FLOOR)
            elif k == itm.OWALL:
                row.append(MAP_WALL)
            else:
                row.append(itm.objnamelist[k])
        grid.append(row)
    for m in visible_monsters():
        grid[m["y"]][m["x"]] = m["symbol"]
    grid[player.playery][player.playerx] = "@"
    return ["".join(row) for row in grid]


def known_objects(limit=60):
    """Everything of interest the player knows of on this level, nearest
    first: stairs, buildings, items, fountains, known traps.  Walls, floor
    and doors are left out."""
    itm, player = E.itm, E.player
    dull = (itm.OUNKNOWN, itm.ONOTHING, itm.OWALL, itm.OOPENDOOR, itm.OCLOSEDDOOR)
    px, py = player.playerx, player.playery
    found = []
    for x in range(E.dungeon.MAXX):
        for y in range(E.dungeon.MAXY):
            k = seen(x, y)
            if k in dull:
                continue
            found.append({"name": itm.objectname[k].strip(), "symbol": itm.objnamelist[k],
                          "x": x, "y": y, "distance": max(abs(x - px), abs(y - py))})
    found.sort(key=lambda o: (o["distance"], o["y"], o["x"]))
    return found[:limit]


TARGETS = {
    "stairs_down": ("OSTAIRSDOWN",), "stairs_up": ("OSTAIRSUP",),
    "dungeon_entrance": ("OENTRANCE",), "entrance": ("OENTRANCE",),
    "volcano": ("OVOLDOWN", "OVOLUP"), "home": ("OHOME",),
    "store": ("ODNDSTORE",), "bank": ("OBANK", "OBANK2"), "college": ("OSCHOOL",),
    "trading_post": ("OTRADEPOST",), "lrs": ("OLRS",), "dealer": ("OPAD",),
    "elevator": ("OELEVATORUP", "OELEVATORDOWN"), "altar": ("OALTAR",),
    "fountain": ("OFOUNTAIN",), "throne": ("OTHRONE", "OTHRONE2"),
    "gold": ("OGOLDPILE", "ODGOLD", "OKGOLD", "OMAXGOLD"), "potion": ("OPOTION",),
    "scroll": ("OSCROLL",), "book": ("OBOOK",), "chest": ("OCHEST",),
}


def target_ids(target):
    """The object ids a target name or a one-character map symbol stands for."""
    itm = E.itm
    key = str(target).strip()
    names = TARGETS.get(key.lower().replace(" ", "_").replace("-", "_"))
    if names:
        return frozenset(getattr(itm, n) for n in names)
    if len(key) == 1 and key != " ":
        ids = frozenset(i for i in range(itm.OCOUNT)
                        if itm.objnamelist[i] == key and i not in hidden_ids())
        if ids:
            return ids
    raise SkillError("unknown target %r: use a map symbol such as %% or !, or one of: %s"
                     % (target, ", ".join(sorted(TARGETS))))


# ====================================================================== paths

def reach(start, goal=None, avoid=(), through_unknown=False, hazards=False):
    """Cheapest walking cost from `start` to every cell a skill may enter
    (Dijkstra over the known map).  Returns (cost, came_from).

    `avoid` cells (monsters) are not entered.  `goal` is always enterable if
    the player knows what is there, whatever it is, so a path can end on a
    monster or a trap the agent chose to walk onto.  With `through_unknown`
    unexplored cells may be crossed, at a cost, on the guess that they are
    floor: the walk plans again as each step shows more of the map.
    `hazards` lets the path cross known traps, at a high cost.  No skill
    walks such a path: it is for saying what lies in the way.
    """
    itm = E.itm
    danger = hazard_ids() if hazards else ()
    cost = {start: 0}
    came = {}
    heap = [(0, start)]
    while heap:
        d, cell = heapq.heappop(heap)
        if d > cost[cell]:
            continue
        if cell == goal:
            break
        x, y = cell
        for dx, dy in STEPS:
            nxt = (x + dx, y + dy)
            if not in_bounds(*nxt):
                continue
            if nxt == goal:
                k = seen(*nxt)
                if k == itm.OUNKNOWN and through_unknown:
                    step = COST_UNKNOWN
                else:
                    step = None if k in (itm.OUNKNOWN, itm.OWALL) else COST_FREE
            elif nxt in avoid:
                step = None
            elif through_unknown and seen(*nxt) == itm.OUNKNOWN:
                step = COST_UNKNOWN
            else:
                step = step_cost(*nxt)
                if step is None and danger and seen(*nxt) in danger:
                    step = COST_HAZARD
            if step is None:
                continue
            nd = d + step
            if nd < cost.get(nxt, 1 << 30):
                cost[nxt] = nd
                came[nxt] = cell
                heapq.heappush(heap, (nd, nxt))
    return cost, came


def path_to(came, start, goal):
    """The cells to walk, first step first, or None if `goal` was not reached."""
    if goal != start and goal not in came:
        return None
    cells = []
    cell = goal
    while cell != start:
        cells.append(cell)
        cell = came[cell]
    cells.reverse()
    return cells


def is_frontier(x, y):
    """A cell the player can stand on with something unknown next to it."""
    for dx, dy in STEPS:
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny) and E.dungeon.know[nx][ny] == E.itm.OUNKNOWN:
            return True
    return False


# ====================================================================== running

FATAL = ("game_over", "level_changed", "teleported")


class Runner:
    """Carries out one skill call on a GameSession-like object, which needs
    send(keys), term.finished, waiting and final_outcome()."""

    def __init__(self, session):
        self.s = session
        self.steps = 0
        self.notes = {}     # extra facts for the report, gathered on the way

    # ------------------------------------------------------------ reading
    def pos(self):
        return (E.player.playerx, E.player.playery)

    def hp(self):
        return E.player.c[E.player.HP]

    def hp_max(self):
        return E.player.c[E.player.HPMAX]

    def over(self):
        return self.s.term.finished or self.s.final_outcome() is not None

    def kind(self):
        """What the game is waiting for: "command", "prompt" or "other"."""
        w = self.s.waiting
        if not w:
            return "other"
        if w.get("direction") and BEHAVE < 5:
            return "command"    # as it was: a direction is read like a command
        return w["kind"]

    def answers(self):
        w = self.s.waiting
        return (w.get("answers") or "") if w else ""

    def on_altar(self):
        x, y = self.pos()
        return E.dungeon.item[x][y] == E.itm.OALTAR

    def monster_cells(self):
        return {(m["x"], m["y"]) for m in visible_monsters()}

    def check_ready(self, impaired=False):
        """Refuse to start unless the game is waiting for a command.  A
        skill that does not walk (rest) passes `impaired`, to be usable
        while blind or confused."""
        if self.over():
            raise SkillError("The game is over.")
        for _ in range(5):  # "press space to continue" needs no decision
            if self.kind() == "prompt" and self.answers() == " ":
                self.press(" ")
        if self.over():
            raise SkillError("The game is over.")
        if self.kind() != "command":
            raise SkillError("The game is asking something. Answer it with send_keys first.")
        if impaired:
            return
        c = E.player.c
        if c[E.player.BLINDCOUNT]:
            raise SkillError("You are blind and cannot see the map. Wait it out or cure it.")
        if c[E.player.CONFUSE]:
            raise SkillError("You are confused and cannot walk straight. Wait it out first.")

    def report(self, result, **extra):
        out = {"result": result, "steps": self.steps}
        out.update(self.notes)
        out.update(extra)
        if not self.over():
            x, y = self.pos()
            out.update(position={"x": x, "y": y}, level=E.dungeon.levelname[E.dungeon.level].strip(),
                       hp=self.hp(), hp_max=self.hp_max(), monsters=visible_monsters()[:8])
        return out

    # ------------------------------------------------------------ acting
    def press(self, key):
        self.s.send([key])

    def clear_prompts(self):
        """Dismiss prompts raised by walking: open doors, ignore everything
        else.  Returns False if the game wants something a skill cannot give."""
        for _ in range(6):
            if self.over():
                return True
            kind = self.kind()
            if kind == "command":
                return True
            if kind != "prompt":
                return False
            if BEHAVE >= 6 and self.on_altar():
                return False    # pray or ignore is the agent's call, not a walk's
            answers = self.answers()
            if answers == DOOR_PROMPT and in_volcano():
                return False    # opening may add Aggravate: the agent's call
            if answers == DOOR_PROMPT:
                self.press("o")
            elif answers == " ":      # "press space to continue"
                self.press(" ")
            elif ESC in answers:
                self.press(ESC)
            elif "i" in answers:
                self.press("i")
            else:
                return False
        return self.kind() == "command"

    def step(self, cell, leave_prompt=False):
        """Move one cell.  With `leave_prompt`, a prompt raised by what is
        there (other than a door) is left for the caller."""
        x, y = self.pos()
        self.press(KEYS[(cell[0] - x, cell[1] - y)])
        self.steps += 1
        if leave_prompt and self.kind() == "prompt" and self.answers() != DOOR_PROMPT:
            return True
        return self.clear_prompts()


class Watch:
    """Notices the things that should interrupt a walk."""

    def __init__(self, runner, ignore_monsters=False):
        self.r = runner
        self.ignore_monsters = ignore_monsters
        self.level = E.dungeon.level
        self.hp = runner.hp()
        self.pos = runner.pos()
        mons = visible_monsters()
        self.count = len(mons)
        self.adjacent = _adjacent(mons)
        self.threats = len(_threats(self.pos, mons))

    def reason(self):
        r = self.r
        if r.over():
            return "game_over"
        if E.dungeon.level != self.level:
            return "level_changed"
        pos = r.pos()
        jumped = max(abs(pos[0] - self.pos[0]), abs(pos[1] - self.pos[1])) > 1
        self.pos = pos
        if jumped:
            return "teleported"
        hp, before = r.hp(), self.hp
        self.hp = hp
        if hp < before:
            return "hurt"
        mons = visible_monsters()
        count, before = len(mons), self.count
        self.count = count
        if LEGACY:
            if mons and mons[0]["distance"] <= 1:
                return "monster_adjacent"
            return "monster_appeared" if count > before else None
        # Stop once for each monster that comes next to you, not at every
        # step taken beside one that stays where it is; and only for new
        # monsters that are near and have a known way to reach you.
        adjacent, was_adjacent = _adjacent(mons), self.adjacent
        threats, were = len(_threats(pos, mons)), self.threats
        self.adjacent, self.threats = adjacent, threats
        if self.ignore_monsters:
            return None
        if adjacent - was_adjacent:
            return "monster_adjacent"
        if threats > were:
            return "monster_appeared"
        return None


def _adjacent(mons):
    return {(m["x"], m["y"]) for m in mons if m["distance"] <= 1}


def _threats(pos, mons):
    """The visible monsters a walk should stop for: within ALERT_DISTANCE,
    with a way to the player over the known map about that long.  One seen
    across the level or through a wall is left out."""
    near = [m for m in mons if m["distance"] <= ALERT_DISTANCE]
    if not near:
        return []
    cost, _ = reach(pos)
    limit = 3 * ALERT_DISTANCE
    out = []
    for m in near:
        # A monster stands on its own cell: look at that and the cells round it.
        cells = [(m["x"], m["y"])] + [(m["x"] + dx, m["y"] + dy) for dx, dy in STEPS]
        if m["distance"] <= 1 or any(cost.get(c, FAR) <= limit for c in cells):
            out.append(m)
    return out


# ====================================================================== skills

def _walk(r, max_steps, next_goal, arrived, ignore_monsters=False, through_unknown=False):
    """Shared loop of travel_to and explore.  `next_goal()` returns the cell
    to head for, or a result string to stop with; `arrived(cell)` says
    whether reaching the cell ends the walk."""
    watch = Watch(r, ignore_monsters)
    stuck = 0
    while r.steps < max_steps:
        goal = next_goal()
        if isinstance(goal, str):
            return goal
        start = r.pos()
        _, came = reach(start, goal, r.monster_cells(), through_unknown)
        cells = path_to(came, start, goal)
        if not cells:
            _explain_no_path(r, start, goal, through_unknown)
            return "no_path"
        guess = through_unknown and seen(*cells[0]) == E.itm.OUNKNOWN
        last = cells[0] == goal and arrived(goal)
        answered = r.step(cells[0], leave_prompt=last)
        why = watch.reason()
        if why in FATAL:
            return why
        if r.pos() == goal and last:
            return "arrived"
        if why == "hurt" and not LEGACY:
            _off_trap(r)
        if not answered:
            return "prompt"
        if why:
            return why
        if r.pos() == start:
            if guess and seen(*cells[0]) != E.itm.OUNKNOWN:
                continue    # the guess was wrong and the cell is now known: plan again
            if seen(*cells[0]) != E.itm.OCLOSEDDOOR and not LEGACY:
                # Not a stuck door: the step was taken as an attack on
                # something the screen does not show.  Trying again would
                # keep attacking it, so stop and say so.
                r.notes["note"] = ("could not step to (%d, %d): something you cannot see "
                                   "is probably there, and moving into it attacks it"
                                   % cells[0])
                return "blocked"
            stuck += 1
            if stuck >= 4:
                r.notes["note"] = "the door at (%d, %d) would not open" % cells[0]
                return "blocked"
        else:
            stuck = 0
    return "max_steps"


def _off_trap(r):
    """After being hurt, do not stay on a trap that will hurt again."""
    if seen(*r.pos()) not in trap_ids():
        return
    trap = r.pos()
    if _step_aside(r):
        r.notes["stepped_off_trap"] = {"x": trap[0], "y": trap[1]}
    else:
        r.notes["on_trap"] = {"x": trap[0], "y": trap[1],
                              "note": "you are standing on a trap that hurts every turn; step off"}


def _explain_no_path(r, start, goal, through_unknown=False):
    """Say why there is no path: monsters in the way, a known trap in the
    way, or a map that does not connect yet."""
    _, came = reach(start, goal, (), through_unknown)
    cells = path_to(came, start, goal)
    if cells:
        on_path = set(cells)
        blockers = [m for m in visible_monsters() if (m["x"], m["y"]) in on_path]
        r.notes["blocked_by"] = blockers
        r.notes["reason"] = "the only known way is through the monsters in blocked_by"
        return
    _, came = reach(start, goal, (), through_unknown, hazards=True)
    crossed = _hazards_on((path_to(came, start, goal) or [])[:-1])
    if crossed:
        r.notes["hazards"] = crossed
        r.notes["reason"] = ("the only known way crosses what is listed in hazards, which "
                             "skills will not walk over: cross it yourself with move, or "
                             "explore for another way")
    else:
        r.notes["reason"] = "the known map does not connect here: explore more"


def _hazards_on(cells):
    """The known traps, pits, teleporters and express elevators among `cells`."""
    danger = hazard_ids()
    return [{"name": E.itm.objectname[seen(x, y)].strip(), "x": x, "y": y}
            for x, y in cells or () if seen(x, y) in danger]


def _unreached(r, start):
    """Explore has nowhere left to walk to.  Returns "explored", or
    "no_path" when more of the level is known to lie behind monsters; what
    lies past a known trap is noted, since a skill will not cross one."""
    def nearest_edge(cost):
        edge = [c for c in cost if c != start and is_frontier(*c)]
        return min(edge, key=lambda c: (cost[c], c[1], c[0])) if edge else None

    cost, came = reach(start)                     # monsters not stepped round
    goal = nearest_edge(cost)
    if goal is not None:
        on_path = set(path_to(came, start, goal))
        r.notes["blocked_by"] = [m for m in visible_monsters() if (m["x"], m["y"]) in on_path]
        r.notes["reason"] = ("there is more to explore, but the only known way to it is "
                             "through the monsters in blocked_by")
        return "no_path"
    cost, came = reach(start, hazards=True)
    goal = nearest_edge(cost)
    if goal is not None:
        r.notes["beyond"] = _hazards_on(path_to(came, start, goal))
        r.notes["note"] = ("explored as far as skills go: more of the level lies past what "
                           "is listed in beyond, which they will not walk over")
    return "explored"


def nearest(ids):
    """The cheapest-to-reach known cell holding one of `ids`, or None."""
    r_pos = (E.player.playerx, E.player.playery)
    cells = [(x, y) for x in range(E.dungeon.MAXX) for y in range(E.dungeon.MAXY)
             if seen(x, y) in ids]
    best = None
    for cell in cells:
        if cell == r_pos:
            return cell
        cost, _ = reach(r_pos, cell)
        if cell in cost and (best is None or cost[cell] < best[0]):
            best = (cost[cell], cell)
    return best[1] if best else (cells[0] if cells else None)


def _find(r, ids, max_steps, ignore_monsters=False):
    """The nearest known cell holding one of `ids`.  In town, where every
    building is there to be found, a map lost to a potion of forgetfulness
    is explored again until one turns up.  Returns (cell, None), or
    (None, result) when the search was interrupted."""
    goal = nearest(ids)
    if goal is not None or LEGACY or E.dungeon.level != 0:
        return goal, None
    result = _explore(r, max_steps, ids, ignore_monsters)
    if result == "found":
        r.notes["note"] = "the map had been forgotten: explored the town to find it again"
        return nearest(ids), None
    return None, ("not_found" if result == "explored" else result)


def travel_to(session, target=None, x=None, y=None, max_steps=300, ignore_monsters=False,
              through_unknown=False):
    """Walk to a cell or to the nearest known thing of a kind.

    With `ignore_monsters` the walk does not stop when monsters appear or
    come next to you (it still goes round them, and stops when you are
    hurt).  With `through_unknown` a walk to x, y may cross cells not yet
    seen, feeling its way.  Results: arrived, not_found, no_path, blocked,
    max_steps, prompt, hurt, monster_adjacent, monster_appeared,
    level_changed, teleported, game_over.  On "arrived" a prompt raised by
    the destination is left unanswered.
    """
    r = Runner(session)
    r.check_ready()
    if target is not None:
        goal, stopped = _find(r, target_ids(target), max_steps, ignore_monsters)
        if goal is None:
            return r.report(stopped or "not_found", target=target)
    elif x is not None and y is not None:
        if not in_bounds(x, y):
            raise SkillError("(%s, %s) is off the map" % (x, y))
        goal = (x, y)
        k = seen(x, y)
        if k == E.itm.OWALL:
            return r.report("no_path", reason="that cell is a wall")
        if k == E.itm.OUNKNOWN and not through_unknown:
            return r.report("no_path", reason="that cell has not been seen: explore, or pass "
                                              "through_unknown to feel the way there")
    else:
        raise SkillError("give a target, or both x and y")
    if r.pos() == goal:
        return r.report("arrived", note="already there")
    result = _walk(r, max_steps, lambda: goal, lambda cell: True, ignore_monsters,
                   through_unknown and target is None)
    return r.report(result, goal={"x": goal[0], "y": goal[1]})


def explore(session, max_steps=300, until=None, ignore_monsters=False):
    """Walk to the nearest unexplored part of the level, again and again.

    `until` is a target name or map symbol: stop with "found" as soon as one
    is known.  `ignore_monsters` is as for travel_to.  Results: explored
    (nothing left to reach; `beyond` lists known traps with more of the
    level past them), no_path (more is left, behind the monsters in
    `blocked_by`), found, plus the interruptions of travel_to.  The report
    lists what was discovered.
    """
    r = Runner(session)
    r.check_ready()
    wanted = target_ids(until) if until is not None else None
    level = E.dungeon.level
    before = {(o["x"], o["y"]) for o in known_objects(10000)}
    result = _explore(r, max_steps, wanted, ignore_monsters)
    extra = {}
    if not r.over() and E.dungeon.level == level:
        extra["discovered"] = [o for o in known_objects(10000)
                               if (o["x"], o["y"]) not in before][:30]
    return r.report(result, **extra)


def _explore(r, max_steps, wanted=None, ignore_monsters=False):
    """The walk of explore: returns the result string."""
    state = {"target": None}

    def found():
        return wanted is not None and any(
            seen(x, y) in wanted for x in range(E.dungeon.MAXX) for y in range(E.dungeon.MAXY))

    def next_goal():
        if found():
            return "found"
        start = r.pos()
        cost, _ = reach(start, None, r.monster_cells())
        target = state["target"]
        if target is None or target not in cost or target == start or not is_frontier(*target):
            frontier = [c for c in cost if c != start and is_frontier(*c)]
            if not frontier and not state.get("looked") and not LEGACY \
                    and len(cost) == 1 and is_frontier(*start):
                # Nothing at all is known, not even the cells next to you
                # (a potion of forgetfulness): wait a turn to look around.
                state["looked"] = True
                r.press(".")
                r.steps += 1
                if not r.clear_prompts():
                    return "prompt"
                return next_goal()
            if not frontier:
                return _unreached(r, start)
            target = state["target"] = min(frontier, key=lambda c: (cost[c], c[1], c[0]))
        return target

    return "found" if found() else _walk(r, max_steps, next_goal, lambda cell: False,
                                         ignore_monsters)


def _step_aside(r):
    """Step onto a free neighbouring cell.  The game only asks about the
    thing underfoot on arrival, so walking back on asks again."""
    start = r.pos()
    occupied = r.monster_cells()
    side = [(start[0] + dx, start[1] + dy) for dx, dy in STEPS]
    side = [c for c in side if in_bounds(*c) and c not in occupied and step_cost(*c) == COST_FREE]
    return bool(side) and r.step(min(side)) and r.pos() != start


def take_stairs(session, direction="down", volcano=False, max_steps=300, ignore_monsters=False):
    """Go to the way down (or up) and take it.

    In town "down" is the dungeon entrance, or the volcanic shaft with
    `volcano`.  From dungeon level 1 "up" is the exit to town.  Results:
    changed_level, not_found (explore first), refused (the game would not
    let you), plus the interruptions of travel_to.
    """
    itm, dungeon = E.itm, E.dungeon
    if direction not in ("down", "up"):
        raise SkillError("direction must be down or up")
    r = Runner(session)
    r.check_ready()
    level = dungeon.level
    exit_step = None
    if direction == "down":
        if level == 0:
            ids, key = ({itm.OVOLDOWN}, "c") if volcano else ({itm.OENTRANCE}, "g")
        else:
            ids, key = {itm.OSTAIRSDOWN}, "d"
        goal, stopped = _find(r, ids, max_steps, ignore_monsters)
        if stopped and stopped != "not_found":
            return r.report(stopped)
    elif level == 0:
        raise SkillError("You are in town: there is no way up.")
    elif level == 1:
        # The way out of level 1 is a gap in the bottom wall.
        goal, key, exit_step = (33, dungeon.MAXY - 2), None, (33, dungeon.MAXY - 1)
    elif level == dungeon.DBOTTOM + 1:
        goal, key = nearest({itm.OVOLUP}), "c"
    else:
        goal, key = nearest({itm.OSTAIRSUP}), "u"
    if goal is None:
        return r.report("not_found", note="not seen on this level yet; explore first")

    if r.pos() == goal and exit_step is None:
        # Standing on it with no prompt showing: step off, then walk back on.
        if not _step_aside(r):
            return r.report("blocked", note="no room to step off and back onto it")
    if r.pos() != goal:
        result = _walk(r, max_steps, lambda: goal, lambda cell: True, ignore_monsters)
        if result != "arrived":
            return r.report(result)

    if exit_step is not None:
        r.step(exit_step)
    elif r.kind() == "prompt" and key in r.answers():
        r.press(key)
        r.clear_prompts()
    else:
        return r.report("prompt", note="the usual question was not asked")
    if r.over():
        return r.report("game_over")
    if dungeon.level != level:
        return r.report("changed_level", was=dungeon.levelname[level].strip())
    return r.report("refused", note="see the screen for the reason")


def _pack_line(index):
    """An inventory line as the game prints it, split into slot and name."""
    text = captured(E.show.show3, index).strip()
    slot, sep, name = text.partition(")")
    if sep and len(slot) == 1:
        return {"slot": slot, "name": name.strip()}
    return {"slot": chr(ord("a") + index), "name": text}


def pick_up(session, target=None, x=None, y=None, max_steps=300, ignore_monsters=False):
    """Walk to things lying on the level and take them.

    With `x` and `y`, the one thing at that cell.  With `target` (a name
    such as potion, or a map symbol), every known one of that kind.  With
    neither, everything known on the level that can be carried, gold
    included (and anything you dropped there: it cannot tell).  The nearest
    is fetched first.  Results: done, pack_full, not_found (nothing known
    to pick up), no_path (none of it can be reached), plus the
    interruptions of travel_to.  Whatever the result, `taken` lists what
    was picked up and `left` what is still lying there and why.  With a
    full pack it does not walk to what it could not carry.
    """
    itm, player = E.itm, E.player
    r = Runner(session)
    r.check_ready()
    carried = item_ids()
    if x is not None or y is not None:
        if x is None or y is None:
            raise SkillError("give both x and y")
        if target is not None:
            raise SkillError("give a target, or x and y, not both")
        if not in_bounds(x, y):
            raise SkillError("(%s, %s) is off the map" % (x, y))
        wanted, only = carried, (x, y)
    else:
        wanted, only = (carried if target is None else target_ids(target) & carried), None
        if not wanted:
            raise SkillError("%r is not something to pick up" % (target,))

    def name_at(cell):
        return itm.objectname[seen(*cell)].strip()

    def known():
        if only is not None:
            return [only] if seen(*only) in wanted else []
        return [(cx, cy) for cx in range(E.dungeon.MAXX) for cy in range(E.dungeon.MAXY)
                if seen(cx, cy) in wanted]

    level = E.dungeon.level
    gold = player.c[player.GOLD]
    purse = gold_ids()
    taken, left = [], {}
    result = None
    while result is None:
        start = r.pos()
        todo = [c for c in known() if c not in left]
        if not _pack_has_room() and any(seen(*c) not in purse for c in todo):
            # Do not walk to what cannot be carried; gold still can be.
            todo = [c for c in todo if seen(*c) in purse]
            if not todo:
                result = "pack_full"
                break
        if not todo:
            break
        occupied = r.monster_cells()
        cost, _ = reach(start, None, occupied)
        near = [c for c in todo if c in cost]
        if len(near) < len(todo):
            past_monsters, _ = reach(start)
            past_traps, _ = reach(start, hazards=True)
            for cell in todo:
                if cell in cost:
                    continue
                if cell in occupied:
                    why = "a monster is standing on it"
                elif cell in past_monsters:
                    why = "monsters stand in the only known way there"
                elif cell in past_traps:
                    why = "the only known way there crosses a known trap"
                else:
                    why = "no known way there"
                left[cell] = {"name": name_at(cell), "x": cell[0], "y": cell[1], "why": why}
        if not near:
            continue
        # Nearest by the walk up to it: the price of stepping onto a thing is
        # for walks that want to pass it by, and this one is going to it.
        goal = min(near, key=lambda c: (cost[c] - (step_cost(*c) or 0) if c != start else 0,
                                        c[1], c[0]))
        what = name_at(goal)
        if goal == start:
            # Standing on it with no question showing: step off and come back.
            if not _step_aside(r):
                left[goal] = {"name": what, "x": goal[0], "y": goal[1],
                              "why": "no room to step off it and back on"}
            continue
        walked = _walk(r, max_steps, lambda: goal, lambda cell: True, ignore_monsters)
        if walked == "no_path":       # something moved into the way: try the rest
            why = r.notes.pop("reason", "no known way there")
            r.notes.pop("blocked_by", None)
            r.notes.pop("hazards", None)
            left[goal] = {"name": what, "x": goal[0], "y": goal[1], "why": why}
            continue
        if walked != "arrived":
            result = walked
            break
        entry = {"name": what, "x": goal[0], "y": goal[1]}
        if r.kind() == "prompt" and "t" in r.answers():
            before = list(player.iven)
            r.press("t")
            answered = r.clear_prompts()
            if r.over():
                result = "game_over"
            elif E.dungeon.level != level:
                result = "level_changed"
            else:
                new = [i for i in range(player.IVENSIZE)
                       if before[i] == itm.ONOTHING and player.iven[i] != itm.ONOTHING]
                if new:
                    entry.update(_pack_line(new[0]))
                    taken.append(entry)
                elif seen(*goal) in carried:
                    result = "pack_full"      # the game would not let you take it
                if result is None and not answered:
                    result = "prompt"
        elif r.kind() == "command":
            if seen(*goal) in carried:
                left[goal] = dict(entry, why="the game did not offer to take it")
            else:                             # gold: taken by walking onto it
                taken.append(entry)
        else:
            r.notes["note"] = "the %s asked something other than whether to take it" % what
            result = "prompt"

    out = {"taken": taken}
    if not r.over() and E.dungeon.level == level:
        if result is None and not _pack_has_room() \
                and any(seen(*c) not in purse and c not in left for c in known()):
            result = "pack_full"      # the gold was fetched; the rest cannot be carried
        # Whatever is still lying there, and why it was not fetched.
        for cell in known():
            if cell in left:
                continue
            if result == "pack_full" and seen(*cell) not in purse:
                why = "your pack is full"
            else:
                why = "not reached: stopped first (%s)" % result
            left[cell] = {"name": name_at(cell), "x": cell[0], "y": cell[1], "why": why}
    if left:
        out["left"] = sorted(left.values(), key=lambda o: (o["y"], o["x"]))[:30]
    if not r.over():
        if player.c[player.GOLD] > gold:
            out["gold_gained"] = player.c[player.GOLD] - gold
        if result == "pack_full":
            out["note"] = "you can carry no more: drop or use something first"
    if result is None:
        result = "done" if taken else ("no_path" if left else "not_found")
    return r.report(result, **out)


# Timed effects the game announces when they start but does not list beside
# the map: player.c[] name, and the name agents are given.
UNLISTED_EFFECTS = (
    ("BLINDCOUNT", "Blind"), ("CONFUSE", "Confused"), ("AGGRAVATE", "Aggravate"),
    ("HASTEMONST", "Haste Monsters"), ("ITCHING", "Itching"), ("CLUMSINESS", "Clumsy"),
    ("SEEINVISIBLE", "See Invisible"), ("HERO", "Heroism"), ("GLOBE", "Invulnerability"),
    ("HALFDAM", "Half Damage"), ("AWARENESS", "Awareness"),
)


def _effects():
    """(player.c[] index, name) of every timed effect: those the game lists
    beside the map, under the names it uses there, then the unlisted ones."""
    listed = [(e.typ, e.string.strip()) for e in E.ularn_win._get_bot_data()]
    return listed + [(getattr(E.player, n), name) for n, name in UNLISTED_EFFECTS]


def active_effects():
    """Names of the timed effects now running."""
    c = E.player.c
    return [name for idx, name in _effects() if c[idx]]


def _pack_has_room():
    """Whether the game would let you take one more thing: the slots it
    lets you use grow with your level (see player.take)."""
    player = E.player
    slots = min(15 + (player.c[player.LEVEL] >> 1), player.IVENSIZE)
    return any(player.iven[i] == E.itm.ONOTHING for i in range(slots))


def rest(session, turns=None, until="hp", max_turns=200, ignore_monsters=False, effect=None):
    """Wait a turn at a time, watching for trouble.

    Without `turns`, rests until HP is full (`until` "hp"), spell points
    are (`until` "spells"), or both are (`until` "both"), for at most
    `max_turns`.  With `turns`, waits that many turns whatever HP is.  With
    `effect`, the name of a timed effect as get_state lists it ("Time
    Stop", "Hold Monst", "Stealth"...), waits until that effect has ended,
    for at most `max_turns` waits.  It stops at once when HP drops or a
    monster comes into view or next to you, and it will not rest on a
    known trap that fires every turn: it steps off first.  It can be used
    while blind or confused.  Results: rested (nothing left to recover),
    waited (the `turns` asked for have passed), effect_ended, max_turns,
    blocked (on a trap with nowhere to step), plus the interruptions of
    travel_to.  "turns" in the report is game time, which stands still
    during a time stop; "steps" is how many times it waited.
    """
    player = E.player
    c = player.c
    if until not in ("hp", "spells", "both"):
        raise SkillError("until must be hp, spells or both")
    wanted = None
    if effect is not None:
        if turns is not None:
            raise SkillError("give turns or effect, not both")
        effects = _effects()
        key = " ".join(str(effect).lower().split())
        wanted = next((e for e in effects if e[1].lower() == key), None)
        if wanted is None:
            raise SkillError("no effect is called %r. The effects are: %s"
                             % (effect, ", ".join(name for _, name in effects)))
    r = Runner(session)
    r.check_ready(impaired=True)

    def lacking():
        hp = c[player.HP] < c[player.HPMAX]
        spells = c[player.SPELLS] < c[player.SPELLMAX]
        return {"hp": hp, "spells": spells, "both": hp or spells}[until]

    turn, hp, spells = player.gtime, c[player.HP], c[player.SPELLS]

    def done(result, **extra):
        out = {"turns": player.gtime - turn}
        if not r.over():
            out.update(hp_gained=c[player.HP] - hp, spells=c[player.SPELLS],
                       spells_max=c[player.SPELLMAX], spells_gained=c[player.SPELLS] - spells)
        if wanted is not None:
            out["effect"] = wanted[1]
        out.update(extra)
        return r.report(result, **out)

    if wanted is not None:
        if not c[wanted[0]]:
            return done("effect_ended", note="that effect is not running")
    elif turns is None and not lacking():
        return done("rested", note="nothing to recover")
    if seen(*r.pos()) in trap_ids():
        trap = r.pos()
        if not _step_aside(r):
            return done("blocked", on_trap={"x": trap[0], "y": trap[1]},
                        note="you are standing on a trap that hurts every turn, with no "
                             "free cell to step to: move off it before resting")
        r.notes["stepped_off_trap"] = {"x": trap[0], "y": trap[1]}
    watch = Watch(r, ignore_monsters)
    limit = max_turns if turns is None else turns
    waited = 0
    result = "max_turns" if turns is None else "waited"
    while waited < limit:
        r.press(".")
        r.steps += 1
        waited += 1
        answered = r.clear_prompts()
        why = watch.reason()
        if why in FATAL:
            result = why
            break
        if why == "hurt":
            _off_trap(r)
        if not answered:
            result = "prompt"
            break
        if why:
            result = why
            break
        if wanted is not None:
            if not c[wanted[0]]:
                result = "effect_ended"
                break
        elif turns is None and not lacking():
            result = "rested"
            break
    return done(result)


def fight(session, max_turns=40, min_hp=0.35, reach_distance=5):
    """Attack the nearest visible monster, and then whatever is next to you.

    Walks up to the nearest monster within `reach_distance` and attacks it
    by moving into it.  Once something has been killed it only goes on
    against monsters already next to you: it never walks off after a new
    target.  It stops with "low_hp" once HP falls to `min_hp` (a fraction of
    the maximum) or to no more than the biggest single blow taken so far,
    and with "hurt_at_range" when HP drops with no visible monster next to
    you (a breath, a spell, or something invisible).  Results: clear,
    no_monsters, low_hp, hurt_at_range, unreachable, max_turns, prompt,
    level_changed, game_over.
    """
    if not 0 <= min_hp < 1:
        raise SkillError("min_hp is a fraction of maximum HP, from 0 up to 1")
    player = E.player
    r = Runner(session)
    r.check_ready()
    level = E.dungeon.level
    exp = player.c[player.EXPERIENCE]
    last_hp = r.hp()
    worst = hurt = 0
    result = "max_turns"
    while r.steps < max_turns:
        if r.over():
            result = "game_over"
            break
        if E.dungeon.level != level:
            result = "level_changed"
            break
        now = r.hp()
        lost, last_hp = last_hp - now, now
        hurt += max(0, lost)
        mons = visible_monsters()
        if lost > 0 and not LEGACY:
            worst = max(worst, lost)
            if not mons or mons[0]["distance"] > 1:
                result = "hurt_at_range"
                break
        if now <= min_hp * r.hp_max() or (worst and now <= worst):
            result = "low_hp"
            break
        killed = player.c[player.EXPERIENCE] > exp and not LEGACY
        near = [m for m in mons if m["distance"] <= (1 if killed else reach_distance)]
        if not near:
            result = "clear" if r.steps else "no_monsters"
            break
        m = near[0]
        target = (m["x"], m["y"])
        start = r.pos()
        if m["distance"] == 1:
            cell = target
        else:
            _, came = reach(start, target, r.monster_cells() - {target})
            cells = path_to(came, start, target)
            if not cells:
                result = "unreachable"
                break
            cell = cells[0]
        if not r.step(cell):
            result = "prompt"
            break
    out = {"turns": r.steps}
    if not r.over():
        # The blows taken, added up: HP at the end less HP at the start
        # would come out negative when a kill raised the character's level.
        hurt += max(0, last_hp - r.hp())
        out.update(experience_gained=player.c[player.EXPERIENCE] - exp, hp_lost=hurt,
                   biggest_hit=worst)
    return r.report(result, **out)


def flee(session, max_steps=20, safe_distance=8):
    """Run from the visible monsters.

    Heads for the place furthest, by walking distance, from every monster
    in view, among the places you can get to before any of them could, and
    plans again after each step as they move.  So it leaves a room by the
    door instead of backing into a corner, and it would sooner run for an
    unexplored edge of the map than into a known dead end.  It knows only
    the map and the monsters you can see.  Results: safe (no monster within
    `safe_distance`, or none with a known way to you), cornered (nowhere
    you can reach first is further from them than here), blocked, max_steps,
    prompt, level_changed, game_over.  The report says where it was heading
    (`toward`).
    """
    if BEHAVE < 4:
        return _flee_one_step(session, max_steps, safe_distance)
    r = Runner(session)
    r.check_ready()
    level = E.dungeon.level
    result = "max_steps"
    target = None
    stuck = 0
    while r.steps < max_steps:
        if r.over():
            result = "game_over"
            break
        if E.dungeon.level != level:
            result = "level_changed"
            break
        mons = visible_monsters()
        if not mons or mons[0]["distance"] >= safe_distance:
            result = "safe"
            break
        occupied = {(m["x"], m["y"]) for m in mons}
        far = _monster_distance(occupied)
        here = r.pos()
        if here not in far:
            r.notes["note"] = "no monster in view has a known way to you"
            result = "safe"
            break
        steps, came = _reach_first(here, occupied, far)

        def worth(cell):
            # How far from the monsters, and an edge of the known map counts
            # for more than a known dead end as far away: there is probably
            # more room past it, and the map fills in on the way there.
            return far.get(cell, FAR) + (safe_distance if is_frontier(*cell) else 0)

        best = max(steps, key=lambda c: (worth(c), -steps[c], -c[1], -c[0]))
        if target in steps and target != here and worth(target) >= worth(best) - 2:
            best = target       # keep going where you were going
        if best == here or worth(best) <= worth(here):
            result = "cornered"
            break
        target = best
        cell = path_to(came, here, best)[0]
        if not r.step(cell):
            result = "prompt"
            break
        if not r.over() and E.dungeon.level == level and r.pos() == here:
            stuck += 1
            if seen(*cell) != E.itm.OCLOSEDDOOR:
                r.notes["note"] = ("could not step to (%d, %d): something you cannot see "
                                   "is probably there, and moving into it attacks it" % cell)
                result = "blocked"
                break
            if stuck >= 4:
                r.notes["note"] = "the door at (%d, %d) would not open" % cell
                result = "blocked"
                break
        else:
            stuck = 0
    extra = {"toward": {"x": target[0], "y": target[1]}} if target else {}
    return r.report(result, **extra)


def _reach_first(start, occupied, far):
    """The cells you can walk to before any monster could, with the steps
    each takes: (steps, came_from).  `far` is each cell's walking distance
    from the nearest monster; a cell is only entered while that is more
    than the steps it takes you to get there."""
    steps = {start: 0}
    came = {}
    heap = [(0, start)]
    while heap:
        d, cell = heapq.heappop(heap)
        if d > steps[cell]:
            continue
        for dx, dy in STEPS:
            nxt = (cell[0] + dx, cell[1] + dy)
            if not in_bounds(*nxt) or nxt in occupied:
                continue
            price = step_cost(*nxt)
            if price is None:
                continue
            nd = d + (2 if price == COST_DOOR else 1)    # a door takes a turn to open
            if nd >= far.get(nxt, FAR) or nd >= steps.get(nxt, FAR):
                continue
            steps[nxt] = nd
            came[nxt] = cell
            heapq.heappush(heap, (nd, nxt))
    return steps, came


def _flee_one_step(session, max_steps, safe_distance):
    """flee as it was up to skills version 3: each step goes to the
    neighbouring cell furthest from any monster, looking no further ahead."""
    r = Runner(session)
    r.check_ready()
    level = E.dungeon.level
    result = "max_steps"
    while r.steps < max_steps:
        if r.over():
            result = "game_over"
            break
        if E.dungeon.level != level:
            result = "level_changed"
            break
        mons = visible_monsters()
        if not mons or mons[0]["distance"] >= safe_distance:
            result = "safe"
            break
        occupied = {(m["x"], m["y"]) for m in mons}
        far = _monster_distance(occupied)
        here = r.pos()
        options = [(here[0] + dx, here[1] + dy) for dx, dy in STEPS]
        options = [c for c in options if in_bounds(*c) and c not in occupied
                   and step_cost(*c) is not None]
        if not options:
            result = "cornered"
            break
        best = max(options, key=lambda c: (far.get(c, 999), -step_cost(*c), -c[1], -c[0]))
        if far.get(best, 999) <= far.get(here, 0):
            result = "cornered"
            break
        if not r.step(best):
            result = "prompt"
            break
    return r.report(result)


def _monster_distance(sources):
    """Walking distance from the nearest monster to each cell it can reach."""
    dist = {c: 0 for c in sources}
    queue = list(sources)
    for cell in queue:
        for dx, dy in STEPS:
            nxt = (cell[0] + dx, cell[1] + dy)
            if in_bounds(*nxt) and nxt not in dist and step_cost(*nxt) is not None:
                dist[nxt] = dist[cell] + 1
                queue.append(nxt)
    return dist


# ====================================================================== shopping

def _stock():
    """What the DND store sells, as its own screen lists it."""
    store, itm, potion, scroll = E.store, E.itm, E.potion, E.scroll
    store._init_itm()
    rows = []
    for i in range(store.DNDSIZE):
        it = store.itm[i]
        if it.obj == itm.OPOTION:
            name = "potion of " + potion.potionname[it.arg][1:]
        elif it.obj == itm.OSCROLL:
            name = "scroll of " + scroll.scrollname[it.arg][1:]
        else:
            name = itm.objectname[it.obj]
        rows.append({"index": i, "name": name.strip(), "price": it.price * 10, "in_stock": it.qty})
    return rows


def _in_store(r):
    return (r.kind() == "prompt" and r.answers() == STORE_PROMPT
            and "Thrift Shoppe" in r.s.screen())


def buy(session, items=(), leave=True, max_steps=300):
    """Buy things at the DND store in town, walking there if needed.

    `items` are names as the store lists them ("chain mail", "potion of
    healing"); part of a name is enough if it matches one item.  With no
    items the store's price list is returned instead.  Results: done (see
    "bought" and "failed"), listed, refused (back taxes are owed), plus the
    interruptions of travel_to if the store was not reached.
    """
    player = E.player
    r = Runner(session)
    if r.over():
        raise SkillError("The game is over.")
    if not _in_store(r):
        r.check_ready()
        if E.dungeon.level != 0:
            raise SkillError("The DND store is in town, and you are not.")
        if seen(*r.pos()) == E.itm.ODNDSTORE and not _step_aside(r):
            return r.report("blocked", note="no room to step off the store and back on")
        went = travel_to(session, target="store", max_steps=max_steps)
        r.steps = went["steps"]
        if went["result"] != "arrived":
            return went
        if r.kind() != "prompt" or "g" not in r.answers():
            return r.report("prompt", note="the store did not ask to be entered (a monster nearby?)")
        r.press("g")
        if r.kind() == "prompt" and r.answers() == ESC:
            r.press(ESC)
            return r.report("refused", note="the store will not serve you until your taxes are paid")
        if not _in_store(r):
            return r.report("prompt", note="not at the store's counter")

    bought, failed = [], []
    stock = _stock()
    for want in items:
        key = str(want).strip().lower()
        hits = [s for s in stock if s["name"].lower() == key] or \
               [s for s in stock if key and key in s["name"].lower()]
        names = sorted({s["name"] for s in hits})
        if not hits:
            failed.append({"item": want, "why": "the store does not sell that"})
            continue
        if len(names) > 1:
            failed.append({"item": want, "why": "matches several items: " + ", ".join(names[:8])})
            continue
        hits = [s for s in hits if s["in_stock"] > 0]
        if not hits:
            failed.append({"item": want, "why": "out of stock"})
            continue
        s = hits[0]
        gold = player.c[player.GOLD]
        if gold < s["price"]:
            failed.append({"item": want, "why": "costs %d gold, you have %d" % (s["price"], gold)})
            continue
        if player.pocketfull():
            failed.append({"item": want, "why": "your pack is full"})
            continue
        page = s["index"] // player.IVENSIZE * player.IVENSIZE
        for _ in range(8):
            if E.store.dnditm == page:
                break
            r.press(" ")
        r.press(chr(ord("a") + s["index"] % player.IVENSIZE))
        if player.c[player.GOLD] == gold - s["price"]:
            bought.append({"name": s["name"], "price": s["price"]})
            stock = _stock()
        else:
            failed.append({"item": want, "why": "the store refused; see the screen"})

    out = {"gold": player.c[player.GOLD]}
    if items:
        out.update(bought=bought, failed=failed)
    else:
        out["stock"] = [{"name": s["name"], "price": s["price"],
                         "affordable": s["price"] <= out["gold"]}
                        for s in stock if s["in_stock"] > 0]
    if leave and _in_store(r):
        r.press(ESC)
    return r.report("done" if items else "listed", **out)
