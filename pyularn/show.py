"""Item name printing and item lists (port of show.c / show.h).

EXPORTED FUNCTIONS
  show_plusses - Prints the number of plusses as indicated by the input arg
  qshowstr     - Show the player's inventory without setting up text mode
  showstr      - Show the player's invertory, setting/exiting text mode
  showwear     - Show wearable items
  showwield    - Show wieldable items
  showread     - Show readable items
  showeat      - Show edible items
  showquaff    - Show quaffable items
  seemagic     - Show magic spells/scrolls/potions discovered
  show1        - Show an item name
  show3        - Show an item name with the numebr of plusses
"""

from .header import *
from . import ularn_game, ularn_win, ularn_ask, dungeon, player, potion, scroll, spell, itm

# =============================================================================
# Local variables

# See magic function line and position counts. Used for paginating see magic.
lincount = 0
count = 0


# =============================================================================
# Local functions

def t_setup(count):
    """Set up for text display for the indicated number of lines."""
    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()
    ularn_win.MoveCursor(1, 1)


def t_endup(count):
    """Restore normal display screen depending on t_setup()."""
    ularn_win.set_display(ularn_win.DISPLAY_MAP)


def seepage():
    """Paginate the seemagic output (3 columns per line)."""
    global count, lincount
    count += 1
    if count == 3:
        lincount += 1
        count = 0
        ularn_win.Printc('\n')
        if lincount > 17:
            lincount = 0
            ularn_ask.more()
            ularn_win.ClearText()


def _wearable(i):
    return i in (itm.OLEATHER, itm.OPLATE, itm.OCHAIN, itm.ORING,
                 itm.OSTUDLEATHER, itm.OSPLINT, itm.OPLATEARMOR,
                 itm.OSSPLATE, itm.OSHIELD, itm.OELVENCHAIN)


def _not_wieldable(i):
    return i in (itm.ODIAMOND, itm.ORUBY, itm.OEMERALD, itm.OSAPPHIRE,
                 itm.OBOOK, itm.OCHEST, itm.OLARNEYE, itm.ONOTHEFT,
                 itm.OSPIRITSCARAB, itm.OCUBEofUNDEAD, itm.OPOTION,
                 itm.OORB, itm.OHANDofFEAR, itm.OBRASSLAMP, itm.OURN,
                 itm.OWWAND, itm.OSPHTALISMAN, itm.OSCROLL)


# =============================================================================
# Exported functions

def show_plusses(plus):
    """Print the number of plusses indicated by the input parameter."""
    if (plus > 0) or player.wizard:
        ularn_win.Printf(" +%d", plus)
    elif plus < 0:
        ularn_win.Printf(" %d", plus)


def qshowstr():
    """Print the player's inventory without setting up/exiting text mode."""
    c = player.c

    ularn_ask.clearpager()
    ularn_win.nosignal = 1  # don't allow ^c etc

    if c[player.GOLD]:
        ularn_win.Printf(".)   %d gold piece%s.", c[player.GOLD], plural(c[player.GOLD]))
        ularn_ask.pager()

    for k in range(player.IVENSIZE):
        if player.iven[k] != itm.ONOTHING:
            show3(k)
            ularn_ask.pager()

    mobuls_used = (player.gtime // 100) + 1
    mobuls_left = (ularn_game.TIMELIMIT // 100) - mobuls_used
    ularn_win.Printf("\nElapsed time is %d.  You have %d mobul%s left.",
                     mobuls_used, mobuls_left, plural(mobuls_left))
    ularn_ask.more()
    ularn_win.nosignal = 0


def showstr():
    """Display the player's inventory (sets up text mode, restores map)."""
    number = 3

    # count items in inventory
    for i in range(player.IVENSIZE):
        if player.iven[i] != itm.ONOTHING:
            number += 1

    t_setup(number)
    qshowstr()
    t_endup(number)


def showwear():
    """Display the items in the player's inventory that can be worn."""
    ularn_win.nosignal = 1  # don't allow ^c etc
    ularn_ask.clearpager()

    # count number of items we will display
    count = 2
    for j in range(player.IVENSIZE):
        i = player.iven[j]
        if i != itm.ONOTHING:
            if _wearable(i):
                count += 1

    t_setup(count)

    # Display the wearable items in item index order
    for i in range(22, 93):
        for j in range(player.IVENSIZE):
            if player.iven[j] == i:
                if _wearable(i):
                    show3(j)
                    ularn_ask.pager()

    ularn_ask.more()
    ularn_win.nosignal = 0
    t_endup(count)


def showwield():
    """Display the items in the player's inventory that can be wielded."""
    ularn_win.nosignal = 1  # don't allow ^c etc
    ularn_ask.clearpager()

    # count how many items
    count = 2
    for j in range(player.IVENSIZE):
        i = player.iven[j]
        if i != itm.ONOTHING:
            if not _not_wieldable(i):
                count += 1

    t_setup(count)

    # display the wieldable items in item order
    for i in range(22, 93):
        for j in range(player.IVENSIZE):
            if player.iven[j] == i:
                if not _not_wieldable(i):
                    show3(j)
                    ularn_ask.pager()

    ularn_ask.more()
    ularn_win.nosignal = 0
    t_endup(count)


def showread():
    """Display the items in the player's inventory that can be read."""
    ularn_win.nosignal = 1  # don't allow ^c etc
    ularn_ask.clearpager()

    count = 2
    for j in range(player.IVENSIZE):
        if player.iven[j] in (itm.OBOOK, itm.OSCROLL):
            count += 1

    t_setup(count)

    # display the readable items in item order
    for i in range(22, 84):
        for j in range(player.IVENSIZE):
            if player.iven[j] == i:
                if i in (itm.OBOOK, itm.OSCROLL):
                    show3(j)
                    ularn_ask.pager()

    ularn_ask.more()
    ularn_win.nosignal = 0
    t_endup(count)


def showeat():
    """Display the items in the player's inventory that can be eaten."""
    ularn_win.nosignal = 1  # don't allow ^c etc
    ularn_ask.clearpager()

    count = 2
    for j in range(player.IVENSIZE):
        if player.iven[j] == itm.OCOOKIE:
            count += 1

    t_setup(count)

    # show the edible items in item order
    for i in range(22, 84):
        for j in range(player.IVENSIZE):
            if player.iven[j] == i:
                if i == itm.OCOOKIE:
                    show3(j)
                    ularn_ask.pager()

    ularn_ask.more()
    ularn_win.nosignal = 0
    t_endup(count)


def showquaff():
    """Display the items in the player's inventory that can be quaffed."""
    ularn_win.nosignal = 1  # don't allow ^c etc
    ularn_ask.clearpager()

    count = 2
    for j in range(player.IVENSIZE):
        if player.iven[j] == itm.OPOTION:
            count += 1

    t_setup(count)

    # show the quaffable items in item order
    for i in range(22, 84):
        for j in range(player.IVENSIZE):
            if player.iven[j] == i:
                if i == itm.OPOTION:
                    show3(j)
                    ularn_ask.pager()

    ularn_ask.more()
    ularn_win.nosignal = 0
    t_endup(count)


def seemagic(arg):
    """Show what magic items have been discovered thus far.

    arg: -1 for just spells, 99 for all spells in game (genie),
         anything else gives spells, scrolls & potions.
    """
    global count, lincount

    count = 0
    lincount = 0
    ularn_win.nosignal = 1

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)

    if arg == 99:
        number = (spell.SPELL_COUNT + 2) // 3 + 4  # lines needed to display

        ularn_win.ClearText()
        ularn_win.MoveCursor(1, 1)

        ularn_win.Print("Availible spells are:\n\n")
        for i in range(spell.SPELL_COUNT):
            ularn_win.Printf("%s %-20s ", spell.spelcode[i], spell.spelname[i])
            seepage()

        seepage()
        ularn_ask.more()
        ularn_win.nosignal = 0
        ularn_win.draws(0, dungeon.MAXX, 0, number)
        return

    elif arg == -1:
        # if display spells while casting one
        number = 0
        for i in range(spell.SPELL_COUNT):
            if player.spelknow[i]:
                number += 1

        number = (number + 2) // 3 + 4  # lines needed to display

        ularn_win.ClearText()
        ularn_win.MoveCursor(1, 1)
    else:
        ularn_win.ClearText()

    ularn_win.Print("The magic spells you have discovered to date are:\n\n")
    for i in range(spell.SPELL_COUNT):
        if player.spelknow[i]:
            ularn_win.Printf("%s %-20s ", spell.spelcode[i], spell.spelname[i])
            seepage()

    if arg == -1:
        seepage()
        ularn_ask.more()
        ularn_win.nosignal = 0
        ularn_win.set_display(ularn_win.DISPLAY_MAP)
        return

    lincount += 3
    if count != 0:
        count = 2
        seepage()

    ularn_win.Print("\nThe magic scrolls you have found to date are:\n\n")
    count = 0
    for i in range(scroll.MAXSCROLL):
        if player.scrollknown[i]:
            ularn_win.Printf("%-26s", scroll.scrollname[i][1:])
            seepage()

    lincount += 3
    if count != 0:
        count = 2
        seepage()

    ularn_win.Print("\nThe magic potions you have found to date are:\n\n")
    count = 0
    for i in range(potion.MAXPOTION):
        if player.potionknown[i]:
            ularn_win.Printf("%-26s", potion.potionname[i][1:])
            seepage()

    if lincount != 0:
        ularn_ask.more()
    ularn_win.nosignal = 0
    ularn_win.set_display(ularn_win.DISPLAY_MAP)


def show1(idx, str2, known):
    """Show an item in the player's inventory.

    str2  : list of names for potions/scrolls indexed by ivenarg, or None.
    known : list indicating if the scroll/potion is known, or None.
    """
    iven = player.iven
    ivenarg = player.ivenarg
    letter = chr(idx + ord('a'))

    # standard
    if known is None:
        if str2 is None:
            ularn_win.Printf("\n%s)   %s", letter, itm.objectname[iven[idx]])
        elif str2[ivenarg[idx]] == "":
            ularn_win.Printf("\n%s)   %s", letter, itm.objectname[iven[idx]])
        else:
            ularn_win.Printf("\n%s)   %s of%s", letter, itm.objectname[iven[idx]],
                             str2[ivenarg[idx]])
    else:
        # scroll or potion or something with a known array
        if str2 is None:
            ularn_win.Printf("\n%s)   %s", letter, itm.objectname[iven[idx]])
        elif str2[ivenarg[idx]] == "":
            ularn_win.Printf("\n%s)   %s", letter, itm.objectname[iven[idx]])
        elif known[ivenarg[idx]] == 0:
            ularn_win.Printf("\n%s)   %s", letter, itm.objectname[iven[idx]])
        else:
            ularn_win.Printf("\n%s)   %s of%s", letter, itm.objectname[iven[idx]],
                             str2[ivenarg[idx]])

    if player.wizard:
        ularn_win.Printf(" [ %d ]", ivenarg[idx])


def show3(index):
    """Show a single item in the player's inventory, including plusses."""
    it = player.iven[index]
    c = player.c

    if it == itm.OPOTION:
        show1(index, potion.potionname, player.potionknown)
    elif it == itm.OSCROLL:
        show1(index, scroll.scrollname, player.scrollknown)
    elif it in (itm.OLARNEYE, itm.OBOOK, itm.OSPIRITSCARAB, itm.ODIAMOND,
                itm.ORUBY, itm.OCUBEofUNDEAD, itm.OEMERALD, itm.OCHEST,
                itm.OCOOKIE, itm.OSAPPHIRE, itm.OORB, itm.OHANDofFEAR,
                itm.OBRASSLAMP, itm.OURN, itm.OWWAND, itm.OSPHTALISMAN,
                itm.ONOTHEFT):
        show1(index, None, None)
    else:
        ularn_win.Printf("\n%s)   %s", chr(index + ord('a')), itm.objectname[it])
        show_plusses(player.ivenarg[index])

    if c[player.WIELD] == index:
        ularn_win.Print(" (weapon in hand)")

    if (c[player.WEAR] == index) or (c[player.SHIELD] == index):
        ularn_win.Print(" (being worn)")
