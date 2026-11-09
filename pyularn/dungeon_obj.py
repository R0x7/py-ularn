"""Static dungeon objects (port of dungeon_obj.c / dungeon_obj.h).

This module contains functions for handling the effects of static objects
in the dungeon.
(ie. Objects that cannot be picked up such as stairs, fountains etc.)

EXPORTED FUNCTIONS

  oopendoor   - processes the player opening a closed door
  oaltar      - processes player stepping onto an alter
  othrone     - processes player stepping onto a throne
  odeadthrone - processes player stepping onto a dead throne
  ofountain   - processes player stepping onto a fountain
  ostairs     - processes player stepping onto the stairs (up or down)
  oteleport   - processes player stepping onto a teleport trap, and all other
                reasons for teleporting the player
  opit        - processes player stepping onto a pit
  oelevator   - processes player stepping onto an elevator
  ostatue     - processes player stepping onto a statue
  omirror     - processes player stepping onto a mirror
"""

from .header import *
from . import dungeon, itm, monster, player, potion, scores, ularn_win

ALTAR_PRO_BOOST = 3


# =============================================================================
# Local functions

def ohear():
    """Function to cast a +3 protection on the player from an altar."""
    c = player.c
    ularn_win.Print("\nYou have been heard!")
    if c[player.ALTPRO] == 0:
        c[player.MOREDEFENSES] += ALTAR_PRO_BOOST
    c[player.ALTPRO] += 800  # protection field
    player.recalc()
    ularn_win.UpdateEffects()


def fch(how, x):
    """Changes a players ability by 1 for ofountain effects.

    Python signature: fch(how, x) where x is the index into player.c of the
    attribute to change (C passes a pointer to the attribute value).
      how < 0 => down, how > 0 => up
    """
    c = player.c
    if how < 0:
        if c[x] > 3:
            ularn_win.Print(" went down by one!")
            c[x] -= 1
        else:
            ularn_win.Print(" remained unchanged!")
    else:
        ularn_win.Print(" went up by one!")
        c[x] += 1
    ularn_win.UpdateStatus()


def fntchange(how):
    """Function to change player attributes for fountain based effects.

    how > 0 => raised, how < 0 => lowered
    """
    level = dungeon.level

    ularn_win.Printc('\n')
    r = rnd(9)
    if r == 1:
        ularn_win.Print("Your strength")
        fch(how, player.STRENGTH)
    elif r == 2:
        ularn_win.Print("Your intelligence")
        fch(how, player.INTELLIGENCE)
    elif r == 3:
        ularn_win.Print("Your wisdom")
        fch(how, player.WISDOM)
    elif r == 4:
        ularn_win.Print("Your constitution")
        fch(how, player.CONSTITUTION)
    elif r == 5:
        ularn_win.Print("Your dexterity")
        fch(how, player.DEXTERITY)
    elif r == 6:
        ularn_win.Print("Your charm")
        fch(how, player.CHARISMA)
    elif r == 7:
        j = rnd(level + 1)
        if how < 0:
            ularn_win.Printf("You lose %d hit point%s!", j, plural(j))
            player.losemhp(j)
        else:
            ularn_win.Printf("You gain %d hit point%s!", j, plural(j))
            player.raisemhp(j)
        ularn_win.UpdateStatus()
    elif r == 8:
        j = rnd(level + 1)
        if how > 0:
            ularn_win.Printf("You just gained %d spell%s!", j, plural(j))
            player.raisemspells(j)
        else:
            ularn_win.Printf("You just lost %d spell%s!", j, plural(j))
            player.losemspells(j)
        ularn_win.UpdateStatus()
    elif r == 9:
        j = 5 * rnd((level + 1) * (level + 1))
        if how < 0:
            ularn_win.Printf("You just lost %d experience point%s!", j, plural(j))
            player.loseexperience(j)
        else:
            ularn_win.Printf("You just gained %d experience point%s!", j, plural(j))
            player.raiseexperience(j)


def obottomless():
    """Processes the player falling into a bottomless pit."""
    ularn_win.Print("\nYou fell into a pit leading straight to HELL!")
    ularn_win.UlarnBeep()

    ularn_win.nap(3000)
    scores.died(scores.DIED_FELL_INTO_BOTTOMLESS_PIT, 0)


# =============================================================================
# Exported functions

def oopendoor(x, y):
    """Processes the player opening a closed door at x, y."""
    c = player.c

    if dungeon.item[x][y] != itm.OCLOSEDDOOR:
        return

    if rnd(11) < 7:
        #
        # Failed to open the door
        # See if something nasty happened instead
        #
        a = dungeon.iarg[x][y]
        if a == 6:
            c[player.AGGRAVATE] += rnd(400)

        elif a in (7, 8):
            ularn_win.Print("\nYou are jolted by an electric shock!")

            player.losehp(scores.DIED_ELECTRIC_SHOCK, rnd(20))
            ularn_win.UpdateStatus()

        elif a == 9:
            ularn_win.Print("\nYou suddenly feel weaker!")
            if c[player.STRENGTH] > 3:
                c[player.STRENGTH] -= 1
            ularn_win.UpdateStatus()

        # Now the trap has been triggered, clear the trap
        dungeon.iarg[x][y] = 0
    else:
        dungeon.item[x][y] = itm.OOPENDOOR
        ularn_win.show1cell(x, y)


def oaltar():
    """Processes player stepping onto an altar."""
    c = player.c
    level = dungeon.level

    while True:
        redo = 0
        ans = ularn_win.get_prompt_input(
            "\nDo you (p) pray  (d) desecrate, or (i) ignore it? ",
            "pdi\033", 1)

        if ans == 'p':
            ularn_win.Print(" pray")
            ans = ularn_win.get_prompt_input(
                "\nDo you (m) give money or (j) just pray? ",
                "mj", 1)

            if ans == 'j':
                p = rund(100)
                if p < 12:
                    monster.createmonster(monster.makemonst(level + 2))
                elif p < 17:
                    player.enchweapon(itm.ENCH_ALTAR)
                elif p < 22:
                    player.enchantarmor(itm.ENCH_ALTAR)
                elif p < 27:
                    ohear()
                else:
                    ularn_win.Print("\nNothing happens.")

            elif ans == 'm':
                ularn_win.Print("\nHow much do you donate? ")
                k = ularn_win.get_num_input(c[player.GOLD])

                if k < 0:
                    redo = 1
                elif c[player.GOLD] < k:
                    ularn_win.Print(" You don't have that much!")
                    ularn_win.nap(1001)
                    redo = 1
                else:
                    #
                    # Remove gold from player
                    #
                    c[player.GOLD] -= k

                    if (k < (c[player.GOLD] // 10)) and (rnd(60) < 30) and not player.wizard:
                        #
                        # Player offers < 1/11% of gold insults the gods 50% of
                        # the time.
                        # Insulted gods send a demon prince to punish the player.
                        #
                        ularn_win.Print(" Cheapskate! The Gods are insulted by such a tiny offering!")
                        dungeon.forget()
                        monster.createmonster(monster.DEMONPRINCE)
                        c[player.AGGRAVATE] += 1500
                        # God takes more gold anyway
                        c[player.GOLD] -= k
                    elif ((k < (c[player.GOLD] + k) // 10) or (k < rnd(50))) and not player.wizard:
                        #
                        # Player offers more than 1/11, but less than 1/10 of
                        # gold.
                        # God has a chance of sending a monster to encourage
                        # the player to be more generous based on how far below
                        # 50 gold the amount doneted is.
                        #
                        monster.createmonster(monster.makemonst(level + 2))
                        c[player.AGGRAVATE] += 500
                        # God takes more gold anyway
                        c[player.GOLD] -= k
                    else:
                        #
                        # Player was reasonably generous, so give a blessing
                        #
                        p = rund(16)
                        if p < 4:
                            ularn_win.Print(" Thank you.")
                        elif p < 6:
                            player.enchantarmor(itm.ENCH_ALTAR)
                            player.enchantarmor(itm.ENCH_ALTAR)
                        elif p < 8:
                            player.enchweapon(itm.ENCH_ALTAR)
                            player.enchweapon(itm.ENCH_ALTAR)
                        else:
                            ohear()

                    ularn_win.UpdateStatus()

        elif ans == 'd':
            ularn_win.Print(" desecrate")
            if rnd(100) < 60:
                monster.createmonster(monster.makemonst(level + 3) + 8)
                c[player.AGGRAVATE] += 2500
            elif rnd(100) < 5:
                player.raiselevel()
            elif rnd(101) < 30:
                ularn_win.Print("\nThe altar crumbles into a pile of dust before your eyes.")
                dungeon.forget()
            else:
                ularn_win.Print("\nNothing happens.")
            ularn_win.UpdateStatus()

        elif ans == 'i' or ans == ESC:
            ularn_win.Print(" ignore")
            if rnd(100) < 30:
                monster.createmonster(monster.makemonst(level + 2))
                c[player.AGGRAVATE] += rnd(450)
            else:
                ularn_win.Print("\nNothing happens.")

        if not redo:
            break


def othrone(arg):
    """Processes player stepping onto a throne."""
    ans = ularn_win.get_prompt_input(
        "\nDo you (p) pry off jewels, (s) sit down, or (i) ignore it? ",
        "psi\033", 1)

    if ans == 'p':
        ularn_win.Print(" pry off")
        k = rnd(101)
        if k < 25:
            i = 0
            while i < rnd(4):  # (C re-evaluates rnd(4) on every iteration)
                player.creategem()  # gems pop off the throne
                i += 1
            dungeon.item[player.playerx][player.playery] = itm.ODEADTHRONE
        elif (k < 40) and (arg == 0):
            monster.createmonster(monster.GNOMEKING)
            dungeon.item[player.playerx][player.playery] = itm.OTHRONE2
        else:
            ularn_win.Print("\nNothing happens.")

    elif ans == 's':
        ularn_win.Print(" sit down")
        k = rnd(101)
        if (k < 30) and (arg == 0):
            monster.createmonster(monster.GNOMEKING)
            dungeon.item[player.playerx][player.playery] = itm.OTHRONE2
        elif k < 35:
            ularn_win.Print("\nZaaaappp!  You've been teleported!\n")
            ularn_win.UlarnBeep()
            oteleport(0)
        else:
            ularn_win.Print("\nNothing happens.")

    elif ans == 'i' or ans == ESC:
        ularn_win.Print(" ignore")


def odeadthrone():
    """Processes player stepping onto a dead throne."""
    ans = ularn_win.get_prompt_input(
        "\nDo you (s) sit down, or (i) ignore it? ",
        "si\033", 1)

    if ans == 's':
        ularn_win.Print(" sit down")
        k = rnd(101)
        if k < 5:
            player.raiselevel()
        elif k < 25:
            ularn_win.Print("\nZaaaappp!  You've been teleported!\n")
            ularn_win.UlarnBeep()
            oteleport(0)
        else:
            ularn_win.Print("\nNothing happens.")

    elif ans == 'i' or ans == ESC:
        ularn_win.Print(" ignore")


def ofountain():
    """Processes player stepping onto a fountain."""
    c = player.c
    level = dungeon.level

    ans = ularn_win.get_prompt_input(
        "\nDo you (d) drink, (w) wash yourself, or (i) ignore it? ",
        "dwi\033", 1)

    if ans == 'd':
        ularn_win.Print("drink")
        if rnd(1501) < 4:
            ularn_win.Print("\nOH MY GOD!! You have caught the *dreadful sleep*!")
            ularn_win.UlarnBeep()
            ularn_win.nap(3000)
            scores.died(scores.DIED_DREADFUL_SLEEP, 0)
            return
        else:
            x = rnd(100)
            if x == 1:
                player.raiselevel()
            elif x < 11:
                x = rnd((level << 2) + 2)
                ularn_win.Printf("\nBleah! The water tasted like stale gatorade!  You lose %d hit point%s!",
                                 x, plural(x))

                player.losehp(scores.DIED_DRANK_POISONOUS_WATER, x)
                ularn_win.UpdateStatus()
            elif x < 14:
                c[player.HALFDAM] += 200 + rnd(200)
                ularn_win.Print("\nThe water makes you vomit.")
            elif x < 17:
                # Same effect as giant strength
                ularn_win.Print("\n  You now have incredible bulging muscles!")
                if c[player.GIANTSTR] == 0:
                    c[player.STREXTRA] += potion.PGIANTSTR_BOOST
                c[player.GIANTSTR] += 700
                ularn_win.UpdateEffects()
            elif x < 45:
                ularn_win.Print("\nNothing seems to have happened.")
            elif rnd(3) != 2:
                fntchange(1)  # change char levels upward
            else:
                fntchange(-1)  # change char levels downward

            if rnd(12) < 3:
                ularn_win.Print("\nThe fountains bubbling slowly quietens.")
                # dead fountain
                dungeon.item[player.playerx][player.playery] = itm.ODEADFOUNTAIN

    elif ans == 'i' or ans == ESC:
        ularn_win.Print(" ignore")

    elif ans == 'w':
        ularn_win.Print("wash yourself.")
        if rnd(100) < 11:
            x = rnd((level << 2) + 2)
            ularn_win.Printf("\nThe water burns like acid!  You lose %d hit point%s!",
                             x, plural(x))

            player.losehp(scores.DIED_DRANK_POISONOUS_WATER, x)
            ularn_win.UpdateStatus()
        elif rnd(100) < 29:
            ularn_win.Print("\nYou are now clean.")
            if c[player.ITCHING]:
                #
                # Managed to get rid of the itching powder, so set it so the
                # next call to regen will cancel the effect.
                #
                c[player.ITCHING] = 1
        elif rnd(100) < 31:
            ularn_win.Print("\nThis water needs soap -- the dirt didn't come off.")
        elif rnd(100) < 34:
            monster.createmonster(monster.WATERLORD)
        else:
            ularn_win.Print("\nNothing seems to have happened.")


def _find_object(obj):
    """Put the player on the first `obj` found scanning x then y (as the C
    stair loops do).  The player position is unchanged if none is found."""
    for x in range(dungeon.MAXX):
        for y in range(dungeon.MAXY):
            if dungeon.item[x][y] == obj:
                player.playerx = x
                player.playery = y
                return


def ostairs(dir):
    """Processes player stepping onto the stairs (dir > 0 up, < 0 down)."""
    ularn_win.Print("\nDo you (s) stay here  or  ")
    if dir > 0:
        ularn_win.Print("(u) go up?  ")
    else:
        ularn_win.Print("(d) go down?  ")

    ans = ularn_win.get_prompt_input("", "sudi\033", 1)

    if ans in (ESC, 's', 'i'):
        ularn_win.Print("stay here.")
        return

    elif ans == 'u':
        ularn_win.Print("go up.")
        if dir < 0:
            ularn_win.Print("\nThe stairs don't go up!")
        else:
            # not on V1
            if (dungeon.level >= 2) and (dungeon.level != (dungeon.DBOTTOM + 1)):
                dungeon.newcavelevel(dungeon.level - 1)
                _find_object(itm.OSTAIRSDOWN)

                if dungeon.mitem[player.playerx][player.playery].mon != monster.MONST_NONE:
                    #
                    # A monster is on the stairs, so find an empty position for
                    # the player.
                    #
                    player.positionplayer()

                ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
                ularn_win.UpdateStatusAndEffects()
            else:
                ularn_win.Print("\nThe stairs lead to a dead end!")

    elif ans == 'd':
        ularn_win.Print("go down.")
        if dir > 0:
            ularn_win.Print("\nThe stairs don't go down!")
        else:
            # not on dungeon bottom or V5
            if ((dungeon.level != 0) and (dungeon.level != dungeon.DBOTTOM) and
                    (dungeon.level != dungeon.VBOTTOM)):
                dungeon.newcavelevel(dungeon.level + 1)
                _find_object(itm.OSTAIRSUP)

                if dungeon.mitem[player.playerx][player.playery].mon != monster.MONST_NONE:
                    #
                    # A monster is on the stairs, so find an empty position for
                    # the player.
                    #
                    player.positionplayer()

                ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
                ularn_win.UpdateStatusAndEffects()
            else:
                ularn_win.Print("\nThe stairs lead to a dead end!")


def oteleport(err):
    """Processes player stepping onto a teleport trap, and all other reasons
    for teleporting the player.
    """
    c = player.c
    DBOTTOM = dungeon.DBOTTOM
    VBOTTOM = dungeon.VBOTTOM
    level = dungeon.level

    if err:
        if rnd(151) < 3:
            # stuck in a rock if the player can't walk through walls
            if c[player.WTW] == 0:
                scores.died(scores.DIED_TRAPPED_IN_SOLID_ROCK, 0)
                return

    # show ?? on bottomline if been teleported
    if not player.wizard:
        c[player.TELEFLAG] = 1

    if level == 0:
        tmp = 0
    elif level <= DBOTTOM:
        # in dungeon
        tmp = rnd(5) + level - 3
        if tmp > DBOTTOM:
            tmp = DBOTTOM
        if tmp < 0:
            tmp = 0
    else:
        # in volcano
        tmp = rnd(4) + level - 2

        if tmp >= VBOTTOM:
            tmp = VBOTTOM
        if tmp < DBOTTOM + 1:
            # back to surface
            tmp = 0

    player.playerx = rnd(dungeon.MAXX - 2)
    player.playery = rnd(dungeon.MAXY - 2)
    if level != tmp:
        dungeon.newcavelevel(tmp)
    else:
        player.positionplayer()
    ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
    ularn_win.UpdateStatusAndEffects()


def opit():
    """Processes player stepping onto a pit."""
    c = player.c
    level = dungeon.level

    if rnd(101) > 81:
        return

    if (rnd(70) > (9 * c[player.DEXTERITY] - player.packweight())) or (rnd(101) < 5):
        # Never fall into a pit if the player has a wand of wonder
        if player.player_has_item(itm.OWWAND):
            ularn_win.Print("\nYou float right over the pit.")
            return

        if level == dungeon.DBOTTOM or level == dungeon.VBOTTOM:
            # Pits on the bottom of the dungeon or volcano are bottomless
            obottomless()
        else:
            if rnd(101) < 20:
                i = 0
                ularn_win.Print("\nYou fell ino a pit!  A poor monster cushions your fall!\n")
            else:
                i = rnd(level * 3 + 3)
                if i > c[player.HP]:
                    i = c[player.HP]

                ularn_win.Printf("\nYou fell into a pit!  You suffer %d hit point%s damage.",
                                 i, plural(i))

            player.losehp(scores.DIED_FELL_INTO_PIT, i)
            ularn_win.nap(2000)
            dungeon.newcavelevel(level + 1)
            ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)


def oelevator(dir):
    """Processes player stepping onto an elevator (dir == 1 up, else down)."""
    DBOTTOM = dungeon.DBOTTOM
    VBOTTOM = dungeon.VBOTTOM
    level = dungeon.level

    if dir == 1:
        # going up
        if level == 0:
            ularn_win.Print(",\nunfortunately, it is out of order.")
            return

        player.playerx = rnd(dungeon.MAXX - 2)
        player.playery = rnd(dungeon.MAXY - 2)
        ularn_win.nap(2000)
        if level <= DBOTTOM:
            # In dungeon
            dungeon.newcavelevel(rund(level))
        else:
            # In volcano
            new_level = DBOTTOM + rund(level - DBOTTOM)
            if new_level == DBOTTOM:
                new_level = 0
            dungeon.newcavelevel(new_level)
    else:
        # going down
        if (level == DBOTTOM) or (level == VBOTTOM):
            ularn_win.nap(2000)
            ularn_win.Print("\nand it leads straight to HELL!")
            ularn_win.UlarnBeep()
            ularn_win.nap(3000)
            scores.died(scores.DIED_ELEVATOR_TO_HELL, 0)
            return
        player.playerx = rnd(dungeon.MAXX - 2)
        player.playery = rnd(dungeon.MAXY - 2)
        ularn_win.nap(2000)

        if level < DBOTTOM:
            # In dungeon
            dungeon.newcavelevel(level + rnd(DBOTTOM - level))
        else:
            # in volcano
            dungeon.newcavelevel(level + rnd(VBOTTOM - level))

    ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
    ularn_win.UpdateStatusAndEffects()


def ostatue():
    """Processes player stepping onto a statue."""
    pass  # nothing happens when you move on a statue


def omirror():
    """Processes player stepping onto a mirror."""
    pass  # nothing happens when you move on a mirror
