"""Locations found on the home level and in the dungeon (port of store.c / store.h).

Exported functions:
  dndstore    : Handles entering the DND store
  oschool     : Handles entering the college of larn
  obank       : Handles entering the bank of larn
  obank2      : Handles entering the 8th branch of the bank of larn
  ointerest   : Calculates interest on bank accounts
  item_value  : Calculates the value of an item as per the trading post
  otradepost  : Handles entering the trading post.
  olrs        : Handles entering the Larn Revenue Service
  opad        : Handles enetering dealer McDope's pad.
  ohome       : Handes the player returning home.
  write_store : Writes all shop data to the save file
  read_store  : Reads all shop data from the save file

Python port note: write_store(fp) / read_store(fp) accept either a dict
(savegame.py passes its state dict section) or a binary file object (the
shop data dict is pickled to / from it).  The write_*/read_* helpers for
each shop take that dict.
"""

import pickle

from .header import *
from . import ularn_game, ularn_win, ularn_ask, player, potion, scroll, dungeon
from . import scores, show
from . import itm as itm_

# =============================================================================
# store.h definitions

# the tax rate for the LRS = 5%
TAXRATE = 0.05


# =============================================================================
#
# ######          ######           #####
# #     #  #    # #     #         #     #   #####   ####   #####   ######
# #     #  ##   # #     #         #           #    #    #  #    #  #
# #     #  # #  # #     #          #####      #    #    #  #    #  #####
# #     #  #  # # #     #               #     #    #    #  #####   #
# #     #  #   ## #     #         #     #     #    #    #  #   #   #
# ######   #    # ######           #####      #     ####   #    #  ######
#

# =============================================================================
# Local variables

# max # items in the dnd store
DNDSIZE = 93

dnditm = 0


class _itm:
    """Store item: price, memory (known array), object, argument, quantity.

    ``mem`` is 0 or the name of the player module array the item's knowledge
    is recorded in ("potionknown" or "scrollknown"), standing in for the C
    int* pointer.
    """

    def __init__(self, price, mem, obj, arg, qty):
        self.price = price
        self.mem = mem
        self.obj = obj
        self.arg = arg
        self.qty = qty


# Store inventory and prices (filled on first use, see _init_itm)
itm = []


def _init_itm():
    """Build the store inventory table (deferred so that itm/potion/scroll are loaded)."""
    if itm:
        return
    I = itm_
    P = potion
    S = scroll
    pk = "potionknown"
    sk = "scrollknown"
    table = [
        # cost    memory   iven name  iven arg      how
        #  gp   pointer  iven[] ivenarg[]     many
        (2,     0,  I.OLEATHER, 0,    3),
        (10,    0,  I.OSTUDLEATHER, 0,    2),
        (40,    0,  I.ORING,    0,    2),
        (85,    0,  I.OCHAIN,   0,    2),
        (220,   0,  I.OSPLINT,  0,    1),
        (400,   0,  I.OPLATE,   0,    1),
        (900,   0,  I.OPLATEARMOR,  0,    1),
        (2600,  0,  I.OSSPLATE, 0,    1),
        (150,   0,  I.OSHIELD,  0,    1),
        (5000,  0,  I.OELVENCHAIN,    0,        0),
        (1000,  0,  I.OORB,   0,    0),  # 10
        (10000, 0,  I.OSLAYER,  0,    0),

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (2,     0,  I.ODAGGER,    0,  3),
        (20,    0,  I.OSPEAR,     0,  3),
        (80,    0,  I.OFLAIL,     0,  2),
        (150,   0,  I.OBATTLEAXE,   0,  2),
        (450,   0,  I.OLONGSWORD,   0,  2),
        (1000,  0,  I.O2SWORD,    0,  2),
        (5000,  0,  I.OSWORD,     0,  1),
        (20000, 0,  I.OLANCE,     0,  1),
        (2000,  0,  I.OSWORDofSLASHING, 0,  0),  # 20
        (7500,  0,  I.OHAMMER,    0,  0),

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (150,   0,  I.OPROTRING,  1,  1),
        (85,    0,  I.OSTRRING, 1,  1),
        (120,   0,  I.ODEXRING, 1,  1),
        (120,   0,  I.OCLEVERRING,  1,  1),
        (180,   0,  I.OENERGYRING,  0,  1),
        (125,   0,  I.ODAMRING, 0,  1),
        (220,   0,  I.OREGENRING, 0,  1),
        (1000,  0,  I.ORINGOFEXTRA, 0,  1),

        (280,   0,  I.OBELT,    0,  1),  # 30
        (400,   0,  I.OAMULET,  5,  1),

        (500,   0,  I.OCUBEofUNDEAD,  0,  0),
        (600,   0,  I.ONOTHEFT, 0,  0),

        (590,   0,  I.OCHEST,   3,  1),
        (200,   0,  I.OBOOK,    2,  1),
        (10,    0,  I.OCOOKIE,  0,  3),
        (666,   0,  I.OHANDofFEAR,    0,  0),

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (20,    pk,  I.OPOTION,  P.PSLEEP,  6),
        (90,    pk,  I.OPOTION,  P.PHEALING,  5),
        (520,   pk,  I.OPOTION,  P.PRAISELEVEL,  1),  # 40
        (100,   pk,  I.OPOTION,  P.PINCABILITY,  2),
        (50,    pk,  I.OPOTION,  P.PWISDOM,  2),
        (150,   pk,  I.OPOTION,  P.PSTRENGTH,  2),
        (70,    pk,  I.OPOTION,  P.PCHARISMA,  1),
        (30,    pk,  I.OPOTION,  P.PDIZZINESS,  7),
        (200,   pk,  I.OPOTION,  P.PLEARNING,  1),
        (50,    pk,  I.OPOTION,  P.PGOLDDET,  1),
        (80,    pk,  I.OPOTION,  P.PMONSTDET, 1),

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (30,    pk,  I.OPOTION,  P.PFORGETFUL, 3),
        (20,    pk,  I.OPOTION,  P.PWATER, 5),  # 50
        (40,    pk,  I.OPOTION,  P.PBLINDNESS, 3),
        (35,    pk,  I.OPOTION,  P.PCONFUSION, 2),
        (520,   pk,  I.OPOTION,  P.PHEROISM, 1),
        (90,    pk,  I.OPOTION,  P.PSTURDINESS, 2),
        (200,   pk,  I.OPOTION,  P.PGIANTSTR, 2),
        (220,   pk,  I.OPOTION,  P.PFIRERESIST, 4),
        (80,    pk,  I.OPOTION,  P.PTREASURE, 6),
        (370,   pk,  I.OPOTION,  P.PINSTHEAL, 3),
        (50,    pk,  I.OPOTION,  P.PPOISON, 1),
        (150,   pk,  I.OPOTION,  P.PSEEINVIS, 3),  # 60

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (850,   0,    I.OORBOFDRAGON, 0,  0),
        (750,   0,    I.OSPIRITSCARAB,  0,  0),
        (8000,  0,    I.OVORPAL,  0,  0),

        (100,   sk,  I.OSCROLL,  S.SENCHANTARM,  2),
        (125,   sk,  I.OSCROLL,  S.SENCHANTWEAP,  2),
        (60,    sk,  I.OSCROLL,  S.SENLIGHTEN,  4),
        (10,    sk,  I.OSCROLL,  S.SBLANK,  4),
        (100,   sk,  I.OSCROLL,  S.SCREATEMONST,  3),
        (200,   sk,  I.OSCROLL,  S.SCREATEITEM,  2),
        (110,   sk,  I.OSCROLL,  S.SAGGMONST,  1),  # 70
        (500,   sk,  I.OSCROLL,  S.STIMEWARP,  2),
        (200,   sk,  I.OSCROLL,  S.STELEPORT,  2),
        (250,   sk,  I.OSCROLL,  S.SAWARENESS,  4),
        (20,    sk,  I.OSCROLL,  S.SHASTEMONST, 5),
        (30,    sk,  I.OSCROLL,  S.SMONSTHEAL, 3),

        # cost    memory  iven name iven arg   how
        #  gp   pointer    iven[]  ivenarg[]  many
        (340,   sk,  I.OSCROLL,  S.SSPIRITPROT, 1),
        (340,   sk,  I.OSCROLL,  S.SUNDEADPROT, 1),
        (300,   sk,  I.OSCROLL,  S.SSTEALTH, 2),
        (400,   sk,  I.OSCROLL,  S.SMAGICMAP, 2),
        (500,   sk,  I.OSCROLL,  S.SHOLDMONST, 2),  # 80
        (1000,  sk,  I.OSCROLL,  S.SGEMPERFECT, 1),
        (500,   sk,  I.OSCROLL,  S.SSPELLEXT, 1),
        (340,   sk,  I.OSCROLL,  S.SIDENTIFY, 2),
        (220,   sk,  I.OSCROLL,  S.SREMCURSE, 3),
        (3900,  sk,  I.OSCROLL,  S.SANNIHILATE, 0),
        (610,   sk,  I.OSCROLL,  S.SPULVERIZE, 1),
        (3000,  sk,  I.OSCROLL,  S.SLIFEPROT, 0),
        (300,   0,    I.OSPHTALISMAN,   0,  0),
        (150,   0,    I.OWWAND,   0,  0),
        (50,    0,    I.OBRASSLAMP, 0,  0),  # 90
        (9500,  0,    I.OPSTAFF,  0,  0),
        (10000, 0,    I.OLIFEPRESERVER, 0, 0),
    ]
    itm.extend(_itm(*t) for t in table)


# =============================================================================
# Local functions

def write_dnd_store(fp):
    """Write the DnD store inventory data (the number of each item remaining)."""
    _init_itm()
    fp["dnd_qty"] = [itm[i].qty for i in range(DNDSIZE)]


def read_dnd_store(fp):
    """Read the DnD Store inventory (the number of each item remaining)."""
    _init_itm()
    qty = fp["dnd_qty"]
    for i in range(DNDSIZE):
        itm[i].qty = qty[i]


def handsfull():
    """Print the hands full message."""
    ularn_win.Print("\nYou can't carry anything more!")
    ularn_win.nap(2200)


def outofstock():
    """Print the out of stock message."""
    ularn_win.Print("\nSorry, but we are out of that item.")
    ularn_win.nap(2200)


def nogold():
    """Print the insufficient funds message."""
    ularn_win.Print("\nYou don't have enough gold to pay for that!")
    ularn_win.nap(2200)


def dnditem(i):
    """Print item i of the DnD store inventory at its place in the 2 column output.

    It is assumed that items will be displayed in pages of IVENSIZE items.
    """
    _init_itm()
    IVENSIZE = player.IVENSIZE

    if i >= DNDSIZE:
        return

    x = (i & 1) * 40 + 1
    y = ((i % IVENSIZE) >> 1) + 5

    ularn_win.MoveCursor(x, y)
    if itm[i].qty == 0:
        ularn_win.Printf("%39s", "")
        return
    ularn_win.Printf("%c) ", chr((i % IVENSIZE) + ord('a')))
    if itm[i].obj == itm_.OPOTION:
        ularn_win.Print("potion of ")
        ularn_win.Printf("%s", potion.potionname[itm[i].arg][1:])
    elif itm[i].obj == itm_.OSCROLL:
        ularn_win.Print("scroll of ")
        ularn_win.Printf("%s", scroll.scrollname[itm[i].arg][1:])
    else:
        ularn_win.Printf("%s", itm_.objectname[itm[i].obj])
    ularn_win.MoveCursor(x + 31, y)
    ularn_win.Printf("%6ld", itm[i].price * 10)


def dnd_2hed():
    """Print the DnD Store heading text."""
    ularn_win.Print("Welcome to the Ularn Thrift Shoppe.  We stock many items explorers find useful\n")
    ularn_win.Print("in their adventures.  Feel free to browse to your heart's content.\n")
    ularn_win.Print("Also be advised that if you break 'em, you pay for 'em.")


def dnd_hed():
    """Display a page of the DnD Store items, starting at dnditm."""
    for i in range(dnditm, player.IVENSIZE + dnditm):
        dnditem(i)

    ularn_win.MoveCursor(50, 18)
    ularn_win.Print("You have ")


# =============================================================================
# Exported functions

def dndstore():
    """Handle entering the DND store."""
    global dnditm
    _init_itm()
    c = player.c

    dnditm = 0
    ularn_win.nosignal = 1  # disable signals

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    ularn_win.ClearText()

    dnd_2hed()
    if player.outstanding_taxes > 0:
        ularn_win.Print("\n\nThe Ularn Revenue Service has ordered us to not do business with tax evaders.\n")
        ularn_win.UlarnBeep()
        ularn_win.Printf("They have also told us that you owe %d gp in back taxes and, as we must\n",
                         int(player.outstanding_taxes))
        ularn_win.Print("comply with the law, we cannot serve you at this time.  So Sorry.\n")
        ularn_win.Print("\nPress ")
        ularn_win.Standout("escape")
        ularn_win.Print(" to leave: ")

        ularn_win.get_prompt_input("", "\033", 0)

        ularn_win.set_display(ularn_win.DISPLAY_MAP)

        ularn_win.nosignal = 0  # enable signals
        return

    dnd_hed()
    while True:
        ularn_win.MoveCursor(59, 18)
        ularn_win.Printf("%ld gold piece%s", c[player.GOLD], plural(c[player.GOLD]))
        ularn_win.ClearToEOL()
        ularn_win.ClearToEOPage(1, 20)  # erase to eod
        ularn_win.Print("\nEnter your transaction [")
        ularn_win.Standout("space")
        ularn_win.Print(" for more, ")
        ularn_win.Standout("escape")
        ularn_win.Print(" to leave]? ")

        i = ularn_win.get_prompt_input("", "abcdefghijklmnopqrstuvwxyz \033", 1)

        if i == chr(12):
            ularn_win.ClearText()
            dnd_2hed()
            dnd_hed()
        elif i == ESC:
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            ularn_win.nosignal = 0  # enable signals

            return
        elif i == ' ':
            ularn_win.ClearToEOPage(1, 4)
            dnditm += player.IVENSIZE
            if dnditm >= DNDSIZE:
                dnditm = 0
            dnd_hed()
        else:
            # buy something
            ularn_win.Printc(i)  # echo the byte
            idx = ord(i) + dnditm - ord('a')
            if idx >= DNDSIZE:
                outofstock()
            elif itm[idx].qty <= 0:
                outofstock()
            elif player.pocketfull():
                handsfull()
            elif c[player.GOLD] < itm[idx].price * 10:
                nogold()
            else:
                # Player learns this item
                if itm[idx].mem != 0:
                    getattr(player, itm[idx].mem)[itm[idx].arg] = 1

                c[player.GOLD] -= itm[idx].price * 10
                itm[idx].qty -= 1
                player.take(itm[idx].obj, itm[idx].arg)
                if itm[idx].qty == 0:
                    dnditem(idx)
                ularn_win.nap(1001)


# =============================================================================
#
#  #####
# #     #   ####   #       #       ######   ####   ######
# #        #    #  #       #       #       #    #  #
# #        #    #  #       #       #####   #       #####
# #        #    #  #       #       #       #  ###  #
# #     #  #    #  #       #       #       #    #  #
#  #####    ####   ######  ######  ######   ####   ######
#

# =============================================================================
# Local variables

# the list of courses taken and the time required
MAX_COURSES = 8
course = [0, 0, 0, 0, 0, 0, 0, 0]
coursetime = [10, 15, 10, 20, 10, 10, 10, 5]


# =============================================================================
# Local functions

def write_college(fp):
    """Write the college data to the save file."""
    fp["course"] = list(course)


def read_college(fp):
    """Read the college data from the save file."""
    course[:] = list(fp["course"])


def sch_hed():
    """Display the header info for the school."""
    P = ularn_win.Print
    ularn_win.ClearText()

    P("The College of Ularn offers the exciting opportunity of higher education to\n")
    P("all inhabitants of the caves.  Here is the class schedule:\n\n\n")
    P("\t\t    Course Name \t       Time Needed\n\n")

    # line 7 of crt
    if course[0] == 0:
        P("\t\ta)  Fighter's Training I        10 mobuls")
    ularn_win.Printc('\n')
    if course[1] == 0:
        P("\t\tb)  Fighter's Training II       15 mobuls")
    ularn_win.Printc('\n')
    if course[2] == 0:
        P("\t\tc)  Introduction to Wizardry    10 mobuls")
    ularn_win.Printc('\n')
    if course[3] == 0:
        P("\t\td)  Applied Wizardry            20 mobuls")
    ularn_win.Printc('\n')
    if course[4] == 0:
        P("\t\te)  Behavioral Psychology       10 mobuls")
    ularn_win.Printc('\n')
    if course[5] == 0:
        P("\t\tf)  Faith for Today             10 mobuls")
    ularn_win.Printc('\n')
    if course[6] == 0:
        P("\t\tg)  Contemporary Dance          10 mobuls")
    ularn_win.Printc('\n')
    if course[7] == 0:
        P("\t\th)  History of Ularn             5 mobuls")

    P("\n\n\t\tAll courses cost 250 gold pieces.")
    ularn_win.MoveCursor(30, 18)
    P("You are presently carrying ")


# =============================================================================
# Exported functions

def oschool():
    """Handle entering the college of larn."""
    c = player.c

    ularn_win.nosignal = 1  # disable signals

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    sch_hed()

    while True:
        ularn_win.MoveCursor(57, 18)
        ularn_win.Printf("%d gold piece%s.   ", c[player.GOLD], plural(c[player.GOLD]))

        ularn_win.Print("\nWhat is your choice [")
        ularn_win.Standout("escape")
        ularn_win.Print(" to leave] ? ")
        ularn_win.yrepcount = 0
        i = ularn_win.get_prompt_input("", "abcdefgh\033", 1)

        if i == chr(12):
            # Pressed ^R, so redraw
            sch_hed()
            continue
        elif i == ESC:
            # exit
            ularn_win.nosignal = 0
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            return

        ularn_win.Printc(i)
        if c[player.GOLD] < 250:
            nogold()
        else:
            ci = ord(i) - ord('a')
            if course[ci]:
                ularn_win.Print("\nSorry but that class is filled.")
                ularn_win.nap(1000)
            elif i <= 'h':
                c[player.GOLD] -= 250
                time_used = 0
                if i == 'a':
                    c[player.STRENGTH] += 2
                    c[player.CONSTITUTION] += 1
                    ularn_win.Print("\nYou feel stronger!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 7)
                    ularn_win.ClearToEOL()

                elif i == 'b':
                    if course[0] == 0:
                        ularn_win.Print("\nSorry but this class has a prerequisite of Fighter's Training I")
                        ularn_win.ClearToEOL()
                        c[player.GOLD] += 250
                        time_used = -10000
                    else:
                        ularn_win.Print("\nYou feel much stronger!")
                        ularn_win.ClearToEOL()
                        ularn_win.MoveCursor(16, 8)
                        ularn_win.ClearToEOL()
                        c[player.STRENGTH] += 2
                        c[player.CONSTITUTION] += 2

                elif i == 'c':
                    c[player.INTELLIGENCE] += 2
                    ularn_win.Print("\nThe task before you now seems more attainable!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 9)
                    ularn_win.ClearToEOL()

                elif i == 'd':
                    if course[2] == 0:
                        ularn_win.Print("\nSorry but this class has a prerequisite of Introduction to Wizardry")
                        ularn_win.ClearToEOL()
                        c[player.GOLD] += 250
                        time_used = -10000
                    else:
                        ularn_win.Print("\nThe task before you now seems very attainable!")
                        ularn_win.ClearToEOL()
                        ularn_win.MoveCursor(16, 10)
                        ularn_win.ClearToEOL()
                        c[player.INTELLIGENCE] += 2

                elif i == 'e':
                    c[player.CHARISMA] += 3
                    ularn_win.Print("\nYou now feel like a born leader!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 11)
                    ularn_win.ClearToEOL()

                elif i == 'f':
                    c[player.WISDOM] += 2
                    ularn_win.Print("\nYou now feel more confident that you can find the potion in time!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 12)
                    ularn_win.ClearToEOL()

                elif i == 'g':
                    c[player.DEXTERITY] += 3
                    ularn_win.Print("\nYou feel like dancing!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 13)
                    ularn_win.ClearToEOL()

                elif i == 'h':
                    c[player.INTELLIGENCE] += 1
                    ularn_win.Print("\nWow! e = mc^2!")
                    ularn_win.ClearToEOL()
                    ularn_win.MoveCursor(16, 14)
                    ularn_win.ClearToEOL()

                time_used += coursetime[ci] * 100

                if time_used > 0:
                    player.gtime += time_used

                    # remember that he has taken that course
                    course[ci] += 1

                    # he regenerated
                    c[player.HP] = c[player.HPMAX]
                    c[player.SPELLS] = c[player.SPELLMAX]

                    # cure blindness too!
                    if c[player.BLINDCOUNT]:
                        c[player.BLINDCOUNT] = 1

                    # end confusion
                    if c[player.CONFUSE]:
                        c[player.CONFUSE] = 1

                    # adjust parameters for time change
                    player.adjusttime(time_used)
                ularn_win.nap(1000)


# =============================================================================
#
# ######                                  #
# #     #    ##    #    #  #    #         #          ##    #####   #    #
# #     #   #  #   ##   #  #   #          #         #  #   #    #  ##   #
# ######   #    #  # #  #  ####           #        #    #  #    #  # #  #
# #     #  ######  #  # #  #  #           #        ######  #####   #  # #
# #     #  #    #  #   ##  #   #          #        #    #  #   #   #   ##
# ######   #    #  #    #  #    #    Of   #######  #    #  #    #  #    #
#

# =============================================================================
# Local variables

# limit of 1 million gold pieces in bank
BANKLIMIT = 1000000

# last time he was in bank
lasttime = 0

# the reference to screen location for each gem
gemorder = [0] * 26  # IVENSIZE
# the appraisal of the gems
gemvalue = [0] * 26  # IVENSIZE


# =============================================================================
# Local functions

def write_bank(fp):
    """Write the bank data to the save file."""
    fp["lasttime"] = lasttime


def read_bank(fp):
    """Read the bank data from the save file."""
    global lasttime
    lasttime = fp["lasttime"]


def appraise(eye, order):
    """Appraise the eye of larn (inventory slot eye, display position order) and offer to buy it."""
    c = player.c

    ularn_win.MoveCursor(1, 20)
    ularn_win.Printf("I see you have %s", itm_.objectname[itm_.OLARNEYE])
    ularn_win.Print("  I must commend you.  I didn't think\nyou could get it.")
    ularn_win.Print("  Shall I appraise it for you? ")
    ularn_win.yrepcount = 0
    if ularn_ask.getyn() == 'y':
        ularn_win.Print("yes.\n  Just one moment please...")
        ularn_win.nap(1000)
        amt = 250000 - cdiv(player.gtime * 7, 100) * 100

        if amt < 50000:
            amt = 50000

        ularn_win.ClearToEOPage(1, 20)
        ularn_win.MoveCursor(1, 20)
        ularn_win.Printf("\nThis is an excellent stone.\n")
        ularn_win.Printf("It is worth %d gold pieces to us\n", amt)
        ularn_win.Print("Would you like to sell it? ")
        ularn_win.yrepcount = 0

        if ularn_ask.getyn() == 'y':
            ularn_win.Print("yes")
            c[player.GOLD] += amt
            player.iven[eye] = itm_.ONOTHING
            c[player.EYEOFLARN] = 0

            ularn_win.MoveCursor((order % 2) * 40 + 1, (order >> 1) + 4)
            ularn_win.Printf("%39s", "")

            ularn_win.MoveCursor(40, 17)
            ularn_win.Printf("%8d", c[player.BANKACCOUNT])
            ularn_win.MoveCursor(49, 18)
            ularn_win.Printf("%8d", c[player.GOLD])
        else:
            ularn_win.Print("no")
            ularn_win.Print("\nIt is, of course, your privilege to keep the stone.")
            ularn_win.nap(500)
    else:
        ularn_win.Print("no.")
        ularn_win.nap(500)

    ularn_win.ClearToEOPage(1, 20)
    ularn_win.MoveCursor(1, 20)


def obanksub():
    """Main processing for the bank."""
    c = player.c
    iven = player.iven
    ivenarg = player.ivenarg
    IVENSIZE = player.IVENSIZE
    eye = 0

    ointerest()  # credit any needed interest

    if dungeon.level == 8:
        c[player.TELEFLAG] = 0

    k = 0
    for i in range(IVENSIZE):
        if iven[i] in (itm_.OLARNEYE, itm_.ODIAMOND, itm_.OEMERALD, itm_.ORUBY, itm_.OSAPPHIRE):
            if iven[i] == itm_.OLARNEYE:
                eye = i
                gemvalue[i] = 250000 - cdiv(player.gtime * 7, 100) * 100
                if gemvalue[i] < 50000:
                    gemvalue[i] = 50000
            else:
                gemvalue[i] = ivenarg[i] * 100
            gemorder[i] = k
            ularn_win.MoveCursor((k % 2) * 40 + 1, (k >> 1) + 4)
            ularn_win.Printf("%c) %s", chr(i + ord('a')), itm_.objectname[iven[i]])
            ularn_win.MoveCursor((k % 2) * 40 + 33, (k >> 1) + 4)
            ularn_win.Printf("%5d", gemvalue[i])
            k += 1
        else:
            gemvalue[i] = 0

    ularn_win.MoveCursor(31, 17)
    ularn_win.Printf("You have %8d gold piece%s in the bank.",
                     c[player.BANKACCOUNT],
                     plural(c[player.BANKACCOUNT]))

    ularn_win.MoveCursor(40, 18)
    ularn_win.Printf("You have %8d gold piece%s", c[player.GOLD], plural(c[player.GOLD]))
    if c[player.BANKACCOUNT] + c[player.GOLD] >= 500000:
        ularn_win.Print("\nNote:  Only deposits under 1,000,000gp can earn interest.")

    if eye:
        appraise(eye, gemorder[eye])

    while True:
        ularn_win.ClearToEOPage(1, 20)
        ularn_win.MoveCursor(1, 20)
        ularn_win.Print("\nYour wish? [(")
        ularn_win.Standout("d")
        ularn_win.Print(") deposit, (")
        ularn_win.Standout("w")
        ularn_win.Print(") withdraw, (")
        ularn_win.Standout("s")
        ularn_win.Print(") sell a stone, or ")
        ularn_win.Standout("escape")
        ularn_win.Print("]  ")
        ularn_win.yrepcount = 0

        i = ularn_win.get_prompt_input("", "dws\033", 1)

        if i == 'd':
            ularn_win.Print("deposit\nHow much? ")
            amt = ularn_win.get_num_input(c[player.GOLD])
            if amt < 0:
                amt = 0
            elif amt > c[player.GOLD]:
                ularn_win.Print("\n  You don't have that much.")
                amt = 0
                ularn_win.nap(2000)

            # Deposit the money
            c[player.GOLD] -= amt
            c[player.BANKACCOUNT] += amt

        elif i == 'w':
            ularn_win.Print("withdraw\nHow much? ")
            amt = ularn_win.get_num_input(c[player.BANKACCOUNT])
            if amt < 0:
                amt = 0
            elif amt > c[player.BANKACCOUNT]:
                ularn_win.Print("\n  You don't have that much in the bank!")
                amt = 0
                ularn_win.nap(2000)

            # Withdraw the money
            c[player.GOLD] += amt
            c[player.BANKACCOUNT] -= amt

        elif i == 's':
            i = ularn_win.get_prompt_input("sell\nWhich stone would you like to sell? ",
                                           "abcdefghijklmnopqrstuvwxys*", 1)

            if i == '*':
                # sell all gems
                for i in range(IVENSIZE):
                    if gemvalue[i]:
                        if iven[i] == itm_.OLARNEYE:
                            c[player.EYEOFLARN] = 0
                        c[player.GOLD] += gemvalue[i]
                        iven[i] = itm_.ONOTHING
                        gemvalue[i] = 0
                        k = gemorder[i]
                        ularn_win.MoveCursor((k % 2) * 40 + 1, (k >> 1) + 4)
                        ularn_win.Printf("%39s", "")
            else:
                i = ord(i) - ord('a')
                if gemvalue[i] == 0:
                    ularn_win.Printf("\nItem %c is not a gemstone!", chr(i + ord('a')))
                    ularn_win.nap(2000)
                else:
                    if iven[i] == itm_.OLARNEYE:
                        c[player.EYEOFLARN] = 0
                    c[player.GOLD] += gemvalue[i]
                    iven[i] = itm_.ONOTHING
                    gemvalue[i] = 0
                    k = gemorder[i]
                    ularn_win.MoveCursor((k % 2) * 40 + 1, (k >> 1) + 4)
                    ularn_win.Printf("%39s", "")

        elif i == ESC:
            return

        ularn_win.MoveCursor(40, 17)
        ularn_win.Printf("%8d", c[player.BANKACCOUNT])
        ularn_win.MoveCursor(49, 18)
        ularn_win.Printf("%8d", c[player.GOLD])


def banktitle(str_):
    """Display the title for this branch of the bank and then perform the bank processing."""
    ularn_win.nosignal = 1  # disable signals
    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()

    ularn_win.Print(str_)
    if player.outstanding_taxes > 0:
        ularn_win.Print("\n\nThe Ularn Revenue Service has ordered that your account be frozen until all\n")
        ularn_win.UlarnBeep()
        ularn_win.Printf("levied taxes have been paid.  They have also told us that you owe %d gp in\n",
                         int(player.outstanding_taxes))
        ularn_win.Print("taxes and we must comply with them. We cannot serve you at this time.  Sorry.\n")
        ularn_win.Print("We suggest you go to the LRS office and pay your taxes.\n")

        ularn_win.Print("\nPress ")
        ularn_win.Standout("escape")
        ularn_win.Print(" to leave: ")

        ularn_win.get_prompt_input("", "\033", 0)

        ularn_win.set_display(ularn_win.DISPLAY_MAP)

        ularn_win.nosignal = 0  # enable signals

        return
    ularn_win.Print("\n\n\tGemstone\t      Appraisal\t\tGemstone\t      Appraisal")

    obanksub()

    ularn_win.nosignal = 0  # enable signals
    ularn_win.set_display(ularn_win.DISPLAY_MAP)


# =============================================================================
# Exported functions

def obank():
    """Handle entering the bank of larn."""
    banktitle("    Welcome to the First National Bank of Ularn.")


def obank2():
    """Handle entering the 8th branch of the bank of larn."""
    banktitle("Welcome to the 8th-level branch office of the First National Bank of Ularn.")


def ointerest():
    """Calculate interest on bank accounts."""
    global lasttime
    c = player.c

    if c[player.BANKACCOUNT] < 0:
        c[player.BANKACCOUNT] = 0
    elif c[player.BANKACCOUNT] > 0 and c[player.BANKACCOUNT] < BANKLIMIT:
        i = cdiv(player.gtime - lasttime, 100)  # mobuls elapsed since last here
        while i > 0 and c[player.BANKACCOUNT] < BANKLIMIT:
            i -= 1
            # at 1 mobul ~=~ 1 hour, is 10 % a year
            c[player.BANKACCOUNT] += cdiv(c[player.BANKACCOUNT], 877)
    lasttime = cdiv(player.gtime, 100) * 100


# =============================================================================
#
# #######
#    #     #####     ##    #####      #    #    #   ####
#    #     #    #   #  #   #    #     #    ##   #  #    #
#    #     #    #  #    #  #    #     #    # #  #  #
#    #     #####   ######  #    #     #    #  # #  #  ###
#    #     #   #   #    #  #    #     #    #   ##  #    #
#    #     #    #  #    #  #####      #    #    #   ####

# =============================================================================
# Local functions

def otradhead():
    """Print the trading post heading text."""
    ularn_win.ClearText()
    ularn_win.Print("Welcome to the Ularn Trading Post.  We buy items that explorers no longer find\n")
    ularn_win.Print("useful.  Since the condition of the items you bring in is not certain,\n")
    ularn_win.Print("and we incur great expense in reconditioning the items, we usually pay\n")
    ularn_win.Print("only 20% of their value were they to be new.  If the items are badly\n")
    ularn_win.Print("damaged, we will pay only 10% of their new value.\n\n")


def cnsitm():
    """Print the 'can't sell unidentified items' message."""
    ularn_win.Print("\nSorry, we can't accept unidentified objects.")


# =============================================================================
# Exported functions

def item_value(it, itarg):
    """Value of an item as per the trading post (-1 if not in the price list)."""
    _init_itm()

    value = -1

    if it in (itm_.ODIAMOND, itm_.ORUBY, itm_.OEMERALD, itm_.OSAPPHIRE):
        value = 20 * itarg
    else:
        found_item = 0
        j = 0
        while j < DNDSIZE and not found_item:
            if itm[j].obj == it:
                if itm[j].obj == itm_.OSCROLL or itm[j].obj == itm_.OPOTION:
                    value = 2 * itm[j + itarg].price
                else:
                    value = itm[j].price

                    arg = itarg

                    if arg >= 0:
                        value *= 2

                    while arg != 0 and value < 500000:
                        if arg > 0:
                            # appreciate if a +n object
                            value = cdiv(14 * (value + 67), 10)
                            arg -= 1
                        else:
                            # depreciate -n object
                            value = cdiv(value * 10, 14)
                            arg += 1

                # always offer at least 1 gp
                if value == 0:
                    value = 1

                found_item = 1

            j += 1

    return value


def otradepost():
    """Handle entering the trading post."""
    global dnditm
    c = player.c

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()

    ularn_win.yrepcount = 0
    dnditm = 0
    otradhead()

    while True:
        ularn_win.Print("\nWhat item do you want to sell to us [")
        ularn_win.Standout("*")
        ularn_win.Print(" for list, or ")
        ularn_win.Standout("escape")
        ularn_win.Print("] ? ")
        ans = ularn_win.get_prompt_input("", "abcdefghijklmnopqrstuvwxyz.*\033", 1)

        if ans == ESC:
            player.recalc()
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            return
        elif ans == '*':
            ularn_win.ClearText()
            show.qshowstr()
            otradhead()
        elif 'a' <= ans <= 'z':
            no_sell_flag = 0

            idx = ord(ans) - ord('a')

            it = player.iven[idx]
            itarg = player.ivenarg[idx]

            if it == itm_.OSCROLL:
                if not player.scrollknown[itarg]:
                    # can't sell unidentified item
                    no_sell_flag = 1
                    cnsitm()
            elif it == itm_.OPOTION:
                if not player.potionknown[itarg]:
                    # can't sell unidentified item
                    no_sell_flag = 1
                    cnsitm()
            elif it == itm_.OLANCE and player.ramboflag:
                no_sell_flag = 1
                ularn_win.Print("\nYou don't *really* want to sell that, now do you?")

            if not no_sell_flag:
                if it == itm_.ONOTHING:
                    ularn_win.Printf("\nYou don't have item %c!", ans)
                else:
                    value = item_value(it, itarg)

                    if value >= 0:
                        # show what the item was
                        show.show3(idx)

                        ularn_win.Printf("\nItem (%c) is worth %d gold piece%s to us.  Do you want to sell it? ",
                                         ans, value, plural(value))
                        if ularn_ask.getyn() == 'y':
                            ularn_win.Print("yes.\n")
                            c[player.GOLD] += value
                            if c[player.WEAR] == idx:
                                c[player.WEAR] = -1
                            if c[player.WIELD] == idx:
                                c[player.WIELD] = -1
                            if c[player.SHIELD] == idx:
                                c[player.SHIELD] = -1
                            player.adjustcvalues(it, itarg)
                            player.iven[idx] = itm_.ONOTHING
                        else:
                            ularn_win.Print("no thanks.\n")
                    else:
                        # negative value indicates that the item is not in the
                        # price list
                        ularn_win.Print("\nSo sorry but we are not authorized to accept that item.")


# =============================================================================
#
# #       ######   #####
# #       #     # #     #
# #       #     # #
# #       ######   #####
# #       #   #         #
# #       #    #  #     #
# ####### #     #  #####
#

# =============================================================================
# Exported functions

def olrs():
    """Handle entering the Larn Revenue Service."""
    c = player.c

    ularn_win.nosignal = 1  # disable signals
    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()

    ularn_win.MoveCursor(1, 4)

    if player.outstanding_taxes:
        if player.cheat:
            ularn_win.Print("Sorry but it seems you are trying to pay off your taxes by cheating!")

            ularn_win.Print("\n\n\tpress [escape] to exit the office.")
            ularn_win.get_prompt_input("", "\033", 0)

            ularn_win.nosignal = 0  # enable signals
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            return

    ularn_win.Print("Welcome to the Ularn Revenue Service district office.  How can we help you?")
    while True:
        ularn_win.MoveCursor(1, 6)
        if player.outstanding_taxes > 0:
            ularn_win.Printf("You presently owe %d gp in taxes.  ", int(player.outstanding_taxes))
        else:
            ularn_win.Print("You do not owe us any taxes.           ")

        ularn_win.MoveCursor(1, 8)
        if c[player.GOLD] > 0:
            ularn_win.Printf("You have %6d gp.    ", c[player.GOLD])
        else:
            ularn_win.Print("You have no gold pieces.  ")

        ularn_win.MoveCursor(1, 20)
        ularn_win.Print("\n\nYour wish? [(")
        ularn_win.Standout("p")
        ularn_win.Print(") pay taxes, or ")
        ularn_win.Standout("escape")
        ularn_win.Print("]  ")

        ularn_win.ClearToEOPage(40, 22)

        ularn_win.yrepcount = 0
        i = ularn_win.get_prompt_input("", "p\033", 1)

        if i == 'p':
            ularn_win.Print("pay taxes.\nHow much? ")
            amt = ularn_win.get_num_input(c[player.GOLD])
            if amt < 0:
                amt = 0
            elif amt > c[player.GOLD]:
                ularn_win.Print("  You don't have that much.")
                amt = 0

            c[player.GOLD] -= scores.paytaxes(amt)

            ularn_win.nap(500)

        elif i == ESC:
            ularn_win.nosignal = 0  # enable signals
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            return


# =============================================================================
#
# #     #         ######                            ###
# ##   ##   ####  #     #   ####   #####   ######   ###     ####
# # # # #  #    # #     #  #    #  #    #  #         #     #
# #  #  #  #      #     #  #    #  #    #  #####    #       ####
# #     #  #      #     #  #    #  #####   #                    #
# #     #  #    # #     #  #    #  #       #               #    #
# #     #   ####  ######    ####   #       ######           ####
#

# =============================================================================
# Local variables

# DrugType
DOPE_SPEED = 0
DOPE_ACID = 1
DOPE_HASH = 2
DOPE_MUSHROOMS = 3
DOPE_COKE = 4
DOPE_COUNT = 5


class DopeDataType:
    def __init__(self, Name, Price, Line, Item):
        self.Name = Name    # The name of this dope
        self.Price = Price  # The selling price
        self.Line = Line    # The display line for showing in MacDope's inventory
        self.Item = Item    # The item id for the drug


# Flags for what dope has been sold
#  0 = Dealer has in stock
#  1 = Sold out
drug = [0, 0, 0, 0, 0]

# filled on first use (see _init_dope)
DopeData = []


def _init_dope():
    """Build the DopeData table (deferred so that itm is loaded)."""
    if DopeData:
        return
    DopeData.extend([
        DopeDataType("Killer Speed",    100,  8, itm_.OSPEED),
        DopeDataType("Groovy Acid",     250,  9, itm_.OACID),
        DopeDataType("Moster Hash",     500, 10, itm_.OHASH),
        DopeDataType("Trippy Shrooms", 1000, 11, itm_.OSHROOMS),
        DopeDataType("Cool Coke",      5000, 12, itm_.OCOKE),
    ])


# =============================================================================
# Local functions

def write_pad(fp):
    """Write the data for McDope's pad to the save file."""
    fp["drug"] = list(drug)


def read_pad(fp):
    """Read the data for McDope's pad from the save file."""
    drug[:] = list(fp["drug"])


def nomore():
    """Print the out of stock message for McDope's."""
    ularn_win.Print("\nSorry man, I ain't got no more of that stuff.")
    ularn_win.nap(2200)


def nocash():
    """Print the insufficient funds message for McDope's."""
    ularn_win.Print("\nWhattaya trying to pull on me? You aint got the cash!")
    ularn_win.nap(1200)


def pad_hd():
    """Display the header info for Dealer McDope's pad."""
    _init_dope()
    ularn_win.ClearText()
    ularn_win.Print("Hey man, welcome to Dealer McDope's Pad!  I gots the some of the finest dope\n")
    ularn_win.Print("you'll find anywhere in Ularn -- check it out...\n\n\n")
    ularn_win.Print("\t\t    The Stash\t\t\tThe Cash\n\n")

    for Dope in range(DOPE_COUNT):
        if drug[Dope] == 0:
            ularn_win.MoveCursor(1, DopeData[Dope].Line)
            ularn_win.Printf("\t\t%c)  %s", chr(ord('a') + Dope), DopeData[Dope].Name)
            ularn_win.MoveCursor(49, DopeData[Dope].Line)
            ularn_win.Printf("%d bucks", DopeData[Dope].Price)

    ularn_win.MoveCursor(30, 18)
    ularn_win.Print("Looks like you got about ")


def snag(itm):
    """Get item itm from McDope's.

    Returns 0 if there is no free inventory slot for the item, 1 if the
    player could take the item.
    """
    ularn_win.ClearToEOPage(1, 20)
    if player.pocketfull():
        ularn_win.Print("\nHey, you can't carry any more.")
        return 0
    else:
        ularn_win.Print("\nOk, here ya go.")
        player.take(itm, 0)

        return 1


# =============================================================================
# Exported functions

def opad():
    """Handle entering dealer McDope's pad."""
    _init_dope()
    c = player.c

    ularn_win.nosignal = 1  # disable signals

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    pad_hd()

    while True:
        ularn_win.MoveCursor(57, 18)
        ularn_win.Printf("%d buck%s on you.   ", c[player.GOLD], plural(c[player.GOLD]))

        ularn_win.Print("\nSo, whaddya want [")
        ularn_win.Standout("escape")
        ularn_win.Print(" to split] ? ")
        ularn_win.yrepcount = 0

        i = ularn_win.get_prompt_input("", "abcde\033", 1)

        if i == chr(12):
            # Redraw
            pad_hd()
            continue
        elif i == ESC:
            ularn_win.nosignal = 0
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            return
        ularn_win.Printc(i)

        if 'a' <= i < chr(ord('a') + DOPE_COUNT):
            Dope = ord(i) - ord('a')

            if drug[Dope]:
                # None of that dope left
                nomore()
            else:
                if c[player.GOLD] < DopeData[Dope].Price:
                    # Player can't afford this
                    nocash()
                elif snag(DopeData[Dope].Item):
                    # Player can afford and has taken, so pay for it.
                    c[player.GOLD] -= DopeData[Dope].Price

                    # Remove line from the screen for this dope
                    ularn_win.MoveCursor(16, DopeData[Dope].Line)
                    ularn_win.ClearToEOL()

                    # Note tht this drug has been bought
                    drug[Dope] += 1
                    ularn_win.nap(1000)


# =============================================================================
#
# #     #
# #     #   ####   #    #  ######
# #     #  #    #  ##  ##  #
# #######  #    #  # ## #  #####
# #     #  #    #  #    #  #
# #     #  #    #  #    #  #
# #     #   ####   #    #  ######
#

# =============================================================================
# Exported functions

def ohome():
    """Handle the player returning home."""
    TIMELIMIT = ularn_game.TIMELIMIT

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    ularn_win.nosignal = 1  # disable signals
    for i in range(player.IVENSIZE):
        # remove the potion of cure dianthroritis from inventory
        if player.iven[i] == itm_.OPOTION:
            if player.ivenarg[i] == potion.PCUREDIANTH:
                player.iven[i] = itm_.ONOTHING
                ularn_win.ClearText()

                ularn_win.Print("Congratulations.  You found the potion of cure "
                                "dianthroritis!\n")
                ularn_win.Print("\nFrankly, No one thought you could do it.")
                ularn_win.Print("  Boy!  Did you surprise them!\n")
                ularn_win.nap(1000)
                if player.gtime > TIMELIMIT:
                    ularn_win.Print("\nHowever... the doctor has the sad duty to "
                                    "inform you that your daughter has\n")
                    ularn_win.Print("died! You didn't make it in time.  In your agony, "
                                    "you kill the doctor,\nyour ")
                    if player.sex == 1:
                        ularn_win.Print("wife")
                    else:
                        ularn_win.Print("husband")
                    ularn_win.Print(" and yourself!  Too bad...\n")
                    ularn_win.nap(5000)
                    scores.died(scores.DIED_KILLED_FAMILY, 0)
                else:
                    ularn_win.Print("\nThe doctor is now administering the potion and, "
                                    "in a few moments,\n")
                    ularn_win.Print("your daughter should be well on her way to "
                                    "recovery.\n")
                    ularn_win.nap(6000)
                    ularn_win.Print("\nThe potion is.")
                    ularn_win.nap(1000)
                    ularn_win.Print(".")
                    ularn_win.nap(1000)
                    ularn_win.Print(".")
                    ularn_win.nap(1000)
                    ularn_win.Print(" working!  The doctor thinks that\n")
                    ularn_win.Print("your daughter will recover in a few days.  "
                                    "Congratulations!")
                    ularn_win.UlarnBeep()
                    ularn_win.nap(5000)
                    scores.died(scores.DIED_WINNER, 0)

    while True:
        ularn_win.ClearText()
        ularn_win.Printf("Welcome home %s.", ularn_game.logname)
        ularn_win.Print("  Latest word from the doctor is not good.\n")

        if player.gtime > TIMELIMIT:
            ularn_win.Print("\nThe doctor has the sad duty to inform you that your "
                            "daughter has died!\n")
            ularn_win.Print("You didn't make it in time.")
            ularn_win.Print("In your agony, you kill the doctor,\nyour ")
            if player.sex == 1:
                ularn_win.Print("wife")
            else:
                ularn_win.Print("husband")
            ularn_win.Print(" and yourself!  Too bad...")
            ularn_win.nap(5000)
            scores.died(scores.DIED_KILLED_FAMILY, 0)

        ularn_win.Print("\nThe diagnosis is confirmed as dianthroritis.  "
                        "He guesses that\n")
        ularn_win.Printf("your daughter has only %d mobuls left in this world.  "
                         "It's up to you,\n", cdiv(TIMELIMIT - player.gtime + 99, 100))
        ularn_win.Printf("%s, to find the only hope for your daughter, the very rare\n",
                         ularn_game.logname)
        ularn_win.Print("potion of cure dianthroritis.  It is rumored that only deep "
                        "in the\n")
        ularn_win.Print("depths of the caves can this potion be found.\n\n\n")
        ularn_win.Print("\n     ----- press ")
        ularn_win.Standout("return")
        ularn_win.Print(" to continue, ")
        ularn_win.Standout("escape")
        ularn_win.Print(" to leave ----- ")

        i = ularn_win.get_prompt_input("", "\033\015", 0)

        if i == ESC:
            ularn_win.set_display(ularn_win.DISPLAY_MAP)

            ularn_win.nosignal = 0  # enable signals

            return


def write_store(fp):
    """Write all shop data to the save file.

    fp is either a dict (filled with the shop data) or a binary file object
    (the shop data dict is written to it with pickle.dump()).
    """
    if isinstance(fp, dict):
        d = fp
    else:
        d = {}
    write_dnd_store(d)
    write_college(d)
    write_bank(d)
    write_pad(d)
    if d is not fp:
        pickle.dump(d, fp)


def read_store(fp):
    """Read all shop data from the save file (dict or binary file, see write_store)."""
    if isinstance(fp, dict):
        d = fp
    else:
        d = pickle.load(fp)
    read_dnd_store(d)
    read_college(d)
    read_bank(d)
    read_pad(d)
