"""Game data used by Ularn (port of ularn_game.c / ularn_game.h).

This Contains:
  . The names of data files used by ularn
  . The player's name
  . Current game options

Exported functions: newgame, sethard, read_options.
"""

import time as _time

from .header import *
from . import player, monster, scores, ularn_win

# =============================================================================
# ularn_game.h definitions

# *************** File Names ***************
SCORENAME = "Uscore"
HELPNAME = "Uhelp"
LEVELSNAME = "Umaps"
FORTSNAME = "Ufortune"

# maximum number moves before the game is called
TIMELIMIT = 40000

# create a checkpoint file every CKCOUNT moves
CKCOUNT = 400

# max size of the players name
LOGNAMESIZE = 40
USERNAME_LENGTH = 40

MAXPATHLEN = 1024

# config.h LIBDIR: the library files directory.  In the Python port the
# read-only library files are shipped in the package data directory.
LIBDIR = DATA_DIR

# =============================================================================
# Exported variables

# Game options
do_fork = 0  # 1=fork on save, 0=save from main process. NOT SUPPORTED
boldon = 1   # 1=bold objects,  0=inverse objects
mail = 1     # 1=mail letters after win game
ckpflag = 1  # 1 if want checkpointing of game, 0 otherwise
nobeep = 0   # true if program is not to beep

libdir = LIBDIR

# The directory for saved games (set by ularn.main; default is the user dir)
savedir = ""

# the game save filename
savefilename = ""

# the temporary save filename
tempfilename = ""

# the score file (the Python port keeps the score file in the user directory)
scorefile = user_path(SCORENAME)

# the help text file
helpfile = data_path(HELPNAME)

# the maze data file
larnlevels = data_path(LEVELSNAME)

# the fortune data file
fortfile = data_path(FORTSNAME)

# the options file filename
optsfile = "ularn.opt"

# the checkpoint file filename
ckpfile = "ularn.ckp"

# the diagnostic filename
diagfile = "diagfile.txt"

# the wizard's password
password = "fizban"

userid = 0          # the players login user id number
loginname = ""      # players login name
logname = ""        # players name storage for scoring

nowelcome = 0          # if nowelcome, don't display welcome message
nomove = 0             # if nomove no count next iteration as move
dropflag = 0           # if 1 then don't lookforobject() next round
restorflag = 0         # 1 means restore has been done
enhance_interface = 0  # 1 means use the enhanced command interface

# Direction deltas
diroffx = [0, 0, 1, 0, -1, 1, -1, 1, -1]
diroffy = [0, 1, 0, -1, 0, -1, -1, 1, 1]
ReverseDir = [0, 3, 4, 1, 2, 8, 7, 6, 5]

dirname = [
    "None",
    "South",
    "East",
    "North",
    "West",
    "Northeast",
    "Northwest",
    "Southeast",
    "Southwest",
]

# =============================================================================
# Local variables

LINE_LEN = 256

# OptionType
OPTION_NULL = 0
OPTION_NAME = 1
OPTION_CLASS = 2
OPTION_GENDER = 3
OPTION_NAP = 4
OPTION_NONAP = 5
OPTION_WELCOME = 6
OPTION_NOWELCOME = 7
OPTION_ENHANCE_INT = 8
OPTION_NOENHANCE_INT = 9
OPTION_BEEP = 10
OPTION_NOBEEP = 11
OPTION_COUNT = 12

OptionString = [
    "",
    "name",
    "class",
    "gender",
    "nap",
    "nonap",
    "welcome",
    "nowelcome",
    "enhanced_interface",
    "noenhanced_interface",
    "beep",
    "nobeep",
]


class _Strtok:
    """Emulation of C strtok() on one string (strtok(Line,..) then strtok(NULL,..))."""

    def __init__(self, s):
        self.s = s
        self.pos = 0

    def next(self, delims):
        s = self.s
        n = len(s)
        p = self.pos
        # skip leading delimiters
        while p < n and s[p] in delims:
            p += 1
        if p >= n:
            self.pos = n
            return None
        start = p
        while p < n and s[p] not in delims:
            p += 1
        tok = s[start:p]
        # the delimiter is overwritten by '\0'; the next scan starts after it
        self.pos = p + 1 if p < n else n
        return tok


# =============================================================================
# Exported functions

def newgame():
    """Perform initialisation for a new game."""
    player.initialtime = int(_time.time())
    srand(player.initialtime & 0xFFFFFFFF)


def sethard(hard):
    """Set the game difficulty level (-1 => default hardness)."""
    if restorflag == 0:
        # don't set c[HARDGAME] if restoring game
        if scores.hashewon() == 0:
            if hard >= 0:
                player.c[player.HARDGAME] = hard
        elif hard > player.c[player.HARDGAME] or player.wizard:
            player.c[player.HARDGAME] = hard

    k = player.c[player.HARDGAME]
    if k != 0:
        for j in range(0, monster.MAXMONST + 8 + 1):
            m = monster.monster[j]

            i = cdiv((6 + k) * m.hitpoints + 1, 6)
            m.hitpoints = 32767 if i > 32767 else i

            i = cdiv((6 + k) * m.damage + 1, 5)
            m.damage = 127 if i > 127 else i

            i = cdiv(10 * m.gold, 10 + k)
            m.gold = 32767 if i > 32767 else i

            i = m.armorclass - k
            m.armorclass = -127 if i < -127 else i

            i = cdiv(7 * m.experience, 7 + k) + 1
            m.experience = 1 if i <= 0 else i


def read_options():
    """Read the ularn options file."""
    global logname, nowelcome, enhance_interface, nobeep, libdir, savedir

    try:
        fp = open(optsfile, "r")
    except OSError:
        # Couldn't open the options file.
        return

    with fp:
        while True:
            # fgets(Line, LINE_LEN, fp) reads at most LINE_LEN-1 characters
            Line = fp.readline(LINE_LEN - 1)

            if Line == "":
                # End of file
                break
            elif Line[0] == '#':
                # Comment line - do nothing
                pass
            else:
                st = _Strtok(Line)
                tok = st.next(" \t\n=")
                if tok is None:
                    # A blank line
                    pass
                elif tok == "OPTION":
                    # Read all options specified on this line.
                    while True:
                        # get the option string
                        tok = st.next(",:\n")

                        # identify the option
                        if tok is None:
                            OptionId = OPTION_NULL
                        else:
                            OptionId = OPTION_NAME
                            Found = 0
                            while OptionId < OPTION_COUNT and not Found:
                                if OptionString[OptionId] == tok:
                                    Found = 1
                                else:
                                    OptionId += 1

                        if OptionId == OPTION_NULL:
                            pass

                        elif OptionId == OPTION_NAME:
                            tok = st.next(":,\n")
                            if tok is not None:
                                logname = tok[:LOGNAMESIZE]

                        elif OptionId == OPTION_CLASS:
                            tok = st.next(":,\n")
                            player.char_picked = player.identify_class(tok)

                        elif OptionId == OPTION_GENDER:
                            tok = st.next(":,\n")
                            if tok == "male":
                                player.sex = 1
                            elif tok == "female":
                                player.sex = 0
                            else:
                                ularn_win.Printf("\nUnknown gender '%s'", tok)

                        elif OptionId == OPTION_NAP:
                            ularn_win.nonap = 0

                        elif OptionId == OPTION_NONAP:
                            ularn_win.nonap = 1

                        elif OptionId == OPTION_WELCOME:
                            nowelcome = 0

                        elif OptionId == OPTION_NOWELCOME:
                            nowelcome = 1

                        elif OptionId == OPTION_ENHANCE_INT:
                            enhance_interface = 1

                        elif OptionId == OPTION_NOENHANCE_INT:
                            enhance_interface = 0

                        elif OptionId == OPTION_BEEP:
                            nobeep = 0

                        elif OptionId == OPTION_NOBEEP:
                            nobeep = 1

                        else:
                            ularn_win.Printf("\nUnrecognised option '%s'", tok)

                        if not (OptionId != OPTION_NULL and OptionId < OPTION_COUNT):
                            break

                elif tok == "LIBDIR":
                    tok = st.next(":\n")
                    if tok is not None:
                        libdir = tok
                elif tok == "SAVEDIR":
                    tok = st.next(":\n")
                    if tok is not None:
                        savedir = tok
                else:
                    ularn_win.Printf("\nUnrecognised option '%s'", tok)
