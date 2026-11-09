"""Player information and the effects of various actions (port of player.c/player.h).

Exported variables:
  char_class        : The name of the player's selected class
  class_num         : The number to identify the character class
  ramboflag         : Is the character rambo?
  sex               : Character's gender
  wizard            : The wizard flag
  cheat             : Has the player cheated
  char_picked       : The character class letter picked
  playerx, playery  : The player's current coordinates
  lastpx, lastpy    : The player's previous coordinates
  initialtime       : The time play started
  gtime             : The clock for the game
  outstanding_taxes : The taxes owed from the score file
  c                 : The character attributes array
  cbak              : The last displayed attributes array
  iven              : The inventory items
  ivenarg           : The inventory item args
  class_            : The character class (level) strings (C name: class)
  skill             : Experience required for each level
  potionknown       : Array indicating potions discovered
  scrollknown       : Array indicating scrolls discovered
  spelknow          : Array indicating spells learnt by the player
  hitflag, hit2flag, hit3flag : Hit flags for player, used for move processing
"""

import pickle

from .header import *

# =============================================================================
# player.h  (defined before importing other pyularn modules so that modules
# importing this one circularly can still see the constants)

INNATE_TELEPORT_LEVEL = 10

# *************** Defines for the character attibute array c[] ******
# AttributeType
# Player ability scores
STRENGTH = 0
INTELLIGENCE = 1
WISDOM = 2
CONSTITUTION = 3
DEXTERITY = 4
CHARISMA = 5
# Hitpoints
HPMAX = 6
HP = 7

GOLD = 8
EXPERIENCE = 9
LEVEL = 10
REGEN = 11
WCLASS = 12
AC = 13
BANKACCOUNT = 14
SPELLMAX = 15
SPELLS = 16
ENERGY = 17
ECOUNTER = 18
MOREDEFENSES = 19
WEAR = 20
PROTECTIONTIME = 21
WIELD = 22
AMULET = 23
REGENCOUNTER = 24
MOREDAM = 25
DEXCOUNT = 26
STRCOUNT = 27
BLINDCOUNT = 28
CAVELEVEL = 29
CONFUSE = 30
ALTPRO = 31
HERO = 32
CHARMCOUNT = 33
INVISIBILITY = 34
CANCELLATION = 35
HASTESELF = 36
EYEOFLARN = 37
AGGRAVATE = 38
GLOBE = 39
TELEFLAG = 40
SLAYING = 41
NEGATESPIRIT = 42
SCAREMONST = 43
AWARENESS = 44
HOLDMONST = 45
TIMESTOP = 46
HASTEMONST = 47
CUBEofUNDEAD = 48
GIANTSTR = 49
FIRERESISTANCE = 50
BESSMANN = 51
NOTHEFT = 52
HARDGAME = 53
BYTESIN = 54
UNUSED_55 = 55
UNUSED_56 = 56
UNUSED_57 = 57
UNISED_58 = 58
VORPAL = 59
LANCEDEATH = 60
SPIRITPRO = 61
UNDEADPRO = 62
SHIELD = 63
STEALTH = 64
# Curses
ITCHING = 65
LAUGHING = 66
DRAINSTRENGTH = 67
CLUMSINESS = 68
INFEEBLEMENT = 69
HALFDAM = 70
# More player flags
SEEINVISIBLE = 71
FILLROOM = 72
SPHCAST = 73
WTW = 74
STREXTRA = 75
TMP = 76             # Temporary work area for total str
LIFEPROT = 77        # Number of life protections read
# Item creation flags for unique items
ORB = 78             # Created orb of expanded awareness
ELVUP = 79           # Created elevator up
ELVDOWN = 80         # Created elevator down
HAND = 81            # Created hand of fear
CUBEUNDEAD = 82      # Created cube of undead control
DRAGSLAY = 83        # Created orb of dragon slaying
NEGATE = 84          # Created scarab of negate spirit
URN = 85             # Created golden urn
LAMP = 86            # Created brass lamp
TALISMAN = 87        # Created talisman of the sphere
WAND = 88            # Created wand of wonder
STAFF = 89           # Created staff of power
DEVICE = 90          # Created device of theft prevention
SLASH = 91           # Created sword of slashing
ELVEN = 92           # Created elven chain
VORP = 93            # Created vorpal sword
SLAY = 94            # Created slayer
PAD = 95             # Created Dealer McDope's
LIFE_PRESERVER = 96  # Created amulet of life preservation
# Misc
COKED = 97           # Flag indicating player is coked
TMP2 = 98            # Storage for original int before Bessmann's hammer
UNUSED_98 = 99
UNUSED_99 = 100
ATTRIBUTE_COUNT = 101

ABILITY_FIRST = STRENGTH
ABILITY_LAST = CHARISMA
ABILITY_COUNT = (ABILITY_LAST - ABILITY_FIRST + 1)

IVENSIZE = 26  # max size of inventory

# =============================================================================
# Exported variables

# class[c[LEVEL]-1] gives the correct name of the player's experience level
aa1 = " mighty evil master"
aa2 = "apprentice demi-god"
aa3 = "  minor demi-god   "
aa4 = "  major demi-god   "
aa5 = "    minor deity    "
aa6 = "    major deity    "
aa7 = "  novice guardian  "
aa8 = "apprentice guardian"
aa9 = "    The Creator    "

# C name: class (a Python keyword)
class_ = [
    "  novice explorer  ", "apprentice explorer", " practiced explorer",  # -3
    "  expert explorer  ", " novice adventurer ", "     adventurer    ",  # -6
    "apprentice conjurer", "     conjurer      ", "  master conjurer  ",  # -9
    "  apprentice mage  ", "       mage        ", " experienced mage  ",  # -12
    "    master mage    ", " apprentice warlord", "  novice warlord   ",  # -15
    "  expert warlord   ", "   master warlord  ", " apprentice gorgon ",  # -18
    "      gorgon       ", "  practiced gorgon ", "   master gorgon   ",  # -21
    "    demi-gorgon    ", "    evil master    ", " great evil master ",  # -24
    aa1, aa1, aa1,  # -27
    aa1, aa1, aa1,  # -30
    aa1, aa1, aa1,  # -33
    aa1, aa1, aa1,  # -36
    aa1, aa1, aa1,  # -39
    aa2, aa2, aa2,  # -42
    aa2, aa2, aa2,  # -45
    aa2, aa2, aa2,  # -48
    aa3, aa3, aa3,  # -51
    aa3, aa3, aa3,  # -54
    aa3, aa3, aa3,  # -57
    aa4, aa4, aa4,  # -60
    aa4, aa4, aa4,  # -63
    aa4, aa4, aa4,  # -66
    aa5, aa5, aa5,  # -69
    aa5, aa5, aa5,  # -72
    aa5, aa5, aa5,  # -75
    aa6, aa6, aa6,  # -78
    aa6, aa6, aa6,  # -81
    aa6, aa6, aa6,  # -84
    aa7, aa7, aa7,  # -87
    aa8, aa8, aa8,  # -90
    aa8, aa8, aa8,  # -93
    "  earth guardian   ", "   air guardian    ", "   fire guardian   ",  # -96
    "  water guardian   ", "   time guardian   ", " ethereal guardian ",  # -99
    aa9, aa9, aa9,  # -102
]

# table of experience needed to be a certain level of player
# skill[c[LEVEL]] is the experience required to attain the next level
MEG = 1000000
skill = [
    0, 10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120,                        # 1-11
    10240, 20480, 40960, 100000, 200000, 400000, 700000, 1 * MEG,             # 12-19
    2 * MEG, 3 * MEG, 4 * MEG, 5 * MEG, 6 * MEG, 8 * MEG, 10 * MEG,            # 20-26
    12 * MEG, 14 * MEG, 16 * MEG, 18 * MEG, 20 * MEG, 22 * MEG, 24 * MEG, 26 * MEG, 28 * MEG,  # 27-35
    30 * MEG, 32 * MEG, 34 * MEG, 36 * MEG, 38 * MEG, 40 * MEG, 42 * MEG, 44 * MEG, 46 * MEG,  # 36-44
    48 * MEG, 50 * MEG, 52 * MEG, 54 * MEG, 56 * MEG, 58 * MEG, 60 * MEG, 62 * MEG, 64 * MEG,  # 45-53
    66 * MEG, 68 * MEG, 70 * MEG, 72 * MEG, 74 * MEG, 76 * MEG, 78 * MEG, 80 * MEG, 82 * MEG,  # 54-62
    84 * MEG, 86 * MEG, 88 * MEG, 90 * MEG, 92 * MEG, 94 * MEG, 96 * MEG, 98 * MEG, 100 * MEG,  # 63-71
    105 * MEG, 110 * MEG, 115 * MEG, 120 * MEG, 125 * MEG, 130 * MEG, 135 * MEG, 140 * MEG,  # 72-79
    145 * MEG, 150 * MEG, 155 * MEG, 160 * MEG, 165 * MEG, 170 * MEG, 175 * MEG, 180 * MEG,  # 80-87
    185 * MEG, 190 * MEG, 195 * MEG, 200 * MEG, 210 * MEG, 220 * MEG, 230 * MEG, 240 * MEG,  # 88-95
    260 * MEG, 280 * MEG, 300 * MEG, 320 * MEG, 340 * MEG, 370 * MEG,          # 96-101
]
del MEG

hitflag = 0   # flag for if player has been hit when running
hit2flag = 0  # flag for if player has been hit when running
hit3flag = 0  # flag for if player has been hit flush input

char_class = ""  # character class
class_num = 0    # character class number

ramboflag = 0
sex = 1          # default is man, 0=woman
wizard = 0       # the wizard mode flag
cheat = 0        # 1 if the player has fudged save file
char_picked = 0  # the character chosen (0 or a 1-char str 'a'..'h')
playerx = 0      # the room on the present level of the player
playery = 0
lastpx = 0       # 0 --- MAXX-1  or  0 --- MAXY-1
lastpy = 0

initialtime = 0        # time playing began
gtime = 0              # the clock for the game
outstanding_taxes = 0  # present tax bill from score file

c = [0] * ATTRIBUTE_COUNT     # Character description array
cbak = [0] * ATTRIBUTE_COUNT  # Backup array for detecting changes

# =============================================================================
# Local variables

MAXPLEVEL = 100  # maximum player level allowed

# Haste step to keep track of frations of moves when hasted
HasteStep = 0

# Character fields affected by the passage of time
TIME_CHANGED_COUNT = 28
time_change = [
    HERO,
    ALTPRO,
    PROTECTIONTIME,
    DEXCOUNT,
    STRCOUNT,
    GIANTSTR,
    CHARMCOUNT,
    INVISIBILITY,
    CANCELLATION,
    HASTESELF,
    AGGRAVATE,
    SCAREMONST,
    STEALTH,
    AWARENESS,
    HOLDMONST,
    HASTEMONST,
    FIRERESISTANCE,
    GLOBE,
    SPIRITPRO,
    UNDEADPRO,
    HALFDAM,
    SEEINVISIBLE,
    ITCHING,
    CLUMSINESS,
    WTW,
    COKED,
    BLINDCOUNT,
    CONFUSE,
]

# Character fields for curses
CURSE_COUNT = 10
curse = [
    BLINDCOUNT,
    CONFUSE,
    AGGRAVATE,
    HASTEMONST,
    ITCHING,
    LAUGHING,
    DRAINSTRENGTH,
    CLUMSINESS,
    INFEEBLEMENT,
    HALFDAM,
]

MAX_CLASSES = 8
MAX_INITIAL_SPELLS = 2
MAX_INITIAL_ITEMS = 3

from . import itm  # noqa: E402  (itm has no pyularn imports)

iven = [itm.ONOTHING] * IVENSIZE  # inventory for player
ivenarg = [0] * IVENSIZE          # inventory args for player

from . import ularn_game, ularn_win, ularn_ask, saveutils, scores, monster  # noqa: E402
from . import dungeon, dungeon_obj, scroll, potion, spell, show  # noqa: E402

# Array of which potions are known to the player.  0 = unknown, 1 = known
potionknown = [0] * potion.MAXPOTION

# Array of which scrolls are known to the player.  0 = unknown, 1 = known
scrollknown = [0] * scroll.MAXSCROLL

# Array of which spells are known to the player.  0 = unknown, 1 = known
# (sized with the literal value of spell.SPELL_COUNT (39) so that this module
#  does not depend on spell.py being fully initialised at import time)
spelknow = [0] * 39


class InitialClassDataType:
    """Initial attributes and inventory of a character class."""

    def __init__(self, ClassName, Attr, InitialSP, InitialHP, KnownSpells,
                 Item, ItemArg, WearItem, WieldItem):
        self.ClassName = ClassName
        self.Attr = Attr
        self.InitialSP = InitialSP
        self.InitialHP = InitialHP
        self.KnownSpells = KnownSpells
        self.Item = Item
        self.ItemArg = ItemArg
        self.WearItem = WearItem
        self.WieldItem = WieldItem


# Built on first use by _class_data() (needs spell.SPELL_* constants).
InitialClassData = None


def _class_data():
    """Return the InitialClassData table, building it on first use."""
    global InitialClassData
    if InitialClassData is None:
        InitialClassData = [
            InitialClassDataType(
                "Ogre",                                        # Class name
                [18, 4, 6, 16, 6, 4],                          # STR, INT, WIS, CON, DEX, CHA
                1, 16,                                         # SP, HP
                [spell.SPELL_MLE, spell.SPELL_COUNT],          # Spells
                [itm.OPOTION, itm.OPOTION, itm.ONOTHING],      # Items
                [-6, -6, 0],                                   # Item args
                -1, -1),                                       # Wear, Wield
            InitialClassDataType(
                "Wizard",
                [8, 16, 16, 6, 6, 8],
                2, 8,
                [spell.SPELL_MLE, spell.SPELL_CHM],
                [itm.OPOTION, itm.OSCROLL, itm.OSCROLL],
                [potion.PTREASURE, -6, -6],
                -1, -1),
            InitialClassDataType(
                "Klingon",
                [14, 12, 4, 12, 8, 3],
                1, 14,
                [spell.SPELL_SSP, spell.SPELL_COUNT],
                [itm.OSTUDLEATHER, itm.OPOTION, itm.ONOTHING],
                [0, -6, 0],
                0, -1),
            InitialClassDataType(
                "Elf",
                [8, 14, 12, 8, 8, 14],
                2, 8,
                [spell.SPELL_MLE, spell.SPELL_COUNT],
                [itm.OLEATHER, itm.OSCROLL, itm.ONOTHING],
                [0, -6, 0],
                0, -1),
            InitialClassDataType(
                "Rogue",
                [8, 12, 8, 10, 14, 6],
                1, 12,
                [spell.SPELL_MLE, spell.SPELL_COUNT],
                [itm.OLEATHER, itm.ODAGGER, itm.OSCROLL],
                [0, 0, scroll.SSTEALTH],
                0, 1),                                         # Wield, wear
            InitialClassDataType(
                "Adventurer",
                [12, 12, 12, 12, 12, 12],
                1, 10,
                [spell.SPELL_PRO, spell.SPELL_MLE],
                [itm.OLEATHER, itm.ODAGGER, itm.ONOTHING],
                [0, 0, 0],
                0, 1),
            InitialClassDataType(
                "Dwarf",
                [16, 6, 8, 16, 4, 4],
                1, 12,
                [spell.SPELL_PRO, spell.SPELL_COUNT],
                [itm.OSPEAR, itm.ONOTHING, itm.ONOTHING],
                [0, 0, 0],
                -1, 0),
            InitialClassDataType(
                "Rambo",
                [3, 3, 3, 3, 3, 3],
                0, 1,
                [spell.SPELL_MLE, spell.SPELL_COUNT],
                [itm.OLANCE, itm.ONOTHING, itm.ONOTHING],
                [0, 0, 0],
                -1, 0),
        ]
    return InitialClassData


# =============================================================================
# Local functions

def pick_char(foo):
    """Pick the player's character class and set initial attributes and inventory.

    foo : 0 to ask, or the class selection character 'a' .. 'h' from the opts.
    """
    global class_num, char_class, ramboflag

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    ularn_win.nosignal = 1  # disable signals

    if foo == 0:
        ularn_win.ClearText()
        ularn_win.MoveCursor(29, 1)
        ularn_win.Standout("The Addiction of Ularn\n\n")
        ularn_win.Print("Pick a character class...\n\n")

        ularn_win.Print("\ta)  Ogre       - Exceptional strength, but thick as a brick\n")
        ularn_win.Print("\n")
        ularn_win.Print("\tb)  Wizard     - Smart, good at magic, but very weak\n")
        ularn_win.Print("\n")
        ularn_win.Print("\tc)  Klingon    - Strong and average IQ, but unwise & very ugly\n")
        ularn_win.Print("\n")
        ularn_win.Print("\td)  Elf        - OK at magic, but a mediocre fighter\n")
        ularn_win.Print("\n")
        ularn_win.Print("\te)  Rogue      - Nimble and smart, but only average strength\n")
        ularn_win.Print("\n")
        ularn_win.Print("\tf)  Adventurer - Jack of all trades, master of none\n")
        ularn_win.Print("\n")
        ularn_win.Print("\tg)  Dwarf      - Strong and healthy, but not good at magic\n")
        ularn_win.Print("\n")
        ularn_win.Print("\th)  Rambo      - A special challenge.\n")
        ularn_win.Print("\t                 Bad at everything, but has a lance of death")

        ularn_win.MoveCursor(1, 24)
        i = ularn_win.get_prompt_input("So, what are ya? ", "abcdefgh", 1)

    else:
        # Character selected in ops
        i = foo
        c[SHIELD] = c[WEAR] = c[WIELD] = -1

    if isinstance(i, str):
        i = ord(i)
    i = i - ord('a')
    class_num = i

    data = _class_data()[i]

    char_class = data.ClassName
    c[SPELLMAX] = data.InitialSP
    c[SPELLS] = data.InitialSP
    c[HPMAX] = data.InitialHP
    c[HP] = data.InitialHP

    for j in range(ABILITY_FIRST, ABILITY_LAST + 1):
        c[j] = data.Attr[j - ABILITY_FIRST]

    for j in range(MAX_INITIAL_SPELLS):
        if data.KnownSpells[j] < spell.SPELL_COUNT:
            spelknow[data.KnownSpells[j]] = 1

    for j in range(MAX_INITIAL_ITEMS):
        iven[j] = data.Item[j]

        if iven[j] == itm.OLANCE:
            c[LANCEDEATH] = 1
            ramboflag = 1

        if data.ItemArg[j] >= 0:
            ivenarg[j] = data.ItemArg[j]
        else:
            ivenarg[j] = rund(-data.ItemArg[j])

    c[WEAR] = data.WearItem
    c[WIELD] = data.WieldItem

    ularn_win.nosignal = 0


# =============================================================================
# Exported functions

def identify_class(class_str):
    """Identify the class selection character ('a' .. 'h') from the class name.

    Returns the class selection character (1-char str), or 0 if not found.
    (C lower-cases class_str in place; Python strings are immutable, so the
    caller must do that itself if it relies on it.)
    """
    if class_str is None:
        # no class string specified
        return 0

    class_str = class_str.lower()

    data = _class_data()
    cls = 0
    found = 0

    while (cls < MAX_CLASSES) and (not found):
        class_cmp_str = data[cls].ClassName.lower()

        if class_str == class_cmp_str:
            found = 1
        else:
            cls += 1

    if cls < MAX_CLASSES:
        return chr(ord('a') + cls)
    else:
        return 0


def makeplayer():
    """Create the player and the player's attributes (start of game only)."""
    global playerx, playery, lastpx, lastpy, gtime

    # Clear the player's attributes
    for i in range(ATTRIBUTE_COUNT):
        c[i] = 0
        cbak[i] = 0

    # Clear the player's inventory
    for i in range(IVENSIZE):
        iven[i] = itm.ONOTHING
        ivenarg[i] = 0

    # Clear spells, potions and scrolls known
    for i in range(potion.MAXPOTION):
        potionknown[i] = 0

    for i in range(scroll.MAXSCROLL):
        scrollknown[i] = 0

    for i in range(spell.SPELL_COUNT):
        spelknow[i] = 0

    c[LEVEL] = 1         # player starts at level one
    c[REGENCOUNTER] = 16
    c[ECOUNTER] = 96     # start regeneration correctly

    c[SHIELD] = -1
    c[WEAR] = -1
    c[WIELD] = -1

    if isinstance(char_picked, str) and 'a' <= char_picked <= 'h':
        # Class specified on command line
        pick_char(char_picked)
    else:
        # Ask for the class
        pick_char(0)

    # Position the player in the home level
    playerx = rnd(dungeon.MAXX - 2)
    playery = rnd(dungeon.MAXY - 2)
    lastpx = 0
    lastpy = 0

    # time clock starts at zero
    gtime = 0
    cbak[SPELLS] = -50
    recalc()


def moveplayer(dir):
    """Move the player from one room to another.

    nomove is set to 1 to stop the next move (inadvertent monsters hitting
    players when walking into walls) if player walks off screen or into wall.
    Returns 0 if can't move in that direction or hit a monster or on an
    object, else 1.
    """
    global playerx, playery, lastpx, lastpy

    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    if c[CONFUSE]:
        if c[LEVEL] < rnd(30):
            dir = rund(9)  # if confused any dir

    k = playerx + ularn_game.diroffx[dir]
    m = playery + ularn_game.diroffy[dir]

    if (k < 0) or (k >= MAXX) or (m < 0) or (m >= MAXY):
        ularn_game.nomove = 1
        ularn_win.yrepcount = 0
        return 0

    i = dungeon.item[k][m]
    j = dungeon.mitem[k][m].mon

    # hit a wall
    if (i == itm.OWALL) and (c[WTW] == 0):
        ularn_game.nomove = 1
        ularn_win.yrepcount = 0
        return 0

    # Can't move onto closed doors if using the enhanced interface
    if ularn_game.enhance_interface and (i == itm.OCLOSEDDOOR):
        ularn_game.nomove = 1
        ularn_win.yrepcount = 0
        return 0

    if (k == 33) and (m == MAXY - 1) and (dungeon.level == 1):
        dungeon.newcavelevel(0)

        # Returning to the home level from the dungeon, so find the
        # dungeon entrance and locate the player at the dungeon entrance.
        for k in range(MAXX):
            for m in range(MAXY):
                if dungeon.item[k][m] == itm.OENTRANCE:
                    playerx = k
                    playery = m
                    positionplayer()
                    ularn_win.drawscreen()
                    return 0
        # (C falls through here with k == MAXX, m == MAXY if no entrance
        #  was found; that cannot happen on the home level.)

    if j > 0:
        monster.hitmonster(k, m)
        ularn_win.yrepcount = 0
        return 0  # hit a monster

    lastpx = playerx
    lastpy = playery
    playerx = k
    playery = m

    if ((i != itm.ONOTHING) and
            (i != itm.OTRAPARROWIV) and
            (i != itm.OIVTELETRAP) and
            (i != itm.OIVDARTRAP) and
            (i != itm.OIVTRAPDOOR)):
        ularn_win.yrepcount = 0
        return 0
    else:
        return 1


def player_has_item(Item):
    """Return 1 if the player is currently carrying Item, 0 otherwise."""
    have_item = 0
    for i in range(IVENSIZE):
        if iven[i] == Item:
            have_item = 1

    return have_item


def raiselevel():
    """Raise the player one level (uses skill[], c[EXPERIENCE], c[LEVEL])."""
    if c[LEVEL] < MAXPLEVEL:
        raiseexperience(skill[c[LEVEL]] - c[EXPERIENCE])


def loselevel():
    """Lower the player's character level by one."""
    if c[LEVEL] > 1:
        loseexperience(c[EXPERIENCE] - skill[c[LEVEL] - 1] + 1)


def raiseexperience(x):
    """Increase experience points."""
    i = c[LEVEL]
    c[EXPERIENCE] += x
    while c[EXPERIENCE] >= skill[c[LEVEL]] and (c[LEVEL] < MAXPLEVEL):
        tmp = (c[CONSTITUTION] - c[HARDGAME]) >> 1
        c[LEVEL] += 1
        raisemhp(rnd(3) + rnd(tmp if tmp > 0 else 1))
        raisemspells(rund(3))
        if c[LEVEL] < 7 - c[HARDGAME]:
            raisemhp(c[CONSTITUTION] >> 2)

    if c[LEVEL] != i:
        # Alert the player to level up
        ularn_win.UlarnBeep()
        ularn_win.Printf("\nWelcome to level %d!", c[LEVEL])
        # if we changed levels

        lev = c[LEVEL]
        if lev == 94:    # earth guardian
            c[WTW] = 99999
        elif lev == 95:  # air guardian
            c[INVISIBILITY] = 99999
        elif lev == 96:  # fire guardian
            c[FIRERESISTANCE] = 99999
        elif lev == 97:  # water guardian
            c[CANCELLATION] = 99999
        elif lev == 98:  # time guardian
            c[HASTESELF] = 99999
        elif lev == 99:  # ethereal guardian
            c[STEALTH] = 99999
            c[SPIRITPRO] = 99999
        elif lev == 100:
            ularn_win.Print("\nYou are now The Creator!")
            for ii in range(dungeon.MAXY):
                for jj in range(dungeon.MAXX):
                    dungeon.know[jj][ii] = dungeon.item[jj][ii]
            for ii in range(spell.SPELL_COUNT):
                spelknow[ii] = 1
            for ii in range(scroll.MAXSCROLL):
                scrollknown[ii] = 1
            for ii in range(potion.MAXPOTION):
                potionknown[ii] = 1

    ularn_win.UpdateStatusAndEffects()


def loseexperience(x):
    """Lose experience points."""
    i = c[LEVEL]
    c[EXPERIENCE] -= x
    if c[EXPERIENCE] < 0:
        c[EXPERIENCE] = 0
    while c[EXPERIENCE] < skill[c[LEVEL] - 1]:
        c[LEVEL] -= 1
        if c[LEVEL] <= 1:
            c[LEVEL] = 1  # down one level

        tmp = (c[CONSTITUTION] - c[HARDGAME]) >> 1  # lose hpoints
        losemhp(rnd(tmp if tmp > 0 else 1))         # lose hpoints
        if c[LEVEL] < 7 - c[HARDGAME]:
            losemhp(c[CONSTITUTION] >> 2)
        losemspells(rund(3))  # lose spells

    if i != c[LEVEL]:
        ularn_win.Printf("\nYou went down to level %d!", c[LEVEL])

    recalc()
    ularn_win.UpdateStatus()


def losehp(Reason, x):
    """Remove hit points from the player (will kill player if hp goes to zero)."""
    c[HP] -= x
    if c[HP] <= 0:
        ularn_win.UlarnBeep()
        ularn_win.Print("\nAlas, you have died.\n")
        ularn_win.Print("\n")
        ularn_win.nap(3000)

        if (Reason == scores.DIED_MONSTER) and (monster.last_monst_id == monster.MONST_NONE):
            Reason = scores.DIED_UNSEEN_ATTACKER
        scores.died(Reason, monster.last_monst_id)


def losemhp(x):
    """Reduce max hitpoints (won't kill player)."""
    c[HP] -= x
    if c[HP] < 1:
        c[HP] = 1

    c[HPMAX] -= x
    if c[HPMAX] < 1:
        c[HPMAX] = 1


def raisehp(x):
    """Gain hitpoints; never makes HP exceed max HP."""
    c[HP] += x
    if c[HP] > c[HPMAX]:
        c[HP] = c[HPMAX]


def raisemhp(x):
    """Increase max HP."""
    c[HPMAX] += x
    c[HP] += x


def raisespells(x):
    """Gain spell points; never exceeds max spell points."""
    c[SPELLS] += x
    if c[SPELLS] > c[SPELLMAX]:
        c[SPELLS] = c[SPELLMAX]


def raisemspells(x):
    """Increase max spell points."""
    c[SPELLMAX] += x
    c[SPELLS] += x


def losespells(x):
    """Decrease the number of spell points."""
    c[SPELLS] -= x
    if c[SPELLS] < 0:
        c[SPELLS] = 0


def losemspells(x):
    """Decrease the maximum number of spell points."""
    c[SPELLMAX] -= x
    if c[SPELLMAX] < 0:
        c[SPELLMAX] = 0
    c[SPELLS] -= x
    if c[SPELLS] < 0:
        c[SPELLS] = 0


def positionplayer():
    """Be sure player is not in a wall (move to the closest empty square)."""
    global playerx, playery

    item = dungeon.item
    mitem = dungeon.mitem

    if ((item[playerx][playery] == itm.ONOTHING) and
            (mitem[playerx][playery].mon == monster.MONST_NONE)):
        # location is clear, so nothing to do
        return

    closest = 10000
    cx = cy = 0

    for x in range(dungeon.MAXX):
        for y in range(dungeon.MAXY):
            if (item[x][y] == itm.ONOTHING) and (mitem[x][y].mon == monster.MONST_NONE):
                # This location is empty, so see how far it is from the desired
                # location.
                dist = (playerx - x) * (playerx - x) + (playery - y) * (playery - y)

                if dist < closest:
                    # This is the closest location found so far
                    cx = x
                    cy = y
                    closest = dist

    if closest == 10000:
        ularn_win.Print("Failure in positionplayer\n")
    else:
        playerx = cx
        playery = cy


def recalc():
    """Recalculate the armor class and weapon class of the player.

    Also sets the LANCEDEATH attribute according to the wielded item.
    """
    c[AC] = c[MOREDEFENSES]
    if c[WEAR] >= 0:
        w = iven[c[WEAR]]
        a = ivenarg[c[WEAR]]
        if w == itm.OSHIELD:
            c[AC] += 2 + a
        elif w == itm.OLEATHER:
            c[AC] += 2 + a
        elif w == itm.OSTUDLEATHER:
            c[AC] += 3 + a
        elif w == itm.ORING:
            c[AC] += 5 + a
        elif w == itm.OCHAIN:
            c[AC] += 6 + a
        elif w == itm.OSPLINT:
            c[AC] += 7 + a
        elif w == itm.OPLATE:
            c[AC] += 9 + a
        elif w == itm.OPLATEARMOR:
            c[AC] += 10 + a
        elif w == itm.OSSPLATE:
            c[AC] += 12 + a
        elif w == itm.OELVENCHAIN:
            c[AC] += 15 + a

    if c[SHIELD] >= 0 and iven[c[SHIELD]] == itm.OSHIELD:
        c[AC] += 2 + ivenarg[c[SHIELD]]

    c[LANCEDEATH] = 0

    if c[WIELD] < 0:
        c[WCLASS] = 0
    else:
        i = ivenarg[c[WIELD]]
        w = iven[c[WIELD]]
        if w == itm.ODAGGER:
            c[WCLASS] = 3 + i
        elif w == itm.OBELT:
            c[WCLASS] = 7 + i
        elif w == itm.OSHIELD:
            c[WCLASS] = 8 + i
        elif w in (itm.OPSTAFF, itm.OSPEAR):
            c[WCLASS] = 10 + i
        elif w == itm.OFLAIL:
            c[WCLASS] = 14 + i
        elif w == itm.OBATTLEAXE:
            c[WCLASS] = 17 + i
        elif w == itm.OLANCE:
            c[LANCEDEATH] = 1
            c[WCLASS] = 20 + i
        elif w in (itm.OLONGSWORD, itm.OVORPAL):
            c[WCLASS] = 22 + i
        elif w == itm.O2SWORD:
            c[WCLASS] = 26 + i
        elif w == itm.OSWORDofSLASHING:
            c[WCLASS] = 30 + i
        elif w == itm.OSLAYER:
            c[WCLASS] = 30 + i
        elif w == itm.OSWORD:
            c[WCLASS] = 32 + i
        elif w == itm.OHAMMER:
            c[WCLASS] = 35 + i
        else:
            c[WCLASS] = 0
    c[WCLASS] += c[MOREDAM]

    # now for regeneration abilities based on rings
    c[REGEN] = 1
    c[ENERGY] = 0

    # (C loops i <= IVENSIZE, reading one element past the end of iven[];
    #  only the real inventory slots are examined here.)
    for i in range(IVENSIZE):
        w = iven[i]
        if w == itm.OPROTRING:
            c[AC] += ivenarg[i] + 1
        elif w == itm.ODAMRING:
            c[WCLASS] += ivenarg[i] + 1
        elif w == itm.OBELT:
            c[WCLASS] += (ivenarg[i] << 1) + 2
        elif w == itm.OREGENRING:
            c[REGEN] += ivenarg[i] + 1
        elif w == itm.ORINGOFEXTRA:
            c[REGEN] += 5 * (ivenarg[i] + 1)
        elif w == itm.OENERGYRING:
            c[ENERGY] += ivenarg[i] + 1


def take(itm_, arg):
    """Put something in the player's inventory.  Returns 0 if success, 1 if failure.

    (C parameter name: itm; renamed to avoid clashing with the itm module.)
    """
    eyeflag = 0

    # Decide how many items the player can carry
    limit = 15 + (c[LEVEL] >> 1)
    if limit > IVENSIZE:
        limit = IVENSIZE

    # find a free inventory slot
    i = 0
    slot = -1
    while (i < limit) and (slot == -1):
        if iven[i] == itm.ONOTHING:
            slot = i
        i += 1

    if slot != -1:
        # found a free inventory slot, so store the item
        need_recalc = 0
        iven[slot] = itm_
        ivenarg[slot] = arg
        if itm_ in (itm.OPROTRING, itm.ODAMRING, itm.OBELT):
            need_recalc = 1
        elif itm_ == itm.ODEXRING:
            c[DEXTERITY] += ivenarg[slot] + 1
            need_recalc = 1
        elif itm_ == itm.OSTRRING:
            c[STREXTRA] += ivenarg[slot] + 1
            need_recalc = 1
        elif itm_ == itm.OCLEVERRING:
            c[INTELLIGENCE] += ivenarg[slot] + 1
            need_recalc = 1
        elif itm_ == itm.OHAMMER:
            c[DEXTERITY] += 10
            c[STREXTRA] += 10
            c[TMP2] = c[INTELLIGENCE]
            c[INTELLIGENCE] = 3 if (c[TMP2] - 10 <= 2) else c[TMP2] - 10
            need_recalc = 1
        elif itm_ == itm.OORB:
            c[ORB] += 1
            c[AWARENESS] += 1
        elif itm_ == itm.OORBOFDRAGON:
            c[SLAYING] += 1
        elif itm_ == itm.OSPIRITSCARAB:
            c[NEGATESPIRIT] += 1
        elif itm_ == itm.OCUBEofUNDEAD:
            c[CUBEofUNDEAD] += 1
        elif itm_ == itm.ONOTHEFT:
            c[NOTHEFT] += 1
        elif itm_ == itm.OSWORDofSLASHING:
            c[DEXTERITY] += 5
            need_recalc = 1
        elif itm_ == itm.OSLAYER:
            c[INTELLIGENCE] += 10
            need_recalc = 1
        elif itm_ == itm.OPSTAFF:
            c[WISDOM] += 10
            need_recalc = 1
        elif itm_ == itm.OLARNEYE:
            c[EYEOFLARN] = 1
            eyeflag = 1

        ularn_win.Print("\nYou pick up:")
        show.show3(slot)
        if need_recalc:
            recalc()
            ularn_win.UpdateStatus()

        if (c[BLINDCOUNT] == 0) and eyeflag:
            ularn_win.Print("\nYour sight fades for a moment...")
            ularn_win.nap(2000)
            ularn_win.drawscreen()
            ularn_win.Print("\nYour sight returns, and everything looks crystal-clear!")
        return 0

    ularn_win.Print("\nYou can't carry anything else.")
    return 1


def drop_object(k):
    """Drop inventory item k.  Returns 1 if something there already else 0."""
    pitflag = 0

    if (k < 0) or (k > 25):
        return 0

    itm_ = iven[k]

    if itm_ == itm.ONOTHING:
        ularn_win.Printf("\nYou don't have item %c! ", chr(k + ord('a')))
        return 1

    if dungeon.item[playerx][playery] == itm.OPIT:
        pitflag = 1
    elif dungeon.item[playerx][playery] > itm.ONOTHING:
        ularn_win.UlarnBeep()
        ularn_win.Print("\nThere's something here already.")
        return 1

    if playery == dungeon.MAXY - 1 and playerx == 33:
        return 1  # not in entrance

    if not pitflag:
        dungeon.item[playerx][playery] = itm_
        dungeon.iarg[playerx][playery] = ivenarg[k]

    # show what item you dropped
    ularn_win.Print("\n  You drop:")
    show.show3(k)

    # Update the player's inventory and status
    iven[k] = itm.ONOTHING

    if c[WIELD] == k:
        c[WIELD] = -1
    if c[WEAR] == k:
        c[WEAR] = -1
    if c[SHIELD] == k:
        c[SHIELD] = -1

    adjustcvalues(itm_, ivenarg[k])
    recalc()
    ularn_win.UpdateStatus()

    if pitflag:
        ularn_win.Printf("\nIt disappears down the pit.")

    # say dropped an item so wont ask to pick it up right away
    ularn_game.dropflag = 1
    return 0


def adjustivenarg(Idx, Amount):
    """Adjust the inventory argument by Amount, updating attributes as required."""
    ivenarg[Idx] += Amount

    w = iven[Idx]
    # Armour
    if w in (itm.OPLATE, itm.OCHAIN, itm.OLEATHER, itm.ORING, itm.OSTUDLEATHER,
             itm.OSPLINT, itm.OPLATEARMOR, itm.OSSPLATE, itm.OSHIELD,
             itm.OELVENCHAIN):
        recalc()
        ularn_win.UpdateStatus()

    # Weapons
    elif w in (itm.OSWORDofSLASHING, itm.OHAMMER, itm.OSWORD, itm.O2SWORD,
               itm.OSPEAR, itm.ODAGGER, itm.OBATTLEAXE, itm.OLONGSWORD,
               itm.OFLAIL, itm.OLANCE, itm.OVORPAL, itm.OSLAYER, itm.OBELT):
        recalc()
        ularn_win.UpdateStatus()

    # Rings
    elif w == itm.ORINGOFEXTRA:
        recalc()

    elif w == itm.OREGENRING:
        recalc()

    elif w == itm.OPROTRING:
        recalc()
        ularn_win.UpdateStatus()

    elif w == itm.OENERGYRING:
        recalc()

    elif w == itm.ODEXRING:
        c[DEXTERITY] += Amount
        recalc()
        ularn_win.UpdateStatus()

    elif w == itm.OSTRRING:
        c[STREXTRA] += Amount
        recalc()
        ularn_win.UpdateStatus()

    elif w == itm.OCLEVERRING:
        c[INTELLIGENCE] += Amount
        recalc()
        ularn_win.UpdateStatus()

    elif w == itm.ODAMRING:
        recalc()
        ularn_win.UpdateStatus()


def enchantarmor(how):
    """Enchant armor the player is currently wearing (how: ENCH_SCROLL/ENCH_ALTAR)."""
    #  Bomb out if we're not wearing anything.
    if c[WEAR] < 0 and c[SHIELD] < 0:
        ularn_win.UlarnBeep()
        ularn_win.Print("\nYou feel a sense of loss.")
        return

    #  Choose what to enchant.
    which = SHIELD if (rund(100) < 50) else WEAR
    if c[which] < 0:
        which = WEAR if (which == SHIELD) else SHIELD

    #  Enchant it and check for destruction at >= +10.
    if ivenarg[c[which]] >= 9:
        if how == itm.ENCH_ALTAR:
            ularn_win.Printf("\nYour %s glows briefly.", itm.objectname[iven[c[which]]])
        elif rnd(10) <= 9:
            ularn_win.Printf("\nYour %s vibrates violently and crumbles into dust!",
                             itm.objectname[iven[c[which]]])

            # Recalculated any attributes affected by destroying the armour
            adjustcvalues(iven[c[which]], ivenarg[c[which]])

            # Destroy the armour
            iven[c[which]] = itm.ONOTHING
            ivenarg[c[which]] = 0
            c[which] = -1

            # Recalculate player's AC
            recalc()
    else:
        ularn_win.Printf("\nYour %s glows for a moment.", itm.objectname[iven[c[which]]])
        # Increase enchantment level by 1
        adjustivenarg(c[which], 1)

    ularn_win.UpdateStatus()


def enchweapon(how):
    """Enchant the weapon presently being wielded (how: ENCH_SCROLL/ENCH_ALTAR)."""
    if c[WIELD] < 0:
        ularn_win.UlarnBeep()
        ularn_win.Print("\nYou feel depressed.")
        return

    Idx = c[WIELD]
    Obj = iven[c[WIELD]]
    if (Obj != itm.OSCROLL) and (Obj != itm.OPOTION):

        if (ivenarg[Idx] >= 9) and (rnd(10) <= 9):
            if how == itm.ENCH_ALTAR:
                ularn_win.Print("\nYour weapon glows a little.")
            else:
                ularn_win.Print("\nYour weapon vibrates violently and crumbles into dust!")

                # Recalculate any attributes affected by destroying the weapon
                adjustcvalues(iven[Idx], ivenarg[Idx])

                # destroy the weapon
                iven[Idx] = itm.ONOTHING
                ivenarg[Idx] = 0
                c[WIELD] = -1

                # Recalculate the player's WC
                recalc()
        else:
            ularn_win.Print("\nYour weapon glows for a moment.")
            adjustivenarg(Idx, 1)

    ularn_win.UpdateStatus()


def pocketfull():
    """Return 1 if pockets are full, else 0."""
    limit = 15 + (c[LEVEL] >> 1)
    if limit > IVENSIZE:
        limit = IVENSIZE

    for i in range(limit):
        if iven[i] == itm.ONOTHING:
            return 0
    return 1


def nearbymonst():
    """Return 1 if a monster is next to the player else 0."""
    x1 = playerx - 1
    x2 = playerx + 1
    y1 = playery - 1
    y2 = playery + 1

    if x1 < 0:
        x1 = 0
    if x2 >= dungeon.MAXX:
        x2 = dungeon.MAXX - 1
    if y1 < 0:
        y1 = 0
    if y2 >= dungeon.MAXY:
        y2 = dungeon.MAXY - 1

    for tx in range(x1, x2 + 1):
        for ty in range(y1, y2 + 1):
            if dungeon.mitem[tx][ty].mon != monster.MONST_NONE:
                return 1  # monster nearby

    return 0


def stealsomething(x, y):
    """Steal an item from the player's pockets for the monster at x, y.

    Returns 1 if steals something else 0.
    """
    mi = dungeon.mitem[x][y]

    # max of 6 stolen items per monster
    if mi.n >= 6:
        return 0

    n = 100
    while n:
        n -= 1
        i = rund(IVENSIZE)
        if iven[i] != itm.ONOTHING:
            if c[WEAR] != i and c[WIELD] != i and c[SHIELD] != i:
                show.show3(i)
                adjustcvalues(iven[i], ivenarg[i])
                n = mi.n
                mi.n += 1
                mi.it[n].item = iven[i]
                mi.it[n].itemarg = ivenarg[i]

                iven[i] = itm.ONOTHING
                ivenarg[i] = 0
                dungeon.beenhere[dungeon.level] += 1

                return 1
    return 0


def emptyhanded():
    """Return 1 if the player carries nothing (except wielded/worn), else 0."""
    for i in range(IVENSIZE):
        if iven[i] != itm.ONOTHING:
            if (i != c[WIELD]) and (i != c[WEAR]) and (i != c[SHIELD]):
                return 0
    return 1


def creategem():
    """Create a gem on a square near the player."""
    r = rnd(4)
    if r == 1:
        i = itm.ODIAMOND
        j = 50
    elif r == 2:
        i = itm.ORUBY
        j = 40
    elif r == 3:
        i = itm.OEMERALD
        j = 30
    else:
        i = itm.OSAPPHIRE
        j = 20

    dungeon.createitem(playerx, playery, i, rndl(j) + (j // 10))


def adjustcvalues(itm_, arg):
    """Change character attributes as needed when dropping/losing an object.

    (C parameter name: itm; renamed to avoid clashing with the itm module.)
    """
    flag = 0
    if itm_ == itm.ODEXRING:
        c[DEXTERITY] -= arg + 1
        flag = 1
    elif itm_ == itm.OSTRRING:
        c[STREXTRA] -= arg + 1
        flag = 1
    elif itm_ == itm.OCLEVERRING:
        c[INTELLIGENCE] -= arg + 1
        flag = 1
    elif itm_ == itm.OHAMMER:
        c[DEXTERITY] -= 10
        c[STREXTRA] -= 10
        c[INTELLIGENCE] = c[TMP2]
        flag = 1
    elif itm_ == itm.OORB:
        c[ORB] -= 1
        c[AWARENESS] -= 1
    elif itm_ == itm.OSWORDofSLASHING:
        c[DEXTERITY] -= 5
        flag = 1
    elif itm_ == itm.OSLAYER:
        c[INTELLIGENCE] -= 10
        flag = 1
    elif itm_ == itm.OPSTAFF:
        c[WISDOM] -= 10
        flag = 1
    elif itm_ == itm.OORBOFDRAGON:
        c[SLAYING] -= 1
    elif itm_ == itm.OSPIRITSCARAB:
        c[NEGATESPIRIT] -= 1
    elif itm_ == itm.OCUBEofUNDEAD:
        c[CUBEofUNDEAD] -= 1
    elif itm_ == itm.ONOTHEFT:
        c[NOTHEFT] -= 1
    elif itm_ == itm.OLANCE:
        c[LANCEDEATH] = 0
    elif itm_ == itm.OLARNEYE:
        c[EYEOFLARN] = 0
        if c[BLINDCOUNT] == 0:
            ularn_win.Print("\nYour sight fades for a moment...")
            ularn_win.nap(2000)
            ularn_win.drawscreen()
            ularn_win.Print("\nYour sight returns but everything looks dull and faded.")
    elif itm_ in (itm.OPOTION, itm.OSCROLL):
        pass
    else:
        flag = 1

    for i in range(ABILITY_FIRST, ABILITY_LAST + 1):
        if c[i] < 3:
            c[i] = 3

    if flag:
        recalc()
        ularn_win.UpdateStatusAndEffects()


def packweight():
    """Return the number of pounds the player is carrying."""
    k = cdiv(c[GOLD], 1000)
    j = 25
    while (iven[j] == itm.ONOTHING) and (j > 0):
        j -= 1

    for i in range(j + 1):
        w = iven[i]
        if w == itm.ONOTHING:
            pass
        elif w in (itm.OSSPLATE, itm.OPLATEARMOR):
            k += 40
        elif w == itm.OPLATE:
            k += 35
        elif w == itm.OHAMMER:
            k += 30
        elif w == itm.OSPLINT:
            k += 26
        elif w in (itm.OCHAIN, itm.OBATTLEAXE, itm.O2SWORD):
            k += 23
        elif w in (itm.OLONGSWORD, itm.OPSTAFF, itm.OSWORD, itm.ORING, itm.OFLAIL):
            k += 20
        elif w in (itm.OELVENCHAIN, itm.OSWORDofSLASHING, itm.OLANCE,
                   itm.OSLAYER, itm.OSTUDLEATHER):
            k += 15
        elif w in (itm.OLEATHER, itm.OSPEAR):
            k += 8
        elif w in (itm.OORBOFDRAGON, itm.OORB, itm.OBELT):
            k += 4
        elif w == itm.OSHIELD:
            k += 7
        elif w == itm.OCHEST:
            k += 30 + ivenarg[i]
        else:
            k += 1

    return k


def adjust_ability(ability, amount):
    """Adjust an ability score, sticking at 3 if it would go below 3."""
    # check that it is an ability being adjusted
    if (ability < ABILITY_FIRST) or (ability > ABILITY_LAST):
        return

    c[ability] += amount
    if c[ability] < 3:
        c[ability] = 3


def regen():
    """Regenerate player HP and spells, and process time based effects."""
    global gtime, HasteStep

    # Handle stop time spell
    if c[TIMESTOP]:
        c[TIMESTOP] -= 1
        if c[TIMESTOP] <= 0:
            recalc()
            ularn_win.UpdateStatusAndEffects()
        return

    # flag indicates whether effect and/or status need update.
    #   1 = Status, 2 = effects, 3 = both
    flag = 0

    if c[HASTESELF] == 0:
        gtime += 1
    else:
        # Player is moving at double speed, so time only passes every
        # second move
        HasteStep += 1
        if HasteStep == 2:
            gtime += 1
            HasteStep = 0

    # regenerate hit points
    if c[HP] != c[HPMAX]:
        c[REGENCOUNTER] -= 1
        if c[REGENCOUNTER] < 0:
            c[REGENCOUNTER] = 22 + (c[HARDGAME] << 1) - c[LEVEL]
            c[HP] += c[REGEN]
            if c[HP] > c[HPMAX]:
                c[HP] = c[HPMAX]

            flag |= 1

    # regenerate spells
    if c[SPELLS] < c[SPELLMAX]:
        c[ECOUNTER] -= 1
        if c[ECOUNTER] < 0:
            c[ECOUNTER] = 100 + 4 * (c[HARDGAME] - c[LEVEL] - c[ENERGY])
            c[SPELLS] += 1

            flag |= 1

    for j in range(TIME_CHANGED_COUNT):
        Attr = time_change[j]
        if c[Attr] != 0:
            # Reduce time remaining for this effect
            c[Attr] -= 1

            # AWARENESS doesn't wear off if the player has the orb
            if Attr == AWARENESS:
                if c[ORB] != 0:
                    c[AWARENESS] += 1

            if c[Attr] == 0:
                # Effect has worn off, so perform appropriate action

                if Attr == HERO:
                    for i in range(ABILITY_FIRST, ABILITY_LAST + 1):
                        adjust_ability(i, -(potion.PHEROISM_BOOST - 1))
                    flag |= 1

                elif Attr == COKED:
                    for i in range(ABILITY_FIRST, ABILITY_LAST + 1):
                        adjust_ability(i, -34)
                    flag |= 1

                elif Attr == ALTPRO:
                    c[MOREDEFENSES] -= dungeon_obj.ALTAR_PRO_BOOST
                    flag |= 3

                elif Attr == PROTECTIONTIME:
                    c[MOREDEFENSES] -= spell.SPELL_PRO_BOOST
                    flag |= 3

                elif Attr == DEXCOUNT:
                    # (sic: C adds the boost again when the spell expires)
                    adjust_ability(DEXTERITY, spell.SDEXTERITY_BOOST)
                    flag |= 3

                elif Attr == STRCOUNT:
                    c[STREXTRA] -= spell.SSTRENGTH_BOOST
                    flag |= 3

                elif Attr == BLINDCOUNT:
                    ularn_win.Print("\nThe blindness lifts.")
                    ularn_win.UlarnBeep()

                elif Attr == CONFUSE:
                    ularn_win.Print("\nYou regain your senses.")
                    ularn_win.UlarnBeep()

                elif Attr == GIANTSTR:
                    # Giant strength wears off, but the playre gets a permanent +1
                    # boost to extra strength.
                    # (unaffected by effects that lower strength).
                    c[STREXTRA] -= (potion.PGIANTSTR_BOOST - 1)
                    flag |= 3

                elif Attr == GLOBE:
                    c[MOREDEFENSES] -= spell.SPELL_GLOBE_BOOST
                    flag |= 1

                elif Attr == HALFDAM:
                    ularn_win.Print("\nYou now feel better.")
                    ularn_win.UlarnBeep()

                elif Attr == SEEINVISIBLE:
                    if player_has_item(itm.OAMULET):
                        # See inv doesn't wear off if player has amulet of invisibility
                        c[SEEINVISIBLE] += 1

                elif Attr == ITCHING:
                    ularn_win.Print("\nThe irritation subsides.")
                    ularn_win.UlarnBeep()

                elif Attr == CLUMSINESS:
                    ularn_win.Print("\nYou now feel less awkward.")
                    ularn_win.UlarnBeep()

                elif Attr == CHARMCOUNT:
                    flag |= 3

                elif Attr in (INVISIBILITY, CANCELLATION, WTW, HASTESELF,
                              SCAREMONST, STEALTH, HOLDMONST, FIRERESISTANCE,
                              SPIRITPRO, UNDEADPRO):
                    flag |= 2

                elif Attr in (AGGRAVATE, HASTEMONST, AWARENESS):
                    pass

    # If the player is still itching then check to see if armour is to be
    # removed
    if c[ITCHING]:
        if (c[WEAR] != -1) or (c[SHIELD] != -1):
            if rnd(100) < 50:
                c[WEAR] = -1
                c[SHIELD] = -1
                ularn_win.Print("\nThe hysteria of itching forces you to remove your armor!")
                ularn_win.UlarnBeep()
                recalc()
                flag |= 1

    # If the player is still clumsy, check to see if the weapon is dropped
    if c[CLUMSINESS]:
        if c[WIELD] != -1:
            # if nothing there
            if dungeon.item[playerx][playery] == itm.ONOTHING:
                # drop your weapon 1/3 of the time
                if rnd(100) < 33:
                    drop_object(c[WIELD])

    if flag == 1:
        ularn_win.UpdateStatus()
    elif flag == 2:
        ularn_win.UpdateEffects()
    elif flag == 3:
        ularn_win.UpdateStatusAndEffects()


def removecurse():
    """Cure the player of curses."""
    for i in range(CURSE_COUNT):
        if c[curse[i]]:
            # Set the time remaining on each curse to 1 so that the next regen
            # will clear the curse
            c[curse[i]] = 1


def adjusttime(tim):
    """Adjust time when time warping and taking courses in school."""
    # adjust time related parameters
    for j in range(TIME_CHANGED_COUNT):
        if c[time_change[j]]:
            c[time_change[j]] -= tim

            if c[time_change[j]] <= 0:
                # if effect would wear off then set the time remaining to 1 so that
                # the next regen will cancel the effect
                c[time_change[j]] = 1

    regen()


def write_player(fp):
    """Write the player data to a save file.

    fp is a binary file object; the data is written as one pickled dict
    (same fields, same order as the C bwrite calls).
    """
    data = {
        "char_class": char_class,
        "ramboflag": ramboflag,
        "wizard": wizard,
        "cheat": cheat,
        "playerx": playerx,
        "playery": playery,
        "initialtime": initialtime,
        "gtime": gtime,
        "outstanding_taxes": outstanding_taxes,
        "c": list(c),
        "iven": list(iven),
        "ivenarg": list(ivenarg),
        "potionknown": list(potionknown),
        "scrollknown": list(scrollknown),
        "spelknow": list(spelknow),
    }
    pickle.dump(data, fp)


def read_player(fp):
    """Read the player data from a save file written by write_player()."""
    global char_class, ramboflag, wizard, cheat, playerx, playery
    global initialtime, gtime, outstanding_taxes, class_num

    data = pickle.load(fp)

    char_class = data["char_class"]
    ramboflag = data["ramboflag"]
    wizard = data["wizard"]
    cheat = data["cheat"]
    playerx = data["playerx"]
    playery = data["playery"]
    initialtime = data["initialtime"]
    gtime = data["gtime"]
    outstanding_taxes = data["outstanding_taxes"]
    c[:] = data["c"]
    iven[:] = data["iven"]
    ivenarg[:] = data["ivenarg"]
    potionknown[:] = data["potionknown"]
    scrollknown[:] = data["scrollknown"]
    spelknow[:] = data["spelknow"]

    # Identify the class number from the class string.
    # identify_class returns the character selection for the class, or 0
    # if the string matches no valid class.
    # (C's identify_class lower-cases char_class in place.)
    char_class = char_class.lower()
    class_num = identify_class(char_class)
    if class_num != 0:
        class_num = ord(class_num) - ord('a')
    else:
        # class got corrupt somehow, so reset to the first class
        char_class = _class_data()[0].ClassName
