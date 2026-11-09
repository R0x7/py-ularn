"""MCP server that lets an AI agent play pyularn.

Speaks the Model Context Protocol (JSON-RPC 2.0, newline-delimited) over
stdin/stdout with no third-party dependencies::

    python -m pyularn.mcp_server        # or the `pyularn-mcp` console script

The game itself is unmodified: it runs in a background thread on a
VirtualTerminal.  Each tool call feeds keys, waits until the game is blocked
waiting for input again, and returns the 80x24 screen plus (optionally) a
structured view of the player's state.

Only one game runs per server process (the engine keeps its state in module
globals, as the C original does).
"""

import io
import json
import random
import re
import sys
import threading
import time
import traceback

from . import header

SERVER_NAME = "pyularn"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

KEY_REFERENCE = """\
Ularn controls (keys are sent with the send_keys tool):
  Movement   h=W j=S k=N l=E  y=NW u=NE b=SW n=SE   (capital letter = run)
  .          stay here one turn            (space) do nothing
  i          inventory                     g      pack weight
  w          wield a weapon                W      wear armour
  T          take off armour               d      drop an item
  q          quaff (drink) a potion        r      read a scroll or book
  e          eat a fortune cookie          c      cast a spell (then a 3-letter code)
  \\          list known spells             o / C  open / close a door
  O          open a chest                  ^      identify adjacent traps
  Z          teleport (level 10+)          P      show taxes owed
  S          save game and quit            Q      quit
  ?          help pages                    v      version
  ^R (<c-r>) redraw screen
Walking onto an object or a building usually brings up a prompt; answer it
with the letter shown.  Answer y/n prompts with y or n; <esc> cancels
most prompts and menus.  Inventory prompts take the item's slot letter.
Map symbols: @ you, # wall, letters are monsters, other symbols are objects:
  * gold  ! potion  ? scroll  [ armour  ( weapon  = ring or mirror
  " amulet  / wand or staff  < gem  B book  C chest  c fortune cookie
  % staircase  ~ elevator  ^ trap  O / D open / closed door  P pit
  A altar  T throne  F fountain  & statue  : drugs
Town buildings: E dungeon entrance, V volcanic shaft, H your home,
  S DND store, M College of Larn, $ bank, T trading post,
  L Larn Revenue Service, P Dealer McDope's Pad.
Walk onto a building to enter it.  The `get_state` tool gives exact stats.
The goal: find the potion of cure dianthroritis and return home with it
before the time limit runs out.
"""

TOKEN_NAMES = {
    "esc": "\x1b", "escape": "\x1b",
    "enter": "\r", "ret": "\r", "return": "\r", "cr": "\r",
    "space": " ", "spc": " ",
    "bs": "\x08", "backspace": "\x08", "del": "\x08",
    "tab": "\t",
    "lt": "<", "gt": ">",
    "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
    "home": "KEY_A1", "pgup": "KEY_A3", "end": "KEY_C1", "pgdn": "KEY_C3",
    "center": "KEY_B2",
}

DIRECTIONS = {
    "n": "k", "north": "k", "s": "j", "south": "j",
    "e": "l", "east": "l", "w": "h", "west": "h",
    "ne": "u", "northeast": "u", "nw": "y", "northwest": "y",
    "se": "n", "southeast": "n", "sw": "b", "southwest": "b",
}

CLASSES = {
    "ogre": "a", "wizard": "b", "klingon": "c", "elf": "d",
    "rogue": "e", "adventurer": "f", "dwarf": "g", "rambo": "h",
}
CLASS_NAMES = {v: k for k, v in CLASSES.items()}


def parse_keys(text):
    """Turn a key string into a list of keys.

    Plain characters are sent as-is; <name> tokens (case-insensitive) send
    special keys: <esc> <enter> <space> <bs> <tab> <up> <down> <left>
    <right> <c-x> (control-x) <lt> <gt>.  A literal '\\n' counts as Enter.
    """
    keys = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "<":
            m = re.match(r"<([A-Za-z0-9_-]+)>", text[i:])
            if m:
                name = m.group(1).lower()
                cm = re.fullmatch(r"(?:c|ctrl)-([a-z])", name)
                if cm:
                    keys.append(chr(ord(cm.group(1)) - 96))
                    i += m.end()
                    continue
                if name in TOKEN_NAMES:
                    keys.append(TOKEN_NAMES[name])
                    i += m.end()
                    continue
        keys.append("\r" if ch == "\n" else ch)
        i += 1
    return keys


MAX_THOUGHT = 2000
MESSAGE_ROW = 19   # screen rows: 0-16 the map, 17-18 status, 19-23 messages

THOUGHT_SCHEMA = {
    "type": "string",
    "description": "A sentence or two on what you are doing and why, in plain words. "
                   "People watching the live view see it scroll under the game, so while "
                   "the view is on, give one with most moves, not only at milestones.",
}

# With the live view on, a game call's result reminds the agent to narrate
# after this many calls in a row without a thought (and every as many after).
QUIET_NUDGE = 8


def _keys_label(keys, limit=24):
    from .spectator import key_label

    parts = [key_label(k) for k in keys[:limit]]
    text = "".join(p if len(p) == 1 else "<%s>" % p for p in parts)
    return text + ("..." if len(keys) > limit else "")


class GameSession:
    """One game running in a background thread on a VirtualTerminal."""

    def __init__(self):
        self.term = None
        self.thread = None
        self.exit_code = None
        self.error = None
        self.lock = threading.Lock()
        self.spectator = None   # pyularn.spectator.Spectator, once bound
        self.watch = None       # (host, port) from --watch, bound lazily
        self.watch_retry_at = 0.0
        self.game_id = 0
        self.seed = None
        self.outcome = None     # set by the death hook once the game is lost or won
        self.record_dir = None  # from --record
        self.recorder = None    # pyularn.recorder.RunRecorder for this game
        self.waiting = None     # what the game is waiting for; see _hook_input
        self.quiet = 0          # game calls in a row without a thought (live view on)
        self.nudge_due = False  # the next result reminds the agent to narrate

    def ensure_spectator(self, force=False):
        """Bind the --watch port if not bound yet.  Binding waits for the
        first game, so an idle server (e.g. another session's) never holds
        the port, and a failed bind is retried while the game runs."""
        if self.spectator is not None or self.watch is None:
            return self.spectator
        now = time.monotonic()
        if not force and now < self.watch_retry_at:
            return None
        self.watch_retry_at = now + 5
        from . import spectator
        host, port = self.watch
        self.spectator = spectator.start(port, host)
        return self.spectator

    # ----------------------------------------------------------- lifecycle
    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, seed=None, argv=None, thought=None, action=None):
        from . import engine, term_virtual, ularn

        self.stop()
        engine.reset()  # fresh globals, as if the game were a new process
        if seed is None:
            # The C game seeds from the clock.  Pick the seed here instead so
            # it can be reported, and any game can be replayed.
            seed = random.SystemRandom().randrange(1, 2 ** 31)
        self.seed = seed
        header.set_seed(seed)
        self._hook_death()
        self._hook_input()
        self.term = term_virtual.VirtualTerminal()
        self.exit_code = None
        self.error = None
        self.outcome = None
        self.recorder = None
        self.quiet, self.nudge_due = 0, False
        self.game_id += 1
        self.ensure_spectator(force=True)
        if self.spectator is not None or self.watch is not None:
            self.term.on_frame = self._on_frame
        # Before the game runs, so the thought comes ahead of its first screen.
        self.publish_thought(thought, action)

        def target():
            try:
                self.exit_code = ularn.run_game(self.term, argv or ["ularn"])
            except BaseException:  # keep the server alive whatever happens
                self.error = traceback.format_exc()
                self.term.mark_finished()

        self.thread = threading.Thread(target=target, name="ularn-game", daemon=True)
        self.thread.start()
        self.term.wait_for_input(15)

    def _on_frame(self, term):
        """Publish the screen to the spectator (runs on the game thread,
        while the game is at a consistent point just before reading a key)."""
        from . import spectator

        if term is not self.term:  # a stale game shutting down
            return
        if self.ensure_spectator() is None:  # port still taken; retry later
            return
        try:
            state = self.state()
        except Exception:
            state = None
        self.spectator.publish(spectator.make_frame(
            term, self.game_id, "game over" if term.finished else "playing", state))

    def publish_thought(self, text, action=None):
        """Show the agent's narration on the live page (ahead of the frames
        its keys produce).  A no-op without --watch.  Every game call comes
        through here, with or without a thought, to count quiet stretches."""
        text = str(text or "").strip()[:MAX_THOUGHT]
        if self.ensure_spectator() is None:
            return
        if not text:
            self.quiet += 1
            self.nudge_due = self.quiet % QUIET_NUDGE == 0
            return
        self.quiet = 0
        from . import player, spectator

        self.spectator.publish({
            "type": "thought", "game": self.game_id, "text": text,
            "action": action, "turn": player.gtime, "t": spectator.now_ms(),
        })

    def stop(self):
        if self.term is not None and self.running:
            self.term.shutdown()
            self.thread.join(5)
        self.close_recording()

    # ----------------------------------------------------------- outcome
    def _hook_death(self):
        """Note why the game ended.  Every ending goes through scores.died(),
        which the other modules look up at call time, so wrapping it here
        leaves the engine itself untouched."""
        from . import scores

        original = scores.died

        def died(Reason, Monster):
            try:
                self.outcome = self._death_outcome(Reason, Monster)
            except Exception:  # never let bookkeeping break the game
                traceback.print_exc(file=sys.stderr)
            original(Reason, Monster)
            # died() only returns when life protection revived the player.
            self.outcome = None

        scores.died = died

    def _hook_input(self):
        """Keep track of what kind of input the game is blocked on: a command
        on the map, or a prompt and the keys it accepts.  As with the death
        hook, the engine's own functions are wrapped, not changed."""
        from . import ularn_win

        self.waiting = None

        def wrap(name, kind):
            original = getattr(ularn_win, name)

            def wrapper(*args, **kwargs):
                previous = self.waiting
                self.waiting = {"kind": kind,
                                "answers": args[1] if kind == "prompt" and len(args) > 1 else None}
                try:
                    return original(*args, **kwargs)
                finally:
                    self.waiting = previous

            setattr(ularn_win, name, wrapper)

        wrap("get_normal_input", "command")
        wrap("get_prompt_input", "prompt")

    def input_state(self):
        """What the next key will be read as, for agents."""
        if self.term is None or self.term.finished:
            return {"kind": "none"}
        w = self.waiting
        if not w:
            return {"kind": "other"}  # typing a number, a name, a spell code...
        out = {"kind": w["kind"]}
        if w["answers"]:
            names = {chr(27): "<esc>", chr(13): "<enter>", " ": "<space>", chr(12): "<c-l>"}
            out["answers"] = [names.get(ch, ch) for ch in w["answers"]]
        return out

    def _progress(self):
        """How far the game got; shared by every kind of outcome."""
        from . import player, dungeon, itm, potion

        c = player.c
        lev = dungeon.level
        return {
            "seed": self.seed,
            "character_class": (player.char_class or "").strip() or None,
            "difficulty": c[player.HARDGAME],
            "dungeon_level": dungeon.levelname[lev].strip()
            if 0 <= lev < len(dungeon.levelname) else lev,
            "deepest": _deepest(),
            "turns": player.gtime,
            "mobuls_left": _mobuls_left(),
            "character_level": c[player.LEVEL],
            "experience": c[player.EXPERIENCE],
            "has_cure": any(player.iven[i] == itm.OPOTION
                            and player.ivenarg[i] == potion.PCUREDIANTH
                            for i in range(player.IVENSIZE)),
        }

    def _death_outcome(self, Reason, Monster):
        from . import monster, scores

        won = Reason == scores.DIED_WINNER
        killer = None
        if Reason == scores.DIED_MONSTER:
            killer = monster.monster[Monster].name
            reason = "killed by %s %s" % ("an" if killer[:1] in "aeiou" else "a", killer)
        elif 0 <= Reason < len(scores.whydead):
            reason = scores.whydead[Reason]
        else:  # DIED_QUICK_QUIT has no message of its own
            reason = "quit"
        if won:
            result = "won"
        elif Reason == scores.DIED_SUSPENDED:
            result = "saved"
        elif Reason in (scores.DIED_QUIT, scores.DIED_QUICK_QUIT):
            result = "quit"
        else:
            result = "died"
        out = {"result": result, "won": won, "reason": reason, "killer": killer,
               "score": scores.calc_score(1 if won else 0)}
        out.update(self._progress())
        return out

    def final_outcome(self):
        """The outcome once the game is over, else None.  A game that ended
        without dying or winning (end_game, a new new_game, a crash) is
        reported as "stopped" or "crashed"."""
        if self.outcome is not None:
            return self.outcome
        if self.term is None or not self.term.finished:
            return None
        out = {"result": "crashed" if self.error else "stopped", "won": False,
               "reason": "the game crashed" if self.error else "stopped by the agent",
               "killer": None, "score": None}
        try:
            out.update(self._progress())
        except Exception:
            traceback.print_exc(file=sys.stderr)
        if self.error:
            out["error"] = self.error.strip().splitlines()[-1]
        return out

    # ----------------------------------------------------------- recording
    def begin_recording(self, requested_difficulty=None, strategy=None, hypotheses=()):
        if self.record_dir is None or self.error:
            return
        from . import recorder

        state = self.state()
        meta = {"seed": self.seed, "game": self.game_id,
                "character_class": state.get("character_class"),
                "difficulty": state.get("difficulty"),
                "requested_difficulty": requested_difficulty,
                "strategy": strategy, "hypotheses": list(hypotheses),
                "notes": None,
                "version": header.PYULARN_VERSION}
        try:
            self.recorder = recorder.RunRecorder(self.record_dir, meta, state)
        except OSError:
            traceback.print_exc(file=sys.stderr)
            self.recorder = None

    def record_action(self, tool, args, thought=None, result=None):
        """Log a tool call after the game handled it, and close the log once
        the game is over."""
        rec = self.recorder
        if rec is None or rec.closed:
            return
        try:
            rec.action(tool, args, str(thought or "").strip()[:MAX_THOUGHT] or None,
                       self.state(), self.screen(), result=result)
        except Exception:
            traceback.print_exc(file=sys.stderr)
        if self.final_outcome() is not None:
            self.close_recording()

    def close_recording(self):
        rec = self.recorder
        if rec is None or rec.closed:
            return
        try:
            outcome = self.final_outcome() or {"result": "stopped", "won": False}
            rec.close(outcome, self.state(), self.screen())
        except Exception:
            traceback.print_exc(file=sys.stderr)

    def send(self, keys, timeout=15):
        if self.term is None:
            raise ToolError("No game in progress. Call new_game first.")
        if self.term.finished:
            raise ToolError("The game has ended. Call new_game to play again.")
        self.term.feed(keys)
        self.term.wait_for_input(timeout)

    # ----------------------------------------------------------- views
    def screen(self):
        if self.term is None:
            return "(no game)"
        return self.term.text(ascii_walls=True)

    def status_line(self):
        if self.term is None:
            return "no game"
        if self.error:
            return "game crashed:\n" + self.error
        if self.term.finished:
            return "game over (exit code %s)" % self.exit_code
        if self.term.is_waiting():
            return "waiting for input"
        return "busy"

    def state(self):
        """Structured snapshot of the player.  Only valid while the game
        thread is blocked waiting for input (or finished)."""
        from . import player, dungeon, itm, show, spell, ularn_game, ularn_win

        c = player.c
        lev = dungeon.level
        st = {
            "status": self.status_line(),
            "seed": self.seed,
            "character_class": (player.char_class or "").strip() or None,
            "difficulty": c[player.HARDGAME],
            "dungeon_level": dungeon.levelname[lev].strip() if 0 <= lev < len(dungeon.levelname) else lev,
            "level_index": lev,
            "deepest": _deepest(),
            "position": {"x": player.playerx, "y": player.playery},
            "turns": player.gtime,
            "time": {"turn_limit": ularn_game.TIMELIMIT, "mobuls_left": _mobuls_left()},
            "rank": player.class_[c[player.LEVEL] - 1].strip()
            if 0 < c[player.LEVEL] <= len(player.class_) else "",
            "stats": {
                "hp": c[player.HP], "hp_max": c[player.HPMAX],
                "spells": c[player.SPELLS], "spells_max": c[player.SPELLMAX],
                "ac": c[player.AC], "wc": c[player.WCLASS],
                "level": c[player.LEVEL], "experience": c[player.EXPERIENCE],
                "gold": c[player.GOLD], "bank": c[player.BANKACCOUNT],
                "str": c[player.STRENGTH], "int": c[player.INTELLIGENCE],
                "wis": c[player.WISDOM], "con": c[player.CONSTITUTION],
                "dex": c[player.DEXTERITY], "cha": c[player.CHARISMA],
            },
        }

        inv = []
        for i in range(player.IVENSIZE):
            if player.iven[i] != itm.ONOTHING:
                text = _capture(show.show3, i).strip()
                inv.append(text)
        st["inventory"] = inv

        effects = []
        for e in ularn_win._get_bot_data():
            if c[e.typ]:
                effects.append(e.string.strip())
        for idx, name in ((player.BLINDCOUNT, "Blind"), (player.CONFUSE, "Confused"),
                          (player.AGGRAVATE, "Aggravate")):
            if c[idx]:
                effects.append(name)
        st["effects"] = effects

        st["known_spells"] = [
            "%s (%s)" % (spell.spelcode[i], spell.spelname[i].strip())
            for i in range(spell.SPELL_COUNT) if player.spelknow[i]
        ]
        st["monsters"] = _visible_monsters()
        from . import skills
        st["objects"] = skills.known_objects(1000)
        st["input"] = self.input_state()
        on_map = ularn_win.CurrentDisplayMode == ularn_win.DISPLAY_MAP
        st["display"] = "map" if on_map else "text"
        st["map"] = skills.map_rows()
        # Below the map and the two status lines the screen shows the latest
        # messages.  In text mode (shops, inventory) the whole screen is text.
        lines = self.term.text(ascii_walls=True).split("\n")
        st["messages"] = [l.strip() for l in lines[MESSAGE_ROW:] if l.strip()] if on_map else []
        outcome = self.final_outcome()
        if outcome is not None:
            st["outcome"] = outcome
        return st


def _mobuls_left():
    """Time left before the daughter dies, as the inventory screen counts it."""
    from . import player, ularn_game

    return (ularn_game.TIMELIMIT // 100) - ((player.gtime // 100) + 1)


def _deepest():
    """The deepest dungeon and volcano levels visited so far (0 = none)."""
    from . import dungeon

    been = dungeon.beenhere
    dungeon_levels = [i for i in range(1, dungeon.MAXLEVEL) if been[i]]
    volcano_levels = [i - dungeon.DBOTTOM for i in range(dungeon.MAXLEVEL, dungeon.NLEVELS) if been[i]]
    return {"dungeon": max(dungeon_levels, default=0), "volcano": max(volcano_levels, default=0)}


def _visible_monsters():
    from . import skills

    return skills.visible_monsters()


def _capture(fn, *args):
    """Run a show.* function and return what it would have printed."""
    from . import ularn_win

    buf = io.StringIO()
    saved = ularn_win.Print, ularn_win.Printf, ularn_win.Printc, ularn_win.Standout

    def p(s):
        buf.write(str(s))

    def pf(fmt, *a):
        try:
            buf.write(fmt % a if a else fmt)
        except (TypeError, ValueError):
            buf.write(fmt)

    ularn_win.Print, ularn_win.Printf, ularn_win.Printc, ularn_win.Standout = p, pf, p, p
    try:
        fn(*args)
    finally:
        ularn_win.Print, ularn_win.Printf, ularn_win.Printc, ularn_win.Standout = saved
    return buf.getvalue()


class ToolError(Exception):
    pass


# ======================================================================= tools

SESSION = GameSession()


def _result(include_state=False, note=None):
    parts = []
    if note:
        parts.append(note)
    parts.append("Status: " + SESSION.status_line())
    parts.append("Screen:\n" + SESSION.screen())
    if include_state and SESSION.term is not None and not SESSION.error:
        parts.append("State:\n" + json.dumps(SESSION.state(), indent=1))
    else:
        outcome = SESSION.final_outcome()
        if outcome is not None:  # the state already carries it
            parts.append("Outcome:\n" + json.dumps(outcome, indent=1))
    if SESSION.nudge_due:
        SESSION.nudge_due = False
        parts.append("Live view: your last %d moves had no `thought`, so the people "
                     "watching cannot tell what you are doing. Add a short `thought` "
                     "(what you are doing and why) to your next move." % SESSION.quiet)
    return "\n\n".join(parts)


def _campaign_defaults(args):
    """When `strategy` names a strategy of the campaign, the game takes its
    hypotheses, character class, difficulty and seed from there."""
    from . import learn

    sid = str(args.get("strategy") or "").strip()
    if not sid or SESSION.record_dir is None:
        return args
    root = _runs_root()
    if not learn.exists(root):
        return args
    campaign = learn.load(root)
    if sid not in campaign["strategies"]:
        return args
    args = dict(args)
    args["_campaign_root"] = root
    args["hypotheses"] = learn.changes(campaign, sid) or [campaign["strategies"][sid]["change"]]
    args["difficulty"] = campaign["difficulty"]
    from . import runs
    seed = learn.next_seed(campaign, sid, learn.stats(campaign, runs.list_runs(root)))
    if seed is not None:        # the trial's next seed; None once they are all played
        args["seed"] = seed
    else:
        args.pop("seed", None)
    cls = learn.character_class(campaign, sid)
    if cls:
        args["character_class"] = cls
    return args


_OWN_HOME = []   # the PYULARN_HOME this process started with, once noted


def _set_home(campaign_root):
    """Give a campaign game a scoreboard of its own.

    Ularn remembers a win: that player's next game starts one difficulty
    higher, owing taxes.  A campaign needs several wins at one difficulty
    and games that do not affect each other, so each of its games runs with
    an empty home folder.  Other games keep the home the server started with.
    """
    import os
    import shutil

    if not _OWN_HOME:
        _OWN_HOME.append(os.environ.get("PYULARN_HOME"))
    if campaign_root is None:
        if _OWN_HOME[0] is None:
            os.environ.pop("PYULARN_HOME", None)
        else:
            os.environ["PYULARN_HOME"] = _OWN_HOME[0]
        return
    home = os.path.join(campaign_root, "home", "server-%d" % os.getpid())
    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(home, exist_ok=True)
    os.environ["PYULARN_HOME"] = home


def tool_new_game(args):
    args = _campaign_defaults(args)
    SESSION.stop()   # the game in progress, if any, ends in the home it was started in
    _set_home(args.get("_campaign_root"))
    cls = str(args.get("character_class", "") or "").strip().lower()
    cls = CLASSES.get(cls, cls)
    if cls and cls not in "abcdefgh":
        raise ToolError("character_class must be a-h or one of: " + ", ".join(CLASSES))
    name = str(args.get("player_name") or "Agent")[:20]
    difficulty = args.get("difficulty")
    argv = None
    if difficulty is not None:
        if isinstance(difficulty, bool) or not isinstance(difficulty, int) \
                or not 0 <= difficulty <= 100:
            raise ToolError("difficulty must be a whole number from 0 to 100")
        argv = ["ularn", "-d", str(difficulty)]
    strategy = str(args.get("strategy") or "").strip()[:100] or None
    hypotheses = _string_list(args, "hypotheses")
    SESSION.start(seed=args.get("seed"), argv=argv, thought=args.get("thought"),
                  action="new game" + (" (%s)" % CLASS_NAMES[cls] if cls else ""))
    # Walk through the start-up screens unless the caller wants them.
    if args.get("skip_intro", True):
        for _ in range(6):
            scr = SESSION.screen()
            if SESSION.term.finished:
                break
            if "Who are you" in scr:
                SESSION.send(list(name) + ["\r"])
            elif "what are ya" in scr and cls:
                SESSION.send(cls)
            elif "Press return to continue" in scr:
                SESSION.send("\r")
            else:
                break
    note = "New game started."
    if difficulty is not None and not SESSION.error:
        from . import player
        actual = player.c[player.HARDGAME]
        if actual != difficulty:
            note += (" Difficulty is %d, not the %d asked for: this player has already "
                     "won, and the scoreboard does not allow an easier game."
                     % (actual, difficulty))
    SESSION.begin_recording(requested_difficulty=difficulty, strategy=strategy,
                            hypotheses=hypotheses)
    if SESSION.recorder is not None:
        note += (" Recording this game to " + SESSION.recorder.dir + " as run "
                 + SESSION.recorder.run_id + ". When it is over, call summarize_run.")
    if SESSION.spectator is not None:
        note += (" Live view for the user: " + SESSION.spectator.url +
                 " (pass `thought` with your moves to narrate for viewers)")
    elif SESSION.watch is not None:
        note += (" Live view unavailable: port %d is in use (another pyularn "
                 "server?); retrying every few seconds." % SESSION.watch[1])
    return _result(include_state=True, note=note)


def tool_send_keys(args):
    keys = parse_keys(str(args.get("keys", "")))
    if not keys:
        raise ToolError("keys is empty")
    if SESSION.term is not None and not SESSION.term.finished:
        SESSION.publish_thought(args.get("thought"), "keys " + _keys_label(keys))
    SESSION.send(keys)
    SESSION.record_action("send_keys", {"keys": str(args.get("keys", ""))}, args.get("thought"))
    return _result(include_state=bool(args.get("include_state", False)))


def tool_move(args):
    d = str(args.get("direction", "")).strip().lower()
    if d not in DIRECTIONS:
        raise ToolError("direction must be one of: " + ", ".join(sorted(DIRECTIONS)))
    key = DIRECTIONS[d]
    if args.get("run"):
        key = key.upper()
    count = max(1, min(int(args.get("count", 1) or 1), 50))
    if SESSION.term is not None and not SESSION.term.finished:
        SESSION.publish_thought(args.get("thought"), "%s %s%s" % (
            "run" if args.get("run") else "move", d, " x%d" % count if count > 1 else ""))
    SESSION.send([key] * count)
    SESSION.record_action("move", {"direction": d, "count": count, "run": bool(args.get("run"))},
                          args.get("thought"))
    return _result(include_state=bool(args.get("include_state", False)))


def tool_get_screen(args):
    return _result(include_state=False)


def tool_get_state(args):
    if SESSION.term is None:
        raise ToolError("No game in progress. Call new_game first.")
    return json.dumps(SESSION.state(), indent=1)


def tool_key_reference(args):
    return KEY_REFERENCE


def tool_end_game(args):
    SESSION.stop()
    return "Game stopped."


MAX_NOTE = 1000   # characters per post-mortem entry
MAX_NOTES = 20    # entries per list


def _string_list(args, name):
    value = args.get(name)
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ToolError("%s must be a list of strings" % name)
    return [v.strip()[:MAX_NOTE] for v in value if v.strip()][:MAX_NOTES]


def _runs_root():
    import os

    if SESSION.record_dir is None:
        raise ToolError("Games are not being recorded: start the server with --record DIR.")
    return os.path.abspath(os.path.expanduser(SESSION.record_dir))


def _run_path(args):
    """The folder of the run a tool call is about: `run_id`, else the run of
    this session's latest game, else the newest run on disk."""
    from . import runs

    root = _runs_root()
    run_id = args.get("run_id")
    if not run_id:
        if SESSION.recorder is not None:
            return SESSION.recorder.dir
        latest = runs.list_runs(root)
        if not latest:
            raise ToolError("No runs have been recorded yet.")
        run_id = latest[0]["run_id"]
    try:
        return runs.run_dir(root, run_id)
    except runs.RunError as e:
        raise ToolError(str(e))


def tool_summarize_run(args):
    from . import runs

    synopsis = str(args.get("synopsis") or "").strip()[:4 * MAX_NOTE]
    if not synopsis:
        raise ToolError("synopsis is empty")
    path = _run_path(args)
    if runs.load_meta(path).get("outcome") is None:
        raise ToolError("That game is still in progress. Finish it or call end_game first.")
    runs.set_notes(path, synopsis, _string_list(args, "went_wrong"),
                   _string_list(args, "worked"), _string_list(args, "next_try"))
    runs.write_index(_runs_root())
    from . import learn
    learn.refresh(_runs_root())
    import os
    return "Post-mortem saved to " + os.path.join(path, "summary.md")


def tool_list_runs(args):
    from . import runs

    limit = args.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ToolError("limit must be a whole number from 1 to 200")
    found = runs.list_runs(_runs_root())
    for key in ("difficulty", "strategy"):
        if args.get(key) is not None:
            found = [m for m in found if m.get(key) == args[key]]
    return json.dumps({"total": len(found),
                       "runs": [runs.brief(m) for m in found[:limit]]}, indent=1)


def tool_get_run(args):
    from . import runs

    return runs.write_summary(_run_path(args))


# ----------------------------------------------------------------- learning

def _learn(fn):
    """Call into pyularn.learn, turning its errors into tool errors."""
    from . import learn

    try:
        return fn(learn, _runs_root())
    except learn.LearnError as e:
        raise ToolError(str(e))


def tool_get_briefing(args):
    return _learn(lambda learn, root: learn.briefing(root))


def tool_propose_strategy(args):
    cls = str(args.get("character_class") or "").strip().lower()
    if cls and cls not in CLASSES:
        raise ToolError("character_class must be one of: " + ", ".join(CLASSES))
    s = _learn(lambda learn, root: learn.propose(
        root, args.get("title"), args.get("change"), parent=args.get("parent") or None,
        character_class=cls or None, retry_reason=args.get("retry_reason")))

    def up_next(learn, root):
        from . import runs
        campaign = learn.load(root)
        return learn.choose_next(campaign, learn.stats(campaign, runs.list_runs(root)))[0]

    nxt = _learn(up_next)
    text = "Strategy %s added, on trial against %s. " % (s["id"], s["parent"])
    if nxt == s["id"]:
        text += "It is the one to play next: new_game(strategy=\"%s\")." % s["id"]
    else:
        text += "It waits its turn: the next game is %s (see get_briefing)." % nxt
    return text


def tool_add_lesson(args):
    lesson = _learn(lambda learn, root: learn.add_lesson(
        root, args.get("text"), evidence=_string_list(args, "evidence"),
        confidence=str(args.get("confidence") or "tentative")))
    return "Lesson %s saved as %s, citing %d run%s." % (
        lesson["id"], lesson["status"], len(lesson["evidence"]),
        "" if len(lesson["evidence"]) == 1 else "s")


def tool_retract_lesson(args):
    lesson = _learn(lambda learn, root: learn.retract_lesson(
        root, str(args.get("lesson_id") or "").strip(), args.get("reason")))
    return "Lesson %s retracted." % lesson["id"]


# ----------------------------------------------------------------- skills

def _int_arg(args, name, default, low, high):
    value = args.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolError("%s must be a whole number from %d to %d" % (name, low, high))
    return value


def _skill_tool(name, label, run):
    """Make the handler of a skill tool.  `label(args)` is the short text
    for the live view; `run(skills, args)` calls the skill."""

    def handler(args):
        from . import skills

        if SESSION.term is None:
            raise ToolError("No game in progress. Call new_game first.")
        if SESSION.term.finished:
            raise ToolError("The game has ended. Call new_game to play again.")
        SESSION.publish_thought(args.get("thought"), label(args))
        try:
            report = run(skills, args)
        except skills.SkillError as e:
            raise ToolError(str(e))
        logged = {k: v for k, v in args.items() if k not in ("thought", "include_state")}
        SESSION.record_action(name, logged, args.get("thought"), result=report)
        return _result(include_state=bool(args.get("include_state", False)),
                       note="Skill result:\n" + json.dumps(report, indent=1))

    return handler


def _travel(skills, args):
    target, x, y = args.get("target"), args.get("x"), args.get("y")
    if target is None and (x is None or y is None):
        raise ToolError("give a target, or both x and y")
    if target is None:
        x = _int_arg(args, "x", None, 0, 66)
        y = _int_arg(args, "y", None, 0, 16)
    return skills.travel_to(SESSION, target=target, x=x, y=y,
                            max_steps=_int_arg(args, "max_steps", 300, 1, 2000))


def _fight(skills, args):
    min_hp = args.get("min_hp", 0.35)
    if isinstance(min_hp, bool) or not isinstance(min_hp, (int, float)) or not 0 <= min_hp < 1:
        raise ToolError("min_hp is a fraction of maximum HP, from 0 up to 1")
    return skills.fight(SESSION, max_turns=_int_arg(args, "max_turns", 40, 1, 500),
                        min_hp=min_hp, reach_distance=_int_arg(args, "reach", 5, 1, 66))


tool_explore = _skill_tool(
    "explore", lambda a: "explore" + (" until %s" % a["until"] if a.get("until") else ""),
    lambda skills, a: skills.explore(SESSION, max_steps=_int_arg(a, "max_steps", 300, 1, 2000),
                                     until=a.get("until")))
tool_travel_to = _skill_tool(
    "travel_to", lambda a: "travel to %s" % (a.get("target") or "%s,%s" % (a.get("x"), a.get("y"))),
    _travel)
tool_take_stairs = _skill_tool(
    "take_stairs", lambda a: "take the stairs %s" % a.get("direction", "down"),
    lambda skills, a: skills.take_stairs(SESSION, direction=str(a.get("direction", "down")),
                                         volcano=bool(a.get("volcano", False)),
                                         max_steps=_int_arg(a, "max_steps", 300, 1, 2000)))
tool_fight = _skill_tool("fight", lambda a: "fight", _fight)
tool_flee = _skill_tool(
    "flee", lambda a: "flee",
    lambda skills, a: skills.flee(SESSION, max_steps=_int_arg(a, "max_steps", 20, 1, 500),
                                  safe_distance=_int_arg(a, "safe_distance", 8, 2, 66)))
tool_buy = _skill_tool(
    "buy", lambda a: "buy " + ", ".join(_string_list(a, "items")) if a.get("items") else "price list",
    lambda skills, a: skills.buy(SESSION, items=_string_list(a, "items"),
                                 leave=bool(a.get("leave", True))))


TOOLS = [
    {
        "name": "new_game",
        "description": "Start a new game of Ularn (ends any game in progress). Returns the screen and player state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "character_class": {
                    "type": "string",
                    "description": "Class letter a-h or name: ogre, wizard, klingon, elf, rogue, adventurer, dwarf, rambo. Leave empty to pick on the class screen yourself.",
                },
                "seed": {"type": "integer", "description": "Optional RNG seed for a reproducible game. Without one a random seed is used and reported in the state."},
                "difficulty": {"type": "integer", "minimum": 0, "maximum": 100,
                               "description": "Difficulty level, 0 (default, easiest) to 100. Once this player has won, the game will not go below the level after the last win."},
                "strategy": {"type": "string", "description": "Optional: a short name for the strategy this game follows. Stored with the recording so runs can be compared."},
                "hypotheses": {"type": "array", "items": {"type": "string"},
                               "description": "Optional: what this game is testing, one idea per entry, e.g. 'bank gold before level 5'. Stored with the recording."},
                "player_name": {"type": "string", "description": "Name used if the game asks who you are."},
                "skip_intro": {"type": "boolean", "description": "Automatically pass the intro screens (default true)."},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_new_game,
    },
    {
        "name": "send_keys",
        "description": "Send keystrokes to the game and return the resulting screen. Plain characters are sent literally; use <esc>, <enter>, <space>, <bs>, <up>/<down>/<left>/<right>, <c-r> for special keys. Call key_reference for the command list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Keys to send, e.g. 'i', 'qa', 'cmle<enter>', '<esc>'."},
                "include_state": {"type": "boolean", "description": "Also return structured player state."},
                "thought": THOUGHT_SCHEMA,
            },
            "required": ["keys"],
        },
        "handler": tool_send_keys,
    },
    {
        "name": "move",
        "description": "Move the player one or more steps in a compass direction (or run until something interesting).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["n", "s", "e", "w", "ne", "nw", "se", "sw"]},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Number of steps (default 1)."},
                "run": {"type": "boolean", "description": "Run in that direction instead of stepping."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
            "required": ["direction"],
        },
        "handler": tool_move,
    },
    {
        "name": "get_screen",
        "description": "Return the current 80x24 game screen without sending input.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_screen,
    },
    {
        "name": "get_state",
        "description": "Return structured player state as JSON: stats, HP, gold, dungeon level, position, inventory, active effects, known spells, difficulty, seed, time left, the deepest levels visited, the map as the player knows it (17 rows of 67 characters: # wall, . explored floor, blank unexplored, otherwise the screen's symbols), the monsters shown on the map, the objects known on this level (stairs, buildings, items), the latest messages, what kind of input the game is waiting for and, once the game is over, its outcome.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_state,
    },
    {
        "name": "key_reference",
        "description": "Return the list of Ularn commands, map symbols and the goal of the game.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_key_reference,
    },
    {
        "name": "end_game",
        "description": "Stop the game in progress without saving.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_end_game,
    },
    {
        "name": "explore",
        "description": "Skill: explore the current level in one call. Walks to the nearest unexplored area again and again, opening doors, picking up gold and ignoring other things it walks over. Stops and says why when the level is explored, a monster appears or comes adjacent, HP drops, the level changes, or the game asks something. The result lists what was discovered.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "until": {"type": "string", "description": "Stop as soon as one of these is known: a target name (stairs_down, stairs_up, potion, ...) or a map symbol such as % or !."},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 2000, "description": "Most steps to take (default 300)."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_explore,
    },
    {
        "name": "travel_to",
        "description": "Skill: walk to a place by the cheapest known route, avoiding known traps. Give a target (the nearest one known is used) or x and y. Targets: stairs_down, stairs_up, dungeon_entrance, volcano, home, store, bank, college, trading_post, lrs, dealer, elevator, altar, fountain, throne, gold, potion, scroll, book, chest, or any map symbol such as ( or [. A prompt raised by the destination is left for you to answer. Stops early for the same reasons as explore.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "A target name or a one-character map symbol."},
                "x": {"type": "integer", "description": "Map column, 0-66 (as in get_state's position)."},
                "y": {"type": "integer", "description": "Map row, 0-16."},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 2000, "description": "Most steps to take (default 300)."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_travel_to,
    },
    {
        "name": "take_stairs",
        "description": "Skill: go to the known stairs and take them. In town, down means the dungeon entrance (or the volcanic shaft with volcano=true); on dungeon level 1, up means the exit to town. Returns not_found if the stairs have not been seen yet: use explore with until=stairs_down first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["down", "up"], "description": "Default down."},
                "volcano": {"type": "boolean", "description": "In town, climb down the volcanic shaft instead of entering the dungeon."},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 2000},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_take_stairs,
    },
    {
        "name": "fight",
        "description": "Skill: attack the nearest visible monster, walking up to it if needed, and keep going until no monster is within reach. Stops with low_hp when HP falls to min_hp of the maximum, so you can flee, heal or cast instead. Melee only: it does not cast spells or use items.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_hp": {"type": "number", "minimum": 0, "exclusiveMaximum": 1, "description": "Stop when HP is at or below this fraction of maximum (default 0.35)."},
                "reach": {"type": "integer", "minimum": 1, "maximum": 66, "description": "Only go after monsters within this many cells (default 5)."},
                "max_turns": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Most attacks and steps (default 40)."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_fight,
    },
    {
        "name": "flee",
        "description": "Skill: step away from the visible monsters until none is within safe_distance. It looks one step ahead only, so it can end in a dead end (result cornered). To run to a specific place, such as the stairs, use travel_to or take_stairs instead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "safe_distance": {"type": "integer", "minimum": 2, "maximum": 66, "description": "Stop once the nearest monster is this far away (default 8)."},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Most steps to take (default 20)."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_flee,
    },
    {
        "name": "buy",
        "description": "Skill: buy items at the DND store in town, walking there and going in if needed. Name items as the store lists them, e.g. 'chain mail' or 'potion of healing'; part of a name works if it matches one item. With no items it returns the store's price list for what is in stock. The result says what was bought, what was not and why.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}, "description": "Items to buy, in order. Leave out to get the price list."},
                "leave": {"type": "boolean", "description": "Leave the store afterwards (default true)."},
                "include_state": {"type": "boolean"},
                "thought": THOUGHT_SCHEMA,
            },
        },
        "handler": tool_buy,
    },
    {
        "name": "summarize_run",
        "description": "Write the post-mortem of a recorded game once it is over: what happened, what went wrong and what the next game should try. It is saved with the recording and shown by list_runs and get_run, so later games can learn from it. Needs the server's --record option.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "synopsis": {"type": "string", "description": "A few sentences on how the game went and why it ended."},
                "went_wrong": {"type": "array", "items": {"type": "string"},
                               "description": "Mistakes and bad luck, one per entry, most important first."},
                "worked": {"type": "array", "items": {"type": "string"},
                           "description": "What went well and is worth repeating."},
                "next_try": {"type": "array", "items": {"type": "string"},
                             "description": "What the next game will do differently or test."},
                "run_id": {"type": "string", "description": "The run to write about (default: this session's latest game)."},
            },
            "required": ["synopsis"],
        },
        "handler": tool_summarize_run,
    },
    {
        "name": "list_runs",
        "description": "List recorded games, newest first: class, difficulty, strategy, how each ended, how deep it got, and the post-mortem's synopsis and next_try. Read this before a new game to build on earlier ones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Most runs to return (default 20)."},
                "difficulty": {"type": "integer", "description": "Only runs at this difficulty."},
                "strategy": {"type": "string", "description": "Only runs with this strategy name."},
            },
        },
        "handler": tool_list_runs,
    },
    {
        "name": "get_briefing",
        "description": "Read this before each game of a learning campaign. It names the strategy to play next and what it tests, lists the playbook's lessons, shows every strategy tried with how far each got, summarises the latest games, and sets out the steps of one cycle. Needs the server's --record option.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_briefing,
    },
    {
        "name": "propose_strategy",
        "description": "Put a new strategy on trial: a proven strategy plus ONE specific change, so the effect of that change can be seen by comparing the two. It plays a fixed number of games and is kept only if it gets clearly further than its parent; get_briefing explains the rules. An idea that was already abandoned is refused unless retry_reason says what has changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "A short name, e.g. 'Armour before the dungeon'."},
                "change": {"type": "string", "description": "The one thing it does differently from its parent, specific enough to follow, e.g. 'Sell the starting weapon and buy leather armor before entering the dungeon'."},
                "parent": {"type": "string", "description": "The proven strategy it builds on (default: the current base)."},
                "retry_reason": {"type": "string", "description": "Only when proposing an idea that was abandoned before: what is different this time."},
                "character_class": {"type": "string", "description": "Only if the change is to play another class: ogre, wizard, klingon, elf, rogue, adventurer, dwarf or rambo."},
            },
            "required": ["title", "change"],
        },
        "handler": tool_propose_strategy,
    },
    {
        "name": "add_lesson",
        "description": "Add a lesson to the playbook that every later game reads. Cite the runs that showed it. Use confidence 'confirmed' only when more than one run agrees; a lesson seen once is 'tentative'. Repeating an existing lesson adds your evidence to it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The lesson, as an instruction a later game can act on."},
                "evidence": {"type": "array", "items": {"type": "string"}, "description": "Run ids that showed it."},
                "confidence": {"type": "string", "enum": ["tentative", "confirmed"], "description": "Default tentative."},
            },
            "required": ["text"],
        },
        "handler": tool_add_lesson,
    },
    {
        "name": "retract_lesson",
        "description": "Mark a playbook lesson as wrong, with the reason. It stays on record, struck through, so it is not learned again by mistake.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lesson_id": {"type": "string", "description": "The lesson's id from the briefing, e.g. L3."},
                "reason": {"type": "string", "description": "What showed it to be wrong."},
            },
            "required": ["lesson_id", "reason"],
        },
        "handler": tool_retract_lesson,
    },
    {
        "name": "get_run",
        "description": "Return the full summary of one recorded game: outcome, hypotheses, post-mortem, the route through the levels, lowest HP, final inventory, last thoughts and the final screen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "A run id from list_runs (default: this session's latest game)."},
            },
        },
        "handler": tool_get_run,
    },
]
TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


# ======================================================================= JSON-RPC

class Server:
    def __init__(self, out):
        self.out = out
        self.write_lock = threading.Lock()

    def send(self, msg):
        data = json.dumps(msg, ensure_ascii=False)
        with self.write_lock:
            self.out.write(data + "\n")
            self.out.flush()

    def handle(self, msg):
        """Handle one decoded JSON-RPC message; return a response or None."""
        if isinstance(msg, list):  # batch (2025-03-26)
            replies = [r for r in (self.handle(m) for m in msg) if r is not None]
            return replies or None
        if not isinstance(msg, dict):
            return _error(None, -32600, "Invalid Request")
        method = msg.get("method")
        mid = msg.get("id")
        is_request = "id" in msg
        if method is None:  # a response to something we never sent
            return None
        try:
            result = self.dispatch(method, msg.get("params") or {})
        except RpcError as e:
            return _error(mid, e.code, e.message) if is_request else None
        except Exception as e:  # pragma: no cover - defensive
            traceback.print_exc(file=sys.stderr)
            return _error(mid, -32603, "Internal error: %s" % e) if is_request else None
        if not is_request:
            return None
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def dispatch(self, method, params):
        if method == "initialize":
            want = params.get("protocolVersion")
            version = want if want in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            return {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": header.PYULARN_VERSION},
                "instructions": "Play the roguelike Ularn. Start with new_game, then use "
                                "move / send_keys and read the returned screen.  When a live view is "
                                "on, give each new_game / move / send_keys call a short `thought` "
                                "saying what you are doing and why; viewers see it under the game."
                                "  Prefer the skill tools (explore, travel_to, take_stairs, fight, "
                                "flee, buy) to single keys: each does a whole errand in one call "
                                "and stops, saying why, when something needs your decision."
                                + ("  Games are recorded and learned from: call get_briefing "
                                   "before a new game and follow the cycle it sets out (list_runs "
                                   "and get_run show earlier games in full), "
                                   "and call summarize_run when the game is over."
                                   if SESSION.record_dir else "")
                                + "\n\n" + KEY_REFERENCE,
            }
        if method == "ping":
            return {}
        if method.startswith("notifications/"):
            return None
        if method == "tools/list":
            return {"tools": [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]}
        if method == "tools/call":
            name = params.get("name")
            tool = TOOLS_BY_NAME.get(name)
            if tool is None:
                raise RpcError(-32602, "Unknown tool: %s" % name)
            try:
                with SESSION.lock:
                    text = tool["handler"](params.get("arguments") or {})
                return {"content": [{"type": "text", "text": text}], "isError": False}
            except ToolError as e:
                return {"content": [{"type": "text", "text": str(e)}], "isError": True}
            except Exception:
                return {"content": [{"type": "text", "text": "Tool failed:\n" + traceback.format_exc()}],
                        "isError": True}
        raise RpcError(-32601, "Method not found: %s" % method)

    def serve(self, inp):
        for line in inp:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self.send(_error(None, -32700, "Parse error"))
                continue
            reply = self.handle(msg)
            if reply is not None:
                self.send(reply)


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def main(argv=None):
    import argparse
    import os

    ap = argparse.ArgumentParser(prog="pyularn-mcp",
                                 description="MCP server that lets an AI agent play pyularn.")
    ap.add_argument("--watch", nargs="?", type=int, const=8765, metavar="PORT",
                    default=int(os.environ["PYULARN_WATCH"]) if os.environ.get("PYULARN_WATCH") else None,
                    help="serve a live spectator page on PORT (default 8765); "
                         "also set by the PYULARN_WATCH environment variable")
    ap.add_argument("--watch-host", default=os.environ.get("PYULARN_WATCH_HOST", "127.0.0.1"),
                    help="address for the spectator page (default 127.0.0.1)")
    ap.add_argument("--record", metavar="DIR", default=os.environ.get("PYULARN_RECORD") or None,
                    help="write each game to its own folder in DIR (see pyularn/recorder.py); "
                         "also set by the PYULARN_RECORD environment variable")
    args = ap.parse_args(argv)
    if args.watch is not None:
        SESSION.watch = (args.watch_host, args.watch)
    SESSION.record_dir = args.record

    # The protocol owns stdout; anything the game might print goes to stderr.
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n", line_buffering=True)
    inp = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    sys.stdout = sys.stderr
    try:
        Server(out).serve(inp)
    finally:
        SESSION.stop()
        if SESSION.spectator is not None:
            SESSION.spectator.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
