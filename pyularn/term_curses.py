"""curses terminal backend (stdlib curses; on Windows: pip install windows-curses)."""

import time

from . import ularn_win

try:
    import curses
except ImportError:  # pragma: no cover - depends on the platform
    curses = None


class CursesTerminal(ularn_win.Terminal):
    """Terminal backend drawing on the curses stdscr."""

    def __init__(self):
        if curses is None:
            raise RuntimeError(
                "the curses module is not available "
                "(on Windows install it with: pip install windows-curses)")
        self.scr = None
        self._colors = False
        self._acs = {}
        self._keymap = {}

    # ------------------------------------------------------------ lifecycle
    def start(self):
        """initscr(); cbreak(); noecho(); nonl(); keypad() as in init_app."""
        self.scr = curses.initscr()
        curses.cbreak()
        curses.noecho()
        curses.nonl()
        try:
            self.scr.intrflush(False)
        except (curses.error, AttributeError):
            pass
        try:
            curses.start_color()
        except curses.error:
            pass
        self.scr.keypad(True)
        self._colors = bool(curses.has_colors())

        self._acs = {
            ularn_win.ACS_BLOCK: curses.ACS_BLOCK,
            ularn_win.ACS_HLINE: curses.ACS_HLINE,
            ularn_win.ACS_VLINE: curses.ACS_VLINE,
            ularn_win.ACS_ULCORNER: curses.ACS_ULCORNER,
            ularn_win.ACS_URCORNER: curses.ACS_URCORNER,
            ularn_win.ACS_LLCORNER: curses.ACS_LLCORNER,
            ularn_win.ACS_LRCORNER: curses.ACS_LRCORNER,
            ularn_win.ACS_TTEE: curses.ACS_TTEE,
            ularn_win.ACS_BTEE: curses.ACS_BTEE,
            ularn_win.ACS_LTEE: curses.ACS_LTEE,
            ularn_win.ACS_RTEE: curses.ACS_RTEE,
            ularn_win.ACS_PLUS: curses.ACS_PLUS,
        }

        km = {}
        for name, value in (
                ("KEY_LEFT", "KEY_LEFT"), ("KEY_RIGHT", "KEY_RIGHT"),
                ("KEY_UP", "KEY_UP"), ("KEY_DOWN", "KEY_DOWN"),
                ("KEY_A1", "KEY_A1"), ("KEY_A3", "KEY_A3"),
                ("KEY_B2", "KEY_B2"), ("KEY_C1", "KEY_C1"),
                ("KEY_C3", "KEY_C3"),
                # keypad keys that many terminals report under other names
                ("KEY_HOME", "KEY_A1"), ("KEY_PPAGE", "KEY_A3"),
                ("KEY_END", "KEY_C1"), ("KEY_NPAGE", "KEY_C3"),
                ("KEY_BACKSPACE", "\010"), ("KEY_ENTER", "\r")):
            code = getattr(curses, name, None)
            if code is not None and code not in km:
                km[code] = value
        # PDCurses (windows-curses) keypad codes
        for name, value in (("KEY_A2", "KEY_UP"), ("KEY_B1", "KEY_LEFT"),
                            ("KEY_B3", "KEY_RIGHT"), ("KEY_C2", "KEY_DOWN"),
                            ("PADENTER", "\r")):
            code = getattr(curses, name, None)
            if code is not None and code not in km:
                km[code] = value
        self._keymap = km

    def stop(self):
        """nl(); echo(); nocbreak(); endwin() as in close_app."""
        if self.scr is None:
            return
        try:
            curses.nl()
            curses.echo()
            curses.nocbreak()
            self.scr.keypad(False)
        except curses.error:
            pass
        curses.endwin()
        self.scr = None

    # ------------------------------------------------------------ output
    def size(self):
        y, x = self.scr.getmaxyx()
        return (x, y)

    def has_colors(self):
        return self._colors

    def init_pair(self, pair, fg, bg):
        # pair 0 is fixed to the default colours in curses
        if pair <= 0 or not self._colors:
            return
        try:
            curses.init_pair(pair, fg, bg)
        except curses.error:
            pass

    def _attr(self, attr):
        a = 0
        if attr & ularn_win.A_STANDOUT:
            a |= curses.A_STANDOUT
        if attr & ularn_win.A_UNDERLINE:
            a |= curses.A_UNDERLINE
        if attr & ularn_win.A_REVERSE:
            a |= curses.A_REVERSE
        if attr & ularn_win.A_BLINK:
            a |= curses.A_BLINK
        if attr & ularn_win.A_BOLD:
            a |= curses.A_BOLD
        pair = ularn_win.PAIR_NUMBER(attr)
        if pair and self._colors:
            a |= curses.color_pair(pair)
        return a

    def move(self, x, y):
        try:
            self.scr.move(y, x)
        except curses.error:
            pass

    def put(self, s, attr=0):
        a = self._attr(attr)
        for ch in s:
            code = self._acs.get(ch)
            try:
                if code is not None:
                    self.scr.addch(code, a)
                else:
                    self.scr.addstr(ch, a)
            except curses.error:
                # writing the bottom right corner raises; the char is shown
                pass

    def clear(self):
        self.scr.clear()

    def clear_eol(self):
        self.scr.clrtoeol()

    def refresh(self):
        self.scr.refresh()

    def beep(self):
        try:
            curses.beep()
        except curses.error:
            pass

    def getkey(self):
        while True:
            try:
                code = self.scr.getch()
            except KeyboardInterrupt:
                raise
            if code == -1:
                continue
            if code in self._keymap:
                return self._keymap[code]
            if code == 127:
                # DEL from the backspace key
                return "\010"
            if 0 <= code < 256:
                return chr(code)
            if code == getattr(curses, "KEY_RESIZE", None):
                continue
            try:
                name = curses.keyname(code).decode("ascii", "replace")
            except (ValueError, curses.error):
                name = "KEY_%d" % code
            return name

    def nap(self, ms):
        if self.scr is not None:
            self.scr.refresh()
        time.sleep(ms / 1000.0)
