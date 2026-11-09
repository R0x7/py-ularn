"""Dungeon levels module (port of dungeon.c / dungeon.h).

This module provides functions to create, load, save etc dungeon levels.

EXPORTED VARIABLES

  item      : The item at each location on the current level
  know      : What the player beleives is at each location
  moved     : The monster moved status for each dungeon location
  stealth   : The monster stealth status for each dungeon location
  hitp      : The monster hit points for each dungeon location
  iarg      : The item arg for each dungeon location
  screen    : Screen data used in moving monsters
  mitem     : The monster and items it has stolen for each dungeon location
  beenhere  : Which dungeon levels have been visited
  level     : The current dungeon level
  levelname : The name of each dungeon level
"""

import array
import pickle
import sys

from .header import *
from . import itm, monster, player, potion, scroll, scores, ularn_game, ularn_win

# =============================================================================
# Exported constants (dungeon.h)

MAXLEVEL = 16   # max # levels in the dungeon + 1
MAXVLEVEL = 5   # max # of levels in the volcano
NLEVELS = (MAXLEVEL + MAXVLEVEL)
DBOTTOM = (MAXLEVEL - 1)
VBOTTOM = (MAXLEVEL + MAXVLEVEL - 1)

# Dungeon level size. MUST bo odd.
MAXX = 67
MAXY = 17

#
# Stealth flags for monsters.
#   STEALTH_SEEN   indicates that the player has seen or somehow knowns
#                  about the monster.
#
#   STEALTH_AWAKE  indicates that the monster is awake and will move
#                  about the dungeon.
#
# A monster will be displayed on the map if
#   1. The player's knowledge of the cell containing the monster is not
#      OUNKNOWN,
# and either:
#   2a. The monster has been seen (STEALTH_SEEN set) or,
#   2b. The monster is awake (STEALTH_AWAKE set)
#       (Awake monsters are assumed to be making noise)
#
STEALTH_SEEN = 1
STEALTH_AWAKE = 2


# =============================================================================
# Items stolen by monsters data structure

class StolenItem:
    """An item carried (stolen) by a monster."""

    __slots__ = ("item", "itemarg")

    def __init__(self, item=0, itemarg=0):
        self.item = item
        self.itemarg = itemarg


class struct_mitem:
    """The monster at a location and the items it has stolen."""

    __slots__ = ("mon", "n", "it")

    def __init__(self, mon=0, n=0, it=None):
        self.mon = mon
        self.n = n
        if it is None:
            it = [StolenItem() for _ in range(6)]
        self.it = it

    def copy(self):
        """Return an independent copy of this record."""
        return struct_mitem(self.mon, self.n,
                            [StolenItem(s.item, s.itemarg) for s in self.it])

    def assign(self, other):
        """In place copy of another record into this one (C struct assign)."""
        self.mon = other.mon
        self.n = other.n
        for d, s in zip(self.it, other.it):
            d.item = s.item
            d.itemarg = s.itemarg


# =============================================================================
# Exported variables

item = [[0] * MAXY for _ in range(MAXX)]      # objects in maze if any
know = [[0] * MAXY for _ in range(MAXX)]      # 1 or 0 if here before
moved = [[0] * MAXY for _ in range(MAXX)]     # monster movement flags
stealth = [[0] * MAXY for _ in range(MAXX)]   # See Stealth flags
hitp = [[0] * MAXY for _ in range(MAXX)]      # monster hp on level
iarg = [[0] * MAXY for _ in range(MAXX)]      # arg for the item array
screen = [[0] * MAXY for _ in range(MAXX)]    # The screen as the player knows it
mitem = [[struct_mitem() for _ in range(MAXY)] for _ in range(MAXX)]  # Items stolen by monstes array

#
# This serves two purposes:
#   1. Indicates which levels have been visited by the player.
#        0  => not visited
#        >0 => visited
#   2. Indicates how many items have been stolen from the player on this level.
#      This is used as a sanity check. Don't blame me, it was like this
#      when I got here :-)
#      Each time an item is stolen this is incremented.
#      When the monster that stole the items is killed, this is decremented
#      for each item the monster drops.
#
beenhere = [0] * NLEVELS

level = 0               # cavelevel player is on = c[CAVELEVEL]

levelname = [
    " H", " 1", " 2", " 3", " 4", " 5",
    " 6", " 7", " 8", " 9", "10", "11", "12", "13", "14", "15",
    "V1", "V2", "V3", "V4", "V5"
]


# =============================================================================
# Macros from dungeon.h

def forget():
    """Destroy object at present location.

    As the player is there, obviously it is known to be destroyed.
    """
    item[player.playerx][player.playery] = itm.ONOTHING
    know[player.playerx][player.playery] = itm.ONOTHING


def disappear(x, y):
    """Wipe out a monster at a location.

    Redraw the location if it is not unknown.
    """
    mitem[x][y].mon = 0
    if know[x][y] != itm.OUNKNOWN:
        ularn_win.show1cell(x, y)


def vxy(x, y):
    """Verify coordinates (C macro).  Returns the adjusted (x, y)."""
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    if x >= MAXX:
        x = MAXX - 1
    if y >= MAXY:
        y = MAXY - 1
    return x, y


# =============================================================================
# Local variables

#
# Data and macros for finding the number of +s for items.
#
NUM_LEATHER_PTS = 15
NUM_H_LEATHER_PTS = 12
nlpts = [0, 0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7]

NUM_CHAIN_PTS = 10
nch = [0, 0, 0, 1, 1, 1, 2, 2, 3, 4]

NUM_PLATE_PTS = 10
NUM_H_PLATE_PTS = 3
nplt = [0, 0, 0, 0, 1, 1, 2, 2, 3, 4]

NUM_DAGGER_PTS = 13
ndgg = [0, 0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 4, 5]

NUM_SWORD_PTS = 13
NUM_H_SWORD_PTS = 6
nsw = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 3]


def newleather():
    """return the + points on created leather armor"""
    return nlpts[rund(NUM_H_LEATHER_PTS if player.c[player.HARDGAME] else NUM_LEATHER_PTS)]


def newchain():
    """return the + points on chain armor"""
    return nch[rund(NUM_CHAIN_PTS)]


def newplate():
    """return + points on plate armor"""
    return nplt[rund(NUM_H_PLATE_PTS if player.c[player.HARDGAME] else NUM_PLATE_PTS)]


def newdagger():
    """return + points on new daggers"""
    return ndgg[rund(NUM_DAGGER_PTS)]


def newsword():
    """return + points on new swords"""
    return nsw[rund(NUM_H_SWORD_PTS if player.c[player.HARDGAME] else NUM_SWORD_PTS)]


class Saved_Level:
    """This is the structure that holds the entire dungeon specifications."""

    def __init__(self):
        self.hitp = [[0] * MAXY for _ in range(MAXX)]
        self.mitem = [[struct_mitem() for _ in range(MAXY)] for _ in range(MAXX)]
        self.item = [[0] * MAXY for _ in range(MAXX)]
        self.iarg = [[0] * MAXY for _ in range(MAXX)]  # must be long for goldpiles
        self.know = [[0] * MAXY for _ in range(MAXX)]


saved_levels = [None] * NLEVELS

level_sums = [0] * NLEVELS


def _storage_sum(storage):
    """Checksum of a stored level (replaces sum() over the raw C struct).

    Uses the same algorithm as saveutils.sum() applied to the level data
    packed as 16 bit values.
    """
    vals = array.array("H")
    for x in range(MAXX):
        vals.extend(v & 0xFFFF for v in storage.hitp[x])
    for x in range(MAXX):
        for m in storage.mitem[x]:
            vals.append(m.mon & 0xFFFF)
            vals.append(m.n & 0xFFFF)
            for s in m.it:
                vals.append(s.item & 0xFFFF)
                vals.append(s.itemarg & 0xFFFF)
    for x in range(MAXX):
        vals.extend(v & 0xFFFF for v in storage.item[x])
    for x in range(MAXX):
        vals.extend(v & 0xFFFF for v in storage.iarg[x])
    for x in range(MAXX):
        vals.extend(v & 0xFFFF for v in storage.know[x])

    s = 0
    for ch in vals.tobytes():
        if s & 0o1:
            s = (s >> 1) + 0x8000
        else:
            s >>= 1
        s += ch
        s &= 0xFFFF
    return s


# =============================================================================
# Local functions

def cannedlevel(lev):
    """Function to read in a maze from a data file.

    Only read in a maze 50% of time.

    Format of maze data file:
      Must contain 21 mazes
        For each maze:
            18 lines (1st 17 used)
            67 characters per line

      Line seperating maps must be single newline character

      Special characters in maze data file:

        # wall                D door
        . random monster      ~ eye of larn
        ! cure dianthroritis  - random object

    Returns 1 for success, -1 for error/use random maze.
    """
    if (lev != DBOTTOM) and (lev != VBOTTOM):
        #
        # The bottom levels are always read from the file.
        # Only read a maze from file around half the time for regular levels.
        #
        if rnd(100) < 50:
            return -1

    try:
        fp = open(data_path("Umaps"), "r")
    except OSError:
        return -1

    with fp:
        #
        # Umap format
        # - lines must be MAXX characters long
        # - must be MAXY characters per map
        # - each map must be seperated by 1 blank line
        #  (a single newline character)
        #

        #
        # Decide which map to use and move to the location of the map in the
        # levels file.
        #
        i = rund(20)
        for j in range(i):
            # Skip a level + the blank line
            for k in range(MAXY + 1):
                row = fp.readline()
                if row == "":
                    sys.stderr.write("fgets: unexpected end of file\n")
                    return -1

        #
        # Read the level from the file
        #
        for i in range(MAXY):
            row = fp.readline()
            if row == "":
                sys.stderr.write("fgets: unexpected end of file\n")
                return -1

            for j in range(MAXX):
                it = itm.ONOTHING
                Monst = monster.MONST_NONE
                arg = 0
                marg = 0
                ch = row[j] if j < len(row) else "\0"
                if ch == "#":
                    it = itm.OWALL
                elif ch == "D":
                    it = itm.OCLOSEDDOOR
                    arg = rnd(30)
                elif ch == "~":
                    if lev == DBOTTOM:
                        it = itm.OLARNEYE
                        Monst = monster.DEMONPRINCE
                        marg = monster.monster[Monst].hitpoints
                elif ch == "!":
                    if lev == VBOTTOM:
                        it = itm.OPOTION
                        arg = 21
                        Monst = monster.LUCIFER
                        marg = monster.monster[Monst].hitpoints
                elif ch == ".":
                    if not (lev <= DBOTTOM - 5):
                        Monst = monster.makemonst(lev + 1)
                        marg = monster.monster[Monst].hitpoints
                elif ch == "-":
                    it, arg = newobject(lev + 1)

                item[j][i] = it
                iarg[j][i] = arg
                mitem[j][i].mon = Monst
                hitp[j][i] = marg
                know[j][i] = item[j][i] if player.wizard else itm.OUNKNOWN

    return 1


def troom(lv, xsize, ysize, tx, ty, glyph):
    """Function to create a treasure room of any size at a given location.

    The room is filled with objects and monsters.
    The coordinate given is that of the upper left corner of the room.
    """
    # clear out space for room
    for j in range(ty - 1, ty + ysize + 1):
        for i in range(tx - 1, tx + xsize + 1):
            item[i][j] = itm.ONOTHING

    # now put in the walls
    for j in range(ty, ty + ysize):
        for i in range(tx, tx + xsize):
            item[i][j] = itm.OWALL
            mitem[i][j].mon = monster.MONST_NONE

    # now clear out interior
    for j in range(ty + 1, ty + ysize - 1):
        for i in range(tx + 1, tx + xsize - 1):
            item[i][j] = itm.ONOTHING

    # locate the door on the treasure room
    r = rnd(2)
    if r == 1:
        i = tx + rund(xsize)
        j = ty + (ysize - 1) * rund(2)
        item[i][j] = itm.OCLOSEDDOOR
        iarg[i][j] = glyph  # on horizontal walls
    elif r == 2:
        i = tx + (xsize - 1) * rund(2)
        j = ty + rund(ysize)
        item[i][j] = itm.OCLOSEDDOOR
        iarg[i][j] = glyph  # on vertical walls

    #
    # must save and use playerx, playery because that's what
    # createmonster() uses
    #
    bupx = player.playerx
    bupy = player.playery

    player.playery = ty + (ysize >> 1)
    if player.c[player.HARDGAME] < 3:
        player.playerx = tx + 1
        while player.playerx <= tx + xsize - 2:
            j = rnd(6)
            for i in range(j + 1):
                something(player.playerx, player.playery, lv + 2)
                monster.createmonster(monster.makemonst(lv + 2))
            player.playerx += 2
    else:
        player.playerx = tx + 1
        while player.playerx <= tx + xsize - 2:
            j = rnd(4)
            for i in range(j + 1):
                something(player.playerx, player.playery, lv + 2)
                monster.createmonster(monster.makemonst(lv + 4))
            player.playerx += 2

    player.playerx = bupx
    player.playery = bupy


def treasureroom(lv):
    """Make a treasure room on a level.

     - level 10's treasure room has the eye in it and demon lords
     - level V5 has potion of cure dianthroritis and demon prince
    """
    tx = 1 + rnd(10)
    while tx < MAXX - 10:
        if (lv == DBOTTOM) or (lv == VBOTTOM) or (rnd(10) <= 2):
            # 20% chance
            xsize = rnd(6) + 3
            ysize = rnd(3) + 3
            ty = rnd(MAXY - 9) + 1  # upper left corner of room
            if (lv == DBOTTOM) or (lv == VBOTTOM):
                tx = tx + rnd(MAXX - 24)
                troom(lv, xsize, ysize, tx, ty, rnd(3) + 6)
            else:
                troom(lv, xsize, ysize, tx, ty, rnd(9))
        tx += 10


def fillroom(what, arg):
    """Function to put an object into an empty room.

    Uses a random walk to find an empty room.
    """
    x = rnd(MAXX - 2)
    y = rnd(MAXY - 2)

    while item[x][y] != itm.ONOTHING:
        x += rnd(3) - 2
        y += rnd(3) - 2

        if x > MAXX - 2:
            x = 1
        if x < 1:
            x = MAXX - 2
        if y > MAXY - 2:
            y = 1
        if y < 1:
            y = MAXY - 2

    item[x][y] = what
    iarg[x][y] = arg


def fillmroom(n, what, arg):
    """Function to fill in a number of objects of the same kind."""
    for i in range(n):
        fillroom(what, arg)


def froom(n, itm_, arg):
    """Fill a room with an item with a certain probability (n in 151)."""
    if rnd(151) < n:
        fillroom(itm_, arg)


#
# Data for the creation of unique items in the game.
#

UNIQUE_1_COUNT = 10
UNIQUE_COUNT = 16

#
# A list of unique items in the game
# The items in the set from which only one can be created per dungeon level
# must be specified first.
# (Built lazily: the itm / player modules may not be loaded yet at import.)
#
UniqueItem = None

# The character flags associated with the creation of each unique item
UniqueFlag = None

# The minimum dungeon level for this item to occur
UniqueMinLevel = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 10, 0, 8, 5]

# The die to roll for determining if this item is created
UniqueRoll = [
    120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
    120, 120, 100, 120, 100, 100]

# The max roll for item creation
UniqueProb = [
    8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
    8, 8, 15, 8, 15, 15]

# The increase in probability for each level in the dungeon above the minimum
# required for the item
UniqueProbLevelMod = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 1, 0, 1, 0]


def _init_unique_tables():
    """Fill UniqueItem / UniqueFlag (needs itm and player constants)."""
    global UniqueItem, UniqueFlag
    if UniqueItem is None:
        UniqueItem = [
            itm.OBRASSLAMP, itm.OWWAND, itm.OORBOFDRAGON, itm.OSPIRITSCARAB,
            itm.OCUBEofUNDEAD, itm.ONOTHEFT,
            itm.OSPHTALISMAN, itm.OHANDofFEAR, itm.OORB, itm.OELVENCHAIN,
            itm.OSWORDofSLASHING, itm.OHAMMER, itm.OSLAYER, itm.OVORPAL,
            itm.OPSTAFF, itm.OLIFEPRESERVER]
        UniqueFlag = [
            player.LAMP, player.WAND, player.DRAGSLAY, player.NEGATE,
            player.CUBEUNDEAD, player.DEVICE,
            player.TALISMAN, player.HAND, player.ORB, player.ELVEN,
            player.SLASH, player.BESSMANN, player.SLAY, player.VORPAL,
            player.STAFF, player.LIFE_PRESERVER]


def makeobject(j):
    """Create the objects in a dungeon level j."""
    c = player.c

    if j == 0:
        # The town level
        fillroom(itm.OENTRANCE, 0)   # entrance to dungeon
        fillroom(itm.ODNDSTORE, 0)   # the DND STORE
        fillroom(itm.OSCHOOL, 0)     # college of Larn
        fillroom(itm.OBANK, 0)       # 1st national bank of larn
        fillroom(itm.OVOLDOWN, 0)    # volcano shaft to temple
        fillroom(itm.OHOME, 0)       # the players home & family
        fillroom(itm.OTRADEPOST, 0)  # the trading post
        fillroom(itm.OLRS, 0)        # the larn revenue service
        return

    if j == DBOTTOM + 1:  # V1
        fillroom(itm.OVOLUP, 0)  # volcano shaft up from the temple

    # make the fixed object in the maze STAIRS and
    # random object ELEVATORS

    # stairs down only on V1 and V2
    if (j > 0) and (j != DBOTTOM) and (j < VBOTTOM - 2):
        fillroom(itm.OSTAIRSDOWN, 0)

    if (j > 1) and (j != DBOTTOM):
        fillroom(itm.OSTAIRSUP, 0)

    # > 3, not on V1 or V5 or 15
    if (j > 3) and (j != DBOTTOM + 1) and (j != VBOTTOM) and (j != DBOTTOM):
        if c[player.ELVUP] == 0:
            if rnd(100) > 85:
                fillroom(itm.OELEVATORUP, 0)
                c[player.ELVUP] += 1

    # < lev 10, or 15 or V5
    if (j > 0) and (j <= DBOTTOM - 5 or j == DBOTTOM or j == VBOTTOM):
        if c[player.ELVDOWN] == 0:
            if rnd(100) > 85:
                fillroom(itm.OELEVATORDOWN, 0)
                c[player.ELVDOWN] += 1

    #  make the random objects in the maze
    fillmroom(rund(3), itm.OBOOK, j)
    fillmroom(rund(3), itm.OCOOKIE, 0)
    fillmroom(rund(3), itm.OALTAR, 0)
    fillmroom(rund(3), itm.OSTATUE, 0)
    fillmroom(rund(3), itm.OFOUNTAIN, 0)
    fillmroom(rund(2), itm.OTHRONE, 0)
    fillmroom(rund(2), itm.OMIRROR, 0)

    # be sure to have pits on V3, V4, and V5
    # because there are no stairs on those levels
    if j >= VBOTTOM - 2:
        fillroom(itm.OPIT, 0)
    fillmroom(rund(3), itm.OPIT, 0)

    # be sure to have trapdoors on V3, V4, and V5
    if j >= VBOTTOM - 2:
        fillroom(itm.OIVTRAPDOOR, 0)
    fillmroom(rund(2), itm.OIVTRAPDOOR, 0)
    fillmroom(rund(2), itm.OTRAPARROWIV, 0)
    fillmroom(rnd(3) - 2, itm.OIVTELETRAP, 0)
    fillmroom(rnd(3) - 2, itm.OIVDARTRAP, 0)

    if j == 1:
        fillmroom(1, itm.OCHEST, j)
    else:
        fillmroom(rund(2), itm.OCHEST, j)

    if j <= DBOTTOM:
        fillmroom(rund(2), itm.ODIAMOND, rnd(10 * j + 1) + 10)
        fillmroom(rund(2), itm.ORUBY, rnd(6 * j + 1) + 6)
        fillmroom(rund(2), itm.OEMERALD, rnd(4 * j + 1) + 4)
        fillmroom(rund(2), itm.OSAPPHIRE, rnd(3 * j + 1) + 2)

    Prob = rnd(4) + 3
    for i in range(Prob):
        fillroom(itm.OPOTION, potion.newpotion())  # make a POTION

    Prob = rnd(5) + 3
    for i in range(Prob):
        fillroom(itm.OSCROLL, scroll.newscroll())  # make a SCROLL

    Prob = rnd(12) + 11
    for i in range(Prob):
        fillroom(itm.OGOLDPILE, 12 * rnd(j + 1) + (j << 3) + 10)  # make GOLD

    if j == 8:
        fillroom(itm.OBANK2, 0)  # branch office of the bank

    if (c[player.PAD] == 0) and (j >= 4):
        if rnd(100) > 75:
            fillroom(itm.OPAD, 0)  # Dealer McDope's Pad
            c[player.PAD] += 1

    froom(2, itm.ORING, 0)              # a ring mail
    froom(1, itm.OSTUDLEATHER, 0)       # a studded leather
    froom(3, itm.OSPLINT, 0)            # a splint mail
    froom(5, itm.OSHIELD, rund(3))      # a shield
    froom(2, itm.OBATTLEAXE, rund(3))   # a battle axe
    froom(5, itm.OLONGSWORD, rund(3))   # a long sword
    froom(5, itm.OFLAIL, rund(3))       # a flail
    froom(7, itm.OSPEAR, rnd(5))        # a spear
    froom(4, itm.OREGENRING, rund(3))   # ring of regeneration
    froom(1, itm.OPROTRING, rund(3))    # ring of protection
    froom(2, itm.OSTRRING, rund(5))     # ring of strength
    froom(2, itm.ORINGOFEXTRA, 0)       # ring of extra regen

    #
    # Unique items.
    # Only one of the following items can be created on a level.
    #
    _init_unique_tables()

    #
    # Check if this level contains an item from the 1 of per level set
    #
    MadeUnique = 0
    Idx = 0
    while Idx < UNIQUE_1_COUNT and not MadeUnique:
        Flag = UniqueFlag[Idx]
        Item = UniqueItem[Idx]

        if c[Flag] == 0:
            if j >= UniqueMinLevel[Idx]:
                Prob = (UniqueProb[Idx] +
                        UniqueProbLevelMod[Idx] * (j - UniqueMinLevel[Idx]))

                if rnd(UniqueRoll[Idx]) < Prob:
                    fillroom(Item, 0)
                    c[Flag] += 1
                    MadeUnique = 1
        Idx += 1

    #
    # Check for creation of other unique items
    #
    for Idx in range(UNIQUE_1_COUNT, UNIQUE_COUNT):
        Flag = UniqueFlag[Idx]
        Item = UniqueItem[Idx]

        if c[Flag] == 0:
            if j >= UniqueMinLevel[Idx]:
                Prob = (UniqueProb[Idx] +
                        UniqueProbLevelMod[Idx] * (j - UniqueMinLevel[Idx]))

                if rnd(UniqueRoll[Idx]) < Prob:
                    fillroom(Item, 0)
                    c[Flag] += 1

    #
    # we don't get these if the difficulty level
    # is >= 3
    #
    if c[player.HARDGAME] < 3 or (rnd(4) == 3):
        if j > 3:
            # only on levels 3 or below
            froom(3, itm.OSWORD, rund(6))       # sunsword
            froom(5, itm.O2SWORD, rnd(6))       # a two handed sword
            froom(3, itm.OBELT, rund(7))        # belt of striking
            froom(3, itm.OENERGYRING, rund(6))  # energy ring
            froom(4, itm.OPLATE, rund(8))       # platemail


def sethp(flg):
    """Creates an entire set of monsters for a level.

    Must be done when entering a new level.
    flg : true if this is the first time on this level,
          false if this is a revisit to the level.
    """
    if flg:
        # All initial monsters are unseen and asleep
        for i in range(MAXY):
            for j in range(MAXX):
                stealth[j][i] = 0

    if level == 0:
        # Don't spawn extra onsters on the home level
        return

    if flg:
        # Get the initial numb er of monsters for this level
        j = rnd(12) + 2 + (level >> 1)
    else:
        # Calculate the number of new monsters to create on revisit
        j = (level >> 1) + 1

    for i in range(j):
        fillmonst(monster.makemonst(level))

    if flg:
        #
        # Only spawn demonlords on first visit to a level otherwise things can
        # get out of hand rather rapidly.
        #

        #
        # level 11 gets 1 demon lord
        # level 12 gets 2 demon lords
        # level 13 gets 3 demon lords
        # level 14 gets 4 demon lords
        # level 15 gets 5 demon lords
        #
        if (level >= (DBOTTOM - 4)) and (level <= DBOTTOM):
            i = level - 10
            for j in range(1, i + 1):
                while fillmonst(monster.DEMONLORD + rund(7)) == -1:
                    pass

        #
        # level V1 gets 1 demon prince
        # level V2 gets 2 demon princes
        # level V3 gets 3 demon princes
        # level V4 gets 4 demon princes
        # level V5 gets 5 demon princes
        #
        if level > DBOTTOM:
            i = level - DBOTTOM
            for j in range(1, i + 1):
                # Keep trying until the demon prince has been placed
                while fillmonst(monster.DEMONPRINCE) == -1:
                    pass


def checkgen():
    """Function to destroy all genocided monsters on the present level."""
    for y in range(MAXY):
        for x in range(MAXX):
            if (monster.monster[mitem[x][y].mon].flags & monster.FL_GENOCIDED) != 0:
                mitem[x][y].mon = 0  # no more monster


def makemaze(lev):
    """Function to make the caverns for a given level.

    Only walls are made (except for canned levels).
    """
    if lev > 0:
        # read maze from data file
        if cannedlevel(lev) == 1:
            return

    if lev == 0:
        tmp = itm.ONOTHING
    else:
        tmp = itm.OWALL

    # fill up maze
    for i in range(MAXY):
        for j in range(MAXX):
            item[j][i] = tmp

    # don't need to do anymore for level 0
    if lev == 0:
        return

    eat(1, 1)

    #  now for open spaces -- not on level 15 or V5
    if (lev != DBOTTOM) and (lev != VBOTTOM):
        tmp2 = rnd(3) + 3
        for tmp in range(tmp2):
            my = rnd(11) + 2
            myl = my - rnd(2)
            myh = my + rnd(2)
            if lev <= DBOTTOM:
                # in dungeon
                mx = rnd(44) + 5
                mxl = mx - rnd(4)
                mxh = mx + rnd(12) + 3
                Monst = 0
            else:
                # in volcano
                mx = rnd(60) + 3
                mxl = mx - rnd(2)
                mxh = mx + rnd(2)
                Monst = monster.makemonst(lev)

            for i in range(mxl, mxh):
                for j in range(myl, myh):
                    item[i][j] = itm.ONOTHING
                    if Monst != monster.MONST_NONE:
                        mitem[i][j].mon = Monst
                        hitp[i][j] = monster.monster[Monst].hitpoints

    if lev != DBOTTOM and lev != VBOTTOM:
        my = rnd(MAXY - 2)
        for i in range(1, MAXX - 1):
            item[i][my] = itm.ONOTHING

    # no treasure rooms above level 5
    if lev > 4:
        treasureroom(lev)


# =============================================================================
# Exported functions

def init_cells():
    """Allocate storage for levels."""
    for i in range(NLEVELS):
        saved_levels[i] = Saved_Level()
        # Fresh storage has no valid checksum yet (C process starts with 0s).
        level_sums[i] = 0


def free_cells():
    """Free storage for levels."""
    for i in range(NLEVELS):
        saved_levels[i] = None


def cgood(x, y, chkitm, chkmonst):
    """Function to check location for emptiness and for dungeon exit.

    if chkitm is TRUE check for no item at this location
    if chkmonst is TRUE check for no monster at this location
    Returns TRUE if a location does not have itm or monst there,
    FALSE (0) otherwise.
    """
    good = 0

    if (y >= 0) and (y <= MAXY - 1) and (x >= 0) and (x <= MAXX - 1):  # within bounds?
        if (level == 1) and (x == 33) and (y == MAXY - 1):
            # exit to level 1 is never good
            return 0

        if (item[x][y] == itm.OWALL) or (item[x][y] == itm.OCLOSEDDOOR):
            # can't make on walls or closed doors
            return 0

        # Location is OK so far
        good = 1

        if chkitm and (item[x][y] != itm.ONOTHING):
            # checking items and it is not free of items
            good = 0

        if chkmonst and (mitem[x][y].mon != monster.MONST_NONE):
            # checking for monsters and not free of monsters
            good = 0

    return good


def dropgold(amount):
    """Function to drop some gold around player."""
    if amount > 250:
        createitem(player.playerx, player.playery, itm.OMAXGOLD, amount)
    else:
        createitem(player.playerx, player.playery, itm.OGOLDPILE, amount)


def fillmonst(what):
    """Function to put a monster into an empty room without walls or other
    monsters.

    Returns 0 if the monster could be created, -1 if no location found.
    """
    # max # of creation attempts
    for trys in range(10, 0, -1):
        x = rnd(MAXX - 2)
        y = rnd(MAXY - 2)

        if ((item[x][y] == itm.ONOTHING) and
                (mitem[x][y].mon == monster.MONST_NONE) and
                ((player.playerx != x) or (player.playery != y))):
            mitem[x][y].mon = what
            stealth[x][y] = 0
            hitp[x][y] = monster.monster[what].hitpoints
            return 0

    return -1  # creation failure


def eat(xx, yy):
    """Function to eat a maze in a level filled with walls."""
    OWALL = itm.OWALL
    ONOTHING = itm.ONOTHING

    dir = rnd(4)
    attempt = 2
    while attempt:
        if dir == 1:
            # west
            if not (xx <= 2):
                if not ((item[xx - 1][yy] != OWALL) or (item[xx - 2][yy] != OWALL)):
                    item[xx - 1][yy] = ONOTHING
                    item[xx - 2][yy] = ONOTHING
                    eat(xx - 2, yy)
        elif dir == 2:
            # east
            if not (xx >= MAXX - 3):
                if not ((item[xx + 1][yy] != OWALL) or (item[xx + 2][yy] != OWALL)):
                    item[xx + 1][yy] = ONOTHING
                    item[xx + 2][yy] = ONOTHING
                    eat(xx + 2, yy)
        elif dir == 3:
            # south
            if not (yy <= 2):
                if not ((item[xx][yy - 1] != OWALL) or (item[xx][yy - 2] != OWALL)):
                    item[xx][yy - 1] = ONOTHING
                    item[xx][yy - 2] = ONOTHING
                    eat(xx, yy - 2)
        elif dir == 4:
            # north
            if not (yy >= MAXY - 3):
                if not ((item[xx][yy + 1] != OWALL) or (item[xx][yy + 2] != OWALL)):
                    item[xx][yy + 1] = ONOTHING
                    item[xx][yy + 2] = ONOTHING
                    eat(xx, yy + 2)

        dir += 1
        if dir > 4:
            dir = 1
            attempt -= 1


def savelevel():
    """Routine to save the present level into storage."""
    storage = saved_levels[level]

    storage.hitp = [col[:] for col in hitp]
    storage.mitem = [[m.copy() for m in col] for col in mitem]
    storage.item = [col[:] for col in item]
    storage.iarg = [col[:] for col in iarg]
    storage.know = [col[:] for col in know]
    level_sums[level] = _storage_sum(storage)


def getlevel():
    """Routine to restore a level from storage."""
    storage = saved_levels[level]

    for x in range(MAXX):
        hitp[x][:] = storage.hitp[x]
        item[x][:] = storage.item[x]
        iarg[x][:] = storage.iarg[x]
        know[x][:] = storage.know[x]
        for y in range(MAXY):
            mitem[x][y].assign(storage.mitem[x][y])

    if level_sums[level] > 0:
        i = _storage_sum(storage)
        if i != level_sums[level]:
            ularn_win.Printf("\nOH NO!!!! INTERNAL MEMORY CORRUPTION!!!!\n")
            ularn_win.Printf("(sum %u of level %d does not match saved sum %u)\n",
                             i, level, level_sums[level])
            ularn_win.UlarnBeep()
            ularn_win.nap(5000)
            scores.died(scores.DIED_INTERNAL_COMPLICATIONS, 0)
    else:
        level_sums[level] = _storage_sum(storage)


def AnalyseWalls(x1, y1, x2, y2):
    """Function to analyse the tiles needed for walls based on the layout of
    adjacent walls.
    """
    OWALL = itm.OWALL
    OOPENDOOR = itm.OOPENDOOR
    OCLOSEDDOOR = itm.OCLOSEDDOOR

    # Limit area to the valid map area
    sx = 0 if (x1 < 0) else x1
    sy = 0 if (y1 < 0) else y1
    ex = (MAXX - 1) if (x2 >= MAXX) else x2
    ey = (MAXY - 1) if (y2 >= MAXY) else y2

    for x in range(sx, ex + 1):
        for y in range(sy, ey + 1):
            if item[x][y] == OWALL:
                # There is a wall here, so analyse connectivity with other walls

                WallArg = 0

                if x > 0:
                    if item[x - 1][y] in (OWALL, OOPENDOOR, OCLOSEDDOOR):
                        WallArg += 1

                if y < (MAXY - 1):
                    if item[x][y + 1] in (OWALL, OOPENDOOR, OCLOSEDDOOR):
                        WallArg += 2

                if x < (MAXX - 1):
                    if item[x + 1][y] in (OWALL, OOPENDOOR, OCLOSEDDOOR):
                        WallArg += 4

                if y > 0:
                    if item[x][y - 1] in (OWALL, OOPENDOOR, OCLOSEDDOOR):
                        WallArg += 8

                iarg[x][y] = WallArg


def newcavelevel(x):
    """Function to enter a new level.

    This routine must be called anytime the player changes levels.  If that
    level is unknown it will be created.  A new set of monsters will be
    created for a new level, and existing levels will get a few more monsters.
    Note that it is here we remove genocided monsters from the present level.
    """
    global level

    if beenhere[level]:
        savelevel()  # put the level back into storage

    if level == 0:
        # if teleported and found the home level then know level we are on
        player.c[player.TELEFLAG] = 0

    #
    # Forget which monster was last hit by the player as it is no longer
    # on this level.
    #
    monster.last_monst_hx = -1
    monster.last_monst_hy = -1

    level = x
    player.c[player.CAVELEVEL] = level
    if beenhere[x]:
        # get the new level and put in working storage
        getlevel()
        # spawn new monsters
        sethp(0)
        # remove any genocided monsters
        checkgen()

        # Position the player on the map
        player.positionplayer()
    else:
        # never been here before, so don't know anything, and no monsters
        for i in range(MAXY):
            for j in range(MAXX):
                know[j][i] = itm.OUNKNOWN
                mitem[j][i].mon = monster.MONST_NONE

        makemaze(x)

        # if this is level 1
        if x == 1:
            # exit from dungeon
            item[33][MAXY - 1] = itm.ONOTHING

        AnalyseWalls(0, 0, MAXX - 1, MAXY - 1)
        makeobject(x)

        beenhere[x] = 1
        # create monsters for this level
        sethp(1)

        if player.wizard or x == 0:
            for j in range(MAXY):
                for i in range(MAXX):
                    know[i][j] = item[i][j]
                    stealth[i][j] |= STEALTH_SEEN

        # wipe out any genocided monsters
        checkgen()

        # Position the player on the map
        player.positionplayer()


def verifyxy(x, y):
    """Function to verify x & y are within the bounds for a level.

    Python signature: verifyxy(x, y) -> (flag, x, y)
    flag == 0 if no adjustment to x and y was required, != 0 otherwise.
    """
    flag = 0

    if x < 0:
        x = 0
        flag += 1
    if y < 0:
        y = 0
        flag += 1
    if x >= MAXX:
        x = MAXX - 1
        flag += 1
    if y >= MAXY:
        y = MAXY - 1
        flag += 1
    return flag, x, y


def checkxy(x, y):
    """Function to check x & y are within the bounds for a level (1 / 0)."""
    return 1 if ((x >= 0) and (x < MAXX) and (y >= 0) and (y < MAXY)) else 0


def createitem(x, y, it, arg):
    """Routine to place an item next to the player.

    When creating gold, arg is the number of gold pieces to drop, not the
    value to be stored in iarg.
    """
    if it >= itm.OCOUNT:
        return  # no such object

    diroffx = ularn_game.diroffx
    diroffy = ularn_game.diroffy

    # Select the initial direction to try at random
    dir = rnd(8)

    for dir_try in range(8):
        # choose direction, try all
        if dir > 8:
            dir = 1  # wraparound the diroff arrays

        ox = x + diroffx[dir]
        oy = y + diroffy[dir]

        if it not in (itm.OKGOLD, itm.OMAXGOLD, itm.ODGOLD, itm.OGOLDPILE):
            if cgood(ox, oy, 1, 0):
                # if we can create an item here
                item[ox][oy] = it
                iarg[ox][oy] = arg
                return
        else:
            # arg contains the number of GP to drop
            # (C reads item[ox][oy] even when off the map; treat that as
            #  "not gold" here, which falls into the default case.)
            cur = item[ox][oy] if checkxy(ox, oy) else -1

            # The C switch falls through from case to case.
            fall = False
            if cur == itm.OGOLDPILE:
                fall = True
                if (iarg[ox][oy] + arg) < 32767:
                    iarg[ox][oy] += arg
                    return
            if fall or cur == itm.ODGOLD:
                fall = True
                if (10 * iarg[ox][oy] + arg) < 327670:
                    i = iarg[ox][oy]
                    iarg[ox][oy] = (10 * i + arg) // 10
                    item[ox][oy] = itm.ODGOLD
                    return
            if fall or cur == itm.OMAXGOLD:
                fall = True
                if (100 * iarg[ox][oy] + arg) < 3276700:
                    i = (100 * iarg[ox][oy]) + arg
                    iarg[ox][oy] = i // 100
                    item[ox][oy] = itm.OMAXGOLD
                    return
            if fall or cur == itm.OKGOLD:
                if (1000 * iarg[ox][oy] + arg) <= 32767000:
                    i = iarg[ox][oy]
                    iarg[ox][oy] = (1000 * i + arg) // 1000
                    item[ox][oy] = itm.OKGOLD
                    return
                else:
                    iarg[ox][oy] = 32767
                return
            # default:
            if cgood(ox, oy, 1, 0):
                item[ox][oy] = it
                if it == itm.OMAXGOLD:
                    iarg[ox][oy] = cdiv(arg, 100)
                else:
                    iarg[ox][oy] = arg
                return

        # try the next direction
        dir += 1


def something(x, y, lev):
    """Function to create a random item around coords x, y.

    Items are created from a designed probability for the input level.
    """
    # correct level?
    if lev < 0 or lev > VBOTTOM:
        return

    # possibly more than one item
    while True:
        item_id, item_arg = newobject(lev)
        createitem(x, y, item_id, item_arg)
        if not (rnd(101) < 8):
            break


LEV_0to3_LAST = 32
LEV_4to6_LAST = 35
LEV_6plus_LAST = 37

nobjtab = None  # built lazily from the itm constants (38 entries)


def _init_nobjtab():
    """Build nobjtab (needs the itm constants)."""
    global nobjtab
    if nobjtab is None:
        nobjtab = [
            0,
            itm.OSCROLL, itm.OSCROLL, itm.OSCROLL, itm.OSCROLL,
            itm.OPOTION, itm.OPOTION, itm.OPOTION, itm.OPOTION,
            itm.OGOLDPILE, itm.OGOLDPILE, itm.OGOLDPILE, itm.OGOLDPILE,
            itm.OBOOK, itm.OBOOK, itm.OBOOK, itm.OBOOK,
            itm.ODAGGER, itm.ODAGGER, itm.ODAGGER,
            itm.OLEATHER, itm.OLEATHER, itm.OLEATHER,
            itm.OREGENRING, itm.OPROTRING, itm.OENERGYRING, itm.ODEXRING, itm.OSTRRING,
            itm.OSPEAR, itm.OBELT, itm.ORING, itm.OSTUDLEATHER, itm.OSHIELD, itm.OFLAIL, itm.OCHAIN,
            itm.O2SWORD, itm.OPLATE, itm.OLONGSWORD]  # 38


def newobject(lev, i=0):
    """Function to return a randomly selected object to be created.

    Python signature: newobject(lev, i=0) -> (object_id, item_arg)
    (C fills *i; `i` is the value returned unchanged if the object type does
    not set an argument.)
    """
    # correct level?  (note: C checks the global `level` here, not `lev`)
    if level < 0 or level > VBOTTOM:
        return 0, i

    _init_nobjtab()

    # Decide what types of objects can be created based on the current level

    if lev <= 3:
        LastObj = LEV_0to3_LAST
    elif lev <= 6:
        LastObj = LEV_4to6_LAST
    else:
        LastObj = LEV_6plus_LAST

    # select the object type
    ObjType = nobjtab[rnd(LastObj)]

    if ObjType == itm.OSCROLL:
        i = scroll.newscroll()
    elif ObjType == itm.OPOTION:
        i = potion.newpotion()
    elif ObjType == itm.OGOLDPILE:
        i = rnd((lev + 1) * 10) + lev * 10 + 10
    elif ObjType == itm.OBOOK:
        i = lev
    elif ObjType == itm.ODAGGER:
        i = newdagger()
    elif ObjType == itm.OLEATHER:
        i = newleather()
    elif ObjType in (itm.OREGENRING, itm.OSHIELD, itm.O2SWORD):
        i = rund(lev // 3 + 1)
    elif ObjType in (itm.OPROTRING, itm.ODEXRING):
        i = rnd(lev // 4 + 1)
    elif ObjType == itm.OENERGYRING:
        i = rund(lev // 4 + 1)
    elif ObjType == itm.OSTRRING:
        i = rnd(lev // 2 + 1)
    elif ObjType == itm.OSPEAR:
        i = rund(lev // 3 + 1)
    elif ObjType in (itm.OBELT, itm.OSTUDLEATHER):
        i = rund(lev // 2 + 1)
    elif ObjType in (itm.ORING, itm.OFLAIL):
        i = rund(lev // 2 + 1)
    elif ObjType == itm.OCHAIN:
        i = newchain()
    elif ObjType == itm.OPLATE:
        i = newplate()
    elif ObjType == itm.OLONGSWORD:
        i = newsword()

    return ObjType, i


def write_levels(fp):
    """Write the dungeon levels to a save file (binary file object fp).

    The data is written with pickle.dump(); returns 0 if successful.
    """
    #
    # Put the current level into storage
    #
    savelevel()

    data = {
        # save which level the player is currently on
        "level": level,
        # Save which levels have been visited by the player
        "beenhere": list(beenhere),
        # Save each of the visited levels
        "levels": {i: saved_levels[i] for i in range(NLEVELS) if beenhere[i]},
    }
    pickle.dump(data, fp)

    return 0


def read_levels(fp):
    """Read the dungeon levels from a save file (binary file object fp).

    Reads the data written by write_levels(); returns 0 if successful.
    """
    global level

    data = pickle.load(fp)

    #
    # Read which level the player is currently on
    #
    level = data["level"]

    #
    # Read which levels have been visited by the player
    #
    beenhere[:] = data["beenhere"]

    #
    # Read each of the visited levels
    #
    for i in range(NLEVELS):
        if beenhere[i]:
            saved_levels[i] = data["levels"][i]

    return 0

