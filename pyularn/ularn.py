"""Main module for ularn: setup and main processing loop (port of ularn.c).

``run_game(terminal, argv)`` runs a whole game on the given Terminal and
returns the exit code when the game ends (so it can run in a thread);
``main(argv)`` runs it on a curses terminal.
"""

import argparse
import os
import sys

from .header import *
from . import ularn_game, ularn_win, ularn_ask, savegame, scores, dungeon_obj
from . import dungeon, player, monster, action, potion, scroll, spell, show
from . import diag, itm
from . import object as object_
from . import help as help_

# =============================================================================
# Local variables
# =============================================================================

BUFSZ = 256   # for getlin buffers
MAX_CMDLINE_PARAM = 255

copyright = (
    "\nUlarn created by Phil Cordier -- based on Larn by Noah Morgan\n"
    "  Updated by Josh Brandt and David Richerby\n"
    "  Rewrite and Windows32/X11/Amiga graphics conversion by Julian Olds")

cmdhelp = (
    "Cmd line format: Ularn [-sicnh] [-o <optsfile>] [-d #] [-r]\n"
    "  -s   show the scoreboard\n"
    "  -i   show scoreboard with inventories\n"
    "  -c   create new scoreboard (wizard only)\n"
    "  -n   suppress welcome message on starting game\n"
    "  -h   print this help text\n"
    "  -o <optsfile> specify .Ularnopts file to be used instead of \"~/.Ularnopts\"\n"
    "  -d # specify level of difficulty (example: Ularn -d 5)\n"
    "  -r   restore checkpoint (.ckp) file\n")

optstring = "sicnhro:d:"

viewflag = 0

# =============================================================================
# Local functions
# =============================================================================


class _OptError(Exception):
    pass


class _ArgParser(argparse.ArgumentParser):
    """ArgumentParser that reports errors instead of exiting."""

    def error(self, message):
        raise _OptError(message)


def _make_parser():
    p = _ArgParser(prog="ularn", add_help=False, allow_abbrev=False)
    p.add_argument("-s", action="store_true", dest="s")
    p.add_argument("-i", action="store_true", dest="i")
    p.add_argument("-c", action="store_true", dest="c")
    p.add_argument("-n", action="store_true", dest="n")
    p.add_argument("-h", action="store_true", dest="h")
    p.add_argument("-r", action="store_true", dest="r")
    p.add_argument("-o", dest="o", action="append")
    p.add_argument("-d", dest="d", action="append")
    return p


def _atoi(s):
    """C atoi(): optional sign and leading digits, 0 if none."""
    s = s.lstrip()
    i = 0
    sign = 1
    if i < len(s) and s[i] in "+-":
        if s[i] == "-":
            sign = -1
        i += 1
    v = 0
    while i < len(s) and s[i].isdigit():
        v = v * 10 + (ord(s[i]) - ord("0"))
        i += 1
    return sign * v


def _show_cmdhelp():
    """The '-h' / '?' (bad option) case of the C option switch."""
    ularn_win.Printf("%s", copyright)
    ularn_win.Printf("\n\n  Version %s.%s (%s)", LARN_VERSION, LARN_PATCHLEVEL, LARN_DATE)
    ularn_win.Printf("\n\n%s", cmdhelp)
    ularn_win.get_prompt_input("\n\nPress space to exit", " ", 0)

    scores.endgame()


def ULarnSetup(argv):
    """Perform once off initialisation and parse the command parameters.

    C signature ULarnSetup(int argc, char *argv[]); argv[0] is the program
    name as in C.
    """
    # clear the loginname and logname
    ularn_game.loginname = ""
    ularn_game.logname = ""

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()

    ularn_win.nap(100)

    home = os.path.expanduser("~")

    # set the save directory (C: the home directory; here ~/.pyularn)
    ularn_game.savedir = user_dir()

    # initialize dungeon storage
    dungeon.init_cells()

    # set the initial clock and initialise the random number generator
    ularn_game.newgame()
    hard = -1
    restore_ckp = 0
    set_optfile = 0
    reset_scores = 0
    show_scores = 0

    #
    # now process the command line arguments
    #
    try:
        opts = _make_parser().parse_args(list(argv[1:]))
    except _OptError:
        # getopt returns '?' for a bad option, which prints the help text
        _show_cmdhelp()
        opts = None

    if opts is not None:
        if opts.s:
            show_scores = 1

        if opts.i:
            show_scores = 2

        if opts.c:
            reset_scores = 1

        if opts.n:
            ularn_game.nowelcome = 1

        if opts.d:
            for optarg in opts.d:
                # specify hardness
                hard = _atoi(optarg)
                if hard > 100:
                    hard = 100
                if hard < 0:
                    ularn_win.Printf("Difficulty level must be > 0\n")
                    ularn_win.Print(cmdhelp)
                    ularn_win.get_prompt_input("\n\nPress space to exit", " ", 0)

                    scores.endgame()

        if opts.h:
            # print out command line arguments
            _show_cmdhelp()

        if opts.o:
            # specify a Ularn.opt filename
            ularn_game.optsfile = opts.o[-1]
            set_optfile = 1

        if opts.r:
            # restore checkpointed game
            restore_ckp = 1

    # Options filename was not specified on the command line, so set default
    if not set_optfile:
        ularn_game.optsfile = os.path.join(home, ularn_game.optsfile)

    # read the options file if there is one
    ularn_game.read_options()

    #
    # Process scorefile initialisation
    #

    # the Ularn scoreboard filename
    ularn_game.scorefile = user_path(ularn_game.SCORENAME)

    if reset_scores:
        # anyone with password can create scoreboard
        ularn_win.Print("Preparing to initialize the scoreboard.\n")
        if ularn_ask.getpassword() != 0:
            if scores.makeboard() == -1:
                ularn_win.Print("Scoreboard creation failed!!\n")
                scores.endgame()
            scores.showscores()
            ularn_win.Print("\nScoreboard initialized.\n")
        scores.endgame()

    if show_scores == 1:
        scores.showscores()
        scores.endgame()
    elif show_scores == 2:
        scores.showallscores()
        scores.endgame()

    # now make scoreboard if it is not there (don't clear)
    if not os.path.exists(ularn_game.scorefile):
        # score file not there
        if scores.makeboard() == -1:
            ularn_win.Printf("I can't create the scoreboard.\n")
            ularn_win.Printf("Check permissions on %s\n", user_dir())
            scores.endgame()

    #
    # Get the user name and id.
    # For OS without usernames, use the logname, if it is specified.
    #
    ularn_game.loginname = ularn_game.logname
    ularn_game.loginname, ularn_game.userid = ularn_win.GetUser(ularn_game.loginname)

    if len(ularn_game.logname) == 0:
        # no logname specified, so use loginname
        ularn_game.logname = ularn_game.loginname

    #
    # Set the file names
    #

    # the Ularn on-line help file
    ularn_game.helpfile = data_path(ularn_game.HELPNAME)

    # the pre-made cave level data file
    ularn_game.larnlevels = data_path(ularn_game.LEVELSNAME)

    # the fortune data file name
    ularn_game.fortfile = data_path(ularn_game.FORTSNAME)

    # save file name in the save directory
    ularn_game.savefilename = os.path.join(
        ularn_game.savedir, "ularn_%s.sav" % ularn_game.loginname)

    # the checkpoint file
    ularn_game.ckpfile = os.path.join(
        user_dir(), "ularn_%s.ckp" % ularn_game.loginname)

    if restore_ckp:
        if not os.path.exists(ularn_game.ckpfile):
            ularn_win.Printf("Cannot find checkpoint file %s\n", ularn_game.ckpfile)
            scores.endgame()
        ularn_win.Printf("Restoring...")
        ularn_game.restorflag = 1
        player.hitflag = 1
        savegame.restoregame(ularn_game.ckpfile)

    # restore game if need to, and haven't restored ckpfile
    if (not ularn_game.restorflag) and os.path.exists(ularn_game.savefilename):
        ularn_game.restorflag = 1
        player.hitflag = 1
        ularn_win.Print("Restoring...")
        savegame.restoregame(ularn_game.savefilename)

    # create new game
    if ularn_game.restorflag == 0:
        # make the character that will play
        player.makeplayer()
        # make the dungeon
        dungeon.newcavelevel(0)

        if ularn_game.nowelcome == 0:
            # welcome the player to the game
            help_.welcome()

    # set up the desired difficulty
    ularn_game.sethard(hard)

    ularn_win.set_display(ularn_win.DISPLAY_MAP)

    ularn_win.showplayer()

    ularn_win.yrepcount = 0
    player.hit2flag = 0


def parse(Action):
    """Execute a command entered by the player."""
    global viewflag

    W = ularn_win
    c = player.c

    if Action == W.ACTION_DIAG:
        if player.wizard:
            diag.diag()
        W.yrepcount = 0
        return

    elif Action == W.ACTION_MOVE_WEST:
        player.moveplayer(4)
        return

    elif Action == W.ACTION_RUN_WEST:
        action.run(4)
        return

    elif Action == W.ACTION_MOVE_EAST:
        player.moveplayer(2)
        return

    elif Action == W.ACTION_RUN_EAST:
        action.run(2)
        return

    elif Action == W.ACTION_MOVE_SOUTH:
        player.moveplayer(1)
        return

    elif Action == W.ACTION_RUN_SOUTH:
        action.run(1)
        return

    elif Action == W.ACTION_MOVE_NORTH:
        player.moveplayer(3)
        return

    elif Action == W.ACTION_RUN_NORTH:
        action.run(3)
        return

    elif Action == W.ACTION_MOVE_NORTHEAST:
        player.moveplayer(5)
        return

    elif Action == W.ACTION_RUN_NORTHEAST:
        action.run(5)
        return

    elif Action == W.ACTION_MOVE_NORTHWEST:
        player.moveplayer(6)
        return

    elif Action == W.ACTION_RUN_NORTHWEST:
        action.run(6)
        return

    elif Action == W.ACTION_MOVE_SOUTHEAST:
        player.moveplayer(7)
        return

    elif Action == W.ACTION_RUN_SOUTHEAST:
        action.run(7)
        return

    elif Action == W.ACTION_MOVE_SOUTHWEST:
        player.moveplayer(8)
        return

    elif Action == W.ACTION_RUN_SOUTHWEST:
        action.run(8)
        return

    elif Action == W.ACTION_WAIT:
        if W.yrepcount:
            viewflag = 1
        return

    elif Action == W.ACTION_NONE:
        W.yrepcount = 0
        ularn_game.nomove = 1
        return

    elif Action == W.ACTION_WIELD:
        W.yrepcount = 0
        action.wield()
        return

    elif Action == W.ACTION_WEAR:
        W.yrepcount = 0
        action.wear()
        return

    elif Action == W.ACTION_READ:
        W.yrepcount = 0
        if c[player.BLINDCOUNT]:
            W.Print("\nYou can't read anything when you're blind!")
        elif c[player.TIMESTOP] == 0:
            action.readscr()
        return

    elif Action == W.ACTION_QUAFF:
        W.yrepcount = 0
        if c[player.TIMESTOP] == 0:
            action.quaff()
        return

    elif Action == W.ACTION_DROP:
        W.yrepcount = 0
        if c[player.TIMESTOP] == 0:
            action.dropobj()
        return

    elif Action == W.ACTION_CAST_SPELL:
        W.yrepcount = 0
        spell.cast()
        return

    elif Action == W.ACTION_OPEN_DOOR:
        W.yrepcount = 0
        action.opendoor()
        return

    elif Action == W.ACTION_CLOSE_DOOR:
        W.yrepcount = 0
        action.closedoor()
        return

    elif Action == W.ACTION_OPEN_CHEST:
        W.yrepcount = 0
        action.openchest()
        return

    elif Action == W.ACTION_INVENTORY:
        W.yrepcount = 0
        ularn_game.nomove = 1
        show.showstr()
        return

    elif Action == W.ACTION_EAT_COOKIE:
        W.yrepcount = 0
        if c[player.TIMESTOP] == 0:
            action.eatcookie()
        return

    elif Action == W.ACTION_LIST_SPELLS:
        W.yrepcount = 0
        show.seemagic(0)
        ularn_game.nomove = 1
        return

    elif Action == W.ACTION_HELP:
        W.yrepcount = 0
        help_.help()
        ularn_game.nomove = 1
        return

    elif Action == W.ACTION_SAVE:
        W.ClearText()
        W.Print("Saving . . .")

        if savegame.savegame(ularn_game.savefilename) == -1:
            W.Print("\nSave game failed.\n")
        player.wizard = 1   # so not show scores
        scores.died(scores.DIED_SUSPENDED, 0)
        return

    elif Action == W.ACTION_TELEPORT:
        W.yrepcount = 0
        if player.wizard:
            W.Print("\nWhich level do you wish to teleport to? ")
            t = int(W.get_num_input(20))
            if t > dungeon.VBOTTOM or t < 0:
                W.Print(" sorry!")
                return

            player.playerx = rnd(dungeon.MAXX - 2)
            player.playery = rnd(dungeon.MAXY - 2)
            dungeon.newcavelevel(t)
            player.positionplayer()
            W.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
            W.UpdateStatusAndEffects()
            return
        if c[player.LEVEL] >= player.INNATE_TELEPORT_LEVEL:
            dungeon_obj.oteleport(1)
            return

        W.Print("\nYou don't know how to teleport yet.")
        return

    elif Action == W.ACTION_IDENTIFY_TRAPS:
        flag = 0
        W.yrepcount = 0
        W.Printc("\n")
        j = player.playery - 1
        while j < player.playery + 2:
            if j < 0:
                j = 0
            if j >= dungeon.MAXY:
                break
            i = player.playerx - 1
            while i < player.playerx + 2:
                if i < 0:
                    i = 0
                if i >= dungeon.MAXX:
                    break
                it = dungeon.item[i][j]
                if it in (itm.OTRAPDOOR, itm.ODARTRAP, itm.OTRAPARROW,
                          itm.OTELEPORTER, itm.OELEVATORUP, itm.OELEVATORDOWN):
                    W.Print("\nIt's ")
                    W.Print(itm.objectname[it])
                    flag += 1
                i += 1
            j += 1
        if flag == 0:
            W.Print("\nNo traps are visible.")
        return

    elif Action == W.ACTION_BECOME_CREATOR:
        W.yrepcount = 0
        ularn_game.nomove = 1
        if not player.wizard:
            if ularn_ask.getpassword() == 0:
                return

        player.raiseexperience(370 * 1000000)

        player.recalc()
        W.UpdateStatus()
        W.drawscreen()
        return

    elif Action == W.ACTION_CREATE_ITEM:
        W.yrepcount = 0
        if player.wizard:
            action.do_create()
        return

    elif Action == W.ACTION_TOGGLE_WIZARD:
        W.yrepcount = 0
        ularn_game.nomove = 1
        if player.wizard:
            W.Print("\nYou are no longer a wizard.")
            player.wizard = 0
            return
        if ularn_ask.getpassword():
            W.Print("\nYou are now a wizard.")
            player.wizard = 1
        else:
            W.Print("Sorry.\n")
        return

    elif Action == W.ACTION_DEBUG_MODE:
        W.yrepcount = 0
        ularn_game.nomove = 1
        if not player.wizard:
            if ularn_ask.getpassword() == 0:
                return
            player.wizard = 1

        for i in range(6):
            c[i] = 70
        player.iven[0] = itm.ONOTHING
        player.iven[1] = itm.ONOTHING
        player.take(itm.OPROTRING, 50)
        player.take(itm.OLANCE, 25)
        for i in range(player.IVENSIZE):
            if player.iven[i] == itm.OLANCE and player.ivenarg[i] == 25:
                c[player.WIELD] = i
                break
        c[player.LANCEDEATH] = 1
        c[player.WEAR] = c[player.SHIELD] = -1
        player.raiseexperience(370 * 1000000)
        c[player.AWARENESS] += 25000

        # learn all spells, scrolls and potions
        # (the C code really sets potionknown[] in the scroll loop)
        for i in range(spell.SPELL_COUNT):
            player.spelknow[i] = 1
        for i in range(scroll.MAXSCROLL):
            player.potionknown[i] = 1
        for i in range(potion.MAXPOTION):
            player.potionknown[i] = 1

        for i in range(scroll.MAXSCROLL):
            if len(scroll.scrollname[i]) > 2:
                dungeon.item[i][0] = itm.OSCROLL
                dungeon.iarg[i][0] = i

        for i in range(potion.MAXPOTION):
            # no null items
            if len(potion.potionname[i]) > 2:
                dungeon.item[(dungeon.MAXX - 1) - i][0] = itm.OPOTION
                dungeon.iarg[(dungeon.MAXX - 1) - i][0] = i

        j = itm.OALTAR

        for i in range(1, dungeon.MAXY):
            dungeon.item[0][i] = j
            dungeon.iarg[0][i] = 0
            j += 1

        for i in range(1, dungeon.MAXX):
            dungeon.item[i][dungeon.MAXY - 1] = j
            dungeon.iarg[i][dungeon.MAXY - 1] = 0
            j += 1

        for i in range(1, dungeon.MAXY - 1):
            dungeon.item[dungeon.MAXX - 1][i] = j
            dungeon.iarg[dungeon.MAXX - 1][i] = 0
            j += 1

        for i in range(dungeon.MAXY):
            for j in range(dungeon.MAXX):
                dungeon.know[j][i] = dungeon.item[j][i]

        c[player.GOLD] += 250000

        player.recalc()
        W.UpdateStatus()
        W.drawscreen()
        return

    elif Action == W.ACTION_REMOVE_ARMOUR:
        W.yrepcount = 0

        if c[player.SHIELD] != -1:
            c[player.SHIELD] = -1
            W.Print("\nYour shield is off.")
            player.recalc()
            W.UpdateStatus()
        else:
            if c[player.WEAR] != -1:
                c[player.WEAR] = -1
                W.Print("\nYour armor is off.")
                player.recalc()
                W.UpdateStatus()
            else:
                W.Print("\nYou aren't wearing anything.")
        return

    elif Action == W.ACTION_PACK_WEIGHT:
        W.Printf("\nThe stuff you are carrying presently weighs %d pound%s.",
                 player.packweight(),
                 plural(player.packweight()))
        ularn_game.nomove = 1
        W.yrepcount = 0
        return

    elif Action == W.ACTION_VERSION:
        W.yrepcount = 0
        W.Printf("\nThe Addiction of Ularn -- Version %s.%s (%s)\nDifficulty level %d",
                 LARN_VERSION,
                 LARN_PATCHLEVEL,
                 LARN_DATE,
                 c[player.HARDGAME])
        if player.wizard:
            W.Print(" (WIZARD)")
        ularn_game.nomove = 1
        if player.cheat:
            W.Print(" (Cheater)")
        W.Print(copyright)
        return

    elif Action == W.ACTION_QUIT:
        W.yrepcount = 0
        action.quit()
        ularn_game.nomove = 1
        return

    elif Action == W.ACTION_REDRAW_SCREEN:
        W.yrepcount = 0
        W.drawscreen()
        ularn_game.nomove = 1
        return

    elif Action == W.ACTION_SHOW_TAX:
        if player.outstanding_taxes > 0:
            W.Printf("\nYou presently owe %d gp in taxes.", player.outstanding_taxes)
        else:
            W.Print("\nYou do not owe any taxes.")
        return

    else:
        W.Print("HELP! unknown command\n")


def _game(argv):
    """Body of the C main() after init_app()."""
    global viewflag

    viewflag = 0

    ULarnSetup(argv)

    # Everything should be common from here on

    while True:
        if ularn_game.dropflag == 0:
            object_.lookforobject()   # see if there is an object here
        else:
            ularn_game.dropflag = 0   # don't show it just dropped an item

        if player.hitflag == 0:
            if player.c[player.HASTEMONST]:
                monster.movemonst()

            monster.movemonst()

        if viewflag == 0:
            ularn_win.showcell(player.playerx, player.playery)
        else:
            viewflag = 0   # show stuff around player

        player.hitflag = 0
        player.hit3flag = 0

        ularn_game.nomove = 1

        # get commands and make moves
        while ularn_game.nomove:
            ularn_game.nomove = 0
            Action = ularn_win.get_normal_input()
            parse(Action)   # may reset nomove=1

        # regenerate hp and spells
        player.regen()

        if player.c[player.TIMESTOP] == 0:
            monster.rmst -= 1
            if monster.rmst <= 0:
                monster.rmst = 120 - (dungeon.level << 2)
                dungeon.fillmonst(monster.makemonst(dungeon.level))

        if Action == ularn_win.ACTION_QUIT:
            break

    #
    # tidyup and exit
    #
    scores.endgame()


def run_game(terminal, argv=None):
    """Run a whole game on `terminal` and return the exit code.

    `argv` is the full command line including the program name, as in C
    (default ["ularn"]).  Returns when the game ends (UlarnExit is caught),
    so this can be used as a thread target.
    """
    if argv is None:
        argv = ["ularn"]

    ularn_win.set_terminal(terminal)
    code = 0
    try:
        ularn_win.init_app()
        _game(argv)
    except UlarnExit as e:
        code = e.code
    finally:
        ularn_win.close_app()
        mark = getattr(terminal, "mark_finished", None)
        if mark is not None:
            mark()
    return code


def main(argv=None):
    """Run the game on a curses terminal (the C main())."""
    from . import term_curses

    if argv is None:
        argv = sys.argv
    try:
        term = term_curses.CursesTerminal()
    except RuntimeError as e:
        sys.stderr.write("%s\n" % e)
        return 1
    try:
        return run_game(term, argv)
    except KeyboardInterrupt:
        return 1
