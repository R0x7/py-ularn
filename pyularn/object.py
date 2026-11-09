"""What a player finds when moving onto a new square (port of object.c/object.h).

Exported functions:
  oopenchest    : Process opening a chest at the player's current location
  lookforobject : Performs processing for the item found at the player's
                  current location.
  (also non-static in C: oscroll, obook, ocookie, ogold, ochest)
"""

from .header import *

from . import ularn_game, ularn_win, player, monster, itm, potion, scroll  # noqa: E402
from . import spell, dungeon, dungeon_obj, store, fortune, scores  # noqa: E402


# =============================================================================
# Local functions

def iopts():
    """Print the ignore option."""
    ularn_win.Print(", or (i) ignore it? ")


def ignore():
    """Print 'ignore.'."""
    ularn_win.Print("ignore.\n")


def opotion(pot):
    """Handle finding a potion of type pot."""
    ans = ularn_win.get_prompt_input(
        "\nDo you (d) drink it, (t) take it, or (i) ignore it? ", "dit\033", 1)

    if ans == ESC or ans == 'i':
        ignore()

    elif ans == 'd':
        ularn_win.Print("drink.\n")
        dungeon.forget()  # destroy potion
        potion.quaffpotion(pot)

    elif ans == 't':
        ularn_win.Print("take.\n")
        if player.take(itm.OPOTION, pot) == 0:
            dungeon.forget()


def oscroll(typ):
    """Process finding a magic scroll of type typ."""
    c = player.c

    ularn_win.Print("\nDo you ")
    if c[player.BLINDCOUNT] == 0:
        ularn_win.Print("(r) read it, ")
    ularn_win.Print("(t) take it")
    iopts()

    ans = ularn_win.get_prompt_input("", "irt\033", 1)

    if ans == ESC or ans == 'i':
        ignore()

    elif ans == 'r':
        if c[player.BLINDCOUNT]:
            return
        ularn_win.Print("read.")
        # remove the scroll
        dungeon.forget()
        # read the scroll
        scroll.read_scroll(typ)

    elif ans == 't':
        ularn_win.Print("take.")
        if player.take(itm.OSCROLL, typ) == 0:
            dungeon.forget()  # destroy it


def obook():
    """Process finding a book."""
    c = player.c

    ularn_win.Print("\nDo you ")
    if c[player.BLINDCOUNT] == 0:
        ularn_win.Print("(r) read it, ")
    ularn_win.Print("(t) take it")
    iopts()

    ans = ularn_win.get_prompt_input("", "irt\033", 1)

    if ans == ESC or ans == 'i':
        ignore()
        return

    elif ans == 'r':
        if c[player.BLINDCOUNT]:
            return
        ularn_win.Print("read.")
        scroll.readbook(dungeon.iarg[player.playerx][player.playery])
        # no more book
        dungeon.forget()
        return

    elif ans == 't':
        ularn_win.Print("take.")
        if player.take(itm.OBOOK, dungeon.iarg[player.playerx][player.playery]) == 0:
            dungeon.forget()  # no more book
        return


def ocookie():
    """Process finding a fortune cookie."""
    c = player.c

    ularn_win.Print("\nDo you (e) eat it, (t) take it")
    iopts()

    ans = ularn_win.get_prompt_input("", "eit\033", 1)

    if ans == ESC or ans == 'i':
        ignore()
        return

    elif ans == 'e':
        ularn_win.Print("eat.\nThe cookie tasted good.")
        dungeon.forget()  # no more cookie
        if c[player.BLINDCOUNT]:
            return

        p = fortune.fortune(ularn_game.fortfile)
        if p is None:
            return

        ularn_win.Print("  A message inside the cookie reads:\n")
        ularn_win.Print(p)
        return

    elif ans == 't':
        ularn_win.Print("take.")
        if player.take(itm.OCOOKIE, 0) == 0:
            dungeon.forget()
        return


def ogold(arg):
    """Pick up some gold.

    arg : the gold object type.  ODGOLD -> pile worth 10x the itemarg,
          OMAXGOLD -> 100x, OKGOLD -> 1000x.
    """
    c = player.c

    i = dungeon.iarg[player.playerx][player.playery]

    if arg == itm.ODGOLD:
        i *= 10
    elif arg == itm.OMAXGOLD:
        i *= 100
    elif arg == itm.OKGOLD:
        i *= 1000

    ularn_win.Printf("\nYou find %d gold piece%s.", i, plural(i))
    c[player.GOLD] += i
    ularn_win.UpdateStatus()

    # destroy gold
    dungeon.item[player.playerx][player.playery] = itm.ONOTHING


def ochest():
    """Handle finding a chest."""
    ans = ularn_win.get_prompt_input(
        "\nDo you (t) take it, (o) try to open it, or (i) ignore it? ",
        "oti\033", 1)

    if ans == 'o':
        ularn_win.Print(" open it.")
        oopenchest()

    elif ans == 't':
        ularn_win.Print(" take")
        if player.take(itm.OCHEST, dungeon.iarg[player.playerx][player.playery]) == 0:
            dungeon.item[player.playerx][player.playery] = itm.ONOTHING

    elif ans == 'i' or ans == ESC:
        ignore()


def finditem(itm_):
    """Say what object we found and ask if player wants to take it.

    (C parameter name: itm; renamed to avoid clashing with the itm module.)
    """
    ularn_win.Printf("\n\nYou find %s", itm.objectname[itm_])

    tmp = dungeon.iarg[player.playerx][player.playery]
    if itm_ in (itm.ODIAMOND, itm.ORUBY, itm.OEMERALD, itm.OSAPPHIRE,
                itm.OSPIRITSCARAB, itm.OORBOFDRAGON, itm.OORB, itm.OHANDofFEAR,
                itm.OWWAND, itm.OCUBEofUNDEAD, itm.ONOTHEFT):
        ularn_win.Print(".")
    else:
        if tmp > 0:
            ularn_win.Printf(" + %d", tmp)
        elif tmp < 0:
            ularn_win.Printf(" %d", tmp)

    ularn_win.Print("\nDo you want to (t) take it")
    iopts()

    i = ularn_win.get_prompt_input("", "it\033", 1)

    if i == 't':
        ularn_win.Print("take.")
        if player.take(itm_, tmp) == 0:
            dungeon.forget()
    else:
        ignore()


# =============================================================================
# Exported functions

def oopenchest():
    """Handle opening a chest."""
    c = player.c
    px = player.playerx
    py = player.playery

    if dungeon.item[px][py] != itm.OCHEST:
        return

    k = rnd(101)
    if k < 40:
        ularn_win.Print("\nThe chest explodes as you open it.")
        ularn_win.UlarnBeep()
        i = rnd(10)
        if i > c[player.HP]:
            i = c[player.HP]

        ularn_win.Printf("\nYou suffer %d hit point%s damage!", i, plural(i))
        player.losehp(scores.DIED_EXPLODING_CHEST, i)
        ularn_win.UpdateStatus()

        r = rnd(10)
        if r == 1:
            c[player.ITCHING] += rnd(1000) + 100
            ularn_win.Print("\nYou feel an irritation spread over your skin!")
            ularn_win.UlarnBeep()

        elif r == 2:
            c[player.CLUMSINESS] += rnd(1600) + 200
            ularn_win.Print("\nYou begin to lose hand-eye co-ordination!")
            ularn_win.UlarnBeep()

        elif r == 3:
            c[player.HALFDAM] += rnd(1600) + 200
            ularn_win.Print("\nYou suddenly feel sick and BARF all over your shoes!")
            ularn_win.UlarnBeep()

        px = player.playerx
        py = player.playery

        # Remove the chest
        dungeon.item[px][py] = itm.ONOTHING

        # create the items in the chest
        if rnd(100) < 69:
            # gems from the chest
            player.creategem()

        dungeon.dropgold(rnd(110 * dungeon.iarg[player.playerx][player.playery] + 200))

        # (rnd(4) is re-evaluated on every loop test, as in C)
        i = 0
        while i < rnd(4):
            dungeon.something(player.playerx, player.playery,
                              dungeon.iarg[player.playerx][player.playery] + 2)
            i += 1
    else:
        ularn_win.Print("\nNothing happens.")


def lookforobject():
    """Look for an object at the player's location and give the player options."""
    c = player.c
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    # can't find objects is time is stopped
    if c[player.TIMESTOP]:
        return

    i = dungeon.item[player.playerx][player.playery]
    if i == itm.ONOTHING:
        return

    ularn_win.showcell(player.playerx, player.playery)
    ularn_win.yrepcount = 0

    if i in (itm.OGOLDPILE, itm.OMAXGOLD, itm.OKGOLD, itm.ODGOLD):
        ogold(i)

    elif i == itm.OPOTION:
        ularn_win.Print("\n\nYou find a magic potion")
        i = dungeon.iarg[player.playerx][player.playery]
        if player.potionknown[i]:
            ularn_win.Printf(" of %s", potion.potionname[i][1:])
        ularn_win.Print(".")
        opotion(i)

    elif i == itm.OSCROLL:
        ularn_win.Print("\n\nYou find a magic scroll")
        i = dungeon.iarg[player.playerx][player.playery]
        if player.scrollknown[i]:
            ularn_win.Printf(" of %s", scroll.scrollname[i][1:])
        ularn_win.Print(".")
        oscroll(i)

    elif i == itm.OALTAR:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is a holy altar here.")
        dungeon_obj.oaltar()

    elif i == itm.OBOOK:
        ularn_win.Print("\n\nYou find a book.")
        obook()

    elif i == itm.OCOOKIE:
        ularn_win.Print("\n\nYou find a fortune cookie.")
        ocookie()

    elif i == itm.OTHRONE:
        if player.nearbymonst():
            return
        ularn_win.Printf("\n\nThere is %s here.", itm.objectname[i])
        dungeon_obj.othrone(0)

    elif i == itm.OTHRONE2:
        if player.nearbymonst():
            return
        ularn_win.Printf("\n\nThere is %s here.", itm.objectname[i])
        dungeon_obj.othrone(1)

    elif i == itm.ODEADTHRONE:
        ularn_win.Printf("\n\nThere is %s here.", itm.objectname[i])
        dungeon_obj.odeadthrone()

    elif i == itm.OORB:
        if player.nearbymonst():
            return
        finditem(i)

    elif i == itm.OBRASSLAMP:
        ularn_win.Print("\nYou find a brass lamp.")

        i = ularn_win.get_prompt_input(
            "\nDo you want to (r) rub it, (t) take it, or (i) ignore it? ",
            "rit\033", 1)

        if i == 'r':
            i = rnd(100)
            if i > 90:
                ularn_win.Print("\nThe magic genie was very upset at being disturbed!")

                player.losehp(scores.DIED_ANNOYED_GENIE, cdiv(c[player.HP], 2) + 1)
                ularn_win.UlarnBeep()

            # higher level, better chance of spell
            elif (rnd(100) + c[player.LEVEL] // 2) > 80:
                ularn_win.Print("\nA magic genie appears!")
                code = spell.get_spell_code("\n  What spell would you like? : ")
                if code is None:
                    code = ""

                ularn_win.Printc('\n')
                if len(code) >= 3:
                    for i in range(spell.SPELL_COUNT):
                        if ((spell.spelcode[i][0] == code[0]) and
                                (spell.spelcode[i][1] == code[1]) and
                                (spell.spelcode[i][2] == code[2])):
                            player.spelknow[i] += 1
                            ularn_win.Printf("\nSpell \"%s\":  %s\n%s", spell.spelcode[i],
                                             spell.spelname[i], spell.speldescript[i])
                            ularn_win.Print("\nThe genie prefers not to be disturbed again.")
                            dungeon.forget()

                            player.recalc()
                            ularn_win.UpdateStatus()
                            return

                ularn_win.Print("\nThe genie has never heard of such a spell!")
                ularn_win.Print("\nThe genie prefers not to be disturbed again.")
                dungeon.forget()

                player.recalc()
                ularn_win.UpdateStatus()
                return
            else:
                ularn_win.Print("\nnothing happened.")

            if rnd(100) < 15:
                ularn_win.Print("\nThe genie prefers not to be disturbed again!")
                dungeon.forget()
                c[player.LAMP] = 0  # chance of finding lamp again

            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OBRASSLAMP, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")
        return

    elif i == itm.OWWAND:
        if player.nearbymonst():
            return
        finditem(i)

    elif i == itm.OHANDofFEAR:
        if player.nearbymonst():
            return
        finditem(i)

    elif i == itm.OPIT:
        ularn_win.Print("\n\nYou're standing at the top of a pit.")
        dungeon_obj.opit()

    elif i == itm.OSTAIRSUP:
        ularn_win.Print("\n\nThere is a circular staircase here.")
        dungeon_obj.ostairs(1)  # up

    elif i == itm.OELEVATORUP:
        ularn_win.Print("\n\nYou have found an express elevator going up.")
        dungeon_obj.oelevator(1)  # up

    elif i == itm.OELEVATORDOWN:
        ularn_win.Print("\n\nYou have found an express elevator going down.")
        dungeon_obj.oelevator(-1)  # down

    elif i == itm.OFOUNTAIN:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is a fountain here.")
        dungeon_obj.ofountain()

    elif i == itm.OSTATUE:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nYou stand before a statue.")
        dungeon_obj.ostatue()

    elif i == itm.OCHEST:
        ularn_win.Print("\n\nThere is a chest here.")
        ochest()

    elif i in (itm.OIVTELETRAP, itm.OTELEPORTER):
        if i == itm.OIVTELETRAP:
            if rnd(11) < 6:
                return
            dungeon.item[player.playerx][player.playery] = itm.OTELEPORTER
            # fall through

        # The player is being teleported, so obviously the player gets
        # to know that a teleport trap is here.
        # oteleport forces a screen redraw, so don't bother display anything
        # here.
        dungeon.know[player.playerx][player.playery] = dungeon.item[player.playerx][player.playery]
        ularn_win.Print("\nZaaaappp!  You've been teleported!\n")
        ularn_win.UlarnBeep()
        ularn_win.nap(3000)
        dungeon_obj.oteleport(0)

    elif i == itm.OSCHOOL:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nYou have found the College of Ularn.")

        i = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if i == 'g':
            store.oschool()  # the college of larn
        else:
            ularn_win.Print(" stay here.")

    elif i == itm.OMIRROR:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is a mirror here.")
        dungeon_obj.omirror()

    elif i in (itm.OBANK2, itm.OBANK):
        if player.nearbymonst():
            return
        if i == itm.OBANK:
            ularn_win.Print("\n\nYou have found the bank of Ularn.")
        else:
            ularn_win.Print("\n\nYou have found a branch office of the bank of Ularn.")

        j = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if j == 'g':
            if i == itm.OBANK:
                store.obank()
            else:
                store.obank2()  # the bank of larn
        else:
            ularn_win.Print(" stay here.")

    elif i == itm.ODEADFOUNTAIN:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is a dead fountain here.")

    elif i == itm.ODNDSTORE:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is a DND store here.")
        i = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if i == 'g':
            store.dndstore()  # the dnd adventurers store
        else:
            ularn_win.Print(" stay here.")

    elif i == itm.OSTAIRSDOWN:
        ularn_win.Print("\n\nThere is a circular staircase here.")
        dungeon_obj.ostairs(-1)  # down

    elif i == itm.OOPENDOOR:
        ularn_win.Print("\nThere is an open door here.")

    elif i == itm.OCLOSEDDOOR:

        # can't move objects if time is stopped
        if c[player.TIMESTOP]:
            return

        dx = player.playerx
        dy = player.playery

        if ularn_game.dropflag:
            return
        ularn_win.Printf("\n\nYou find %s", itm.objectname[i])
        ularn_win.Print("\nDo you (o) try to open it")
        iopts()

        i = ularn_win.get_prompt_input("", "oi\033", 1)

        if (i == ESC) or (i == 'i'):
            ignore()
            player.playerx = player.lastpx
            player.playery = player.lastpy
            player.lastpx = dx
            player.lastpy = dy
        else:
            ularn_win.Print("open.")

            # Try and open the door that is here
            dungeon_obj.oopendoor(player.playerx, player.playery)

            if dungeon.item[player.playerx][player.playery] == itm.OCLOSEDDOOR:
                # Door didn't open.
                # Move the player back where they came from.
                player.playerx = player.lastpx
                player.playery = player.lastpy
                player.lastpx = dx
                player.lastpy = dy

    elif i == itm.OENTRANCE:
        ularn_win.Print("\nYou have found ")
        ularn_win.Print(itm.objectname[itm.OENTRANCE])
        ularn_win.Print("\nDo you (g) go inside")
        iopts()
        i = ularn_win.get_prompt_input("", "gi\033", 1)

        if i == 'g':
            dungeon.newcavelevel(1)
            player.playerx = 33
            player.playery = MAXY - 2

            # Make sure the entrance to the dungeon is clear
            dungeon.item[33][MAXY - 1] = itm.ONOTHING
            dungeon.mitem[33][MAXY - 1].mon = monster.MONST_NONE

            ularn_win.draws(0, MAXX, 0, MAXY)
            ularn_win.UpdateStatusAndEffects()
            return
        else:
            ignore()

    elif i == itm.OVOLDOWN:
        ularn_win.Print("\nYou have found ")
        ularn_win.Print(itm.objectname[itm.OVOLDOWN])
        ularn_win.Print("\nDo you (c) climb down")
        iopts()
        i = ularn_win.get_prompt_input("", "ci\033", 1)

        if (i == ESC) or (i == 'i'):
            ignore()
            return
        if dungeon.level != 0:
            ularn_win.Print("\nThe shaft only extends 5 feet downward!")
            return
        if player.packweight() > 45 + 3 * (c[player.STRENGTH] + c[player.STREXTRA]):
            ularn_win.Print("\nYou slip and fall down the shaft.")
            ularn_win.UlarnBeep()

            player.losehp(scores.DIED_SLIPPED_VOLCANO_SHAFT, 30 + rnd(20))
            ularn_win.UpdateStatus()
        else:
            ularn_win.Print("climb down.")
        ularn_win.nap(3000)
        dungeon.newcavelevel(dungeon.DBOTTOM + 1)  # down to V1
        player.playerx = rnd(MAXX - 2)
        player.playery = rnd(MAXY - 2)
        player.positionplayer()
        ularn_win.draws(0, MAXX, 0, MAXY)
        ularn_win.UpdateStatusAndEffects()
        return

    elif i == itm.OVOLUP:
        ularn_win.Print("\nYou have found ")
        ularn_win.Print(itm.objectname[itm.OVOLUP])
        ularn_win.Print("\nDo you (c) climb up")
        iopts()
        i = ularn_win.get_prompt_input("", "ci\033", 1)

        if (i == ESC) or (i == 'i'):
            ignore()
            return
        if player.packweight() > 40 + 5 * (c[player.DEXTERITY] + c[player.STRENGTH] + c[player.STREXTRA]):
            ularn_win.Print("\nYou slip and fall down the shaft.")
            ularn_win.UlarnBeep()

            player.losehp(scores.DIED_SLIPPED_VOLCANO_SHAFT, 15 + rnd(20))
            ularn_win.UpdateStatus()
            return
        ularn_win.Print("climb up.")

        ularn_win.nap(3000)
        dungeon.newcavelevel(0)
        found = 0
        for i in range(MAXY):
            for j in range(MAXX):
                # put player near volcano shaft
                if dungeon.item[j][i] == itm.OVOLDOWN:
                    player.playerx = j
                    player.playery = i
                    found = 1
                    player.positionplayer()
                    break
            if found:
                break
        ularn_win.draws(0, MAXX, 0, MAXY)
        ularn_win.UpdateStatusAndEffects()
        return

    elif i in (itm.OTRAPARROWIV, itm.OTRAPARROW):
        if i == itm.OTRAPARROWIV:
            if rnd(17) < 13:
                return  # for an arrow trap
            dungeon.item[player.playerx][player.playery] = itm.OTRAPARROW
            # fall through
        ularn_win.Print("\nYou are hit by an arrow!")
        ularn_win.UlarnBeep()  # for an arrow trap

        player.losehp(scores.DIED_SHOT_BY_ARROW, rnd(10) + dungeon.level)
        ularn_win.UpdateStatus()
        return

    elif i in (itm.OIVDARTRAP, itm.ODARTRAP):
        if i == itm.OIVDARTRAP:
            if rnd(17) < 13:
                return  # for a dart trap
            dungeon.item[player.playerx][player.playery] = itm.ODARTRAP
            # fall through
        ularn_win.Print("\nYou are hit by a dart!")
        ularn_win.UlarnBeep()  # for a dart trap

        player.losehp(scores.DIED_HIT_BY_DART, rnd(5))
        c[player.STRENGTH] -= 1
        if c[player.STRENGTH] < 3:
            c[player.STRENGTH] = 3
        ularn_win.UpdateStatus()
        return

    elif i in (itm.OIVTRAPDOOR, itm.OTRAPDOOR):
        if i == itm.OIVTRAPDOOR:
            if rnd(17) < 13:
                return  # for a trap door
            dungeon.item[player.playerx][player.playery] = itm.OTRAPDOOR
            # fall through
        for i in range(player.IVENSIZE):
            if player.iven[i] == itm.OWWAND:
                ularn_win.Print("\nYou escape a trap door.")
                return
        if (dungeon.level == dungeon.DBOTTOM) or (dungeon.level == dungeon.VBOTTOM):
            ularn_win.Print("\nYou fall through a trap door leading straight to HELL!")
            ularn_win.UlarnBeep()
            ularn_win.nap(3000)
            scores.died(scores.DIED_FELL_THROUGH_BOTTOMLESS_TRAPDOOR, 0)
        ularn_win.Print("\nYou fall through a trap door!")
        ularn_win.UlarnBeep()
        player.losehp(scores.DIED_FELL_THROUGH_TRAPDOOR, rnd(5 + dungeon.level))
        ularn_win.nap(2000)
        dungeon.newcavelevel(dungeon.level + 1)
        ularn_win.draws(0, MAXX, 0, MAXY)
        ularn_win.UpdateStatusAndEffects()
        return

    elif i == itm.OTRADEPOST:
        if player.nearbymonst():
            return
        ularn_win.Print("\nYou have found the Ularn trading Post.")
        i = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if i == 'g':
            store.otradepost()
        else:
            ularn_win.Print("stay here.")
        return

    elif i == itm.OHOME:
        if player.nearbymonst():
            return
        ularn_win.Print("\nYou have found your way home.")
        i = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if i == 'g':
            store.ohome()
        else:
            ularn_win.Print("stay here.")
        return

    elif i == itm.OPAD:
        if player.nearbymonst():
            return
        ularn_win.Print("\nYou have found Dealer McDope's Hideout!")
        i = ularn_win.get_prompt_input(
            "\nDo you (c) check it out, or (i) ignore it? ",
            "ci\033", 1)

        if i == 'c':
            store.opad()
        else:
            ularn_win.Print("forget it.")
        return

    elif i == itm.OSPEED:
        ularn_win.Print("\nYou find some speed.")
        i = ularn_win.get_prompt_input(
            "\nDo you (s) snort it, (t) take it, or (i) ignore it? ",
            "sti\033", 1)

        if i == 's':
            ularn_win.Print("snort!")
            ularn_win.Print("\nOhwowmanlikethingstotallyseemtoslowdown!")
            c[player.HASTESELF] += 200 + c[player.LEVEL]
            c[player.HALFDAM] += 300 + rnd(200)
            player.adjust_ability(player.INTELLIGENCE, -2)
            player.adjust_ability(player.WISDOM, -2)
            player.adjust_ability(player.CONSTITUTION, -2)
            player.adjust_ability(player.DEXTERITY, -2)
            player.adjust_ability(player.STRENGTH, -2)
            dungeon.forget()
            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OSPEED, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")

    elif i == itm.OSHROOMS:
        ularn_win.Print("\nYou find some magic mushrooms.")
        i = ularn_win.get_prompt_input(
            "\nDo you (e) eat them, (t) take them, or (i) ignore them? ",
            "eti\033", 1)

        if i == 'e':
            ularn_win.Print("eat!")
            ularn_win.Print("\nThings start to get real spacey...")
            c[player.HASTEMONST] += rnd(75) + 25
            c[player.CONFUSE] += 30 + rnd(10)
            player.adjust_ability(player.WISDOM, 2)
            player.adjust_ability(player.CHARISMA, 2)
            dungeon.forget()
            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OSHROOMS, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")

    elif i == itm.OACID:
        ularn_win.Print("\nYou find some LSD.")
        i = ularn_win.get_prompt_input(
            "\nDo you (e) eat it, (t) take it, or (i) ignore it? ",
            "eit\033", 1)

        if i == 'e':
            ularn_win.Print("eat!")
            ularn_win.Print("\nYou are now frying your ass off!")
            c[player.CONFUSE] += 30 + rnd(10)
            player.adjust_ability(player.WISDOM, 2)
            player.adjust_ability(player.INTELLIGENCE, 2)
            c[player.AWARENESS] += 1500
            c[player.AGGRAVATE] += 1500
            # heal monsters
            for j in range(MAXY):
                for k in range(MAXX):
                    if dungeon.mitem[k][j].mon:
                        dungeon.hitp[k][j] = monster.monster[dungeon.mitem[k][j].mon].hitpoints
            dungeon.forget()
            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OACID, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")

    elif i == itm.OHASH:
        ularn_win.Print("\nYou find some hashish.")
        i = ularn_win.get_prompt_input(
            "\nDo you (s) smoke it, (t) take it, or (i) ignore it? ",
            "sti\033", 1)

        if i == 's':
            ularn_win.Print("smoke!")
            ularn_win.Print("\nWOW! You feel stooooooned...")
            c[player.HASTEMONST] += rnd(75) + 25
            player.adjust_ability(player.INTELLIGENCE, 2)
            player.adjust_ability(player.WISDOM, 2)
            player.adjust_ability(player.CONSTITUTION, -2)
            player.adjust_ability(player.DEXTERITY, -2)
            c[player.HALFDAM] += 300 + rnd(200)
            c[player.CLUMSINESS] += rnd(1800) + 200
            dungeon.forget()
            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OHASH, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")

    elif i == itm.OCOKE:
        ularn_win.Print("\nYou find some cocaine.")
        i = ularn_win.get_prompt_input(
            "\nDo you want to (s) snort it, (t) take it, or (i) ignore it? ",
            "sit\033", 1)

        if i == 's':
            ularn_win.Print("snort!")
            ularn_win.Print("\nYour nose begins to bleed!")
            player.adjust_ability(player.DEXTERITY, -2)
            player.adjust_ability(player.CONSTITUTION, -2)
            player.adjust_ability(player.CHARISMA, 3)

            for i in range(player.ABILITY_FIRST, player.ABILITY_LAST + 1):
                player.adjust_ability(i, 33)
            c[player.COKED] += 10
            dungeon.forget()
            ularn_win.UpdateStatus()
        elif i == 't':
            ularn_win.Print("take.")
            if player.take(itm.OCOKE, 0) == 0:
                dungeon.forget()
        else:
            ularn_win.Print("ignore.")

    elif i == itm.OWALL:
        pass

    elif i == itm.OANNIHILATION:
        if player.player_has_item(itm.OSPHTALISMAN):
            ularn_win.Print("\nThe Talisman of the Sphere protects you from annihilation!")
            return

        # annihilated by sphere of annihilation
        scores.died(scores.DIED_SPHERE_ANNIHILATION, 0)
        return

    elif i == itm.OLRS:
        if player.nearbymonst():
            return
        ularn_win.Print("\n\nThere is an LRS office here.")
        i = ularn_win.get_prompt_input(
            "\nDo you (g) go inside, or (i) stay here? ",
            "gi\033", 1)

        if i == 'g':
            store.olrs()  # the larn revenue service
        else:
            ularn_win.Print(" stay here.")

    else:
        finditem(i)
