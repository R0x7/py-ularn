"""Scrolls and books (port of scroll.c and scroll.h).

Exported variables:
  scrollname  : The name of each scroll.

Exported functions:
  newscroll   : create a new scroll # with the correct probability
  read_scroll : process reading a scroll.
  readbook    : process reading a book.
"""

from .header import *

# ------------------------------------------------------------------ scroll.h
# (Defined before importing other pyularn modules so that modules importing
#  this one circularly can still see the constants.)

MAXSCROLL = 28  # maximum number of scrolls that are possible

# *** Scrolls ***
SENCHANTARM = 0
SENCHANTWEAP = 1
SENLIGHTEN = 2
SBLANK = 3
SCREATEMONST = 4
SCREATEITEM = 5
SAGGMONST = 6
STIMEWARP = 7
STELEPORT = 8
SAWARENESS = 9
SHASTEMONST = 10
SMONSTHEAL = 11
SSPIRITPROT = 12
SUNDEADPROT = 13
SSTEALTH = 14
SMAGICMAP = 15
SHOLDMONST = 16
SGEMPERFECT = 17
SSPELLEXT = 18
SIDENTIFY = 19
SREMCURSE = 20
SANNIHILATE = 21
SPULVERIZE = 22
SLIFEPROT = 23
S_MAX = 23  # Greatest defined scroll number

# ------------------------------------------------------------------ Exported variables

# name array for scrolls
scrollname = [
    " enchant armor",
    " enchant weapon",
    " enlightenment",
    " blank paper",
    " create monster",
    " create artifact",
    " aggravate monsters",
    " time warp",
    " teleportation",
    " expanded awareness",
    " haste monsters",
    " monster healing",
    " spirit protection",
    " undead protection",
    " stealth",
    " magic mapping",
    " hold monsters",
    " gem perfection",
    " spell extension",
    " identify",
    " remove curse",
    " annihilation",
    " pulverization",
    " life protection",
    "  ",
    "  ",
    "  ",
    "  ",
]

# ------------------------------------------------------------------ Local variables

# data for the function to read a scroll
xh = 0
yh = 0
yl = 0
xl = 0

# List of attributes affected by spell extension
EXTENSION_COUNT = 11
# (exten[] itself is defined below, after the module imports.)


# Array to create scroll numbers with appropriate probability of
# occurrence.

SCROLL_PROB_SIZE = 81

scprob = [
    SENCHANTARM, SENCHANTARM, SENCHANTARM, SENCHANTARM,
    SENCHANTWEAP, SENCHANTWEAP, SENCHANTWEAP, SENCHANTWEAP, SENCHANTWEAP,
    SENLIGHTEN, SENLIGHTEN, SENLIGHTEN, SENLIGHTEN, SENLIGHTEN, SENLIGHTEN,
    SBLANK, SBLANK, SBLANK, SBLANK, SBLANK,
    SCREATEMONST, SCREATEMONST, SCREATEMONST,
    SCREATEITEM, SCREATEITEM, SCREATEITEM, SCREATEITEM, SCREATEITEM,
    SAGGMONST, SAGGMONST, SAGGMONST, SAGGMONST, SAGGMONST,
    STIMEWARP, STIMEWARP, STIMEWARP, STIMEWARP,
    STELEPORT, STELEPORT, STELEPORT,
    SAWARENESS, SAWARENESS, SAWARENESS, SAWARENESS,
    SHASTEMONST, SHASTEMONST, SHASTEMONST, SHASTEMONST,
    SMONSTHEAL, SMONSTHEAL, SMONSTHEAL,
    SSPIRITPROT, SSPIRITPROT, SSPIRITPROT,
    SUNDEADPROT, SUNDEADPROT, SUNDEADPROT, SUNDEADPROT,
    SSTEALTH, SSTEALTH,
    SMAGICMAP, SMAGICMAP,
    SHOLDMONST, SHOLDMONST, SHOLDMONST,
    SGEMPERFECT, SGEMPERFECT,
    SSPELLEXT, SSPELLEXT,
    SIDENTIFY, SIDENTIFY, SIDENTIFY,
    SREMCURSE, SREMCURSE, SREMCURSE, SREMCURSE,
    SANNIHILATE,
    SPULVERIZE, SPULVERIZE, SPULVERIZE,
    SLIFEPROT,
]

from . import ularn_win, potion, spell, player, dungeon, dungeon_obj, monster, itm  # noqa: E402

exten = [
    player.PROTECTIONTIME,
    player.DEXCOUNT,
    player.STRCOUNT,
    player.CHARMCOUNT,
    player.INVISIBILITY,
    player.CANCELLATION,
    player.HASTESELF,
    player.GLOBE,
    player.SCAREMONST,
    player.HOLDMONST,
    player.TIMESTOP,
]


def _to_short(v):
    """Emulate a C (short) cast."""
    return ((v + 0x8000) & 0xFFFF) - 0x8000


# ------------------------------------------------------------------ Exported functions

def newscroll():
    """Create scroll #s with the correct probability of occurence."""
    return scprob[rund(SCROLL_PROB_SIZE)]


def read_scroll(typ):
    """Perform the processing of the effect of reading a scroll."""
    global xh, yh, yl, xl

    c = player.c
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    if typ < 0 or typ >= MAXSCROLL:
        return  # be sure we are within bounds

    if player.scrollknown[typ] == 0:
        player.scrollknown[typ] = 1
    ularn_win.Printf("\nYou read a scroll of %s.", scrollname[typ][1:])

    if typ == SENCHANTARM:
        player.enchantarmor(itm.ENCH_SCROLL)
        return

    elif typ == SENCHANTWEAP:
        player.enchweapon(itm.ENCH_SCROLL)
        return

    elif typ == SENLIGHTEN:
        yh = min(player.playery + 7, MAXY)
        xh = min(player.playerx + 25, MAXX)
        yl = max(player.playery - 7, 0)
        xl = max(player.playerx - 25, 0)
        for i in range(yl, yh):
            for j in range(xl, xh):
                dungeon.know[j][i] = dungeon.item[j][i]
                if dungeon.mitem[j][i].mon != monster.MONST_NONE:
                    dungeon.stealth[j][i] |= dungeon.STEALTH_SEEN
        ularn_win.nap(2000)
        ularn_win.draws(xl, xh, yl, yh)
        return

    elif typ == SBLANK:
        return

    elif typ == SCREATEMONST:
        monster.createmonster(monster.makemonst(dungeon.level + 1))
        return

    elif typ == SCREATEITEM:
        dungeon.something(player.playerx, player.playery, dungeon.level)
        return

    elif typ == SAGGMONST:
        c[player.AGGRAVATE] += 800
        return

    elif typ == STIMEWARP:
        #  This code is slightly wrong in that, if gtime is small and
        #  we can't go back by the required number of mobuls, it's
        #  still reported that we did.  I don't think this is
        #  critical -- dmr
        i = cdiv(rnd(1000) - 850, 100)
        if i == 0:
            i = 1

        player.gtime += 100 * i
        if player.gtime < 0:
            player.gtime = 0

        ularn_win.Printf("\nYou go %sward in time by %d mobul%s",
                         "back" if i < 0 else "for", abs(i), plural(i))

        player.adjusttime(i * 100)  # adjust time for time warping
        return

    elif typ == STELEPORT:
        dungeon_obj.oteleport(0)
        return

    elif typ == SAWARENESS:
        c[player.AWARENESS] += 1800
        return

    elif typ == SHASTEMONST:
        c[player.HASTEMONST] += rnd(55) + 12
        ularn_win.Printf("  You feel nervous.")
        return

    elif typ == SMONSTHEAL:
        for i in range(MAXY):
            for j in range(MAXX):
                if dungeon.mitem[j][i].mon:
                    dungeon.hitp[j][i] = monster.monster[dungeon.mitem[j][i].mon].hitpoints
        ularn_win.Printf("  You feel uneasy.")
        return

    elif typ == SSPIRITPROT:
        c[player.SPIRITPRO] += 300 + rnd(200)
        ularn_win.UpdateEffects()
        return

    elif typ == SUNDEADPROT:
        c[player.UNDEADPRO] += 300 + rnd(200)
        ularn_win.UpdateEffects()
        return

    elif typ == SSTEALTH:
        c[player.STEALTH] += 250 + rnd(250)
        ularn_win.UpdateEffects()
        return

    elif typ == SMAGICMAP:
        for i in range(MAXY):
            for j in range(MAXX):
                dungeon.know[j][i] = dungeon.item[j][i]
                if dungeon.mitem[j][i].mon != monster.MONST_NONE:
                    dungeon.stealth[j][i] |= dungeon.STEALTH_SEEN
        ularn_win.nap(2000)
        ularn_win.draws(0, MAXX, 0, MAXY)
        return

    elif typ == SHOLDMONST:
        c[player.HOLDMONST] += 30
        ularn_win.UpdateEffects()
        return

    elif typ == SGEMPERFECT:
        for i in range(player.IVENSIZE):
            if player.iven[i] in (itm.ODIAMOND, itm.ORUBY, itm.OEMERALD, itm.OSAPPHIRE):
                j = player.ivenarg[i]
                j *= 2
                if (j <= 0) and player.ivenarg[i]:
                    j = 2550
                player.ivenarg[i] = _to_short(j)

    elif typ == SSPELLEXT:
        for i in range(EXTENSION_COUNT):
            c[exten[i]] <<= 1

    elif typ == SIDENTIFY:
        for i in range(player.IVENSIZE):
            if player.iven[i] == itm.OPOTION:
                player.potionknown[player.ivenarg[i]] = 1
            if player.iven[i] == itm.OSCROLL:
                player.scrollknown[player.ivenarg[i]] = 1

    elif typ == SREMCURSE:
        player.removecurse()

    elif typ == SANNIHILATE:
        spell.annihilate()

    elif typ == SPULVERIZE:
        spell.godirect(spell.SPELL_LIT, 150, "The ray hits the %s.", 10, ularn_win.EFFECT_LIT)

    elif typ == SLIFEPROT:
        c[player.LIFEPROT] += 1


def readbook(arg):
    """Read a book. arg is the dungeon level of the book (its itemarg)."""
    c = player.c

    if arg <= 3:
        tmp = max(spell.splev[arg], 1)

        i = rund(tmp + 1)
    else:
        if arg >= dungeon.NLEVELS:
            arg = dungeon.NLEVELS - 1

        # Stop finding lower level spells deeper in the dungeon

        tmp = max(spell.splev[arg] - 9, 1)
        i = rnd(tmp) + 9

    # Learn this spell more
    player.spelknow[i] += 1

    ularn_win.Printf("\nSpell \"%s\":  %s\n%s.",
                     spell.spelcode[i], spell.spelname[i], spell.speldescript[i])

    # Boost int 40% of the time
    if rnd(10) == 4:
        ularn_win.Print("\nYou feel clever!")
        c[player.INTELLIGENCE] += 1
        ularn_win.UpdateStatus()
