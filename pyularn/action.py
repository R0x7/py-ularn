"""Player actions (port of action.c / action.h).

EXPORTED FUNCTIONS
  run       : Move in a direction until something interesting happens
  wield     : Wield an item
  wear      : Wear armour or shield
  dropobj   : Drop an object
  readscr   : Read a scroll or a book from the inventory
  eatcookie : Eat a cookie in inventory, and display fortune if possible.
  quaff     : Drink a potion in inventory
  opendoor  : Open a closed door (enhanced interface only)
  closedoor : Close an open door
  openchest : Open a chest at the current location (enhanced interface only)
  quit      : Asks if really want to quit.
  do_create : Create an item (wizard only)
"""

from .header import *
from . import (ularn_game, ularn_win, ularn_ask, savegame as savegame_, itm, player,
               monster, dungeon, dungeon_obj, object as object_, potion, scroll,
               show, fortune as fortune_, scores)

# =============================================================================
# Local variables

# Possible answers to various selections
SelectItemAns = "abcdefghijklmnopqrstuvwxyz*\033"
SelectDropAns = "abcdefghijklmnopqrstuvwxyz*.\033"
SelectWieldAns = "abcdefghijklmnopqrstuvwxyz*-\033"

# Types of uses of an item
USE_WIELD = 0
USE_QUAFF = 1
USE_READ = 2
USE_WEAR = 3
USE_EAT = 4
USE_DROP = 5
USE_COUNT = 6

# String for each use
UseStrings = [
    "wield",
    "quaff",
    "read",
    "wear",
    "eat",
    "drop",
]


def _dirsub():
    """Call ularn_ask.dirsub (C: int dirsub(int *x, int *y)).

    Returns (d, x, y).
    """
    return ularn_ask.dirsub(0, 0)


# =============================================================================
# Local functions

def ydhi(x):
    """Print the 'you don't have item' message (x is the item letter)."""
    ularn_win.Printf("\nYou don't have item %c!", x)


def ycwi(x):
    """Print the 'you can't wield item' message (x is the item letter)."""
    ularn_win.Printf("\nYou can't wield item %c!", x)


def whatitem(Use):
    """Ask the player what item to use for a particular use.

    Returns the character input: the item letter (a .. z), '*' for show list,
    '-' for nothing (wield only), '.' for gold (drop only) or ESC for abort.
    """
    tmp = []

    if Use == USE_DROP:
        tmp.append('.')

    for j in range(player.IVENSIZE):
        it = player.iven[j]
        if it == itm.ONOTHING:
            ItemUse = USE_COUNT
        elif it in (itm.OSWORDofSLASHING, itm.OHAMMER, itm.OSWORD, itm.O2SWORD,
                    itm.OSPEAR, itm.ODAGGER, itm.OBATTLEAXE, itm.OLONGSWORD,
                    itm.OFLAIL, itm.OSLAYER, itm.OLANCE, itm.OVORPAL):
            ItemUse = USE_WIELD
        elif it == itm.OPOTION:
            ItemUse = USE_QUAFF
        elif it in (itm.OSCROLL, itm.OBOOK):
            ItemUse = USE_READ
        elif it in (itm.OPLATE, itm.OCHAIN, itm.OLEATHER, itm.ORING,
                    itm.OSTUDLEATHER, itm.OSPLINT, itm.OPLATEARMOR,
                    itm.OSSPLATE, itm.OSHIELD, itm.OELVENCHAIN):
            ItemUse = USE_WEAR
        elif it == itm.OCOOKIE:
            ItemUse = USE_EAT
        else:
            ItemUse = USE_DROP

        if (ItemUse != USE_COUNT) and ((Use == USE_DROP) or (ItemUse == Use)):
            tmp.append(chr(j + ord('a')))

    prompt = "\nWhat do you want to %s [%s * for all%s] ?" % (
        UseStrings[Use],
        "".join(tmp),
        " - for none" if (Use == USE_WIELD) else "")

    if Use == USE_WIELD:
        Ans = ularn_win.get_prompt_input(prompt, SelectWieldAns, 1)
    elif Use == USE_DROP:
        Ans = ularn_win.get_prompt_input(prompt, SelectDropAns, 1)
    else:
        Ans = ularn_win.get_prompt_input(prompt, SelectItemAns, 1)

    if Ans == ESC:
        ularn_win.Print(" aborted.")

    return Ans


# =============================================================================
# Exported functions

def run(dir):
    """Move the player in the input direction until something interesting."""
    i = 1
    while i:
        i = player.moveplayer(dir)
        if i > 0:
            if player.c[player.HASTEMONST]:
                monster.movemonst()
            monster.movemonst()
            monster.randmonst()
            player.regen()
        if player.hitflag:
            i = 0
        if i != 0:
            ularn_win.showcell(player.playerx, player.playery)


def wield():
    """Ask the player what to wield and wield it."""
    c = player.c
    iven = player.iven

    while True:
        i = whatitem(USE_WIELD)
        if i == ESC:
            return
        elif i == '*':
            show.showwield()
        elif i == '-':
            c[player.WIELD] = -1
            ularn_win.Print("\nYou unwield your weapon.")
            player.recalc()
            ularn_win.UpdateStatus()
            return
        elif ('a' <= i <= 'z'):
            it = ord(i) - ord('a')
            if iven[it] == itm.ONOTHING:
                ydhi(i)
                return
            elif iven[it] == itm.OPOTION:
                ycwi(i)
                return
            elif iven[it] == itm.OSCROLL:
                ycwi(i)
                return
            elif (c[player.SHIELD] != -1) and (iven[it] == itm.O2SWORD):
                ularn_win.Print("\nBut one arm is busy with your shield!")
                return
            elif (c[player.WEAR] == it) or (c[player.SHIELD] == it):
                ularn_win.Printf("\nYou can't wield your %s while you're wearing it!",
                                 "armor" if (c[player.WEAR] == it) else "shield")
                return
            else:
                c[player.WIELD] = it
                ularn_win.Printf("\nYou wield %s", itm.objectname[iven[it]])
                show.show_plusses(player.ivenarg[it])
                ularn_win.Printc('.')
                player.recalc()
                ularn_win.UpdateStatus()
                return


def wear():
    """Wear armour or a shield."""
    c = player.c
    iven = player.iven

    while True:
        i = whatitem(USE_WEAR)
        if i == ESC:
            return
        elif i == '*':
            show.showwear()
        elif ('a' <= i <= 'z'):
            it = ord(i) - ord('a')
            t = iven[it]
            if t == itm.ONOTHING:
                ydhi(i)
                return
            elif t in (itm.OLEATHER, itm.OCHAIN, itm.OPLATE, itm.OSTUDLEATHER,
                       itm.ORING, itm.OSPLINT, itm.OPLATEARMOR,
                       itm.OELVENCHAIN, itm.OSSPLATE):
                if c[player.WEAR] != -1:
                    ularn_win.Print("\nYou are already wearing some armor.")
                    return
                c[player.WEAR] = it
                if c[player.WIELD] == it:
                    c[player.WIELD] = -1
                ularn_win.Printf("\nYou put on your %s", itm.objectname[iven[it]])
                show.show_plusses(player.ivenarg[it])
                ularn_win.Printc('.')
                player.recalc()
                ularn_win.UpdateStatus()
                return
            elif t == itm.OSHIELD:
                if c[player.SHIELD] != -1:
                    ularn_win.Print("\nYou are already wearing a shield.")
                    return
                # C indexes iven[-1] when nothing is wielded (undefined);
                # treat "nothing wielded" as not a two handed sword.
                if (c[player.WIELD] >= 0) and (iven[c[player.WIELD]] == itm.O2SWORD):
                    ularn_win.Print("\nYour hands are busy with the two handed sword!")
                    return
                c[player.SHIELD] = it
                if c[player.WIELD] == it:
                    c[player.WIELD] = -1
                ularn_win.Print("\nYou put on your shield")
                show.show_plusses(player.ivenarg[it])
                ularn_win.Printc('.')
                player.recalc()
                ularn_win.UpdateStatus()
                return
            else:
                ularn_win.Print("\nYou can't wear that!")


def dropobj():
    """Drop an object (or some gold) from the player's inventory."""
    c = player.c
    pitflag = 0
    px = player.playerx
    py = player.playery

    while True:
        i = whatitem(USE_DROP)
        if i == ESC:
            return
        if i == '*':
            show.showstr()
        else:
            # drop some gold
            if i == '.':
                p = dungeon.item[px][py]
                if p == itm.OPIT:
                    pitflag = 1
                if (p != itm.ONOTHING) and not pitflag:
                    ularn_win.Print("\nThere's something here already!")
                    return
                ularn_win.Print("\n\n")
                ularn_win.Print("How much gold do you drop? ")
                amt = ularn_win.get_num_input(c[player.GOLD])
                if amt <= 0:
                    return
                if amt > c[player.GOLD]:
                    ularn_win.Print("\nYou don't have that much!")
                    return

                if amt <= 32767:
                    dungeon.item[px][py] = itm.OGOLDPILE
                    n = amt
                elif amt <= 327670:
                    dungeon.item[px][py] = itm.ODGOLD
                    n = amt // 10
                    amt = 10 * n
                elif amt <= 3276700:
                    dungeon.item[px][py] = itm.OMAXGOLD
                    n = amt // 100
                    amt = 100 * n
                elif amt <= 32767000:
                    dungeon.item[px][py] = itm.OKGOLD
                    n = amt // 1000
                    amt = 1000 * n
                else:
                    dungeon.item[px][py] = itm.OKGOLD
                    n = 32767
                    amt = 32767000

                c[player.GOLD] -= amt
                ularn_win.Printf(" You drop %d gold piece%s.", amt, plural(amt))

                if pitflag:
                    dungeon.item[px][py] = itm.OPIT
                    ularn_win.Print("\nThe gold disappears down the pit.")
                else:
                    dungeon.iarg[px][py] = n

                ularn_win.UpdateStatus()
                ularn_game.dropflag = 1
                return
            else:
                player.drop_object(ord(i) - ord('a'))
                return


def readscr():
    """Read a scroll or book being carried."""
    iven = player.iven
    while True:
        i = whatitem(USE_READ)
        if i == ESC:
            return
        if i != '.':
            if i == '*':
                show.showread()
            else:
                k = ord(i) - ord('a')
                if iven[k] == itm.OSCROLL:
                    scroll.read_scroll(player.ivenarg[k])
                    iven[k] = itm.ONOTHING
                    return
                if iven[k] == itm.OBOOK:
                    scroll.readbook(player.ivenarg[k])
                    iven[k] = itm.ONOTHING
                    return
                if iven[k] == itm.ONOTHING:
                    ydhi(i)
                    return
                ularn_win.Print("\nThere's nothing on it to read.")
                return


def eatcookie():
    """Eat a cookie one is carrying."""
    iven = player.iven
    while True:
        i = whatitem(USE_EAT)
        if i == ESC:
            return
        if i != '.':
            if i == '*':
                show.showeat()
            elif iven[ord(i) - ord('a')] == itm.OCOOKIE:
                ularn_win.Print("\nThe cookie was delicious.")
                iven[ord(i) - ord('a')] = itm.ONOTHING
                if not player.c[player.BLINDCOUNT]:
                    p = fortune_.fortune(ularn_game.fortfile)
                    if p is not None:
                        ularn_win.Print("  Inside you find a scrap of paper that says:\n")
                        ularn_win.Print(p)
                return
            elif iven[ord(i) - ord('a')] == itm.ONOTHING:
                ydhi(i)
                return
            else:
                ularn_win.Print("\nYou can't eat that!")
                return


def quaff():
    """Quaff a potion being carried."""
    iven = player.iven
    while True:
        i = whatitem(USE_QUAFF)
        if i == ESC:
            return
        if i != '.':
            if i == '*':
                show.showquaff()
            elif iven[ord(i) - ord('a')] == itm.OPOTION:
                potion.quaffpotion(player.ivenarg[ord(i) - ord('a')])
                iven[ord(i) - ord('a')] = itm.ONOTHING
                return
            elif iven[ord(i) - ord('a')] == itm.ONOTHING:
                ydhi(i)
                return
            else:
                ularn_win.Print("\nYou wouldn't want to quaff that, would you? ")
                return


def _no_door_msg():
    if player.c[player.BLINDCOUNT] == 0:
        ularn_win.Print("\nYou see no door there.")
    else:
        ularn_win.Print("\nYou cannot feel any door there.")


def opendoor():
    """Open a closed door near the player (enhanced interface only)."""
    if not ularn_game.enhance_interface:
        return

    # can't move objects is time is stopped
    if player.c[player.TIMESTOP]:
        ularn_win.Printf("\nNothing can be moved while time is stopped!")
        return

    d, dx, dy = _dirsub()

    # don't ask about items at player's location after trying to open a door
    ularn_game.dropflag = 1

    if not dungeon.checkxy(dx, dy):
        _no_door_msg()
    else:
        if dungeon.item[dx][dy] == itm.OOPENDOOR:
            ularn_win.Print("\nThat door is already open.")
        elif dungeon.item[dx][dy] != itm.OCLOSEDDOOR:
            _no_door_msg()
        else:
            dungeon_obj.oopendoor(dx, dy)
            if dungeon.item[dx][dy] == itm.OOPENDOOR:
                ularn_win.Print("\nThe door opens.")
            else:
                ularn_win.Print("\nThe door resists.")


def closedoor():
    """Close an open door (adjacent with enhanced interface, else here)."""
    # can't move objects is time is stopped
    if player.c[player.TIMESTOP]:
        ularn_win.Printf("\nNothing can be moved while time is stopped!")
        return

    ularn_win.showcell(player.playerx, player.playery)

    if ularn_game.enhance_interface:
        d, dx, dy = _dirsub()

        # don't ask about items at player's location after trying to close a door
        ularn_game.dropflag = 1

        if not dungeon.checkxy(dx, dy):
            _no_door_msg()
        else:
            if dungeon.item[dx][dy] == itm.OCLOSEDDOOR:
                ularn_win.Print("\nThat door is already closed.")
            elif dungeon.item[dx][dy] != itm.OOPENDOOR:
                _no_door_msg()
            else:
                dungeon.item[dx][dy] = itm.OCLOSEDDOOR
                dungeon.iarg[dx][dy] = 0  # Clear traps on door
                ularn_win.Print("\nThe door closes.")
    else:
        px = player.playerx
        py = player.playery
        i = dungeon.item[px][py]
        if i != itm.OOPENDOOR:
            ularn_win.Print("\nThere is no open door here.")
            return
        ularn_win.Print("\nThe door closes.")
        # forget() macro
        dungeon.item[px][py] = itm.ONOTHING
        dungeon.know[px][py] = itm.ONOTHING
        dungeon.item[px][py] = itm.OCLOSEDDOOR
        dungeon.iarg[px][py] = 0
        ularn_game.dropflag = 1  # So we won't be asked to open it


def openchest():
    """Open a chest at the player's current location."""
    if dungeon.item[player.playerx][player.playery] != itm.OCHEST:
        ularn_win.Print("\nThere isn't a chest to open here.")
    else:
        object_.oopenchest()
        ularn_game.dropflag = 1  # so we don't get asked to open it again


def quit():
    """Ask if the player really wants to quit."""
    monster.lastmonst = ""
    i = ularn_win.get_prompt_input(
        "\n\nDo you really want to quit? (y)es, (n)o, (s)ave", "yns\033", 1)

    if i == 'y':
        scores.died(scores.DIED_QUICK_QUIT, 0)
    elif i == 'n' or i == ESC:
        ularn_win.Print(" no.")
    elif i == 's':
        ularn_win.Print(" save.")
        ularn_win.Print("\nSaving...")
        savegame_.savegame(ularn_game.savefilename)
        player.wizard = 1
        scores.died(scores.DIED_SUSPENDED, 0)


def do_create():
    """Create an item or monster (wizard only)."""
    while True:
        Retry = 0
        t = ularn_win.get_prompt_input(
            "\nType of item (Scroll/Potion/Monster/Other) : ", "SsPpMmOo\033", 1)

        px = player.playerx
        py = player.playery

        if t == ESC:
            pass
        elif t in ('s', 'S'):
            ularn_win.Print(" Scroll Arg: ")
            a = ularn_win.get_num_input(scroll.MAXSCROLL)
            ularn_win.Printf("\ncreateitem(OSCROLL, %d)", a)
            dungeon.createitem(px, py, itm.OSCROLL, a)
            ularn_game.dropflag = 1
        elif t in ('p', 'P'):
            ularn_win.Print(" Potion Arg: ")
            a = ularn_win.get_num_input(potion.MAXPOTION)
            ularn_win.Printf("\ncreateitem(OPOTION, %d)", a)
            dungeon.createitem(px, py, itm.OPOTION, a)
            ularn_game.dropflag = 1
        elif t in ('o', 'O'):
            ularn_win.Print("\n\n")
            ularn_win.Print("Item : ")
            t = ularn_win.get_num_input(0)
            ularn_win.Print("Arg : ")
            a = ularn_win.get_num_input(0)
            ularn_win.Printf("\ncreateitem(%d, %d)", t, a)
            dungeon.createitem(px, py, t, a)
            ularn_game.dropflag = 1
        elif t in ('m', 'M'):
            ularn_win.Print("\n\n")
            ularn_win.ClearToEOPage(1, 23)
            ularn_win.Print("Monst : ")
            t = ularn_win.get_num_input(0)
            ularn_win.Printf("\ncreatemonster(%d)", t)
            monster.createmonster(t)
            ularn_game.dropflag = 1
        else:
            Retry = 1

        if not Retry:
            break
