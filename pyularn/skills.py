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
  was sent to is left for the agent.
* It stops when a monster appears or comes adjacent, when HP drops, when
  the level changes, and when the game asks something it cannot answer.

A skill returns a dict whose "result" says why it stopped.  The skills run
on the caller's thread while the game thread waits for input, which is the
only time the engine's globals may be read.
"""

import heapq
import importlib

ESC = "\x1b"

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
    return _ids("OPIT", "OTELEPORTER", "OTRAPARROW", "ODARTRAP", "OTRAPDOOR", "OANNIHILATION")


def gold_ids():
    return _ids("OGOLDPILE", "ODGOLD", "OKGOLD", "OMAXGOLD")


def seen(x, y):
    """What the player knows to be at (x, y), as the screen shows it."""
    k = E.dungeon.know[x][y]
    return E.itm.ONOTHING if k in hidden_ids() else k


def in_bounds(x, y):
    return 0 <= x < E.dungeon.MAXX and 0 <= y < E.dungeon.MAXY


def step_cost(x, y):
    """Cost of walking onto (x, y), or None if a skill will not go there."""
    itm = E.itm
    k = seen(x, y)
    if k in (itm.OUNKNOWN, itm.OWALL) or k in hazard_ids():
        return None
    if k in (itm.ONOTHING, itm.OOPENDOOR) or k in gold_ids():
        return COST_FREE
    if k == itm.OCLOSEDDOOR:
        return COST_DOOR
    return COST_OBJECT


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
            if k == monster.INVISIBLESTALKER and c[player.SEEINVISIBLE] == 0:
                continue
            if monster.DEMONLORD <= k <= monster.LUCIFER and c[player.EYEOFLARN] == 0:
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

def reach(start, goal=None, avoid=()):
    """Cheapest walking cost from `start` to every cell a skill may enter
    (Dijkstra over the known map).  Returns (cost, came_from).

    `avoid` cells (monsters) are not entered.  `goal` is always enterable if
    the player knows what is there, whatever it is, so a path can end on a
    monster or a trap the agent chose to walk onto.
    """
    itm = E.itm
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
                step = None if seen(*nxt) in (itm.OUNKNOWN, itm.OWALL) else COST_FREE
            elif nxt in avoid:
                step = None
            else:
                step = step_cost(*nxt)
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
        return w["kind"] if w else "other"

    def answers(self):
        w = self.s.waiting
        return (w.get("answers") or "") if w else ""

    def monster_cells(self):
        return {(m["x"], m["y"]) for m in visible_monsters()}

    def check_ready(self):
        """Refuse to start unless the game is waiting for a command."""
        if self.over():
            raise SkillError("The game is over.")
        for _ in range(5):  # "press space to continue" needs no decision
            if self.kind() == "prompt" and self.answers() == " ":
                self.press(" ")
        if self.over():
            raise SkillError("The game is over.")
        if self.kind() != "command":
            raise SkillError("The game is asking something. Answer it with send_keys first.")
        c = E.player.c
        if c[E.player.BLINDCOUNT]:
            raise SkillError("You are blind and cannot see the map. Wait it out or cure it.")
        if c[E.player.CONFUSE]:
            raise SkillError("You are confused and cannot walk straight. Wait it out first.")

    def report(self, result, **extra):
        out = {"result": result, "steps": self.steps}
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
            answers = self.answers()
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

    def __init__(self, runner):
        self.r = runner
        self.level = E.dungeon.level
        self.hp = runner.hp()
        self.pos = runner.pos()
        self.count = len(visible_monsters())

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
        if mons and mons[0]["distance"] <= 1:
            return "monster_adjacent"
        if count > before:
            return "monster_appeared"
        return None


# ====================================================================== skills

def _walk(r, max_steps, next_goal, arrived):
    """Shared loop of travel_to and explore.  `next_goal()` returns the cell
    to head for, or a result string to stop with; `arrived(cell)` says
    whether reaching the cell ends the walk."""
    watch = Watch(r)
    stuck = 0
    while r.steps < max_steps:
        goal = next_goal()
        if isinstance(goal, str):
            return goal
        start = r.pos()
        _, came = reach(start, goal, r.monster_cells())
        cells = path_to(came, start, goal)
        if not cells:
            return "no_path"
        last = cells[0] == goal and arrived(goal)
        answered = r.step(cells[0], leave_prompt=last)
        why = watch.reason()
        if why in FATAL:
            return why
        if r.pos() == goal and last:
            return "arrived"
        if not answered:
            return "prompt"
        if why:
            return why
        if r.pos() == start:
            stuck += 1
            if stuck >= 4:
                return "blocked"
        else:
            stuck = 0
    return "max_steps"


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


def travel_to(session, target=None, x=None, y=None, max_steps=300):
    """Walk to a cell or to the nearest known thing of a kind.

    Results: arrived, not_found, no_path, blocked, max_steps, prompt, hurt,
    monster_adjacent, monster_appeared, level_changed, teleported, game_over.
    On "arrived" a prompt raised by the destination is left unanswered.
    """
    r = Runner(session)
    r.check_ready()
    if target is not None:
        goal = nearest(target_ids(target))
        if goal is None:
            return r.report("not_found", target=target)
    elif x is not None and y is not None:
        if not in_bounds(x, y):
            raise SkillError("(%s, %s) is off the map" % (x, y))
        goal = (x, y)
        if seen(x, y) in (E.itm.OUNKNOWN, E.itm.OWALL):
            return r.report("no_path", reason="that cell is a wall or has not been seen")
    else:
        raise SkillError("give a target, or both x and y")
    if r.pos() == goal:
        return r.report("arrived", note="already there")
    result = _walk(r, max_steps, lambda: goal, lambda cell: True)
    return r.report(result, goal={"x": goal[0], "y": goal[1]})


def explore(session, max_steps=300, until=None):
    """Walk to the nearest unexplored part of the level, again and again.

    `until` is a target name or map symbol: stop with "found" as soon as one
    is known.  Results: explored (nothing left to reach), found, plus the
    interruptions of travel_to.  The report lists what was discovered.
    """
    r = Runner(session)
    r.check_ready()
    wanted = target_ids(until) if until is not None else None
    level = E.dungeon.level
    before = {(o["x"], o["y"]) for o in known_objects(10000)}
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
            if not frontier:
                return "explored"
            target = state["target"] = min(frontier, key=lambda c: (cost[c], c[1], c[0]))
        return target

    result = "found" if found() else _walk(r, max_steps, next_goal, lambda cell: False)
    extra = {}
    if not r.over() and E.dungeon.level == level:
        extra["discovered"] = [o for o in known_objects(10000)
                               if (o["x"], o["y"]) not in before][:30]
    return r.report(result, **extra)


def _step_aside(r):
    """Step onto a free neighbouring cell.  The game only asks about the
    thing underfoot on arrival, so walking back on asks again."""
    start = r.pos()
    occupied = r.monster_cells()
    side = [(start[0] + dx, start[1] + dy) for dx, dy in STEPS]
    side = [c for c in side if in_bounds(*c) and c not in occupied and step_cost(*c) == COST_FREE]
    return bool(side) and r.step(min(side)) and r.pos() != start


def take_stairs(session, direction="down", volcano=False, max_steps=300):
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
        goal = nearest(ids)
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
        result = _walk(r, max_steps, lambda: goal, lambda cell: True)
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


def fight(session, max_turns=40, min_hp=0.35, reach_distance=5):
    """Attack the nearest visible monster until none is within reach.

    Walks up to monsters within `reach_distance` and attacks by moving into
    them.  Stops with "low_hp" once HP falls to `min_hp` (a fraction of the
    maximum).  Results: clear, no_monsters, low_hp, unreachable, max_turns,
    prompt, level_changed, game_over.
    """
    if not 0 <= min_hp < 1:
        raise SkillError("min_hp is a fraction of maximum HP, from 0 up to 1")
    player = E.player
    r = Runner(session)
    r.check_ready()
    level = E.dungeon.level
    exp = player.c[player.EXPERIENCE]
    hp = r.hp()
    result = "max_turns"
    while r.steps < max_turns:
        if r.over():
            result = "game_over"
            break
        if E.dungeon.level != level:
            result = "level_changed"
            break
        if r.hp() <= min_hp * r.hp_max():
            result = "low_hp"
            break
        near = [m for m in visible_monsters() if m["distance"] <= reach_distance]
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
        out.update(experience_gained=player.c[player.EXPERIENCE] - exp, hp_lost=hp - r.hp())
    return r.report(result, **out)


def flee(session, max_steps=20, safe_distance=8):
    """Step away from the visible monsters, one cell at a time.

    Each step goes to the neighbouring cell that is furthest, by walking
    distance, from any monster.  It only looks one step ahead, so it can run
    into a dead end.  Results: safe (no monster within `safe_distance`),
    cornered, max_steps, prompt, level_changed, teleported, game_over.
    """
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
