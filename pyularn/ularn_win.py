"""Window / input layer (port of ularn_win.h + ularn_wintty.c).

This is the curses based TTY display module of Ularn.  Instead of talking to
curses directly it keeps a tiny curses-like model (windows with their own
buffers, touch/refresh semantics and a "physical" screen image) and sends
the resulting screen changes to a pluggable :class:`Terminal` backend
(``term_curses.CursesTerminal`` for play, ``term_virtual.VirtualTerminal``
for tests and remote control).

Keys
----
``Terminal.getkey()`` returns a ``str``:

* a single character for every ordinary byte, including control characters
  (Enter is ``'\\r'`` because the C code runs curses with ``nonl()``,
  backspace ``'\\x08'``, escape ``'\\x1b'``, ctrl-R ``'\\x12'``);
* a curses key name for special keys: ``"KEY_LEFT"``, ``"KEY_RIGHT"``,
  ``"KEY_UP"``, ``"KEY_DOWN"``, ``"KEY_A1"``, ``"KEY_A3"``, ``"KEY_B2"``,
  ``"KEY_C1"``, ``"KEY_C3"`` (keypad), any other ``"KEY_*"`` name is ignored.

Attributes
----------
Attributes passed to ``Terminal.put`` are ints: a bit mask of ``A_*`` flags
or-ed with ``COLOR_PAIR(n)`` (``n`` = one of the ``C_*`` colours; every pair
is colour ``n`` on black, as set up by ``setup_colour_pairs``).
"""

import os
import struct

from .header import *
from . import ularn_game, player, dungeon, monster, itm

# =============================================================================
# Terminal backend interface
# =============================================================================

A_NORMAL = 0x00
A_STANDOUT = 0x01
A_UNDERLINE = 0x02
A_REVERSE = 0x04
A_BLINK = 0x08
A_BOLD = 0x10
A_ATTRIBUTES = 0xFF
A_COLOR = 0xFF00


def COLOR_PAIR(n):
    """Attribute bits selecting colour pair n."""
    return (n & 0xFF) << 8


def PAIR_NUMBER(attr):
    """Colour pair number encoded in an attribute."""
    return (attr & A_COLOR) >> 8


# curses colour numbers
COLOR_BLACK = 0
COLOR_RED = 1
COLOR_GREEN = 2
COLOR_YELLOW = 3
COLOR_BLUE = 4
COLOR_MAGENTA = 5
COLOR_CYAN = 6
COLOR_WHITE = 7

# Line drawing characters (curses ACS_*).  Backends that can draw the real
# alternate character set translate these; others just show the glyphs.
ACS_BLOCK = "█"
ACS_HLINE = "─"
ACS_VLINE = "│"
ACS_ULCORNER = "┌"
ACS_URCORNER = "┐"
ACS_LLCORNER = "└"
ACS_LRCORNER = "┘"
ACS_TTEE = "┬"
ACS_BTEE = "┴"
ACS_LTEE = "├"
ACS_RTEE = "┤"
ACS_PLUS = "┼"

ACS_CHARS = (ACS_BLOCK, ACS_HLINE, ACS_VLINE, ACS_ULCORNER, ACS_URCORNER,
             ACS_LLCORNER, ACS_LRCORNER, ACS_TTEE, ACS_BTEE, ACS_LTEE,
             ACS_RTEE, ACS_PLUS)


class Terminal:
    """Abstract character-cell terminal used by the window layer.

    Coordinates are 0-based, x = column, y = row.  All output is buffered
    until ``refresh()``.
    """

    def start(self):
        """Prepare the terminal for use (called by init_app)."""

    def stop(self):
        """Restore the terminal (called by close_app)."""

    def size(self):
        """Return (columns, rows)."""
        return (80, 24)

    def has_colors(self):
        """True if the terminal can show colours."""
        return False

    def init_pair(self, pair, fg, bg):
        """Define colour pair `pair` as fg on bg (curses colour numbers)."""

    def move(self, x, y):
        """Move the cursor to column x, row y."""
        raise NotImplementedError

    def put(self, s, attr=A_NORMAL):
        """Write string s at the cursor with attribute attr, advancing it."""
        raise NotImplementedError

    def clear(self):
        """Clear the whole screen."""
        raise NotImplementedError

    def clear_eol(self):
        """Clear from the cursor to the end of the line."""
        raise NotImplementedError

    def refresh(self):
        """Make all output visible."""

    def beep(self):
        """Ring the bell."""

    def getkey(self):
        """Block until a key is pressed and return it (see module doc)."""
        raise NotImplementedError

    def nap(self, ms):
        """Sleep for ms milliseconds."""


_terminal = None


def set_terminal(t):
    """Select the Terminal backend used by init_app and all output."""
    global _terminal
    _terminal = t


def get_terminal():
    """Return the current Terminal backend."""
    return _terminal


# =============================================================================
# Minimal curses model
# =============================================================================

SCREEN_COLS = 80
SCREEN_LINES = 24


class _Screen:
    """The physical screen image (curses newscr/curscr)."""

    def __init__(self, lines, cols):
        self.lines = lines
        self.cols = cols
        self.ch = [[" "] * cols for _ in range(lines)]
        self.at = [[0] * cols for _ in range(lines)]


_screen = None


class _Window:
    """A curses WINDOW: its own buffer, cursor, attribute and change marks."""

    def __init__(self, nlines, ncols, begin_y, begin_x):
        self.h = nlines
        self.w = ncols
        self.y0 = begin_y
        self.x0 = begin_x
        self.ch = [[" "] * ncols for _ in range(nlines)]
        self.at = [[0] * ncols for _ in range(nlines)]
        self.dirty = [[False] * ncols for _ in range(nlines)]
        self.cy = 0
        self.cx = 0
        self.attr = 0
        self.clearok = False
        self.scrollok = False

    def is_dirty(self):
        for row in self.dirty:
            if True in row:
                return True
        return False


def newwin(nlines, ncols, begin_y, begin_x):
    return _Window(nlines, ncols, begin_y, begin_x)


def delwin(win):
    pass


def wattrset(win, attr):
    win.attr = attr


def wmove(win, y, x):
    if 0 <= y < win.h and 0 <= x < win.w:
        win.cy = y
        win.cx = x
        return True
    return False


def waddch(win, ch):
    """Add a character at the window cursor (curses waddch semantics)."""
    if isinstance(ch, int):
        ch = chr(ch) if ch else " "
    y, x = win.cy, win.cx
    win.ch[y][x] = ch
    win.at[y][x] = win.attr
    win.dirty[y][x] = True
    x += 1
    if x >= win.w:
        if y < win.h - 1:
            win.cy = y + 1
            win.cx = 0
        elif win.scrollok:
            wscroll(win)
            win.cx = 0
        else:
            # bottom right corner: cursor stays, curses returns ERR
            return False
    else:
        win.cx = x
    return True


def mvwaddch(win, y, x, ch):
    if not wmove(win, y, x):
        return False
    return waddch(win, ch)


def mvwaddstr(win, y, x, s):
    if not wmove(win, y, x):
        return False
    for ch in s:
        if not waddch(win, ch):
            return False
    return True


def werase(win):
    for y in range(win.h):
        for x in range(win.w):
            win.ch[y][x] = " "
            win.at[y][x] = 0
            win.dirty[y][x] = True
    win.cy = 0
    win.cx = 0


def wclear(win):
    werase(win)
    win.clearok = True


def touchwin(win):
    for row in win.dirty:
        for x in range(len(row)):
            row[x] = True


def wscroll(win):
    """Scroll the window up one line (curses scroll())."""
    if not win.scrollok:
        return False
    del win.ch[0]
    del win.at[0]
    win.ch.append([" "] * win.w)
    win.at.append([0] * win.w)
    touchwin(win)
    return True


def scrollok(win, flag):
    win.scrollok = bool(flag)


def _send(row_y, x_start, chars, attr):
    _terminal.move(x_start, row_y)
    _terminal.put("".join(chars), attr)


def wrefresh(win):
    """Copy the changed parts of win to the screen and update the terminal."""
    if _terminal is None or _screen is None:
        return
    scr = _screen
    full = win.clearok
    win.clearok = False
    for wy in range(win.h):
        sy = win.y0 + wy
        drow = win.dirty[wy]
        if sy < 0 or sy >= scr.lines:
            for x in range(win.w):
                drow[x] = False
            continue
        crow = win.ch[wy]
        arow = win.at[wy]
        srow_c = scr.ch[sy]
        srow_a = scr.at[sy]
        run_x = -1
        run = []
        run_attr = 0
        for wx in range(win.w):
            sx = win.x0 + wx
            changed = False
            if drow[wx] and 0 <= sx < scr.cols:
                drow[wx] = False
                c = crow[wx]
                a = arow[wx]
                if full or srow_c[sx] != c or srow_a[sx] != a:
                    srow_c[sx] = c
                    srow_a[sx] = a
                    changed = True
            else:
                drow[wx] = False
            if changed and not full:
                if run and (run_attr != arow[wx] or run_x + len(run) != sx):
                    _send(sy, run_x, run, run_attr)
                    run = []
                if not run:
                    run_x = sx
                    run_attr = arow[wx]
                run.append(crow[wx])
            elif run:
                _send(sy, run_x, run, run_attr)
                run = []
        if run:
            _send(sy, run_x, run, run_attr)
    if full:
        # clearok: clear the screen and redraw everything from the image
        _terminal.clear()
        for sy in range(scr.lines):
            x = 0
            while x < scr.cols:
                a = scr.at[sy][x]
                start = x
                while x < scr.cols and scr.at[sy][x] == a:
                    x += 1
                seg = scr.ch[sy][start:x]
                if a != 0 or any(ch != " " for ch in seg):
                    _send(sy, start, seg, a)
    cx = min(win.x0 + win.cx, scr.cols - 1)
    cy = min(win.y0 + win.cy, scr.lines - 1)
    _terminal.move(cx, cy)
    _terminal.refresh()


def refresh():
    wrefresh(stdscr)


def getch():
    """wgetch(stdscr): refresh stdscr if it changed, then read a key."""
    if stdscr is not None and stdscr.is_dirty():
        wrefresh(stdscr)
    return _terminal.getkey()


def has_colors():
    return bool(_terminal.has_colors())


def init_pair(pair, fg, bg):
    _terminal.init_pair(pair, fg, bg)


# =============================================================================
# Exported variables
# =============================================================================

nonap = 0
nosignal = 0

enable_scroll = 0

yrepcount = 0

# =============================================================================
# Enums (ularn_win.h)
# =============================================================================

# FormatType
FORMAT_NORMAL = 0
FORMAT_STANDOUT = 1
FORMAT_STANDOUT2 = 2
FORMAT_STANDOUT3 = 3
FORMAT_BOLD = 4
FORMAT_INVERSE = 5

# DisplayModeType
DISPLAY_MAP = 0      # Map display mode for moving around dungeons
DISPLAY_TEXT = 1     # Text display mode for scores, shops etc.

# DirEffectsType
EFFECT_MLE = 0
EFFECT_SSP = 1
EFFECT_BAL = 2
EFFECT_LIT = 3
EFFECT_CLD = 4
EFFECT_COUNT = 5

# MagicEffectsType
MAGIC_SPARKLE = 0
MAGIC_SLEEP = 1
MAGIC_WEB = 2
MAGIC_PHANTASMAL = 3
MAGIC_CLOUD = 4
MAGIC_VAPORIZE = 5
MAGIC_DEHYDRATE = 6
MAGIC_DRAIN = 7
MAGIC_FLOOD = 8
MAGIC_FINGER = 9
MAGIC_TELEPORT = 10
MAGIC_FIRE = 11
MAGIC_WALL = 12
MAGIC_DEMON = 13
MAGIC_ANNIHILATE = 14
MAGIC_COUNT = 15

# ActionType
ACTION_NULL = 0
ACTION_DIAG = 1
ACTION_MOVE_WEST = 2
ACTION_RUN_WEST = 3
ACTION_MOVE_EAST = 4
ACTION_RUN_EAST = 5
ACTION_MOVE_SOUTH = 6
ACTION_RUN_SOUTH = 7
ACTION_MOVE_NORTH = 8
ACTION_RUN_NORTH = 9
ACTION_MOVE_NORTHEAST = 10
ACTION_RUN_NORTHEAST = 11
ACTION_MOVE_NORTHWEST = 12
ACTION_RUN_NORTHWEST = 13
ACTION_MOVE_SOUTHEAST = 14
ACTION_RUN_SOUTHEAST = 15
ACTION_MOVE_SOUTHWEST = 16
ACTION_RUN_SOUTHWEST = 17
ACTION_WAIT = 18
ACTION_NONE = 19
ACTION_WIELD = 20
ACTION_WEAR = 21
ACTION_READ = 22
ACTION_QUAFF = 23
ACTION_DROP = 24
ACTION_CAST_SPELL = 25
ACTION_OPEN_DOOR = 26
ACTION_CLOSE_DOOR = 27
ACTION_OPEN_CHEST = 28
ACTION_INVENTORY = 29
ACTION_EAT_COOKIE = 30
ACTION_LIST_SPELLS = 31
ACTION_HELP = 32
ACTION_SAVE = 33
ACTION_TELEPORT = 34
ACTION_IDENTIFY_TRAPS = 35
ACTION_BECOME_CREATOR = 36
ACTION_CREATE_ITEM = 37
ACTION_TOGGLE_WIZARD = 38
ACTION_DEBUG_MODE = 39
ACTION_REMOVE_ARMOUR = 40
ACTION_PACK_WEIGHT = 41
ACTION_VERSION = 42
ACTION_QUIT = 43
ACTION_REDRAW_SCREEN = 44
ACTION_SHOW_TAX = 45
ACTION_COUNT = 46

# =============================================================================
# Local variables
# =============================================================================

# player id file (used when the OS gives no user name / id)
PIDName = "ularn.pid"
FIRST_PID = 1001

UseColor = 0
CaretActive = 0

M_NONE = 0
M_SHIFT = 1
M_CTRL = 2
M_ASCII = 255

MAX_KEY_BINDINGS = 3

NUM_DIRS = 8
DirActions = [
    ACTION_MOVE_WEST,
    ACTION_MOVE_EAST,
    ACTION_MOVE_SOUTH,
    ACTION_MOVE_NORTH,
    ACTION_MOVE_NORTHEAST,
    ACTION_MOVE_NORTHWEST,
    ACTION_MOVE_SOUTHEAST,
    ACTION_MOVE_SOUTHWEST,
]

_N = (None, 0)

# Default keymap.  Allow up to MAX_KEY_BINDINGS per action.
# Each binding is (VirtKey, ModKey).
KeyMap = [
    [_N, _N, _N],                                          # ACTION_NULL
    [("~", M_ASCII), _N, _N],                              # ACTION_DIAG
    [("h", M_ASCII), ("KEY_LEFT", M_ASCII), _N],           # ACTION_MOVE_WEST
    [("H", M_ASCII), _N, _N],                              # ACTION_RUN_WEST
    [("l", M_ASCII), ("KEY_RIGHT", M_ASCII), _N],          # ACTION_MOVE_EAST
    [("L", M_ASCII), _N, _N],                              # ACTION_RUN_EAST
    [("j", M_ASCII), ("KEY_DOWN", M_ASCII), _N],           # ACTION_MOVE_SOUTH
    [("J", M_ASCII), _N, _N],                              # ACTION_RUN_SOUTH
    [("k", M_ASCII), ("KEY_UP", M_ASCII), _N],             # ACTION_MOVE_NORTH
    [("K", M_ASCII), _N, _N],                              # ACTION_RUN_NORTH
    [("u", M_ASCII), ("KEY_A3", M_ASCII), _N],             # ACTION_MOVE_NORTHEAST
    [("U", M_ASCII), _N, _N],                              # ACTION_RUN_NORTHEAST
    [("y", M_ASCII), ("KEY_A1", M_ASCII), _N],             # ACTION_MOVE_NORTHWEST
    [("Y", M_ASCII), _N, _N],                              # ACTION_RUN_NORTHWEST
    [("n", M_ASCII), ("KEY_C3", M_ASCII), _N],             # ACTION_MOVE_SOUTHEAST
    [("N", M_ASCII), _N, _N],                              # ACTION_RUN_SOUTHEAST
    [("b", M_ASCII), ("KEY_C1", M_ASCII), _N],             # ACTION_MOVE_SOUTHWEST
    [("B", M_ASCII), _N, _N],                              # ACTION_RUN_SOUTHWEST
    [(".", M_ASCII), _N, _N],                              # ACTION_WAIT
    [(" ", M_ASCII), _N, _N],                              # ACTION_NONE
    [("w", M_ASCII), _N, _N],                              # ACTION_WIELD
    [("W", M_ASCII), _N, _N],                              # ACTION_WEAR
    [("r", M_ASCII), _N, _N],                              # ACTION_READ
    [("q", M_ASCII), _N, _N],                              # ACTION_QUAFF
    [("d", M_ASCII), _N, _N],                              # ACTION_DROP
    [("c", M_ASCII), _N, _N],                              # ACTION_CAST_SPELL
    [("o", M_ASCII), _N, _N],                              # ACTION_OPEN_DOOR
    [("C", M_ASCII), _N, _N],                              # ACTION_CLOSE_DOOR
    [("O", M_ASCII), _N, _N],                              # ACTION_OPEN_CHEST
    [("i", M_ASCII), _N, _N],                              # ACTION_INVENTORY
    [("e", M_ASCII), _N, _N],                              # ACTION_EAT_COOKIE
    [("\\", M_ASCII), _N, _N],                             # ACTION_LIST_SPELLS
    [("?", M_ASCII), _N, _N],                              # ACTION_HELP
    [("S", M_ASCII), _N, _N],                              # ACTION_SAVE
    [("Z", M_ASCII), _N, _N],                              # ACTION_TELEPORT
    [("^", M_ASCII), _N, _N],                              # ACTION_IDENTIFY_TRAPS
    [("_", M_ASCII), _N, _N],                              # ACTION_BECOME_CREATOR
    [("+", M_ASCII), _N, _N],                              # ACTION_CREATE_ITEM
    [("-", M_ASCII), _N, _N],                              # ACTION_TOGGLE_WIZARD
    [("`", M_ASCII), _N, _N],                              # ACTION_DEBUG_MODE
    [("T", M_ASCII), _N, _N],                              # ACTION_REMOVE_ARMOUR
    [("g", M_ASCII), _N, _N],                              # ACTION_PACK_WEIGHT
    [("v", M_ASCII), _N, _N],                              # ACTION_VERSION
    [("Q", M_ASCII), _N, _N],                              # ACTION_QUIT
    [("\x12", M_ASCII), _N, _N],                           # ACTION_REDRAW_SCREEN (^R)
    [("P", M_ASCII), _N, _N],                              # ACTION_SHOW_TAX
]

RunKeyMap = ("KEY_B2", M_ASCII)

# Ularn_Color_Type
C_BLACK = 0
C_RED = 1
C_GREEN = 2
C_YELLOW = 3
C_BLUE = 4
C_MAGENTA = 5
C_CYAN = 6
C_WHITE = 7
C_COUNT = 8

ColorPairs = [
    (COLOR_BLACK, COLOR_BLACK),
    (COLOR_RED, COLOR_BLACK),
    (COLOR_GREEN, COLOR_BLACK),
    (COLOR_YELLOW, COLOR_BLACK),
    (COLOR_BLUE, COLOR_BLACK),
    (COLOR_MAGENTA, COLOR_BLACK),
    (COLOR_CYAN, COLOR_BLACK),
    (COLOR_WHITE, COLOR_BLACK),
]

Runkey = 0
Event = ACTION_NULL
GotChar = 0
EventChar = "\0"

#
# Characters for tiles
#
WallTile = ["#"] * 16
# '#', '-', '|', '+', '-', '-', '+', '-', '|', '+', '|', '|', '+', '-', '|', '#'

# Tiles for directional effects
EffectTile = [
    ["*", "|", "-", "|", "-", "/", "\\", "\\", "/"],
    ["*", "|", "-", "|", "-", "/", "\\", "\\", "/"],
    ["*", "|", "-", "|", "-", "/", "\\", "\\", "/"],
    ["*", "|", "-", "|", "-", "/", "\\", "\\", "/"],
    ["*", "|", "-", "|", "-", "/", "\\", "\\", "/"],
]

EffectColor = [
    C_GREEN,
    C_CYAN,
    C_RED,
    C_YELLOW,
    C_WHITE,
]

MAX_MAGICFX_FRAME = 8


class MagicEffectDataType:
    """Frames: number of frames; Tile: primary tile per frame; Color: per frame."""

    def __init__(self, Frames, Tile, Color):
        self.Frames = Frames
        self.Tile = Tile
        self.Color = Color


magicfx_tile = [
    # Sparkle
    MagicEffectDataType(
        8,
        ["-", "\\", "|", "/", "-", "\\", "|", "/"],
        [C_RED, C_YELLOW, C_GREEN, C_CYAN, C_BLUE, C_MAGENTA, C_RED, C_YELLOW]),
    # Sleep
    MagicEffectDataType(
        6,
        ["z", "Z", "z", "Z", "z", "Z", 0, 0],
        [C_RED, C_RED, C_GREEN, C_GREEN, C_BLUE, C_BLUE, 0, 0]),
    # Web
    MagicEffectDataType(
        6,
        [".", "o", "*", "#", "#", "#", 0, 0],
        [C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_GREEN, C_BLUE, 0, 0]),
    # Phantasmal forces
    MagicEffectDataType(
        6,
        [".", ":", "^", "A", "A", "A", 0, 0],
        [C_BLUE, C_BLUE, C_MAGENTA, C_MAGENTA, C_CYAN, C_CYAN, 0, 0]),
    # Cloud kill
    MagicEffectDataType(
        6,
        [".", "o", "*", "#", "#", "O", 0, 0],
        [C_GREEN, C_GREEN, C_GREEN, C_GREEN, C_YELLOW, C_GREEN, 0, 0]),
    # Vaporize rock
    MagicEffectDataType(
        6,
        [".", "o", "*", "#", "#", "O", 0, 0],
        [C_RED, C_RED, C_RED, C_RED, C_YELLOW, C_RED, 0, 0]),
    # Dehydrate
    MagicEffectDataType(
        6,
        [".", ":", "|", "T", "^", "~", 0, 0],
        [C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, 0, 0]),
    # Drain life
    MagicEffectDataType(
        6,
        ["#", "*", "|", ":", "o", ".", 0, 0],
        [C_YELLOW, C_YELLOW, C_YELLOW, C_RED, C_RED, C_RED, 0, 0]),
    # Flood
    MagicEffectDataType(
        6,
        [".", "o", "O", "o", "O", "o", 0, 0],
        [C_BLUE, C_BLUE, C_BLUE, C_CYAN, C_CYAN, C_BLUE, 0, 0]),
    # Finger of death
    MagicEffectDataType(
        6,
        ["#", "*", "|", ":", "o", ".", 0, 0],
        [C_RED, C_RED, C_MAGENTA, C_MAGENTA, C_BLUE, C_BLUE, 0, 0]),
    # Teleport away
    MagicEffectDataType(
        6,
        [":", "|", "H", "H", "|", ":", 0, 0],
        [C_CYAN, C_CYAN, C_CYAN, C_BLUE, C_BLUE, C_BLUE, 0, 0]),
    # Magic fire
    MagicEffectDataType(
        6,
        [".", "o", "*", "#", "#", "O", 0, 0],
        [C_RED, C_RED, C_RED, C_RED, C_YELLOW, C_RED, 0, 0]),
    # Make wall
    MagicEffectDataType(
        6,
        [".", ":", "H", "#", "#", "#", 0, 0],
        [C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_RED, C_WHITE, 0, 0]),
    # Summon demon
    MagicEffectDataType(
        6,
        [".", ":", "^", "8", "8", "8", 0, 0],
        [C_MAGENTA, C_MAGENTA, C_RED, C_RED, C_YELLOW, C_YELLOW, 0, 0]),
    # Annihilate (scroll)
    MagicEffectDataType(
        6,
        ["-", "|", "-", "|", "-", "|", 0, 0],
        [C_RED, C_RED, C_YELLOW, C_YELLOW, C_GREEN, C_GREEN, 0, 0]),
]

#
# Display attributes and colours
# (C arrays are sized OCOUNT / MONST_COUNT; missing entries are zero.)
#
_TABLE_PAD = 256

ItemAttr = [
    0, 0,
    # Dungeon features
    A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE,
    A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE,
    0,
    # gold piles
    0, 0, 0, 0,
    # eye of larn
    A_STANDOUT,
    # armour
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0,
    # weapons
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0,
    # rings
    0, 0, 0, 0, 0, 0, 0, 0,
    # magic items
    0, 0, 0, A_REVERSE, A_REVERSE, A_BOLD, 0, A_BOLD,
    0, 0, 0, 0, 0, 0, 0, 0,
    0,
    # gems
    0, 0, 0, 0,
    # buildings/entrances
    A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE, A_REVERSE,
    A_REVERSE, A_REVERSE, A_REVERSE,
    # traps
    0, 0, 0, 0, 0, 0, 0,
    # misc
    0, 0, 0,
    # drugs
    0, 0, 0, 0, 0,
]
ItemAttr += [0] * (_TABLE_PAD - len(ItemAttr))

ItemColor = [
    C_WHITE, C_WHITE,
    # Dungeon features
    C_WHITE, C_YELLOW, C_YELLOW, C_YELLOW, C_WHITE, C_GREEN, C_WHITE, C_BLUE,
    C_WHITE, C_RED, C_WHITE, C_RED, C_WHITE, C_WHITE, C_WHITE, C_WHITE,
    C_WHITE,
    # gold piles
    C_YELLOW, C_YELLOW, C_YELLOW, C_YELLOW,
    # eye of larn
    C_WHITE,
    # armour
    C_CYAN, C_CYAN, C_WHITE, C_CYAN, C_WHITE, C_CYAN, C_CYAN, C_CYAN,
    C_WHITE, C_GREEN,
    # weapons
    C_CYAN, C_WHITE, C_CYAN, C_CYAN, C_WHITE, C_CYAN, C_CYAN, C_CYAN,
    C_WHITE, C_WHITE, C_MAGENTA, C_YELLOW,
    # rings
    C_WHITE, C_GREEN, C_BLUE, C_WHITE, C_CYAN, C_RED, C_MAGENTA, C_WHITE,
    # magic items
    C_WHITE, C_WHITE, C_YELLOW, C_CYAN, C_YELLOW, C_CYAN, C_WHITE, C_RED,
    C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE,
    C_WHITE,
    # gems
    C_WHITE, C_RED, C_GREEN, C_BLUE,
    # buildings/entrances
    C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE,
    C_WHITE, C_WHITE, C_WHITE,
    # traps
    C_RED, C_RED, C_RED, C_RED, C_RED, C_RED, C_RED,
    # misc
    C_WHITE, C_WHITE, C_WHITE,
    # drugs
    C_WHITE, C_WHITE, C_WHITE, C_WHITE, C_WHITE,
]
ItemColor += [0] * (_TABLE_PAD - len(ItemColor))

MonstColor = [
    C_WHITE,
    C_WHITE, C_GREEN, C_GREEN, C_WHITE, C_WHITE, C_RED, C_GREEN, C_GREEN,
    C_RED, C_RED, C_RED, C_CYAN, C_GREEN, C_WHITE, C_BLUE, C_RED,
    C_WHITE, C_WHITE, C_RED, C_RED, C_CYAN, C_GREEN, C_YELLOW, C_WHITE,
    C_WHITE, C_GREEN, C_WHITE, C_CYAN, C_YELLOW, C_RED, C_MAGENTA, C_WHITE,
    C_YELLOW, C_YELLOW, C_YELLOW, C_YELLOW, C_RED, C_WHITE, C_WHITE, C_WHITE,
    C_CYAN, C_GREEN, C_YELLOW, C_MAGENTA, C_GREEN, C_BLUE, C_BLUE, C_MAGENTA,
    C_GREEN, C_MAGENTA, C_RED, C_YELLOW, C_CYAN, C_YELLOW, C_GREEN, C_RED,
    C_WHITE, C_YELLOW, C_GREEN, C_CYAN, C_BLUE, C_RED, C_MAGENTA, C_CYAN,
    C_MAGENTA,
]
MonstColor += [0] * (_TABLE_PAD - len(MonstColor))

#
# Current display mode
#
CurrentDisplayMode = DISPLAY_TEXT

stdscr = None
MapWindow = None
StatusWindow = None
EffectsWindow = None
MessageWindow = None

TextWindow = None

# =============================================================================
# Text mode stuff
# =============================================================================

LINE_LENGTH = 80

#
# Messages
#
MAX_MSG_LINES = 5
CurrentMsgFormat = FORMAT_NORMAL
MsgCursorX = 1
MsgCursorY = 1

#
# Text
#
MAX_TEXT_LINES = 24
TEXT_LINE_LENGTH = 80
CurrentTextFormat = FORMAT_NORMAL
TextCursorX = 1
TextCursorY = 1

#
# Generalised text buffer
# Top left corner is x=1, y=1
#
CurrentFormat = FORMAT_NORMAL
CursorX = 1
CursorY = 1
MaxLine = 0

#
# The monster to use for showing mimics. Changes every 10 turns.
#
mimicmonst = None   # set to monster.MIMIC by init_app (C: = MIMIC)

# Repaint flag to force redraw of everything, not just deltas
Repaint = 0

RefreshEachChar = 1

_app_open = False

# =============================================================================
# Local functions
# =============================================================================


def SetWallTiles():
    """Set the wall tiles to the ACS line drawing values."""
    WallTile[0] = ACS_BLOCK
    WallTile[1] = ACS_HLINE
    WallTile[2] = ACS_VLINE
    WallTile[3] = ACS_URCORNER
    WallTile[4] = ACS_HLINE
    WallTile[5] = ACS_HLINE
    WallTile[6] = ACS_ULCORNER
    WallTile[7] = ACS_TTEE
    WallTile[8] = ACS_VLINE
    WallTile[9] = ACS_LRCORNER
    WallTile[10] = ACS_VLINE
    WallTile[11] = ACS_RTEE
    WallTile[12] = ACS_LLCORNER
    WallTile[13] = ACS_BTEE
    WallTile[14] = ACS_LTEE
    WallTile[15] = ACS_PLUS


def SetCursesAttr(Format):
    """Set curses text display attributes for the indicated format."""
    BaseAttr = 0

    if Format == FORMAT_NORMAL:
        if UseColor:
            wattrset(TextWindow, BaseAttr | COLOR_PAIR(C_WHITE))
        else:
            wattrset(TextWindow, A_NORMAL)
    elif Format == FORMAT_STANDOUT:
        if UseColor:
            wattrset(TextWindow, BaseAttr | COLOR_PAIR(C_RED))
        else:
            wattrset(TextWindow, A_STANDOUT)
    elif Format == FORMAT_STANDOUT2:
        if UseColor:
            wattrset(TextWindow, BaseAttr | COLOR_PAIR(C_GREEN))
        else:
            wattrset(TextWindow, A_BOLD)
    elif Format == FORMAT_STANDOUT3:
        if UseColor:
            wattrset(TextWindow, BaseAttr | COLOR_PAIR(C_BLUE))
        else:
            wattrset(TextWindow, A_UNDERLINE)
    else:
        pass


def setup_colour_pairs():
    """Setup the colour pairs used by curses."""
    for i in range(C_COUNT):
        init_pair(i, ColorPairs[i][0], ColorPairs[i][1])


def PaintStatus():
    """Paint the status area."""
    c = player.c

    wattrset(StatusWindow, COLOR_PAIR(C_WHITE))

    if Repaint:
        wclear(StatusWindow)
        for i in range(80):
            mvwaddch(StatusWindow, 0, i, " ")
            mvwaddch(StatusWindow, 1, i, " ")

    #
    # Build the top status line
    #
    Line = ""

    # Spells
    if c[player.SPELLMAX] > 99:
        Buf = "Spells:%3d(%3d)" % (c[player.SPELLS], c[player.SPELLMAX])
    else:
        Buf = "Spells:%3d(%2d) " % (c[player.SPELLS], c[player.SPELLMAX])

    Line += Buf

    # AC, WC
    Buf = " AC: %-3d  WC: %-3d  Level" % (c[player.AC], c[player.WCLASS])
    Line += Buf

    # Level
    if c[player.LEVEL] > 99:
        Buf = "%3d" % c[player.LEVEL]
    else:
        Buf = " %-2d" % c[player.LEVEL]
    Line += Buf

    # Exp, class
    Buf = " Exp: %-9d %s" % (c[player.EXPERIENCE], player.class_[c[player.LEVEL] - 1])
    Line += Buf

    mvwaddstr(StatusWindow, 0, 0, Line)

    #
    # Format the second line of the status
    #
    Buf = "%d (%d)" % (c[player.HP], c[player.HPMAX])

    Line = "HP: %11s STR=%-2d INT=%-2d WIS=%-2d CON=%-2d DEX=%-2d CHA=%-2d LV:" % (
        Buf,
        c[player.STRENGTH] + c[player.STREXTRA],
        c[player.INTELLIGENCE],
        c[player.WISDOM],
        c[player.CONSTITUTION],
        c[player.DEXTERITY],
        c[player.CHARISMA])

    if (dungeon.level == 0) or player.wizard:
        c[player.TELEFLAG] = 0

    if c[player.TELEFLAG]:
        Line += " ?"
    else:
        Line += dungeon.levelname[dungeon.level]

    Buf = "  Gold: %-8d" % c[player.GOLD]
    Line += Buf

    mvwaddstr(StatusWindow, 1, 0, Line)

    wrefresh(StatusWindow)

    #
    # Mark all character values as displayed.
    #
    c[player.TMP] = c[player.STRENGTH] + c[player.STREXTRA]
    cbak = player.cbak
    for i in range(min(100, len(cbak), len(c))):
        cbak[i] = c[i]


class bot_side_def:
    """Effects strings: typ is the c[] index, string the text shown."""

    def __init__(self, typ, string):
        self.typ = typ
        self.string = string


# The typ fields are the names of player.c[] indices, resolved at call time
# so that this module does not depend on player being fully imported.
_bot_data_src = [
    ("STEALTH",        "  Stealth    "),
    ("UNDEADPRO",      "  Undead Pro "),
    ("SPIRITPRO",      "  Spirit Pro "),
    ("CHARMCOUNT",     "  Charm      "),
    ("TIMESTOP",       "  Time Stop  "),
    ("HOLDMONST",      "  Hold Monst "),
    ("GIANTSTR",       "  Giant Str  "),
    ("FIRERESISTANCE", "  Fire Resit "),
    ("DEXCOUNT",       "  Dexterity  "),
    ("STRCOUNT",       "  Strength   "),
    ("SCAREMONST",     "  Scare      "),
    ("HASTESELF",      "  Haste Self "),
    ("CANCELLATION",   "  Cancel     "),
    ("INVISIBILITY",   "  Invisible  "),
    ("ALTPRO",         "  Protect 3  "),
    ("PROTECTIONTIME", "  Protect 2  "),
    ("WTW",            "  Wall-Walk  "),
]

bot_data = None


def _get_bot_data():
    global bot_data
    if bot_data is None:
        bot_data = [bot_side_def(getattr(player, n), s) for (n, s) in _bot_data_src]
    return bot_data


def PaintEffects():
    """Paint the effects display."""
    c = player.c
    cbak = player.cbak

    # (The C code sets the attribute of StatusWindow here, not EffectsWindow.)
    wattrset(StatusWindow, COLOR_PAIR(C_WHITE))

    if Repaint:
        wclear(EffectsWindow)

    bd = _get_bot_data()
    for i in range(17):
        idx = bd[i].typ
        WasSet = (cbak[idx] != 0)
        IsSet = (c[idx] != 0)

        if Repaint or (IsSet != WasSet):
            if IsSet:
                mvwaddstr(EffectsWindow, i, 0, bd[i].string)
            else:
                mvwaddstr(EffectsWindow, i, 0, "             ")

        cbak[idx] = c[idx]

    wrefresh(EffectsWindow)


def GetTile(x, y):
    """Get the tile to be displayed for a location on the map.

    C signature GetTile(x, y, &TileId, &Attr, &ColorPair); returns the tuple
    (TileId, Attr, ColorPair).
    """
    global mimicmonst

    c = player.c
    know = dungeon.know
    objnamelist = itm.objnamelist

    Attr = 0

    if (x == player.playerx) and (y == player.playery) and (c[player.BLINDCOUNT] == 0):
        #
        # This is the square containing the player and the players isn't
        # blind, so return the player tile.
        #
        return ("@", 0, C_RED)

    #
    # Work out what is here
    #
    kn = know[x][y]
    if kn == itm.OUNKNOWN:
        #
        # The player doesn't know what is at this position.
        #
        TileId = objnamelist[itm.OUNKNOWN]
        Attr = ItemAttr[kn]
        ColorPair = C_BLACK
    else:
        k = dungeon.mitem[x][y].mon
        if k != 0:
            st = dungeon.stealth[x][y]
            if (c[player.BLINDCOUNT] == 0) and \
               (((st & dungeon.STEALTH_SEEN) != 0) or
                    ((st & dungeon.STEALTH_AWAKE) != 0)):
                #
                # There is a monster here and the player is not blind and the
                # monster is seen or awake.
                #
                if k == monster.MIMIC:
                    if (player.gtime % 10) == 0:
                        while True:
                            mimicmonst = rnd(monster.MAXMONST)
                            if mimicmonst != monster.INVISIBLESTALKER:
                                break

                    TileId = monster.monstnamelist[mimicmonst]
                    ColorPair = MonstColor[mimicmonst]
                elif (k == monster.INVISIBLESTALKER) and (c[player.SEEINVISIBLE] == 0):
                    TileId = objnamelist[kn]
                    Attr = ItemAttr[kn]
                    ColorPair = ItemColor[kn]
                elif (k >= monster.DEMONLORD) and (k <= monster.LUCIFER) and \
                        (c[player.EYEOFLARN] == 0):
                    # demons are invisible if not have the eye
                    TileId = objnamelist[kn]
                    Attr = ItemAttr[kn]
                    ColorPair = ItemColor[kn]
                else:
                    TileId = monster.monstnamelist[k]
                    ColorPair = MonstColor[k]
            else:
                #
                # The monster at this location is not known to the player, so
                # show the tile for the item at this location
                #
                TileId = objnamelist[kn]
                Attr = ItemAttr[kn]
                ColorPair = ItemColor[kn]
        else:
            TileId = objnamelist[kn]
            Attr = ItemAttr[kn]
            ColorPair = ItemColor[kn]

    # Handle walls
    if TileId == objnamelist[itm.OWALL]:
        TileId = WallTile[dungeon.iarg[x][y]]

    return (TileId, Attr, ColorPair)


def PaintMap():
    """Repaint the map."""
    if Repaint:
        wclear(MapWindow)

        for y in range(dungeon.MAXY):
            for x in range(dungeon.MAXX):
                TileId, Attr, Color = GetTile(x, y)

                if UseColor:
                    wattrset(MapWindow, Attr | COLOR_PAIR(Color))
                else:
                    wattrset(MapWindow, Attr)

                mvwaddch(MapWindow, y, x, TileId)

    wrefresh(MapWindow)


def PaintTextWindow():
    """Repaint the window in text mode."""
    touchwin(TextWindow)
    wrefresh(TextWindow)


def PaintMapWindow():
    """Repaint the window in map mode."""
    PaintStatus()
    PaintEffects()
    PaintTextWindow()
    PaintMap()

    showplayer()


def PaintWindow():
    """Repaint the window."""
    global Repaint

    Repaint = 1

    if CurrentDisplayMode == DISPLAY_MAP:
        PaintMapWindow()
    else:
        PaintTextWindow()

    Repaint = 0


# =============================================================================
# Exported functions
# =============================================================================


def init_app():
    """Initialise the app and create the windows. Returns 1 on success."""
    global _screen, stdscr, MapWindow, StatusWindow, EffectsWindow, MessageWindow
    global TextWindow, UseColor, CaretActive, CurrentDisplayMode
    global CurrentMsgFormat, MsgCursorX, MsgCursorY
    global CurrentTextFormat, TextCursorX, TextCursorY
    global CurrentFormat, CursorX, CursorY, MaxLine, mimicmonst, Repaint
    global RefreshEachChar, Runkey, Event, GotChar, EventChar, _app_open
    global yrepcount

    if _terminal is None:
        from . import term_curses
        set_terminal(term_curses.CursesTerminal())

    # Reset the module state so that several games can run in one process.
    CurrentDisplayMode = DISPLAY_TEXT
    CurrentMsgFormat = FORMAT_NORMAL
    MsgCursorX = 1
    MsgCursorY = 1
    CurrentTextFormat = FORMAT_NORMAL
    TextCursorX = 1
    TextCursorY = 1
    CurrentFormat = FORMAT_NORMAL
    CursorX = 1
    CursorY = 1
    MaxLine = 0
    mimicmonst = monster.MIMIC
    Repaint = 0
    RefreshEachChar = 1
    CaretActive = 0
    Runkey = 0
    Event = ACTION_NULL
    GotChar = 0
    EventChar = "\0"
    yrepcount = 0

    # Initialise curses app
    _terminal.start()
    _screen = _Screen(SCREEN_LINES, SCREEN_COLS)
    stdscr = newwin(SCREEN_LINES, SCREEN_COLS, 0, 0)
    _app_open = True

    setup_colour_pairs()

    # Create windows
    MapWindow = newwin(17, 67, 0, 0)
    StatusWindow = newwin(2, 80, 17, 0)
    EffectsWindow = newwin(17, 13, 0, 67)
    MessageWindow = newwin(5, 80, 19, 0)

    SetWallTiles()

    # Start colour mode for slowlaris
    wattrset(stdscr, A_STANDOUT | COLOR_PAIR(C_RED))
    mvwaddch(stdscr, 0, 0, "*")

    touchwin(stdscr)
    wrefresh(stdscr)

    UseColor = 1 if has_colors() else 0

    refresh()

    #
    # Clear the text buffers
    #
    TextWindow = MessageWindow

    SetCursesAttr(FORMAT_NORMAL)

    for y in range(MAX_MSG_LINES):
        for x in range(LINE_LENGTH):
            mvwaddch(TextWindow, y, x, " ")
    wrefresh(TextWindow)

    TextWindow = stdscr

    SetCursesAttr(FORMAT_NORMAL)

    for y in range(MAX_TEXT_LINES):
        for x in range(LINE_LENGTH):
            mvwaddch(TextWindow, y, x, " ")
    wrefresh(TextWindow)

    return 1


def close_app():
    """Close the application, freeing all resources (safe to call twice)."""
    global _app_open
    if not _app_open:
        return
    _app_open = False
    delwin(MessageWindow)
    delwin(EffectsWindow)
    delwin(StatusWindow)
    delwin(MapWindow)
    if _terminal is not None:
        _terminal.stop()


def get_normal_input():
    """Get the next command input. Returns an ACTION_* constant."""
    global Event, Runkey, EventChar, GotChar

    Event = ACTION_NULL
    Runkey = 0

    while Event == ACTION_NULL:
        wrefresh(MapWindow)
        EventChar = getch()
        GotChar = 1

        #
        # Decide the event corresponding to the key pressed
        #

        # Decode key press as a ULarn Action

        #
        # Check ASCII key bindings if no virtual key matches and
        # got a valid ASCII char
        #
        Found = 0
        Action = ACTION_NULL

        if (not Found) and GotChar:
            Action = ACTION_NULL

            while (Action < ACTION_COUNT) and (not Found):
                for i in range(MAX_KEY_BINDINGS):
                    if KeyMap[Action][i][1] == M_ASCII:
                        # ASCII key binding
                        if EventChar == KeyMap[Action][i][0]:
                            Found = 1

                if not Found:
                    Action += 1

        if Found:
            Event = Action
        else:
            # check run key
            if (EventChar == RunKeyMap[0]) and (RunKeyMap[1] == M_ASCII):
                Runkey = 1

        #
        # Clear enhanced interface events in enhanced interface is not active
        #
        if not ularn_game.enhance_interface:
            if (Event == ACTION_OPEN_DOOR) or (Event == ACTION_OPEN_CHEST):
                Event = ACTION_NULL

    if Runkey:
        idx = 0
        got_dir = 0

        while (idx < NUM_DIRS) and (not got_dir):
            if DirActions[idx] == Event:
                got_dir = 1
            else:
                idx += 1

        if got_dir:
            # modify into a run event
            Event = Event + 1

    return Event


def get_prompt_input(prompt, answers, ShowCursor):
    """Display prompt and wait until a key in answers is pressed; return it."""
    global CaretActive, GotChar, EventChar

    Print(prompt)

    if ShowCursor:
        CaretActive = 1

    #
    # Process events until a character in answers has been pressed.
    #
    GotChar = 0
    while not GotChar:
        wrefresh(TextWindow)

        EventChar = getch()
        GotChar = 1

        if GotChar:
            #
            # Search for the input character in the answers string
            #
            if len(EventChar) != 1 or EventChar not in answers:
                #
                # Not an answer we want
                #
                GotChar = 0

    if ShowCursor:
        CaretActive = 0

    return EventChar


def _isprint(ch):
    return len(ch) == 1 and " " <= ch <= "~"


# printable characters (C locale) plus BS and CR
_inputchars = "".join(chr(v) for v in range(256) if _isprint(chr(v))) + "\010\015"


def get_password_input(Len):
    """Input a password, echoing '*'.

    C signature get_password_input(char *password, int Len); returns the
    password string (at most Len characters).
    """
    global CursorX

    password = []
    Pos = 0
    while True:
        ch = get_prompt_input("", _inputchars, 1)

        if _isprint(ch) and (Pos < Len):
            password.append(ch)
            Pos += 1
            Printc("*")
        elif ch == "\010":
            #
            # Backspace
            #
            if Pos > 0:
                CursorX -= 1
                Printc(" ")
                CursorX -= 1
                Pos -= 1
                del password[Pos:]

                wmove(TextWindow, CursorY - 1, CursorX - 1)
                wrefresh(TextWindow)

        if ch == "\015":
            break

    return "".join(password[:Pos])


def get_string_input(Len):
    """Input a string, echoing it.

    C signature get_string_input(char *string, int Len); returns the string.
    """
    global CursorX

    string = []
    Pos = 0
    while True:
        ch = get_prompt_input("", _inputchars, 1)

        if _isprint(ch) and (Pos < Len):
            string.append(ch)
            Pos += 1
            Printc(ch)
        elif ch == "\010":
            #
            # Backspace
            #
            if Pos > 0:
                CursorX -= 1
                Printc(" ")
                CursorX -= 1
                Pos -= 1
                del string[Pos:]

                wmove(TextWindow, CursorY - 1, CursorX - 1)
                wrefresh(TextWindow)

        if ch == "\015":
            break

    return "".join(string[:Pos])


def get_num_input(defval):
    """Input a number; '*' or an empty entry returns defval."""
    global CursorX

    Pos = 0
    value = 0
    neg = 0

    while True:
        ch = get_prompt_input("", "-*0123456789\010\015", 1)

        if (ch == "-") and (Pos == 0):
            #
            # Minus
            #
            neg = 1
            Printc(ch)
            Pos += 1
        if ch == "*":
            return defval
        elif ch == "\010":
            #
            # Backspace
            #
            if Pos > 0:
                if (Pos == 1) and neg:
                    neg = 0
                else:
                    value = value // 10

                CursorX -= 1
                Printc(" ")
                CursorX -= 1
                Pos -= 1
                wmove(TextWindow, CursorY - 1, CursorX - 1)
                wrefresh(TextWindow)
        elif ("0" <= ch <= "9"):
            #
            # digit
            #
            value = value * 10 + (ord(ch) - ord("0"))
            Printc(ch)
            Pos += 1

        if ch == "\015":
            break

    if Pos == 0:
        return defval
    else:
        if neg:
            value = -value

        return value


def get_dir_input(prompt, ShowCursor):
    """Input a direction key; returns the ACTION_MOVE_* for it."""
    global CaretActive

    #
    # Display the prompt at the current position
    #
    Print(prompt)

    #
    # Show the cursor if required
    #
    if ShowCursor:
        CaretActive = 1

    got_dir = 0

    while not got_dir:
        get_normal_input()

        idx = 0

        while (idx < NUM_DIRS) and (not got_dir):
            if DirActions[idx] == Event:
                got_dir = 1
            else:
                idx += 1

    if ShowCursor:
        CaretActive = 0

    return Event


def UpdateStatus():
    """Update the status lines showing the player's attributes."""
    if CurrentDisplayMode == DISPLAY_TEXT:
        # Don't redisplay if in text mode
        return

    PaintStatus()


def UpdateEffects():
    """Update the display of effects currently in play."""
    if CurrentDisplayMode == DISPLAY_TEXT:
        # Don't redisplay if in text mode
        return

    PaintEffects()


def UpdateStatusAndEffects():
    """Update status and effects display."""
    if CurrentDisplayMode == DISPLAY_TEXT:
        # Don't redisplay if in text mode
        return

    #
    # Do effects first as update status will mark all effects as current
    #
    PaintEffects()
    PaintStatus()


def set_display(Mode):
    """Set the display mode (DISPLAY_MAP / DISPLAY_TEXT) and redraw."""
    global MsgCursorX, MsgCursorY, CurrentMsgFormat
    global TextCursorX, TextCursorY, CurrentTextFormat
    global CurrentDisplayMode, CursorX, CursorY, CurrentFormat, MaxLine, TextWindow

    #
    # Save the current settings
    #
    if CurrentDisplayMode == DISPLAY_MAP:
        MsgCursorX = CursorX
        MsgCursorY = CursorY
        CurrentMsgFormat = CurrentFormat
    elif CurrentDisplayMode == DISPLAY_TEXT:
        TextCursorX = CursorX
        TextCursorY = CursorY
        CurrentTextFormat = CurrentFormat

    CurrentDisplayMode = Mode

    #
    # Set the text buffer settings for the new display mode
    #
    if CurrentDisplayMode == DISPLAY_MAP:
        CursorX = MsgCursorX
        CursorY = MsgCursorY
        CurrentFormat = CurrentMsgFormat

        MaxLine = MAX_MSG_LINES

        TextWindow = MessageWindow

    elif CurrentDisplayMode == DISPLAY_TEXT:
        CursorX = TextCursorX
        CursorY = TextCursorY
        CurrentFormat = CurrentTextFormat

        MaxLine = MAX_TEXT_LINES

        TextWindow = stdscr

    PaintWindow()


def IncCursorY(Count):
    """Increase the cursor y position, scrolling the text window if required."""
    global CursorY

    inc = Count
    Scroll = 0

    while inc > 0:
        CursorY = CursorY + 1

        if CursorY > MaxLine:
            Scroll = 1
            CursorY -= 1

            scrollok(TextWindow, 1)

            wscroll(TextWindow)

            scrollok(TextWindow, 0)

            SetCursesAttr(FORMAT_NORMAL)
            for x in range(LINE_LENGTH):
                mvwaddch(TextWindow, CursorY - 1, x, " ")

        inc -= 1

    wrefresh(TextWindow)


def IncCursorX(Count):
    """Increase the cursor x position, handling line wrap."""
    global CursorX

    CursorX = CursorX + Count
    if CursorX > LINE_LENGTH:
        CursorX = 1
        IncCursorY(1)


def ClearText():
    """Clear the currently active text display."""
    global CursorX, CursorY

    #
    # Clear the text buffer
    #
    SetCursesAttr(FORMAT_NORMAL)

    for y in range(MaxLine):
        for x in range(LINE_LENGTH):
            mvwaddch(TextWindow, y, x, " ")

    wrefresh(TextWindow)

    CursorX = 1
    CursorY = 1


def UlarnBeep():
    """Make a beep (unless the nobeep option is set)."""
    #
    # Play a beep
    #
    if not ularn_game.nobeep:
        _terminal.beep()


def MoveCursor(x, y):
    """Locate the text cursor at x, y where 1, 1 is the top left corner."""
    global CursorX, CursorY

    CursorX = x
    CursorY = y


def Printc(c):
    """Print a single character to the current text output."""
    global CursorX

    if isinstance(c, int):
        c = chr(c & 0xFF)

    if c == "\t":
        incx = ((((CursorX - 1) // 8) + 1) * 8 + 1) - CursorX
        IncCursorX(incx)

    elif c == "\n":
        CursorX = 1
        IncCursorY(1)

    elif c == "\015":
        pass

    else:
        SetCursesAttr(CurrentFormat)
        mvwaddch(TextWindow, CursorY - 1, CursorX - 1, c)

        if RefreshEachChar:
            wrefresh(TextWindow)

        IncCursorX(1)


def Print(string):
    """Print a string to the current text output."""
    global RefreshEachChar

    if string is None:
        return

    if len(string) == 0:
        return

    RefreshEachChar = 0

    for ch in string:
        if ch == "\0":
            break   # C string terminator
        Printc(ch)

    RefreshEachChar = 1

    wrefresh(TextWindow)


def Printf(fmt, *args):
    """Formatted print: Print(fmt % args)."""
    try:
        buf = fmt % args
    except (TypeError, ValueError):
        buf = fmt if not args else fmt + " ".join(str(a) for a in args)

    Print(buf)


def Standout(String):
    """Display a string in the standout style."""
    global CurrentFormat

    CurrentFormat = FORMAT_STANDOUT

    Print(String)

    CurrentFormat = FORMAT_NORMAL


def SetFormat(format):
    """Set the format for future text printing."""
    global CurrentFormat

    CurrentFormat = format


def ClearToEOL():
    """Clear from the cursor to the end of the line (cursor unchanged)."""
    for x in range(CursorX, LINE_LENGTH + 1):
        SetCursesAttr(FORMAT_NORMAL)
        mvwaddch(TextWindow, CursorY - 1, x - 1, " ")


def ClearToEOPage(x, y):
    """Clear from position (x, y) to the end of the page (cursor unchanged)."""
    SetCursesAttr(FORMAT_NORMAL)

    for tx in range(x, LINE_LENGTH + 1):
        mvwaddch(TextWindow, y - 1, tx - 1, " ")

    for ty in range(y + 1, MaxLine + 1):
        for tx in range(1, LINE_LENGTH + 1):
            mvwaddch(TextWindow, ty - 1, tx - 1, " ")


def show1cell(x, y):
    """Display a single cell of the map, making it known if not blind."""
    # see nothing if blind
    if player.c[player.BLINDCOUNT]:
        return

    # we end up knowing about it
    dungeon.know[x][y] = dungeon.item[x][y]
    if dungeon.mitem[x][y].mon != monster.MONST_NONE:
        dungeon.stealth[x][y] |= dungeon.STEALTH_SEEN

    TileId, Attr, Color = GetTile(x, y)

    wattrset(MapWindow, Attr | COLOR_PAIR(Color))
    mvwaddch(MapWindow, y, x, TileId)

    wrefresh(MapWindow)


def showplayer():
    """Show the player on the map."""
    px = player.playerx
    py = player.playery

    if player.c[player.BLINDCOUNT] == 0:
        TileId = "@"
        Attr = 0
        Color = C_RED
    else:
        TileId, Attr, Color = GetTile(px, py)

    wattrset(MapWindow, Attr | COLOR_PAIR(Color))
    mvwaddch(MapWindow, py, px, TileId)
    wmove(MapWindow, py, px)
    wrefresh(MapWindow)


def showcell(x, y):
    """Display the cells around (x, y); the player gets to know them."""
    c = player.c
    know = dungeon.know
    item = dungeon.item
    mitem = dungeon.mitem
    stealth = dungeon.stealth

    #
    # Decide how much the player knows about around him/her.
    #
    if c[player.AWARENESS]:
        minx = x - 3
        maxx = x + 3
        miny = y - 3
        maxy = y + 3
    else:
        minx = x - 1
        maxx = x + 1
        miny = y - 1
        maxy = y + 1

    if c[player.BLINDCOUNT]:
        minx = x
        maxx = x
        miny = y
        maxy = y

    #
    # Limit the area to the map extents
    #
    if minx < 0:
        minx = 0
    if maxx > dungeon.MAXX - 1:
        maxx = dungeon.MAXX - 1
    if miny < 0:
        miny = 0
    if maxy > dungeon.MAXY - 1:
        maxy = dungeon.MAXY - 1

    for my in range(miny, maxy + 1):
        for mx in range(minx, maxx + 1):
            if (mx == player.playerx) and (my == player.playery):
                know[mx][my] = item[mx][my]
            elif (know[mx][my] != item[mx][my]) or \
                    ((mx == player.lastpx) and (my == player.lastpy)) or \
                    ((mitem[mx][my].mon != monster.MONST_NONE) and
                     ((stealth[mx][my] & dungeon.STEALTH_SEEN) == 0)):
                #
                # Only draw areas not already known (and hence displayed)
                #
                know[mx][my] = item[mx][my]
                if mitem[mx][my].mon != monster.MONST_NONE:
                    stealth[mx][my] |= dungeon.STEALTH_SEEN

                TileId, Attr, Color = GetTile(mx, my)

                wattrset(MapWindow, Attr | COLOR_PAIR(Color))
                mvwaddch(MapWindow, my, mx, TileId)

    showplayer()


def drawscreen():
    """Redraw the entire screen."""
    PaintWindow()


def draws(minx, miny, maxx, maxy):
    """Redraw a sub-section of the screen (the TTY version redraws all)."""
    PaintWindow()


def mapeffect(x, y, effect, dir):
    """Draw a directional effect on the map."""
    wattrset(MapWindow, A_NORMAL | COLOR_PAIR(EffectColor[effect]))
    mvwaddch(MapWindow, y, x, EffectTile[effect][dir])
    wmove(MapWindow, 0, 0)

    touchwin(MapWindow)
    wrefresh(MapWindow)


def magic_effect_frames(fx):
    """The number of frames in a magic effect animation."""
    return magicfx_tile[fx].Frames


def magic_effect(x, y, fx, frame):
    """Draw 1 frame of the animation for a magic effect."""
    wattrset(MapWindow, COLOR_PAIR(magicfx_tile[fx].Color[frame]))
    mvwaddch(MapWindow, y, x, magicfx_tile[fx].Tile[frame])
    wmove(MapWindow, 0, 0)

    touchwin(MapWindow)
    wrefresh(MapWindow)


def nap(delay):
    """Delay for a number of milliseconds."""
    if _terminal is not None:
        _terminal.nap(delay)


def GetUser(username=""):
    """Get the username and user id.

    C signature GetUser(char *username, int *uid); here `username` is the
    name from the options file (may be empty) and the function returns the
    tuple (username, uid).

    UNIX branch: uid = getuid(), username = $USER.  When the OS provides no
    user id / name (e.g. Windows) the non-UNIX branch is used: ask the
    player for a name if none is given and look the uid up in a player id
    file, allocating a new one from FIRST_PID if needed.
    """
    env_user = os.environ.get("USER")
    if hasattr(os, "getuid") and env_user:
        return (env_user, os.getuid())

    if username is None or len(username) == 0:
        #
        # Name is not yet specified, so ask player for the name
        #
        Print("Who are you? ")
        username = get_string_input(ularn_game.USERNAME_LENGTH)

        if len(username) == 0:
            username = "Anon"

    # get the Player Id
    recsize = ularn_game.USERNAME_LENGTH + 1
    pidfile = user_path(PIDName)

    def _record(name, pid):
        b = name.encode("latin-1", "replace")[:recsize - 1]
        return b + b"\0" * (recsize - len(b)) + struct.pack("<i", pid)

    uid = FIRST_PID
    if not os.path.exists(pidfile):
        # Need to create the PID file.
        try:
            with open(pidfile, "wb") as fp:
                uid = FIRST_PID
                fp.write(_record(username, uid))
        except OSError:
            pass
    else:
        # search the PID file for this player id
        Found = 0
        TmpPid = FIRST_PID
        try:
            with open(pidfile, "rb") as fp:
                while not Found:
                    rec = fp.read(recsize + 4)
                    if len(rec) < recsize + 4:
                        break
                    TmpName = rec[:recsize].split(b"\0", 1)[0].decode("latin-1")
                    TmpPid = struct.unpack("<i", rec[recsize:])[0]
                    if TmpName == username:
                        uid = TmpPid
                        Found = 1
        except OSError:
            pass

        if not Found:
            uid = TmpPid + 1
            try:
                with open(pidfile, "ab") as fp:
                    fp.write(_record(username, uid))
            except OSError:
                pass

    return (username, uid)
