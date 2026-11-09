"""Potions (port of potion.c and potion.h).

Exported variables:
  potionname  : The name of each potion

Exported functions:
  newpotion   : create a new potion with the required probabilities
  quaffpotion : process quaffing a potion.
"""

from .header import *

# ------------------------------------------------------------------ potion.h
# (Defined before importing other pyularn modules so that modules importing
#  this one circularly can still see the constants.)

MAXPOTION = 35  # maximum number of potions that are possible

# *** Potions ***
PSLEEP = 0
PHEALING = 1
PRAISELEVEL = 2
PINCABILITY = 3
PWISDOM = 4
PSTRENGTH = 5
PCHARISMA = 6
PDIZZINESS = 7
PLEARNING = 8
PGOLDDET = 9
PMONSTDET = 10
PFORGETFUL = 11
PWATER = 12
PBLINDNESS = 13
PCONFUSION = 14
PHEROISM = 15
PSTURDINESS = 16
PGIANTSTR = 17
PFIRERESIST = 18
PTREASURE = 19
PINSTHEAL = 20
PCUREDIANTH = 21
PPOISON = 22
PSEEINVIS = 23
P_MAX = 23  # Greatest defined potion number

# The amount to boost ability scores for a potion of heroism
PHEROISM_BOOST = 11

# The amount to boos strength for apotion of giant strength
PGIANTSTR_BOOST = 21

# ------------------------------------------------------------------ Exported variables

# name array for magic potions
potionname = [
    " sleep",
    " healing",
    " raise level",
    " increase ability",
    " wisdom",
    " strength",
    " raise charisma",
    " dizziness",
    " learning",
    " gold detection",
    " monster detection",
    " forgetfulness",
    " water",
    " blindness",
    " confusion",
    " heroism",
    " sturdiness",
    " giant strength",
    " fire resistance",
    " treasure finding",
    " instant healing",
    " cure dianthroritis",
    " poison",
    " see invisible",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
    "  ",
]

# ------------------------------------------------------------------ Local variables

# Array to return a potion number created with appropriate probability
# of occurrence.
# Each potion appears in this array a number of times proportionate to
# its probability of occurence.

POTION_PROB_SIZE = 41

potprob = [
    PSLEEP, PSLEEP,
    PHEALING, PHEALING, PHEALING,
    PRAISELEVEL,
    PINCABILITY, PINCABILITY,
    PWISDOM, PWISDOM,
    PSTRENGTH, PSTRENGTH,
    PCHARISMA, PCHARISMA,
    PDIZZINESS, PDIZZINESS,
    PLEARNING,
    PGOLDDET, PGOLDDET, PGOLDDET,
    PMONSTDET, PMONSTDET, PMONSTDET,
    PFORGETFUL, PFORGETFUL,
    PWATER, PWATER,
    PBLINDNESS,
    PCONFUSION,
    PHEROISM,
    PSTURDINESS,
    PGIANTSTR,
    PFIRERESIST,
    PTREASURE, PTREASURE,
    PINSTHEAL, PINSTHEAL,
    # No Cure Dianthroritis
    PPOISON, PPOISON,
    PSEEINVIS, PSEEINVIS,
]

from . import player, monster, dungeon, itm, ularn_win  # noqa: E402


# ------------------------------------------------------------------ Exported functions

def newpotion():
    """Return a potion # created with probability of occurrence."""
    return potprob[rund(POTION_PROB_SIZE)]


def quaffpotion(pot):
    """Handle the effects of drinking a potion."""
    c = player.c
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    # check for within bounds
    if pot < 0 or pot >= MAXPOTION:
        return

    if player.potionknown[pot] == 0:
        player.potionknown[pot] = 1
    ularn_win.Printf("\nYou drink a potion of %s.", potionname[pot][1:])

    # In the switch, if no status/attr changes then use return,
    # else use break to get the UpdateStatusAndEffects call.

    if pot == PSLEEP:
        ularn_win.Print("\n  You fall asleep...")
        i = rnd(11) - (c[player.CONSTITUTION] >> 2) + 2
        i -= 1
        while i > 0:
            monster.parse2()
            ularn_win.nap(1000)
            i -= 1

        ularn_win.Print("\n.. you wake up.")
        return

    elif pot == PHEALING:
        ularn_win.Print("\n  You feel better.")
        if c[player.HP] == c[player.HPMAX]:
            # Already fully healed, so increase max hp
            player.raisemhp(1)
        else:
            c[player.HP] += rnd(20) + 20 + c[player.LEVEL]
            if c[player.HP] > c[player.HPMAX]:
                c[player.HP] = c[player.HPMAX]

    elif pot == PRAISELEVEL:
        ularn_win.Print("\n  You feel much more skillful!")
        player.raiselevel()
        player.raisemhp(1)

    elif pot == PINCABILITY:
        ularn_win.Print("\n  You feel strange for a moment.")
        i = player.ABILITY_FIRST + rund(player.ABILITY_COUNT)
        c[i] += 1

    elif pot == PWISDOM:
        ularn_win.Print("\n  You feel more self-confident!")
        c[player.WISDOM] += rnd(2)

    elif pot == PSTRENGTH:
        ularn_win.Print("\n  Wow!  You feel great!")
        if c[player.STRENGTH] < 12:
            c[player.STRENGTH] = 12
        else:
            c[player.STRENGTH] += 1

    elif pot == PCHARISMA:
        ularn_win.Print("\n  You feel charismatic!")
        c[player.CHARISMA] += 1

    elif pot == PDIZZINESS:
        ularn_win.Print("\n  You become dizzy!")
        c[player.STRENGTH] -= 1
        if c[player.STRENGTH] < 3:
            c[player.STRENGTH] = 3

    elif pot == PLEARNING:
        ularn_win.Print("\n  You feel clever!")
        c[player.INTELLIGENCE] += 1

    elif pot == PGOLDDET:
        ularn_win.Print("\n  You feel greedy...")
        ularn_win.nap(2000)

        for i in range(MAXY):
            for j in range(MAXX):
                if (dungeon.item[j][i] == itm.OGOLDPILE) or (dungeon.item[j][i] == itm.OMAXGOLD):
                    ularn_win.show1cell(j, i)
        ularn_win.showplayer()
        return

    elif pot == PMONSTDET:
        for i in range(MAXY):
            for j in range(MAXX):
                if dungeon.mitem[j][i].mon:
                    ularn_win.show1cell(j, i)
        return

    elif pot == PFORGETFUL:
        ularn_win.Print("\n  You stagger for a moment...")

        for i in range(MAXY):
            for j in range(MAXX):
                dungeon.know[j][i] = itm.OUNKNOWN
        ularn_win.nap(2000)
        ularn_win.draws(0, MAXX, 0, MAXY)
        return

    elif pot == PWATER:
        return

    elif pot == PBLINDNESS:
        ularn_win.Print("\n  You can't see anything!")
        c[player.BLINDCOUNT] += 250  # dang, that's a long time.
        # erase the character, too!

        ularn_win.showplayer()
        return

    elif pot == PCONFUSION:
        ularn_win.Print("\n  You feel confused.")
        c[player.CONFUSE] += 20 + rnd(9)
        return

    elif pot == PHEROISM:
        ularn_win.Print("\n  WOW!  You feel fantastic!")
        if c[player.HERO] == 0:
            for i in range(player.ABILITY_FIRST, player.ABILITY_LAST + 1):
                c[i] += PHEROISM_BOOST
        c[player.HERO] += 250

    elif pot == PSTURDINESS:
        ularn_win.Print("\n  You feel healthier!")
        c[player.CONSTITUTION] += 1

    elif pot == PGIANTSTR:
        ularn_win.Print("\n  You now have incredible bulging muscles!")
        if c[player.GIANTSTR] == 0:
            c[player.STREXTRA] += PGIANTSTR_BOOST
        c[player.GIANTSTR] += 700

    elif pot == PFIRERESIST:
        ularn_win.Print("\n  You feel a chill run up your spine!")
        c[player.FIRERESISTANCE] += 1000

    elif pot == PTREASURE:
        ularn_win.Print("\n  You feel greedy...")
        ularn_win.nap(2000)
        for i in range(MAXY):
            for j in range(MAXX):
                k = dungeon.item[j][i]
                if k in (itm.ODIAMOND, itm.ORUBY, itm.OEMERALD,
                         itm.OMAXGOLD, itm.OSAPPHIRE, itm.OLARNEYE,
                         itm.OGOLDPILE):
                    ularn_win.show1cell(j, i)
        ularn_win.showplayer()
        return

    elif pot == PINSTHEAL:
        c[player.HP] = c[player.HPMAX]
        player.removecurse()

    elif pot == PCUREDIANTH:
        ularn_win.Print("\n  You don't seem to be affected.")
        return

    elif pot == PPOISON:
        ularn_win.Print("\n  You feel a sickness engulf you!")
        c[player.HALFDAM] += 200 + rnd(200)
        return

    elif pot == PSEEINVIS:
        ularn_win.Print("\n  You feel your vision sharpen.")
        c[player.SEEINVISIBLE] += rnd(1000) + 400
        monster.monstnamelist[monster.INVISIBLESTALKER] = 'I'
        return

    # show new stats
    ularn_win.UpdateStatusAndEffects()
    return
