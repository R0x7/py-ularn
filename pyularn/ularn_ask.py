"""Common questions asked of the player (port of ularn_ask.c / ularn_ask.h).

more        - Asks press space to continue
clearpager  - resets pagination calculations for paged text output
pager       - Call to perform pagination after each line of text is output
getyn       - Asks for a yes no answer
getpassword - Get the password for wizard
dirsub      - Asks for a direction
"""

from .header import *
from . import ularn_game, ularn_win, player

# the current line number for paginating text
srcount = 0


def more():
    """Ask the player to press space to continue."""
    ularn_win.Print("\n  --- press ")
    ularn_win.Standout("space")
    ularn_win.Print(" to continue --- ")
    ularn_win.get_prompt_input("", " ", 0)


def clearpager():
    """Reset the pagination line count."""
    global srcount
    srcount = 0


def pager():
    """Call after each line of paged output; pauses every 22 lines."""
    global srcount
    srcount += 1
    if srcount >= 22:
        srcount = 0
        more()
        ularn_win.ClearText()


def getyn():
    """Get a y/Y/n/N/ESC answer (space counts as ESC). Returns the 1-char str."""
    i = ularn_win.get_prompt_input("", "yYnN\033 ", 1)

    if i.isspace():
        i = ESC

    return i


def getpassword():
    """Ask for the wizard password. Returns 1 if correct, else 0."""
    ularn_win.Print("\nEnter Password: ")

    gpwbuf = ularn_win.get_password_input(8)

    if gpwbuf != ularn_game.password:
        ularn_win.Print("\nSorry.\n")
        return 0
    else:
        return 1


def dirsub(x=0, y=0):
    """Ask for a direction.

    C signature int dirsub(int *x, int *y); the x, y arguments are ignored
    (accepted for call compatibility) and the tuple (d, x, y) is returned:
    d is the direction index (1..8, matching diroffx/diroffy) and (x, y)
    is the cell next to the player in that direction.
    """
    #
    # Direction keys. Order must match diroff
    #
    dir_order = [
        ularn_win.ACTION_MOVE_SOUTH,
        ularn_win.ACTION_MOVE_EAST,
        ularn_win.ACTION_MOVE_NORTH,
        ularn_win.ACTION_MOVE_WEST,
        ularn_win.ACTION_MOVE_NORTHEAST,
        ularn_win.ACTION_MOVE_NORTHWEST,
        ularn_win.ACTION_MOVE_SOUTHEAST,
        ularn_win.ACTION_MOVE_SOUTHWEST,
        0,
    ]

    ans = ularn_win.get_dir_input("\nIn What Direction? ", 1)

    d = 0
    while dir_order[d] != ans:
        d += 1

    d += 1

    ularn_win.Print(ularn_game.dirname[d])

    x = player.playerx + ularn_game.diroffx[d]
    y = player.playery + ularn_game.diroffy[d]

    return (d, x, y)
