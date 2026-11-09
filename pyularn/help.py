"""Help file and welcome screen (port of help.c / help.h).

Format of the Ularn help file:

The 1st character of file is the # of pages of help available (ascii digit).
The first page (23 lines) of the file is for the introductory message
(not counted in above).
The pages of help text are 23 lines per page.
The help file allows escape sequences for specifying formatting of the text.
The currently supported sequences are:
  ^[[7m - Set text format to standout  (red)
  ^[[8m - Set text format to standout2 (green)
  ^[[9m - Set text format to standout3 (blue)
  ^[[m  - Set text format to normal.

EXPORTED FUNCTIONS
  help    - Display the help file.
  welcome - Display the welcome message
"""

from .header import *
from . import ularn_game, ularn_win

# =============================================================================
# Local variables

# Help file escape sequence states.
HELP_NORMAL = 0
HELP_ESC = 1
HELP_COUNT = 2

# The help file handle.
help_fp = None

# Contents of the C tmbuf in show_help_page (fgets leaves the buffer
# unchanged at end of file, so the previous line is printed again).
_tmbuf = ""


def _helpfile():
    """Name of the help file (ularn_game.helpfile, default data_path("Uhelp"))."""
    name = ularn_game.helpfile
    if not name:
        name = data_path("Uhelp")
    return name


def _fgets(fp, n):
    """Emulate fgets(buf, n, fp); returns None at end of file."""
    s = fp.readline(n - 1)
    if s == "":
        return None
    return s


# =============================================================================
# Local functions

def retcont():
    """Say press return to continue."""
    ularn_win.MoveCursor(1, 24)
    ularn_win.Print("Press ")
    ularn_win.Standout("return")
    ularn_win.Print(" to continue: ")

    ularn_win.get_prompt_input("", "\015\033", 0)


def openhelp():
    """Open the help file and return the number of pages (-1 on failure)."""
    global help_fp
    name = _helpfile()
    try:
        help_fp = open(name, "r", encoding="latin-1")
    except OSError:
        help_fp = None
        ularn_win.Printf("Can't open help file \"%s\" ", name)

        ularn_win.nap(4000)
        return -1

    ch = help_fp.read(1)
    if ch == "":
        return -1 - ord('0')   # fgetc returned EOF
    return ord(ch) - ord('0')


def show_help_page():
    """Print the next page of help in the help file."""
    global _tmbuf

    ularn_win.ClearText()

    for line in range(23):
        s = _fgets(help_fp, 128)
        if s is not None:
            _tmbuf = s
        tmbuf = _tmbuf

        line_len = len(tmbuf)

        state = HELP_NORMAL

        line_pos = 0
        while line_pos < line_len:
            if state == HELP_NORMAL:
                if (tmbuf[line_pos] == '^') and ((line_pos + 3) < line_len):
                    if (tmbuf[line_pos + 1] == '[') and (tmbuf[line_pos + 2] == '['):
                        state = HELP_ESC
                        line_pos += 3

                if state == HELP_NORMAL:
                    ularn_win.Printc(tmbuf[line_pos])
                    line_pos += 1

            elif state == HELP_ESC:
                if tmbuf[line_pos] == '7':
                    ularn_win.SetFormat(ularn_win.FORMAT_STANDOUT)
                    line_pos += 1
                elif tmbuf[line_pos] == '8':
                    ularn_win.SetFormat(ularn_win.FORMAT_STANDOUT2)
                    line_pos += 1
                elif tmbuf[line_pos] == '9':
                    ularn_win.SetFormat(ularn_win.FORMAT_STANDOUT3)
                    line_pos += 1
                elif tmbuf[line_pos] == 'm':
                    ularn_win.SetFormat(ularn_win.FORMAT_NORMAL)

                line_pos += 1
                state = HELP_NORMAL


def _close_help():
    global help_fp
    if help_fp is not None:
        help_fp.close()
    help_fp = None


# =============================================================================
# Exported functions

def help():
    """Display the help file."""
    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    # open the help file and get # pages
    num_pages = openhelp()

    if num_pages < 0:
        _close_help()
        ularn_win.set_display(ularn_win.DISPLAY_MAP)
        return

    # skip over intro message
    for i in range(23):
        _fgets(help_fp, 128)

    page = num_pages
    while page > 0:
        show_help_page()

        # intercept ESC's
        if page > 1:
            ularn_win.Print("    ---- Press ")
            ularn_win.Standout("return")
            ularn_win.Print(" to exit, ")
            ularn_win.Standout("space")
            ularn_win.Print(" for more help ---- ")

            i = ularn_win.get_prompt_input("", " \015\033", 0)

            if (i == '\015') or (i == ESC):
                _close_help()
                ularn_win.set_display(ularn_win.DISPLAY_MAP)

                return
        page -= 1

    _close_help()
    retcont()

    ularn_win.set_display(ularn_win.DISPLAY_MAP)


def welcome():
    """Display the welcome message and background."""
    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    # open the help file
    num_pages = openhelp()
    if num_pages < 0:
        _close_help()
        return

    show_help_page()

    _close_help()

    # press return to continue
    retcont()

    ularn_win.set_display(ularn_win.DISPLAY_MAP)
