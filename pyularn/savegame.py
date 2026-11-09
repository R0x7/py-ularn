"""Functions for saving and loading the game (port of savegame.c / savegame.h).

Exported functions:
  savegame    : Function to save the game
  restoregame : Function to load the game

Python port: the save file holds one pickled dict with exactly the state the
C write_player / write_levels / write_store / write_monster_data /
write_spheres functions write.  File layout (all through saveutils.bwrite so
the FileSum checksum is kept):

    4 bytes  little-endian length of the pickle
    n bytes  pickle of the state dict
    4 bytes  little-endian FileSum of everything before it
"""

import os
import pickle
import struct

from .header import *
from . import saveutils, ularn_game, ularn_win, monster, player
from . import dungeon, sphere, store, scores

SAVE_FORMAT = 1


# =============================================================================
# Local functions

def greedy():
    """Subroutine to not allow greedy cheaters (displays a message and quits)."""
    if player.wizard:
        return

    ularn_win.Print("\n\nI am so sorry but your character is a little TOO good!  Since this\n")
    ularn_win.Print("cannot normally happen from an honest game, I must assume that you cheated.\n")
    ularn_win.Print("Since you are GREEDY as well as a CHEATER, I cannot allow this game\n")
    ularn_win.Print("to continue.\n")
    ularn_win.nap(5000)
    player.cheat = 1
    player.c[player.GOLD] = player.c[player.BANKACCOUNT] = 0
    scores.died(scores.DIED_GREEDY_CHEATER, 0)
    return


def fsorry():
    """Subroutine to not allow altered save files; sets the cheat flag."""
    if player.cheat:
        return

    ularn_win.Print("\nSorry but your savefile has been altered.\n")
    ularn_win.Print("However, since I am a good sport, I will let you play.\n")
    ularn_win.Print("Be advised, though, that you won't be placed on the scoreboard.")
    player.cheat = 1
    ularn_win.nap(4000)


def fcheat():
    """Subroutine to not allow game if save file can't be deleted (quits the game)."""
    if player.wizard:
        return
    if player.cheat:
        return

    ularn_win.Print("\nSorry but your savefile can't be deleted.  This can only mean\n")
    ularn_win.Print("that you tried to CHEAT by protecting the directory the savefile\n")
    ularn_win.Print("is in.  Since this is unfair to the rest of the Ularn community, I\n")
    ularn_win.Print("cannot let you play this game.\n")
    ularn_win.nap(5000)
    player.c[player.GOLD] = player.c[player.BANKACCOUNT] = 0
    scores.died(scores.DIED_PROTECTED_SAVE_FILE, 0)
    return


# -----------------------------------------------------------------------------
# State collection / restoration (replaces the binary write_xxx / read_xxx
# calls of the C savegame / restoregame)

def _set(mod, name, value):
    """Assign a restored global back to its module (lists are updated in place)."""
    cur = getattr(mod, name, None)
    if isinstance(cur, list) and isinstance(value, list):
        cur[:] = value
    else:
        setattr(mod, name, value)


def _write_player(state):
    """State written by C write_player()."""
    state["player"] = {
        "char_class": player.char_class,
        "ramboflag": player.ramboflag,
        "wizard": player.wizard,
        "cheat": player.cheat,
        "playerx": player.playerx,
        "playery": player.playery,
        "initialtime": player.initialtime,
        "gtime": player.gtime,
        "outstanding_taxes": player.outstanding_taxes,
        "c": list(player.c),
        "iven": list(player.iven),
        "ivenarg": list(player.ivenarg),
        "potionknown": list(player.potionknown),
        "scrollknown": list(player.scrollknown),
        "spelknow": list(player.spelknow),
    }


def _read_player(state):
    """State read by C read_player(), including the class identification."""
    d = state["player"]
    for name in ("char_class", "ramboflag", "wizard", "cheat", "playerx",
                 "playery", "initialtime", "gtime", "outstanding_taxes",
                 "c", "iven", "ivenarg", "potionknown", "scrollknown",
                 "spelknow"):
        _set(player, name, d[name])

    # Identify the class number from the class string.
    # identify_class returns the character selection for the class, or 0
    # if the string matches no valid class.
    # (C's identify_class lower-cases char_class in place.)
    player.char_class = str(player.char_class).lower()
    class_num = player.identify_class(player.char_class)
    if class_num:
        if isinstance(class_num, str):
            class_num = ord(class_num)
        player.class_num = class_num - ord('a')
    else:
        # class got corrupt somehow, so reset to the first class
        table = player.InitialClassData
        if table is None and hasattr(player, "_class_data"):
            table = player._class_data()
        player.char_class = table[0].ClassName


def _write_levels(state):
    """State written by C write_levels()."""
    # Put the current level into storage
    dungeon.savelevel()

    state["dungeon"] = {
        # save which level the player is currently on
        "level": dungeon.level,
        # Save which levels have been visited by the player
        "beenhere": list(dungeon.beenhere),
        # Save each of the visited levels
        "saved_levels": {i: dungeon.saved_levels[i]
                         for i in range(dungeon.NLEVELS) if dungeon.beenhere[i]},
    }


def _read_levels(state):
    """State read by C read_levels()."""
    d = state["dungeon"]

    # Read which level the player is currently on
    dungeon.level = d["level"]

    # Read which levels have been visited by the player
    _set(dungeon, "beenhere", d["beenhere"])

    # Read each of the visited levels
    for i in range(dungeon.NLEVELS):
        if dungeon.beenhere[i]:
            dungeon.saved_levels[i] = d["saved_levels"][i]


def _write_monster_data(state):
    """State written by C write_monster_data()."""
    state["monster"] = {
        # the random monster generation time
        "rmst": monster.rmst,
        # genocide status
        "genocided": [1 if (monster.monster[i].flags & monster.FL_GENOCIDED) != 0 else 0
                      for i in range(monster.MAXMONST)],
    }


def _read_monster_data(state):
    """State read by C read_monster_data()."""
    d = state["monster"]

    # read the random monster generation time
    monster.rmst = d["rmst"]

    # read genocide status
    for i in range(monster.MAXMONST):
        if d["genocided"][i]:
            monster.monster[i].flags |= monster.FL_GENOCIDED


def _write_spheres(state):
    """State written by C write_spheres(): every sphere of the list, in list order."""
    recs = []
    sp = sphere.spheres
    while sp is not None:
        recs.append(sp)
        sp = sp.next
    state["spheres"] = recs


def _read_spheres(state):
    """State read by C read_spheres().

    As in C each sphere read is pushed onto the head of the list.
    """
    sphere.spheres = None

    for sp in state["spheres"]:
        sp.next = sphere.spheres
        sphere.spheres = sp


# =============================================================================
# Exported functions

def savegame(fname):
    """Save the current game data to file fname. Returns 0 if OK, -1 on error."""
    ularn_win.nosignal = 1

    # Save the current level to storage
    dungeon.savelevel()

    # make sure the interest on bank deposits is up to date
    store.ointerest()

    # try and create the save file
    try:
        fp = open(fname, "wb")
    except OSError:
        ularn_win.Printf("Can't open file <%s> to save game\n", fname)
        ularn_win.nosignal = 0
        return -1

    saveutils.FileSum = 0

    state = {"format": SAVE_FORMAT}
    _write_player(state)
    _write_levels(state)
    state["store"] = {}
    store.write_store(state["store"])
    _write_monster_data(state)
    _write_spheres(state)

    data = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)

    with fp:
        saveutils.bwrite(fp, struct.pack("<I", len(data)))
        saveutils.bwrite(fp, data)

        # file sum
        saveutils.bwrite(fp, struct.pack("<I", saveutils.FileSum & 0xFFFFFFFF))

    ularn_win.nosignal = 0

    return 0


def restoregame(fname):
    """Restore a game from file fname."""
    c = player.c

    try:
        fp = open(fname, "rb")
    except OSError:
        ularn_win.Printf("Can't open file <%s> to restore game\n", fname)
        ularn_win.nap(4000)
        c[player.GOLD] = c[player.BANKACCOUNT] = 0
        scores.died(scores.DIED_MISSING_SAVE_FILE, 0)
        return

    ularn_win.Printf(" Reading data...")
    dungeon.init_cells()

    saveutils.FileSum = 0

    with fp:
        (n,) = struct.unpack("<I", saveutils.bread(fp, 4))
        data = saveutils.bread(fp, n)

        # sum of everything so far
        thesum = saveutils.FileSum & 0xFFFFFFFF

        (asum,) = struct.unpack("<I", saveutils.bread(fp, 4))

    # read_player / read_levels / read_store / read_monster_data / read_spheres
    # (in C these come before the checksum test, so a restored cheat flag
    # does not hide fsorry())
    try:
        state = pickle.loads(data)
        _read_player(state)
        _read_levels(state)
        store.read_store(state["store"])
        _read_monster_data(state)
        _read_spheres(state)
    except UlarnExit:
        raise
    except Exception:
        # The save data could not be decoded: same handling as a failed bread
        ularn_win.Printf("Error reading from save file\n")
        ularn_win.nap(4000)
        scores.died(scores.DIED_POST_MORTEM_DEATH, 0)
        return

    if asum != thesum:
        fsorry()

    player.lastpx = 0
    player.lastpy = 0

    if fname == ularn_game.ckpfile:
        try:
            fp = open(fname, "ab+")
        except OSError:
            # Hmmm. We should be able to write to this file, something fishy
            # is going on.
            fcheat()
        else:
            fp.close()
    else:
        try:
            os.unlink(fname)
        except OSError:
            # can't unlink save file
            fcheat()

    # for the greedy cheater checker
    TotalAttr = 0
    for i in range(player.ABILITY_FIRST, player.ABILITY_LAST):
        TotalAttr += c[i]
        if c[i] > 300:
            greedy()

    if TotalAttr > 600:
        greedy()

    if c[player.HPMAX] > 999 or c[player.SPELLMAX] > 125:
        greedy()

    # XP has been boosted in the save file, so fix character level
    if c[player.LEVEL] == 25 and c[player.EXPERIENCE] > player.skill[24]:
        tmp_xp = c[player.EXPERIENCE] - player.skill[24]  # amount to go up
        c[player.EXPERIENCE] = player.skill[24]
        player.raiseexperience(tmp_xp)

    # Get the current dungeon level from storage
    dungeon.getlevel()
