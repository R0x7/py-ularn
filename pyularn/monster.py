"""Monster module (port of monster.c / monster.h).

This module handles most aspects of monsters in the game.
It provides the monster definitions.
Handles monster creation.
All monster movement, including attacking the player (including special
attacks) is handled here.
Also handles loading and saving monster state data.

EXPORTED VARIABLES

  monstnamelist : The character code for displaying each monster
  monsttilelist : The gfx tile for each monster
  monster       : The monster data
  lastmonst     : The name of the last monster being processed.
  last_monst_id : The id of the last monster being processed.
  last_monst_hx : The x location of the last monster hit by the player
  last_monst_hy : The y location of the last monster hit by the player
  rmst          : The random monster creation countdown.
"""

import pickle

from .header import *
from . import dungeon, itm, player, scores, show, sphere, ularn_game, ularn_win

MAXMONST = 57   # maximum # monsters in the dungeon


class monst:
    """struct monst"""

    __slots__ = ("name", "level", "armorclass", "damage", "attack",
                 "intelligence", "gold", "hitpoints", "experience", "flags")

    def __init__(self, name, level, armorclass, damage, attack,
                 intelligence, gold, hitpoints, experience, flags):
        self.name = name
        self.level = level
        self.armorclass = armorclass
        self.damage = damage
        self.attack = attack
        self.intelligence = intelligence
        self.gold = gold
        self.hitpoints = hitpoints
        self.experience = experience
        self.flags = flags


#
#  Flags for monst structure
#
FL_NONE = 0x00       # Nothing of interest
FL_GENOCIDED = 0x01  # Monster has been genocided
FL_HEAD = 0x02       # Monster has a head
FL_NOBEHEAD = 0x04   # Monster cannot be beheaded by Vorpy
FL_SLOW = 0x08       # Monster moves at 1/2 nornal speed
FL_FLY = 0x10        # Monster can fly over pits and trapdoors
FL_SPIRIT = 0x20     # Is a spirit (affected by spirit prot)
FL_UNDEAD = 0x40     # Is undead (affected by undead prot)
FL_INFRAVIS = 0x80   # Monster has infravision (see invisible)

# ************ Defines for the monsters as objects (MonsterIdType) ************
MONST_NONE = 0
LEMMING = 1
GNOME = 2
HOBGOBLIN = 3
JACKAL = 4
KOBOLD = 5
ORC = 6
SNAKE = 7
CENTIPEDE = 8
JACULI = 9
TROGLODYTE = 10
ANT = 11
EYE = 12
LEPRECHAUN = 13
NYMPH = 14
QUASIT = 15
RUSTMONSTER = 16
ZOMBIE = 17
ASSASSINBUG = 18
BUGBEAR = 19
HELLHOUND = 20
ICELIZARD = 21
CENTAUR = 22
TROLL = 23
YETI = 24
WHITEDRAGON = 25
ELF = 26
CUBE = 27
METAMORPH = 28
VORTEX = 29
ZILLER = 30
VIOLETFUNGI = 31
WRAITH = 32
FORVALAKA = 33
LAMANOBE = 34
OSEQUIP = 35
ROTHE = 36
XORN = 37
VAMPIRE = 38
INVISIBLESTALKER = 39
POLTERGEIST = 40
DISENCHANTRESS = 41
SHAMBLINGMOUND = 42
YELLOWMOLD = 43
UMBERHULK = 44
GNOMEKING = 45
MIMIC = 46
WATERLORD = 47
BRONZEDRAGON = 48
GREENDRAGON = 49
PURPLEWORM = 50
XVART = 51
SPIRITNAGA = 52
SILVERDRAGON = 53
PLATINUMDRAGON = 54
GREENURCHIN = 55
REDDRAGON = 56
DEMONLORD = 57
DEMONLORD_II = 58
DEMONLORD_III = 59
DEMONLORD_IV = 60
DEMONLORD_V = 61
DEMONLORD_VI = 62
DEMONLORD_VII = 63
DEMONPRINCE = 64
LUCIFER = 65
MONST_COUNT = 66

# =============================================================================
# Exported variables

# Character codes to use for monsters
monstnamelist = [
    ' ', 'l', 'G', 'H', 'J', 'K', 'O', 'S',
    'c', 'j', 't', 'A', 'E', 'L', 'N', 'Q',
    'R', 'Z', 'a', 'b', 'h', 'i', 'C', 'T',
    'Y', 'd', 'e', 'g', 'm', 'v', 'z', 'F',
    'W', 'f', 'l', 'o', 'r', 'X', 'V', ' ',
    'p', 'q', 's', 'y', 'U', 'k', 'M', 'w',
    'D', 'D', 'P', 'x', 'n', 'D', 'D', 'u',
    'D', '1', '2', '3', '4', '5', '6', '7',
    '9', '0'
]

# Tile numbers to use for monsters
monsttilelist = [
    0,
    0, 1, 2, 3, 4, 5, 6, 7,
    8, 9, 10, 11, 12, 13, 14, 15,
    16, 17, 18, 19, 20, 21, 22, 23,
    24, 25, 26, 27, 28, 29, 30, 31,
    32, 33, 34, 35, 36, 37, 38, 39,
    40, 41, 42, 43, 44, 45, 46, 47,
    48, 49, 50, 51, 52, 53, 54, 55,
    56, 56, 57, 58, 59, 60, 61, 62,
    63
]

#
#  for the monster data
#
#  array to do rnd() to create monsters <= a given level
#
monstlevel = [5, 11, 17, 22, 27, 33, 39, 42, 46, 50, 53, 56]

monster = [
# NAME                    LV   AC    DAM ATT  INT GOLD     HP     EXP   FLAGS
# ----------------------------------------------------------------------------------------------
  monst("unseen attacker",      0,    0,   0,  0,   1,    0,     0,       0, 0),
  monst("lemming",              1,    0,   0,  0,   3,    0,     0,       1, FL_HEAD),
  monst("gnome",                1,   10,   1,  0,   8,   30,     2,       2, FL_HEAD|FL_INFRAVIS),
  monst("hobgoblin",            1,   13,   2,  0,   5,   25,     3,       2, FL_HEAD|FL_SLOW),
  monst("jackal",               1,    7,   1,  0,   4,    0,     1,       1, FL_HEAD),
  monst("kobold",               1,   15,   1,  0,   7,   10,     1,       1, FL_HEAD|FL_INFRAVIS),
  monst("orc",                  2,   15,   3,  0,   9,   40,     5,       2, FL_HEAD),
  monst("snake",                2,   10,   1,  0,   3,    0,     3,       1, FL_HEAD),
  monst("giant centipede",      2,   13,   1,  4,   3,    0,     2,       2, FL_HEAD),
  monst("jaculi",               2,    9,   1,  0,   3,    0,     2,       1, FL_HEAD),
  monst("troglodyte",           2,   10,   2,  0,   5,   80,     5,       3, FL_HEAD|FL_SLOW),
  monst("giant ant",            2,    8,   1,  4,   4,    0,     5,       4, FL_HEAD),
  monst("floating eye",         3,    8,   2,  0,   3,    0,     7,       2, FL_FLY),
  monst("leprechaun",           3,    3,   0,  8,   3, 1500,    15,      40, FL_HEAD),
  monst("nymph",                3,    3,   0, 14,   9,    0,    20,      40, FL_HEAD),
  monst("quasit",               3,    5,   3,  0,   3,    0,    14,      10, FL_HEAD),
  monst("rust monster",         3,    5,   0,  1,   3,    0,    18,      20, FL_HEAD),
  monst("zombie",               3,   12,   3,  0,   3,    0,     9,       7, FL_HEAD|FL_UNDEAD),
  monst("assassin bug",         4,    4,   3,  0,   3,    0,    23,      13, FL_HEAD),
  monst("bugbear",              4,    5,   4, 15,   5,   40,    24,      33, FL_HEAD|FL_INFRAVIS),
  monst("hell hound",           4,    5,   2,  2,   6,    0,    20,      33, FL_HEAD),
  monst("ice lizard",           4,   11,   3, 10,   6,   50,    19,      23, FL_HEAD|FL_SLOW),
  monst("centaur",              4,    6,   4,  0,  10,   40,    25,      43, FL_HEAD),
  monst("troll",                5,    9,   5,  0,   9,   80,    55,     250, FL_HEAD),
  monst("yeti",                 5,    8,   4,  0,   5,   50,    45,      90, FL_HEAD),
  monst("white dragon",         5,    4,   5,  5,  16,  500,    65,    1000, FL_HEAD),
  monst("elf",                  5,    3,   3,  0,  15,   50,    25,      33, FL_HEAD|FL_INFRAVIS),
  monst("gelatinous cube",      5,    9,   3,  0,   3,    0,    24,      43, 0),
  monst("metamorph",            6,    9,   3,  0,   3,    0,    32,      40, FL_SLOW),
  monst("vortex",               6,    5,   4,  0,   3,    0,    33,      53, 0),
  monst("ziller",               6,   15,   3,  0,   3,    0,    34,      33, FL_HEAD),
  monst("violet fungus",        6,   12,   3,  0,   3,    0,    39,      90, 0),
  monst("wraith",               6,    3,   1,  6,   3,    0,    36,     300, FL_HEAD|FL_FLY|FL_UNDEAD),
  monst("forvalaka",            6,    3,   5,  0,   7,    0,    55,     270, FL_HEAD|FL_INFRAVIS),
  monst("lama nobe",            7,   14,   7,  0,   6,    0,    36,      70, FL_HEAD),
  monst("osequip",              7,    4,   7, 16,   4,    0,    36,      90, FL_HEAD),
  monst("rothe",                7,   15,   5,  0,   3,  100,    53,     230, FL_HEAD|FL_INFRAVIS),
  monst("xorn",                 7,    6,   7,  0,  13,    0,    63,     290, FL_INFRAVIS),
  monst("vampire",              7,    5,   4,  6,  17,    0,    55,     950, FL_HEAD|FL_FLY|FL_UNDEAD),
  monst("invisible stalker",    7,    5,   6,  0,   5,    0,    55,     330, FL_HEAD|FL_SLOW),
  monst("poltergeist",          8,    1,   8,  0,   3,    0,    55,     430, FL_SPIRIT),
  monst("disenchantress",       8,    3,   1,  9,   3,    0,    57,     500, FL_HEAD),
  monst("shambling mound",      8,   13,   5,  0,   6,    0,    47,     390, 0),
  monst("yellow mold",          8,   12,   4,  0,   3,    0,    37,     240, 0),
  monst("umber hulk",           8,    6,   7, 11,  14,    0,    67,     600, FL_HEAD|FL_INFRAVIS),
  monst("gnome king",           9,   -1,  10,  0,  18, 2000,   120,    3000, FL_HEAD|FL_INFRAVIS),
  monst("mimic",                9,    9,   7,  0,   8,    0,    57,     100, 0),
  monst("water lord",           9,  -10,  15,  7,  20,    0,   155,   15000, FL_HEAD|FL_NOBEHEAD),
  monst("bronze dragon",        9,    5,   9,  3,  16,  300,    90,    4000, FL_HEAD|FL_FLY),
  monst("green dragon",         9,    4,   4, 10,  15,  200,    80,    2500, FL_HEAD|FL_FLY),
  monst("purple worm",          9,   -1,  13,  0,   3,  100,   130,   15000, FL_HEAD),
  monst("xvart",                9,   -2,  14,  0,  13,    0,   100,    1000, FL_HEAD|FL_SLOW),
  monst("spirit naga",         10,  -20,  15, 12,  23,    0,   100,   20000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_SPIRIT|FL_INFRAVIS),
  monst("silver dragon",       10,   -4,  10,  3,  20,  700,   110,   10000, FL_HEAD|FL_FLY),
  monst("platinum dragon",     10,   -7,  15, 13,  22, 1000,   150,   25000, FL_HEAD|FL_FLY),
  monst("green urchin",        10,   -5,  12,  0,   3,    0,    95,    5000, 0),
  monst("red dragon",          10,   -4,  13,  3,  19,  800,   120,   14000, FL_HEAD|FL_FLY),
  monst("type I demon lord",   12,  -40,  20,  3,  20,    0,   150,   50000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type II demon lord",  13,  -45,  25,  5,  22,    0,   200,   75000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type III demon lord", 14,  -50,  30,  9,  24,    0,   250,  100000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type IV demon lord",  15,  -55,  35, 11,  26,    0,   300,  125000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type V demon lord",   16,  -60,  40, 13,  28,    0,   350,  150000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type VI demon lord",  17,  -65,  45, 13,  30,    0,   400,  175000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("type VII demon lord", 18,  -70,  50,  6,  32,    0,   450,  200000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("demon prince",        19,  -90,  80,  6,  40,    0,  1000,  500000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS),
  monst("God of Hellfire",     20, -120, 100,  6, 100,    0, 32767, 1000000, FL_HEAD|FL_NOBEHEAD|FL_FLY|FL_INFRAVIS)
]


lastmonst = ""                  # name of the current monster
last_monst_id = MONST_NONE      # the last monster hitting the player
last_monst_hx = 0               # x location of the last monster hit by player
last_monst_hy = 0               # y location of the last monster hit by player
rmst = 80                       # Random monster creation timer

# =============================================================================
# Local variables

#
# Monster movement area for the current monster movement
#
move_xl = 0
move_yl = 0
move_xh = 0
move_yh = 0

#
# The maximum path distance for smart monster movement
#
distance = 0

#
# The new location for the last monster moved
# These will be set to -1 if the monster died.
#
movedx = 0
movedy = 0

#
# Rustable armour data (built lazily from the itm constants)
#
ARMORTYPES = 6

rustarm = None


def _init_rustarm():
    """Build the rustarm table (needs the itm constants)."""
    global rustarm
    if rustarm is None:
        rustarm = [
            [itm.OSTUDLEATHER, -2],
            [itm.ORING, -4],
            [itm.OCHAIN, -5],
            [itm.OSPLINT, -6],
            [itm.OPLATE, -8],
            [itm.OPLATEARMOR, -9]
        ]


def _wielded_item():
    """iven[c[WIELD]] with C's out-of-range read (c[WIELD] == -1) mapped to
    'nothing' instead of Python's negative indexing."""
    w = player.c[player.WIELD]
    if 0 <= w < len(player.iven):
        return player.iven[w]
    return itm.ONOTHING


# =============================================================================
# Local functions

def checkloss(x):
    """Function to subtract hp from user and flag bottomline display.

    Note: if x > c[HP] this routine could kill the player!
    """
    if x > 0:
        player.losehp(scores.DIED_MONSTER, x)
        ularn_win.UpdateStatus()


def dropsomething(x, y, monst):
    """Function to create an object when a monster dies."""
    if monst in (ORC, NYMPH, ELF, TROGLODYTE, TROLL, ROTHE, VIOLETFUNGI,
                 PLATINUMDRAGON, GNOMEKING, REDDRAGON):
        dungeon.something(x, y, dungeon.level)
        return
    elif monst == LEPRECHAUN:
        if rnd(101) >= 75:
            player.creategem()
        if rnd(5) == 1:
            dropsomething(x, y, LEPRECHAUN)
        # fall through to LEMMING
        return
    elif monst == LEMMING:
        return


def rust_armour():
    """Function to rust armour.

    Returns the format string to print.
    """
    c = player.c
    iven = player.iven
    ivenarg = player.ivenarg

    _init_rustarm()

    Rusted = 0
    ArmourId = itm.ONOTHING  # (uninitialised in C when no armour is worn)

    Armour = c[player.WEAR]
    Shield = c[player.SHIELD]

    #
    # Rust the shield, if present and rustable, first
    #
    if Shield != -1:
        if ivenarg[Shield] > -1:
            player.adjustivenarg(Shield, -1)
            Rusted = 1

    #
    # If nothing rusted yet then rust the armour if possible
    #
    if not Rusted and (Armour != -1):
        # find the armor in table
        ArmourId = iven[Armour]
        i = 0
        Found = 0

        while (i < ARMORTYPES) and not Found:
            if ArmourId == rustarm[i][0]:
                Found = 1
            else:
                i += 1

        if Found:
            if ivenarg[Armour] > rustarm[i][1]:
                player.adjustivenarg(Armour, -1)
                Rusted = 1

    # if rusting did not occur
    if not Rusted:
        if ArmourId == itm.OLEATHER:
            p = "\nThe %s hit you -- you are lucky you have leather on."
        elif ArmourId == itm.OSSPLATE:
            p = "\nThe %s hit you -- you are fortunate to have stainless steel armor!"
        elif ArmourId == itm.OELVENCHAIN:
            p = "\nThe %s hit you -- you are very lucky to have such strong elven chain!"
        else:
            p = "\nThe %s hit you."
    else:
        ularn_win.UlarnBeep()
        p = "\nThe %s hit you -- your armor feels weaker."

    return p


#
# Function to process special attacks from monsters
#
# atckno   monster     effect
# ---------------------------------------------------
# 0  none
# 1  rust      eat armor
# 2  hell hound    breathe light fire
# 3  dragon      breathe fire
# 4  giant centipede   weakening strength
# 5  white dragon    cold breath
# 6  wraith      drain level
# 7  waterlord   water gusher
# 8  leprechaun    steal gold
# 9  disenchantress    disenchant weapon or armor
# 10 ice lizard    hits with barbed tail
# 11 umber hulk    confusion
# 12 spirit naga   cast spells taken from special attacks
# 13 platinum dragon   psionics
# 14 nymph       steal objects
# 15 bugbear     bite
# 16 osequip
#

spsel = [1, 2, 3, 5, 6, 8, 9, 11, 13, 14]


def spattack(x, xx, yy):
    """Function to process special attacks from monsters.

    x  : The special attack number.
    xx : The x coordinate of the monster.
    yy : The y coordinate of the monster.

    Returns 1 if must do a show1cell(xx,yy) on return, 0 otherwise.
    """
    c = player.c
    p = None
    need_beep = 0
    need_show = 0

    xx, yy = dungeon.vxy(xx, yy)  # verify x & y coordinates

    monst = dungeon.mitem[xx][yy].mon

    #
    # cancel only works 5% of time for demon prince and god
    #
    if c[player.CANCELLATION]:
        if monst >= DEMONPRINCE:
            if rnd(100) >= 95:
                return 0
        else:
            return 0

    # staff of power cancels demonlords/wraiths/vampires 75% of time
    # lucifer is unaffected
    if monst != LUCIFER:
        if (monst >= DEMONLORD) or (monst == WRAITH) or (monst == VAMPIRE):
            if player.player_has_item(itm.OPSTAFF):
                if rnd(100) < 75:
                    return 0

    # if have cube of undead control, undead monsters do nothing
    if (monster[monst].flags & FL_UNDEAD) != 0:
        if c[player.CUBEofUNDEAD] or c[player.UNDEADPRO]:
            return 0

    if x == 1:
        p = rust_armour()
        # Recalculate the AC and WC
        player.recalc()

    elif x == 2:
        i = rnd(15) + 8 - c[player.AC]
        if c[player.FIRERESISTANCE]:
            p = "\nThe %s's flame doesn't faze you!"
        else:
            p = "\nThe %s breathes fire at you!"
            need_beep = 1
        checkloss(i)

    elif x == 3:
        i = rnd(20) + 25 - c[player.AC]

        if c[player.FIRERESISTANCE]:
            p = "\nThe %s's flame doesn't faze you!"
        else:
            p = "\nThe %s breathes fire at you!"
            need_beep = 1
        checkloss(i)

    elif x == 4:
        if c[player.STRENGTH] > 3:
            p = "\nThe %s stung you!  You feel weaker."
            need_beep = 1
            player.adjust_ability(player.STRENGTH, -1)
        else:
            p = "\nThe %s stung you!"

    elif x == 5:
        p = "\nThe %s blasts you with his cold breath."
        i = rnd(15) + 18 - c[player.AC]
        need_beep = 1
        checkloss(i)

    elif x == 6:
        if player.player_has_item(itm.OLIFEPRESERVER):
            # Life preserver prevents all drain life attacks
            return 0

        p = "\nThe %s drains you of your life energy!"
        player.loselevel()
        if monst == DEMONPRINCE:
            player.losemspells(1)
        if monst == LUCIFER:
            player.loselevel()
            player.losemspells(2)
            for i in range(player.STRENGTH, player.DEXTERITY + 1):
                player.adjust_ability(i, -1)
        need_beep = 1

    elif x == 7:
        p = "\nThe %s got you with a gusher!"
        i = rnd(15) + 25 - c[player.AC]
        need_beep = 1
        checkloss(i)

    elif x == 8:
        # he has a device of no theft
        if c[player.NOTHEFT]:
            return 0

        if c[player.GOLD]:
            p = "\nThe %s hit you.  Your purse feels lighter."
            if c[player.GOLD] > 32767:
                c[player.GOLD] >>= 1
            else:
                c[player.GOLD] -= rnd(1 + (c[player.GOLD] >> 1))

            if c[player.GOLD] < 0:
                c[player.GOLD] = 0
        else:
            p = "\nThe %s couldn't find any gold to steal."
        dungeon.disappear(xx, yy)
        need_beep = 1
        need_show = 1

    elif x == 9:
        # disenchant
        Attempt = 50
        Disenchant = 0

        while (Attempt > 0) and (not Disenchant):
            # randomly select item
            i = rund(player.IVENSIZE)
            m = player.iven[i]
            if ((m != itm.ONOTHING) and (player.ivenarg[i] > 0) and
                    (m != itm.OSCROLL) and (m != itm.OPOTION)):
                # This item can be disenchanted
                Disenchant = 3
                if player.ivenarg[i] < Disenchant:
                    Disenchant = player.ivenarg[i]

                player.adjustivenarg(i, -Disenchant)

                p = "\nThe %s hits you with a spell of disenchantment! "

                need_beep = 1
                show.show3(i)

                Disenchant = 1

            Attempt -= 1

        #
        # Set the message if the disenchant failed.
        #
        if not Disenchant:
            p = "\nThe %s nearly misses."

    elif x == 10:
        p = "\nThe %s hit you with its barbed tail."
        i = rnd(25) - c[player.AC]
        need_beep = 1
        checkloss(i)

    elif x == 11:
        if player.wizard:
            return 0

        p = "\nThe %s has confused you."
        need_beep = 1
        c[player.CONFUSE] += 10 + rnd(10)

    elif x == 12:
        # performs any number of other special attacks
        need_show = spattack(spsel[rund(10)], xx, yy)

    elif x == 13:
        p = "\nThe %s flattens you with it's psionics!"
        i = rnd(15) + 30 - c[player.AC]
        need_beep = 1
        checkloss(i)

    elif x == 14:
        # he has device of no theft
        if c[player.NOTHEFT]:
            return 0

        if player.emptyhanded() == 1:
            p = "\nThe %s couldn't find anything to steal."
        else:
            ularn_win.Printf("\nThe %s picks your pocket and takes:", lastmonst)
            if player.stealsomething(xx, yy) == 0:
                ularn_win.Print("  nothing")
            teleportmonst(xx, yy, dungeon.mitem[xx][yy].mon)

            need_beep = 1
            need_show = 1

    elif x == 15:
        i = rnd(10) + 5 - c[player.AC]
        p = "\nThe %s bit you!"
        need_beep = 1
        checkloss(i)

    elif x == 16:
        i = rnd(15) + 10 - c[player.AC]
        p = "\nThe %s bit you!"
        need_beep = 1
        checkloss(i)

    #
    # This attack needs a beep to be played to alert the player
    # to bad things.
    #
    if need_beep:
        ularn_win.UlarnBeep()

    #
    # If a message has been set then display the message
    #
    if p:
        ularn_win.Printf(p, lastmonst)

        player.recalc()
        ularn_win.UpdateStatus()

    return need_show


def mmove(sx, sy, dx, dy):
    """Function to actually perform the monster movement.

    This function sets movedx & movedy to the new monster position, or -1
    if the monster was killed or otherwise removed from the level.
    """
    global movedx, movedy

    c = player.c
    mitem = dungeon.mitem
    item = dungeon.item
    iarg = dungeon.iarg
    hitp = dungeon.hitp
    know = dungeon.know
    moved = dungeon.moved
    stealth = dungeon.stealth

    monst_killed = 0

    if (dx == player.playerx) and (dy == player.playery):
        # The destination is the player, so the monster attacks
        hitplayer(sx, sy)
        moved[sx][sy] = 1
        movedx = sx
        movedy = sy
        return

    monst_id = mitem[sx][sy].mon
    it = item[dx][dy]

    # Copy the monster and items it is carrying to the new location
    for i in range(mitem[sx][sy].n):
        mitem[dx][dy].it[i].item = mitem[sx][sy].it[i].item
        mitem[dx][dy].it[i].itemarg = mitem[sx][sy].it[i].itemarg
        mitem[sx][sy].it[i].item = itm.ONOTHING
        mitem[sx][sy].it[i].itemarg = 0
    mitem[dx][dy].n = mitem[sx][sy].n
    mitem[dx][dy].mon = mitem[sx][sy].mon

    # monsters that move are obviously awake
    stealth[dx][dy] |= dungeon.STEALTH_AWAKE
    hitp[dx][dy] = hitp[sx][sy]

    # clear the monster from the old location
    mitem[sx][sy].mon = MONST_NONE
    mitem[sx][sy].n = 0
    hitp[sx][sy] = 0

    # mark this monster as moved
    moved[dx][dy] = 1

    # perform special processing for monsters

    if monst_id == LEMMING:
        # 2% chance moving a lemming creates a new lemming
        # in the old spot, holy shit, ten percent? Damn!
        if rnd(100) <= 2:
            mitem[sx][sy].mon = LEMMING
            hitp[sx][sy] = hitp[dx][dy]

    if monst_id == LEPRECHAUN:
        # leprechaun takes gold and gems
        if it in (itm.OGOLDPILE, itm.OMAXGOLD, itm.OKGOLD, itm.ODGOLD,
                  itm.ODIAMOND, itm.ORUBY, itm.OEMERALD, itm.OSAPPHIRE):
            if mitem[dx][dy].n < 6:
                n = mitem[dx][dy].n
                mitem[dx][dy].it[n].item = item[dx][dy]
                mitem[dx][dy].it[n].itemarg = iarg[dx][dy]
                mitem[dx][dy].n += 1
            item[dx][dy] = itm.ONOTHING
            iarg[dx][dy] = 0

    if monst_id == TROLL:
        # if a troll regenerate him
        if (player.gtime & 1) == 0:
            if monster[monst_id].hitpoints > hitp[dx][dy]:
                hitp[dx][dy] += 1

    # check for monsters walking into traps and spheres of annihilation

    trap_damage = 0
    trap_msg = None
    who = ""

    if it == itm.OANNIHILATION:
        # demons dispel spheres
        if monst_id >= DEMONLORD:
            have_talisman = player.player_has_item(itm.OSPHTALISMAN)

            if ((not have_talisman) or
                    (have_talisman and (monst_id == LUCIFER) and (rnd(10) > 7))):
                # delete the sphere
                trap_msg = "\nThe %s%s dispels the sphere!"
                sphere.rmsphere(dx, dy)
            else:
                # monster annihilated
                trap_msg = "\nThe %s%s is destroyed by the sphere of annihilation!"
                mitem[dx][dy].mon = MONST_NONE
                mitem[dx][dy].n = 0
                hitp[dx][dy] = 0
                monst_killed = 1
        else:
            # monster annihilated
            trap_msg = "\nThe %s%s is destroyed by the sphere of annihilation!"
            mitem[dx][dy].mon = MONST_NONE
            mitem[dx][dy].n = 0
            hitp[dx][dy] = 0
            monst_killed = 1
    elif it == itm.OTRAPARROW:
        who = "An arrow"
        trap_damage = rnd(10) + dungeon.level
    elif it == itm.ODARTRAP:
        who = "A dart"
        trap_damage = rnd(6)
    elif it == itm.OTELEPORTER:
        # monster hits teleport trap
        if monst_id < DEMONLORD:
            trap_msg = "\nThe %s%s gets teleported."
            teleportmonst(dx, dy, mitem[dx][dy].mon)
            dx = movedx
            dy = movedy
    elif it == itm.OPIT:
        if (monster[monst_id].flags & FL_FLY) == 0:
            # non-flying monsters can fall into pits and trap doors
            trap_msg = "\nThe %s%s fell into a pit."
            mitem[dx][dy].mon = MONST_NONE
            hitp[dx][dy] = 0
            monst_killed = 1
    elif it == itm.OTRAPDOOR:
        if (monster[monst_id].flags & FL_FLY) == 0:
            # non-flying monsters can fall into pits and trap doors
            trap_msg = "\nThe %s%s fell through a trapdoor."
            mitem[dx][dy].mon = MONST_NONE
            hitp[dx][dy] = 0
            monst_killed = 1
    elif (it == itm.OELEVATORUP) or (it == itm.OELEVATORDOWN):
        # The monster enters an elevator
        if monst_id < DEMONLORD:
            trap_msg = "\nThe %s%s is carried away by an elevator!"
            mitem[dx][dy].mon = MONST_NONE
            hitp[dx][dy] = 0
            monst_killed = 1

    if trap_damage > 0:
        # the monster was damaged by a trap
        hitp[dx][dy] -= trap_damage

        if hitp[dx][dy] <= 0:
            # the trap killed the monster
            mitem[dx][dy].mon = MONST_NONE
            trap_msg = "\n%s hits and kills the %s."
            monst_killed = 1
        else:
            trap_msg = "\n%s hits the %s."

    #
    # Store the location to which this monster has been moved, or -1 if
    # the monster was destroyed
    #
    if monst_killed:
        movedx = -1
        movedy = -1
    else:
        movedx = dx
        movedy = dy

    # if blind don't show where monsters are
    if c[player.BLINDCOUNT]:
        return

    # (C can index off the map here if a failed teleport left a stale
    #  movedx/movedy of -1; such a location is simply not displayed.)
    dest_on_map = dungeon.checkxy(dx, dy)

    if dest_on_map and know[dx][dy] != itm.OUNKNOWN:
        if trap_msg is not None:
            ularn_win.Printf(trap_msg, who, monster[monst_id].name)
            ularn_win.UlarnBeep()

    if (monst_id >= DEMONLORD) and (monst_id <= LUCIFER) and (c[player.EYEOFLARN] == 0):
        #
        # don't update the screen for demonlords and above if the player
        # doesn't have the eye of larn as the player can't see the monster.
        #
        return

    # Update the screen
    if know[sx][sy] != itm.OUNKNOWN:
        ularn_win.show1cell(sx, sy)
    if dest_on_map and know[dx][dy] != itm.OUNKNOWN:
        ularn_win.show1cell(dx, dy)


def valid_monst_move(x, y, monst_id):
    """Check if the location x, y is a valid place for monster monst_id to
    move or attack.

    Does NOT check if the location is already occupied by another monster.
    Returns 0 if the monster cannot occupy this position, 1 if it can.
    """
    tmpitem = dungeon.item[x][y]

    at_player = (x == player.playerx) and (y == player.playery)
    at_entrance = (x == 33) and (y == dungeon.MAXY - 1) and (dungeon.level == 1)

    #
    # A monster cannot pass through a closed door or a wall.
    # However, while a monster cannot hit the player through a closed door
    # a monster can hit a player who is walking through walls.
    #
    blocked = (tmpitem == itm.OCLOSEDDOOR) or ((tmpitem == itm.OWALL) and not at_player)

    #
    # Vampires will not move onto mirrors.
    #
    monster_special = (monst_id == VAMPIRE) and (tmpitem == itm.OMIRROR)

    if monst_id >= DEMONPRINCE:
        # walls and closed doors are no hindrance to a demon prince or above
        blocked = False

    if at_entrance or blocked or monster_special:
        # Return 0  (false) to indicate illegal position
        return 0
    else:
        return 1


def smart_move(x, y):
    """Function to move smart monsters."""
    screen = dungeon.screen
    item = dungeon.item
    diroffx = ularn_game.diroffx
    diroffy = ularn_game.diroffy
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    monst = dungeon.mitem[x][y].mon

    # get the screen region to check for monster movement
    xl = move_xl - 2
    yl = move_yl - 2
    xh = move_xh + 2
    yh = move_yh + 2
    xl, yl = dungeon.vxy(xl, yl)
    xh, yh = dungeon.vxy(xh, yh)

    for sy in range(yl, yh + 1):
        for sx in range(xl, xh + 1):
            if valid_monst_move(sx, sy, monst):
                if monst >= DEMONPRINCE:
                    # Monsters of rank DEMONPRICE and above ignore traps etc
                    screen[sx][sy] = 0
                else:
                    # smart monsters will avoid traps
                    t = item[sx][sy]
                    if t in (itm.OELEVATORUP, itm.OELEVATORDOWN, itm.OTRAPARROW,
                             itm.ODARTRAP, itm.OTELEPORTER):
                        # all monsters avoid there traps
                        screen[sx][sy] = 127
                    elif t in (itm.OPIT, itm.OTRAPDOOR):
                        if (monster[monst].flags & FL_FLY) != 0:
                            # flying monsters ignore pits and trap doors.
                            screen[sx][sy] = 0
                        else:
                            screen[sx][sy] = 127
                    else:
                        screen[sx][sy] = 0
            else:
                # not valid for this monster to move here
                screen[sx][sy] = 127

    # Mark the player's location
    screen[player.playerx][player.playery] = 1

    # now perform proximity ripple from playerx, playery to monster
    xl = move_xl - 1
    yl = move_yl - 1
    xh = move_xh + 1
    yh = move_yh + 1
    xl, yl = dungeon.vxy(xl, yl)
    xh, yh = dungeon.vxy(xh, yh)

    path_dist = 1
    found_path = 0

    while (path_dist < distance) and (not found_path):
        for sy in range(yl, yh + 1):
            for sx in range(xl, xh + 1):
                if screen[sx][sy] == path_dist:
                    #
                    # This square is path_dist steps from the player, so advance
                    # the path by one in all directions not already part of a path.
                    #
                    for z in range(1, 9):
                        xtmp = sx + diroffx[z]
                        ytmp = sy + diroffy[z]

                        if (xtmp >= 0) and (xtmp < MAXX) and (ytmp >= 0) and (ytmp < MAXY):
                            # This square is within the map
                            if screen[xtmp][ytmp] == 0:
                                #
                                # a valid position that is not part of a path has
                                # been found, so mark it as path_dist + 1 away from
                                # the player
                                #
                                screen[xtmp][ytmp] = path_dist + 1

                                if (xtmp == x) and (ytmp == y):
                                    found_path = 1

        path_dist += 1

    if found_path:
        # did find connectivity
        #
        # Now find the square with a distance 1 lower than the distance to the
        # monster being moved.
        #
        path_dist = screen[x][y] - 1

        for z in range(1, 9):
            xl = x + diroffx[z]
            yl = y + diroffy[z]

            if dungeon.level == 0:
                #
                # On the home level monsters can move right to the edge
                # of the map
                #
                on_map = dungeon.checkxy(xl, yl)
            else:
                #
                # In the dungeon and volcano monsters can not move onto the
                # outer border of walls.
                #
                on_map = (xl >= 1) and (xl < (MAXX - 1)) and (yl >= 1) and (yl < (MAXY - 1))

            if on_map:
                if screen[xl][yl] == path_dist:
                    if dungeon.mitem[xl][yl].mon == MONST_NONE:
                        mmove(x, y, xl, yl)
                        return


def dumb_move(x, y):
    """Function to move dumb monsters."""
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY
    playerx = player.playerx
    playery = player.playery

    w1 = [0] * 9
    w1x = [0] * 9
    w1y = [0] * 9

    monst_id = dungeon.mitem[x][y].mon
    xl = x - 1
    yl = y - 1
    xh = x + 2
    yh = y + 2

    if x < playerx:
        xl += 1
    elif x > playerx:
        xh -= 1

    if y < playery:
        yl += 1
    elif y > playery:
        yh -= 1

    if xl < 0:
        xl = 0
    if xh > MAXX:
        xh = MAXX
    if yl < 0:
        yl = 0
    if yh > MAXY:
        yh = MAXY

    for k in range(9):
        w1[k] = 10000

    # For each square compute distance to player

    tmp = 0
    for tx in range(xl, xh):
        for ty in range(yl, yh):
            if (valid_monst_move(tx, ty, monst_id) and
                    (dungeon.mitem[tx][ty].mon == MONST_NONE)):
                w1[tmp] = ((playerx - tx) * (playerx - tx) +
                           (playery - ty) * (playery - ty))
                w1x[tmp] = tx
                w1y[tmp] = ty
            tmp += 1

    # find the closest square in the search area
    j = 0
    for k in range(1, 9):
        if w1[k] < w1[j]:
            j = k

    if (w1[j] < 10000) and ((x != w1x[j]) or (y != w1y[j])):
        mmove(x, y, w1x[j], w1y[j])


def scared_move(x, y):
    """Function to move scared monsters."""
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    # move in random direction
    nx = x + rnd(3) - 2
    ny = y + rnd(3) - 2

    if nx < 0:
        nx = 0
    if nx >= MAXX:
        nx = MAXX - 1
    if ny < 0:
        ny = 0
    if ny >= MAXY:
        ny = MAXY - 1

    if (valid_monst_move(nx, ny, dungeon.mitem[x][y].mon) and
            (dungeon.mitem[nx][ny].mon == MONST_NONE)):
        # This is a valid place to move, so move there
        mmove(x, y, nx, ny)

    return


def movemt(x, y):
    """This routine is responsible for determining where one monster at (x,y)
    will move to.
    """
    c = player.c

    monst = dungeon.mitem[x][y].mon

    # half speed monsters only move every other turn
    if (monster[monst].flags & FL_SLOW) != 0:
        if (player.gtime & 1) == 1:
            return

    # choose destination randomly if scared

    # Check for hand of fear
    Scared = player.player_has_item(itm.OHANDofFEAR)

    if c[player.SCAREMONST]:
        #
        # hand of fear is scarier (may work on higher level monsters) if scare
        # monster is in effect.
        #
        Scared += 1
    elif (Scared == 1) and (rnd(10) > 4):
        #
        # Hand of fear alone is only effective 60% of the time
        #
        Scared = 0

    if (monst > DEMONLORD) or (monst == PLATINUMDRAGON):
        #
        # A demon lord or higher is only scared if the player has both
        # the hand of fear and scare monster active.
        # Even then, only half the time
        #
        Scared = 0 if (Scared <= 1) else (1 if rnd(10) > 5 else 0)

    # Call the appropriate move routine
    if Scared:
        scared_move(x, y)
    elif monster[monst].intelligence > 10 - c[player.HARDGAME]:
        smart_move(x, y)
    else:
        dumb_move(x, y)


# =============================================================================
# Exported functions

def createmonster(mon):
    """Function to create a monster next to the player."""
    mitem = dungeon.mitem
    diroffx = ularn_game.diroffx
    diroffy = ularn_game.diroffy

    if mon < 1 or mon > MAXMONST + 8:
        ularn_win.UlarnBeep()
        ularn_win.Printf("\ncan't createmonst(%d)\n", mon)
        ularn_win.nap(3000)
        return

    while (monster[mon].flags & FL_GENOCIDED) != 0 and (mon < MAXMONST):
        mon += 1  # genocided?

    # choose direction, then try all
    k = rnd(8)
    i = -8
    while i < 0:
        if k > 8:
            k = 1  # wraparound the diroff arrays
        x = player.playerx + diroffx[k]
        y = player.playery + diroffy[k]

        # if we can create a monster here
        if dungeon.cgood(x, y, 0, 1):
            mitem[x][y].mon = mon
            dungeon.hitp[x][y] = monster[mon].hitpoints
            dungeon.stealth[x][y] = 0  # New monsters are not seen or awake

            if mon in (ROTHE, POLTERGEIST, VAMPIRE):
                # These monsters are initially awake
                dungeon.stealth[x][y] |= dungeon.STEALTH_AWAKE
            return
        i += 1
        k += 1


def mon_has_item(x, y, Item):
    """Returns true if the monster at location x, y has Item in its inventory.

    If there is no monster at x, y then the function returns false.
    """
    has_item = 0

    m = dungeon.mitem[x][y]
    if m.mon != 0:
        for i in range(m.n):
            if m.it[i].item == Item:
                has_item = 1

    return has_item


def fullhit(xx):
    """Function to return hp damage to monster due to a number of full hits."""
    c = player.c

    if (xx < 0) or (xx > 20):
        return 0  # fullhits are out of range

    if c[player.LANCEDEATH]:
        return 10000  # lance of death

    i = xx * ((c[player.WCLASS] >> 1) + c[player.STRENGTH] + c[player.STREXTRA] -
              c[player.HARDGAME] - 12 + c[player.MOREDAM])

    return i if (i >= 1) else xx


def ifblind(x, y):
    """Subroutine to copy the word "monster" into lastmonst if the player is
    blind, or the monster name if not.
    """
    global last_monst_id, lastmonst

    x, y = dungeon.vxy(x, y)  # verify correct x,y coordinates
    if player.c[player.BLINDCOUNT]:
        last_monst_id = MONST_NONE
        s = "monster"
    else:
        last_monst_id = dungeon.mitem[x][y].mon
        s = monster[last_monst_id].name
    lastmonst = s


def hitmonster(x, y):
    """Function to hit a monster at the designated coordinates.

    This routine is used for a bash & slash type attack on a monster.
    """
    c = player.c
    iven = player.iven
    ivenarg = player.ivenarg

    if c[player.TIMESTOP]:
        return  # not if time stopped

    x, y = dungeon.vxy(x, y)  # verify coordinates are within range

    monst = dungeon.mitem[x][y].mon
    if monst == MONST_NONE:
        return

    player.hit3flag = 1
    ifblind(x, y)

    tmp = (monster[monst].armorclass + c[player.LEVEL] + c[player.DEXTERITY] +
           cdiv(c[player.WCLASS], 4) - 12 - c[player.HARDGAME])

    damag = 0
    # need at least random chance to hit
    if (rnd(20) < tmp) or (rnd(71) < 5):
        ularn_win.Print("\nYou hit")
        flag = 1
        damag = fullhit(1)

        if damag < 9999:
            damag = rnd(damag) + 1
    else:
        ularn_win.Print("\nYou missed")
        flag = 0
    ularn_win.Printf(" the %s.", lastmonst)

    #
    #  If the monser was hit, deal with weapon dulling.
    #
    if (flag and
            (monst == RUSTMONSTER or monst == DISENCHANTRESS or monst == CUBE) and
            (c[player.WIELD] >= 0)):
        w = c[player.WIELD]
        # if it's not already dulled to hell
        if (((ivenarg[w] > -10) and
             (iven[w] in (itm.OSLAYER, itm.ODAGGER, itm.OSPEAR, itm.OFLAIL,
                          itm.OBATTLEAXE, itm.OLONGSWORD, itm.O2SWORD,
                          itm.OLANCE, itm.OHAMMER, itm.OVORPAL, itm.OBELT))) or
                (ivenarg[w] > 0)):
            ularn_win.Printf("\nYour weapon is dulled by the %s.", lastmonst)
            ularn_win.UlarnBeep()

            player.adjustivenarg(w, -1)
        elif ivenarg[w] <= -10:
            # Destroy the weapon if it is too badly damaged
            ularn_win.Printf("\nYour weapon disintegrates!")
            # Adjust character attributes for the destroyed item
            player.adjustcvalues(iven[w], ivenarg[w])
            # Destroy the item
            iven[w] = itm.ONOTHING
            ivenarg[w] = 0
            # No longer wielding anything
            c[player.WIELD] = -1
            # Didn't hit after all...
            flag = 0

        # Recalculate WC
        player.recalc()
        ularn_win.UpdateStatus()

    if flag:
        hitm(x, y, damag, 0)
        if (monst >= DEMONLORD) and (c[player.LANCEDEATH]) and (dungeon.hitp[x][y]):
            ularn_win.Printf("\nYour lance of death tickles the %s!", lastmonst)

    if monst == METAMORPH:
        if dungeon.hitp[x][y] < 25 and dungeon.hitp[x][y] > 0:
            dungeon.mitem[x][y].mon = BRONZEDRAGON + rund(9)
            ularn_win.show1cell(x, y)

    if dungeon.mitem[x][y].mon == LEMMING:
        if rnd(100) <= 40:
            createmonster(LEMMING)


def hitm(x, y, amt, SpellFlag):
    """Function to just hit a monster at a given coordinates.

    This routine is used to specifically damage a monster at a location.
    The function handles damage from both weapons and spells.
    Returns the number of hitpoints the monster absorbed.
    """
    global last_monst_hx, last_monst_hy

    c = player.c
    mitem = dungeon.mitem
    hitp = dungeon.hitp

    x, y = dungeon.vxy(x, y)  # verify coordinates are within range
    amt2 = amt  # save initial damage so we can return it
    monst = mitem[x][y].mon

    # if half damage curse adjust damage points
    if c[player.HALFDAM]:
        amt >>= 1
    if amt <= 0:
        amt2 = 1
        amt = 1

    last_monst_hx = x
    last_monst_hy = y

    # make sure hitting monst wakes the monster
    dungeon.stealth[x][y] |= dungeon.STEALTH_AWAKE

    if c[player.HOLDMONST] > 0:
        #
        # Hit a monster breaks hold monster spell.
        # Set HOLDMONST counter to 1 so the next regen will cancel the effect.
        #
        c[player.HOLDMONST] = 1

    # if a dragon and orb(s) of dragon slaying
    if c[player.SLAYING]:
        if monst in (WHITEDRAGON, REDDRAGON, GREENDRAGON, BRONZEDRAGON,
                     PLATINUMDRAGON, SILVERDRAGON):
            amt *= 3

    if not SpellFlag:
        # Deal with weapon based effects

        # Deal with Vorpy
        if ((c[player.WIELD] > 0) and
                (player.iven[c[player.WIELD]] == itm.OVORPAL) and
                (rnd(20) == 1) and
                ((monster[monst].flags & FL_HEAD) != 0) and
                ((monster[monst].flags & FL_NOBEHEAD) == 0)):
            ularn_win.Printf("\nThe Vorpal Blade beheads the %s!", lastmonst)
            amt = hitp[x][y]

        if monst >= DEMONLORD:
            if c[player.LANCEDEATH]:
                amt = 300
            if _wielded_item() == itm.OSLAYER:
                amt = 10000

    hpoints = hitp[x][y]
    if hpoints <= amt:
        ularn_win.Printf("\nThe %s died!", lastmonst)
        player.raiseexperience(monster[monst].experience)
        dungeon.disappear(x, y)

        if mitem[x][y].n > 0:
            for i in range(mitem[x][y].n):
                dungeon.createitem(x, y,
                                   mitem[x][y].it[i].item,
                                   mitem[x][y].it[i].itemarg)
            dungeon.beenhere[dungeon.level] -= mitem[x][y].n

            if dungeon.beenhere[dungeon.level] < 1:
                dungeon.beenhere[dungeon.level] = 1

            mitem[x][y].n = 0
            amt = monster[monst].gold
            if amt > 0:
                dungeon.dropgold(rnd(amt) + amt)
        else:
            amt = monster[monst].gold
            if amt > 0:
                dungeon.dropgold(rnd(amt) + amt)
            dropsomething(x, y, monst)
        ularn_win.show1cell(x, y)
        ularn_win.showcell(player.playerx, player.playery)
        player.recalc()
        ularn_win.UpdateStatus()
        hitp[x][y] = 0

        return hpoints

    hitp[x][y] = hpoints - amt
    return amt2


def hitplayer(x, y):
    """Function for the monster at the designated location to hit the player."""
    global last_monst_id

    c = player.c

    x, y = dungeon.vxy(x, y)  # verify coordinates are within range

    last_monst_id = dungeon.mitem[x][y].mon
    mster = dungeon.mitem[x][y].mon

    if dungeon.know[x][y] == itm.OUNKNOWN:
        ularn_win.show1cell(x, y)

    bias = (c[player.HARDGAME]) + 1
    player.hitflag = player.hit2flag = player.hit3flag = 1
    ularn_win.yrepcount = 0

    ifblind(x, y)

    if mster == LEMMING:
        return

    if (monster[mster].flags & FL_INFRAVIS) == 0:
        # Monsters without infravision might miss invisible players
        if c[player.INVISIBILITY]:
            if rnd(33) < 20:
                ularn_win.Printf("\nThe %s misses wildly!", lastmonst)
                return

    if (mster < DEMONLORD) and (mster != PLATINUMDRAGON):
        if c[player.CHARMCOUNT]:
            if rnd(30) + 5 * monster[mster].level - c[player.CHARISMA] < 30:
                ularn_win.Printf("\nThe %s is awestruck by your magnificence!", lastmonst)
                return

    dam = monster[mster].damage
    dam += rnd(1 if (dam < 1) else dam) + monster[mster].level

    #
    # demon lords/prince/god of hellfire damage is reduced if wielding
    # Slayer
    #
    if mster >= DEMONLORD:
        if _wielded_item() == itm.OSLAYER:
            # does between 1/10 and 1/2 damage
            dam = cdiv(rnd(5) * dam, 10)

    #
    # spirit naga's and poltergeist's damage is halved if scarab of
    # negate spirit
    #
    if c[player.NEGATESPIRIT] or c[player.SPIRITPRO]:
        if (monster[mster].flags & FL_SPIRIT) != 0:
            dam = cdiv(dam, 2)

    #  halved if undead and cube of undead control
    if c[player.CUBEofUNDEAD] or c[player.UNDEADPRO]:
        if (monster[mster].flags & FL_UNDEAD) != 0:
            dam = cdiv(dam, 2)

    hit_success = 0
    at_chance = max(c[player.AC], 1)

    if monster[mster].attack > 0:
        #
        # If the hit isn't good enough to do a special attack on its own then
        # a monster has a 1:at_chance of performing a special attack
        #
        if ((dam + bias + 8) > c[player.AC]) or (rnd(at_chance) == 1):
            if spattack(monster[mster].attack, x, y):
                # The monster successfully performed a special attack
                return
            else:
                #
                # The monster did a special attack and failed to affect the
                # player, so note that the monster hit and weaken the normal
                # attack.
                #
                hit_success = 1
                bias -= 2

    if ((dam + bias) > c[player.AC]) or (rnd(at_chance) == 1):
        ularn_win.Printf("\n  The %s hit you.", lastmonst)
        hit_success = 1

        # Reduce the damage by the player's AC
        dam -= c[player.AC]
        if dam < 0:
            dam = 0

        if dam > 0:
            player.losehp(scores.DIED_MONSTER, dam)
            ularn_win.UpdateStatus()

    if hit_success == 0:
        ularn_win.Printf("\n  The %s missed.", lastmonst)


def makemonst(lev):
    """Function to return monster number for a randomly selected monster for
    the given cave level.
    """
    if lev < 1:
        lev = 1
    if lev > 12:
        lev = 12

    tmp = WATERLORD

    if lev < 5:
        min_monst_id = 1
        max_monst_id = monstlevel[lev - 1]
    else:
        min_monst_id = monstlevel[lev - 4] + 1
        max_monst_id = monstlevel[lev - 1]

    num_ids = (max_monst_id - min_monst_id) + 1

    while tmp == WATERLORD:
        tmp = min_monst_id + rund(num_ids)

    while (monster[tmp].flags & FL_GENOCIDED) != 0 and (tmp < MAXMONST):
        tmp += 1

    if dungeon.level <= dungeon.DBOTTOM:
        if rnd(100) < 10:
            tmp = LEMMING

    return tmp


def randmonst():
    """Function to randomly create monsters if needed."""
    global rmst

    #  don't make monsters if time is stopped
    if player.c[player.TIMESTOP]:
        return

    rmst -= 1
    if rmst <= 0:
        rmst = 120 - (dungeon.level << 2)
        dungeon.fillmonst(makemonst(dungeon.level))


def teleportmonst(xx, yy, monst):
    """Function to teleport a monster."""
    global movedx, movedy

    mitem = dungeon.mitem
    hitp = dungeon.hitp

    # max # of teleport attempts
    for trys in range(10, 0, -1):
        x = rnd(dungeon.MAXX - 2)
        y = rnd(dungeon.MAXY - 2)
        if ((dungeon.item[x][y] == itm.ONOTHING) and (mitem[x][y].mon == MONST_NONE) and
                ((player.playerx != x) or (player.playery != y))):
            mitem[x][y].mon = monst
            mitem[xx][yy].mon = MONST_NONE

            hitp[x][y] = monster[monst].hitpoints
            hitp[xx][yy] = 0
            for i in range(mitem[xx][yy].n):
                mitem[x][y].it[i].item = mitem[xx][yy].it[i].item
                mitem[x][y].it[i].itemarg = mitem[xx][yy].it[i].itemarg
                mitem[xx][yy].it[i].item = itm.ONOTHING
                mitem[xx][yy].it[i].itemarg = 0
            mitem[x][y].n = mitem[xx][yy].n
            mitem[xx][yy].n = 0

            # store the new location
            movedx = x
            movedy = y

            ularn_win.show1cell(xx, yy)

            return


def movemonst():
    """This routine has the responsibility to determine which monsters are to
    move, and to perform the movement.
    """
    global move_xl, move_yl, move_xh, move_yh, distance
    global last_monst_hx, last_monst_hy

    c = player.c
    mitem = dungeon.mitem
    moved = dungeon.moved
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    # no action if time is stopped
    if c[player.TIMESTOP]:
        return

    # Check for haste self
    if c[player.HASTESELF]:
        if (c[player.HASTESELF] & 1) == 0:
            return

    # move the spheres of annihilation if any
    sphere.movsphere()

    # no action if monsters are held
    if c[player.HOLDMONST]:
        return

    if c[player.AGGRAVATE]:
        # determine window of monsters to move
        move_yl = player.playery - 5
        move_yh = player.playery + 6
        move_xl = player.playerx - 10
        move_xh = player.playerx + 11
        distance = 40  # depth of intelligent monster movement
    else:
        move_yl = player.playery - 3
        move_yh = player.playery + 4
        move_xl = player.playerx - 5
        move_xh = player.playerx + 6
        distance = 17  # depth of intelligent monster movement

    if dungeon.level == 0:
        # if on outside level monsters can move in perimeter
        if move_yl < 0:
            move_yl = 0
        if move_yh > MAXY:
            move_yh = MAXY
        if move_xl < 0:
            move_xl = 0
        if move_xh > MAXX:
            move_xh = MAXX
    else:
        # if in a dungeon monsters can't be on the perimeter (wall there)
        if move_yl < 1:
            move_yl = 1
        if move_yh > MAXY - 1:
            move_yh = MAXY - 1
        if move_xl < 1:
            move_xl = 1
        if move_xh > MAXX - 1:
            move_xh = MAXX - 1

    # now reset monster moved flags
    for j in range(move_yl, move_yh):
        for i in range(move_xl, move_xh):
            moved[i][j] = 0

    #
    # Move the last monster hit by the player
    # This is mainly to make monster hit by spells move towards the player,
    # even if out of the normal movement range.
    # If the last monster hit by the player no longer exists then
    # last_monst_hx and last_monst_hy will be out of the map range
    # (actually set to -1).
    #
    if ((last_monst_hx >= 0) and (last_monst_hx < MAXX) and
            (last_monst_hy >= 0) and (last_monst_hy < MAXY)):
        moved[last_monst_hx][last_monst_hy] = 0
        if mitem[last_monst_hx][last_monst_hy].mon != MONST_NONE:
            movemt(last_monst_hx, last_monst_hy)
            last_monst_hx = movedx
            last_monst_hy = movedy

    if c[player.AGGRAVATE] or not c[player.STEALTH]:
        # move monsters for aggravation or not stealthed
        for j in range(move_yl, move_yh):  # look thru all locations in window
            for i in range(move_xl, move_xh):
                if (mitem[i][j].mon != MONST_NONE) and (moved[i][j] == 0):
                    # if there is a monster to move and it isn't already moved
                    movemt(i, j)
    else:
        for j in range(move_yl, move_yh):
            for i in range(move_xl, move_xh):
                if (mitem[i][j].mon != MONST_NONE) and (moved[i][j] == 0):
                    # if there is a monster to move and it isn't already moved
                    if (dungeon.stealth[i][j] & dungeon.STEALTH_AWAKE) != 0:
                        # Move awake monsters
                        movemt(i, j)


def parse2():
    """Move things while player is out of action."""
    # move the monsters
    if player.c[player.HASTEMONST]:
        movemonst()

    movemonst()
    randmonst()
    player.regen()


def write_monster_data(fp):
    """Function to write the monster data to the save file (binary fp).

    The data is written with pickle.dump().
    """
    data = {
        # write the random nonster generation time
        "rmst": rmst,
        # Write genocide status
        "genocided": [1 if (monster[i].flags & FL_GENOCIDED) != 0 else 0
                      for i in range(MAXMONST)],
    }
    pickle.dump(data, fp)


def read_monster_data(fp):
    """Function to read the monster data from the save file (binary fp)."""
    global rmst

    data = pickle.load(fp)

    # read the random nonster generation time
    rmst = data["rmst"]

    # read genocide status
    for i in range(MAXMONST):
        genocided = data["genocided"][i]

        if genocided:
            monster[i].flags |= FL_GENOCIDED
