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
import re
import sys
import threading
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


class GameSession:
    """One game running in a background thread on a VirtualTerminal."""

    def __init__(self):
        self.term = None
        self.thread = None
        self.exit_code = None
        self.error = None
        self.lock = threading.Lock()
        self.spectator = None   # pyularn.spectator.Spectator, if --watch
        self.game_id = 0

    # ----------------------------------------------------------- lifecycle
    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, seed=None, argv=None):
        from . import engine, term_virtual, ularn

        self.stop()
        engine.reset()  # fresh globals, as if the game were a new process
        header.set_seed(seed)  # None = seed from the clock, like the C game
        self.term = term_virtual.VirtualTerminal()
        self.exit_code = None
        self.error = None
        self.game_id += 1
        if self.spectator is not None:
            self.term.on_frame = self._on_frame

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
        try:
            state = self.state()
        except Exception:
            state = None
        self.spectator.publish({
            "game": self.game_id,
            "status": "game over" if term.finished else "playing",
            "key": spectator.key_label(term.last_key),
            "rows": spectator.screen_runs(term),
            "state": state,
            "t": spectator.now_ms(),
        })

    def stop(self):
        if self.term is not None and self.running:
            self.term.shutdown()
            self.thread.join(5)

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
        from . import player, dungeon, itm, show, spell, ularn_win

        c = player.c
        lev = dungeon.level
        st = {
            "status": self.status_line(),
            "dungeon_level": dungeon.levelname[lev].strip() if 0 <= lev < len(dungeon.levelname) else lev,
            "level_index": lev,
            "position": {"x": player.playerx, "y": player.playery},
            "turns": player.gtime,
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
        return st


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
    return "\n\n".join(parts)


def tool_new_game(args):
    cls = str(args.get("character_class", "") or "").strip().lower()
    cls = CLASSES.get(cls, cls)
    if cls and cls not in "abcdefgh":
        raise ToolError("character_class must be a-h or one of: " + ", ".join(CLASSES))
    name = str(args.get("player_name") or "Agent")[:20]
    SESSION.start(seed=args.get("seed"))
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
    if SESSION.spectator is not None:
        note += " Live view for the user: " + SESSION.spectator.url
    return _result(include_state=True, note=note)


def tool_send_keys(args):
    keys = parse_keys(str(args.get("keys", "")))
    if not keys:
        raise ToolError("keys is empty")
    SESSION.send(keys)
    return _result(include_state=bool(args.get("include_state", False)))


def tool_move(args):
    d = str(args.get("direction", "")).strip().lower()
    if d not in DIRECTIONS:
        raise ToolError("direction must be one of: " + ", ".join(sorted(DIRECTIONS)))
    key = DIRECTIONS[d]
    if args.get("run"):
        key = key.upper()
    count = max(1, min(int(args.get("count", 1) or 1), 50))
    SESSION.send([key] * count)
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
                "seed": {"type": "integer", "description": "Optional RNG seed for a reproducible game."},
                "player_name": {"type": "string", "description": "Name used if the game asks who you are."},
                "skip_intro": {"type": "boolean", "description": "Automatically pass the intro screens (default true)."},
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
        "description": "Return structured player state as JSON: stats, HP, gold, dungeon level, position, inventory, active effects and known spells.",
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
                                "move / send_keys and read the returned screen.\n\n" + KEY_REFERENCE,
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
    args = ap.parse_args(argv)
    if args.watch is not None:
        from . import spectator
        SESSION.spectator = spectator.start(args.watch, args.watch_host)

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
