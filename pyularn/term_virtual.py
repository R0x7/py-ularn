"""In-memory terminal backend for tests and remote control (e.g. an MCP server).

Typical use with the game running in a background thread::

    term = VirtualTerminal()
    t = threading.Thread(target=ularn.run_game, args=(term, ["ularn", "-n"]),
                         daemon=True)
    t.start()
    term.wait_for_input(5)          # game is now blocked waiting for a key
    print("\\n".join(term.snapshot()))
    term.feed("j")                  # move south
    term.wait_for_input(5)          # wait until the game is idle again
    term.shutdown()                 # abort the game (getkey raises)
"""

import collections
import threading

from .header import UlarnExit
from . import ularn_win

ACS_TO_ASCII = {
    ularn_win.ACS_BLOCK: "#",
    ularn_win.ACS_HLINE: "-",
    ularn_win.ACS_VLINE: "|",
    ularn_win.ACS_ULCORNER: "+",
    ularn_win.ACS_URCORNER: "+",
    ularn_win.ACS_LLCORNER: "+",
    ularn_win.ACS_LRCORNER: "+",
    ularn_win.ACS_TTEE: "+",
    ularn_win.ACS_BTEE: "+",
    ularn_win.ACS_LTEE: "+",
    ularn_win.ACS_RTEE: "+",
    ularn_win.ACS_PLUS: "+",
}


class TerminalClosed(UlarnExit):
    """Raised from getkey() after shutdown(); ends the game like exit(1)."""

    def __init__(self):
        super().__init__(1)


class VirtualTerminal(ularn_win.Terminal):
    """An 80x24 character + attribute grid with a thread-safe key queue."""

    def __init__(self, cols=80, rows=24, colors=True, translate_newline=True):
        self.cols = cols
        self.rows = rows
        self.colors = colors
        self.translate_newline = translate_newline
        self._lock = threading.RLock()
        self._cond = threading.Condition(threading.Lock())
        self._queue = collections.deque()
        self._waiting = False
        self._closed = False
        self._finished = False
        self.input_requests = 0      # number of getkey() calls so far
        self.beeps = 0
        self.started = False
        self.cx = 0
        self.cy = 0
        self.chars = [[" "] * cols for _ in range(rows)]
        self.attrs = [[0] * cols for _ in range(rows)]
        self.pairs = {}
        self.last_key = None
        # Optional observer: on_frame(term) is called on the game thread each
        # time the game is about to wait for a key, and once when it ends.
        self.on_frame = None

    # ------------------------------------------------------------ lifecycle
    def start(self):
        with self._cond:
            self._finished = False
        self.started = True
        self.clear()

    def stop(self):
        self.started = False
        with self._cond:
            already = self._finished
            self._finished = True
            self._cond.notify_all()
        if not already:
            self._emit_frame()

    def mark_finished(self):
        """Mark the game as over (wakes up wait_for_input)."""
        with self._cond:
            already = self._finished
            self._finished = True
            self._cond.notify_all()
        if not already:
            self._emit_frame()

    @property
    def finished(self):
        with self._cond:
            return self._finished

    def shutdown(self):
        """Make the blocked (or next) getkey() raise TerminalClosed."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    # ------------------------------------------------------------ output
    def size(self):
        return (self.cols, self.rows)

    def has_colors(self):
        return self.colors

    def init_pair(self, pair, fg, bg):
        self.pairs[pair] = (fg, bg)

    def move(self, x, y):
        with self._lock:
            self.cx = max(0, min(self.cols - 1, x))
            self.cy = max(0, min(self.rows - 1, y))

    def put(self, s, attr=0):
        with self._lock:
            y = self.cy
            x = self.cx
            for ch in s:
                if x >= self.cols:
                    break
                self.chars[y][x] = ch
                self.attrs[y][x] = attr
                x += 1
            self.cx = min(x, self.cols - 1)

    def clear(self):
        with self._lock:
            for y in range(self.rows):
                for x in range(self.cols):
                    self.chars[y][x] = " "
                    self.attrs[y][x] = 0
            self.cx = 0
            self.cy = 0

    def clear_eol(self):
        with self._lock:
            for x in range(self.cx, self.cols):
                self.chars[self.cy][x] = " "
                self.attrs[self.cy][x] = 0

    def refresh(self):
        pass

    def beep(self):
        self.beeps += 1

    def nap(self, ms):
        pass

    # ------------------------------------------------------------ input
    def _emit_frame(self):
        cb = self.on_frame
        if cb is not None:
            try:
                cb(self)
            except Exception:  # an observer must never break the game
                import traceback
                traceback.print_exc()

    def getkey(self):
        """Block until a key is queued (signals waiters that we are idle)."""
        # Called on the game thread with the screen complete for this input:
        # a consistent moment for observers to look at the game.
        self._emit_frame()
        with self._cond:
            self.input_requests += 1
            self._waiting = True
            self._cond.notify_all()
            try:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    raise TerminalClosed()
                key = self._queue.popleft()
            finally:
                self._waiting = False
            self.last_key = key
            self._cond.notify_all()
            return key

    def feed(self, keys):
        """Queue input.

        `keys` is a str (each character is one key) or an iterable of keys
        (1-char strings or special key names such as "KEY_LEFT").  If
        translate_newline is set, '\\n' is queued as '\\r' (Enter under nonl()).
        """
        if isinstance(keys, str):
            keys = list(keys)
        with self._cond:
            for k in keys:
                if self.translate_newline and k == "\n":
                    k = "\r"
                self._queue.append(k)
            self._cond.notify_all()

    def pending(self):
        """Number of queued keys not yet read by the game."""
        with self._cond:
            return len(self._queue)

    def is_waiting(self):
        """True if the game is blocked in getkey() with no queued input."""
        with self._cond:
            return self._waiting and not self._queue

    def wait_for_input(self, timeout=None):
        """Wait until the game is idle (waiting for a key, queue empty) or over.

        Returns True if the game is waiting for input, False on timeout or if
        the game has finished.
        """
        with self._cond:
            ok = self._cond.wait_for(
                lambda: (self._waiting and not self._queue) or self._finished,
                timeout)
            if not ok:
                return False
            return self._waiting and not self._queue and not self._finished

    # ------------------------------------------------------------ inspection
    def snapshot(self, ascii_walls=False):
        """The screen as a list of `rows` strings (each `cols` wide)."""
        with self._lock:
            lines = []
            for row in self.chars:
                if ascii_walls:
                    lines.append("".join(ACS_TO_ASCII.get(ch, ch) for ch in row))
                else:
                    lines.append("".join(row))
            return lines

    def text(self, ascii_walls=False):
        """The screen as one string, trailing blanks stripped from each line."""
        return "\n".join(l.rstrip() for l in self.snapshot(ascii_walls))

    def cursor(self):
        """Current cursor position (x, y), 0-based."""
        with self._lock:
            return (self.cx, self.cy)

    def attr_at(self, x, y):
        """Attribute int at (x, y) (A_* flags | COLOR_PAIR(n))."""
        with self._lock:
            return self.attrs[y][x]
