"""Scoreboard display and update at the end of the game (port of scores.c / scores.h).

Exported functions:
  makeboard     : Create a new scoreboard (deleting the old one)
  hashewon      : Checks if the player has previously won.
  paytaxes      : Note the payment of taxes.
  showscores    : Display the scoreboard
  showallscores : Show scores including inventories.
  endgame       : Game tidyup and exit function.
  died          : Function to handle player dying.

Python port: the score file is stored as JSON at ularn_game.scorefile
(default header.user_path("Uscore")) instead of the binary struct dump.
"""

import json
import os

from .header import *
from . import ularn_game, ularn_win, ularn_ask, monster, itm, dungeon, player
from . import show, store, sphere

# =============================================================================
# scores.h definitions

# max number of people on a scoreboard max
SCORESIZE = 25

# Player died reasons (DiedReasonType)
DIED_MONSTER = 0
DIED_QUIT = 1
DIED_SUSPENDED = 2
DIED_SELF_ANNIHLATED = 3
DIED_SHOT_BY_ARROW = 4
DIED_HIT_BY_DART = 5
DIED_FELL_INTO_PIT = 6
DIED_FELL_INTO_BOTTOMLESS_PIT = 7
DIED_WINNER = 8
DIED_TRAPPED_IN_SOLID_ROCK = 9
DIED_MISSING_SAVE_FILE = 10
DIED_OLD_SAVE_FILE = 11
DIED_GREEDY_CHEATER = 12
DIED_PROTECTED_SAVE_FILE = 13
DIED_KILLED_FAMILY = 14
DIED_ERASED_BY_WAYWARD_FINGER = 15
DIED_FELL_THROUGH_BOTTOMLESS_TRAPDOOR = 16
DIED_FELL_THROUGH_TRAPDOOR = 17
DIED_DRANK_POISONOUS_WATER = 18
DIED_ELECTRIC_SHOCK = 19
DIED_SLIPPED_VOLCANO_SHAFT = 20
DIED_STUPIDITY = 21
DIED_ATTACKED_BY_DEMON = 22
DIED_OWN_MAGIC = 23
DIED_UNSEEN_ATTACKER = 24
DIED_DREADFUL_SLEEP = 25
DIED_EXPLODING_CHEST = 26
DIED_INTERNAL_COMPLICATIONS = 27
DIED_SPHERE_ANNIHILATION = 28
DIED_POST_MORTEM_DEATH = 29
DIED_MALLOC_FAILURE = 30
DIED_ANNOYED_GENIE = 31
DIED_ELEVATOR_TO_HELL = 32
DIED_QUICK_QUIT = 33
DIED_COUNT = 34

# =============================================================================
# Local variables

# This is a header written to the scoreboard file for version identification
# If the scoreboard format doesn't match then make a new score board.
# If you change the score board format then increase SCORE_VERSION by 1
# to prevent ularn from  attempting to use old format scoreboards.
SCORE_VERSION = 1


class score_header_type:
    def __init__(self, Id, Format):
        self.Id = Id
        self.Format = Format


CurrentHeader = score_header_type("ulsb", SCORE_VERSION)


class score_type:
    """This is the structure for the scoreboard."""

    def __init__(self):
        self.score = 0        # the score of the player
        self.suid = 0         # the user id number of the player
        self.reason = 0       # the reason the player died
        self.what = 0         # the number of the monster that killed player
        self.level = 0        # the level player was on when he died
        self.hardlev = 0      # the level of difficulty player played at
        self.order = 0        # the relative ordering place of this entry
        self.who = ""         # the name of the character
        self.char_class = ""  # the character class
        # this is the inventory list of the character
        self.sciv = [[0, 0] for _ in range(player.IVENSIZE)]


class win_score_type:
    """This is the structure for the winning scoreboard."""

    def __init__(self):
        self.score = 0        # the score of the player
        self.timeused = 0     # the time used in mobuls to win the game
        self.taxes = 0        # taxes he owes to LRS
        self.suid = 0         # the user id number of the player
        self.hardlev = 0      # the level of difficulty player played at
        self.order = 0        # the relative ordering place of this entry
        self.who = ""         # the name of the character
        self.char_class = ""  # the character class


_SCORE_FIELDS = ("score", "suid", "reason", "what", "level", "hardlev",
                 "order", "who", "char_class", "sciv")
_WIN_FIELDS = ("score", "timeused", "taxes", "suid", "hardlev", "order",
               "who", "char_class")

# storage for the scoreboard (created lazily: needs player.IVENSIZE)
scoreboard = []

# storage for the winners scoreboard
winboard = []


def _init_boards():
    """Allocate the static score board arrays on first use."""
    if not scoreboard:
        scoreboard.extend(score_type() for _ in range(SCORESIZE))
    if not winboard:
        winboard.extend(win_score_type() for _ in range(SCORESIZE))


# Died reason messages
whydead = [
    "killed by a monster",
    "quit",
    "suspended",
    "self - annihilated",
    "shot by an arrow",
    "hit by a dart",
    "fell into a pit",
    "fell into a pit to HELL",
    "a winner",
    "trapped in solid rock",
    "killed by a missing save file",
    "killed by an old save file",
    "caught by the greedy cheater checker trap",
    "killed by a protected save file",
    "killed his family and committed suicide",
    "erased by a wayward finger",
    "fell through a trap door to HELL",
    "fell through a trap door",
    "drank some poisonous water",
    "fried by an electric shock",
    "slipped in a volcano shaft",
    "killed by a stupid act of frustration",
    "attacked by a revolting demon",
    "hit by his own magic",
    "demolished by an unseen attacker",
    "fell into the dreadful sleep",
    "killed by an exploding chest",
    "died of internal complications",
    "annihilated by a sphere",
    "died a post mortem death",
    "wasted by a malloc() failure",
    "wasted by an annoyed genie",
    "took an elevator straight to HELL",
]

# The last error reading/writing the score file
scorerror = 0

# The score to highlight when showing the score board
# This is set to the player's score if it is better that the previous score
highlight_pos = -1
highlight_win = 0


# =============================================================================
# Local functions

def calc_score(Winner):
    """Calculate the score for the player (Winner: 0 = non-winner, 1 = winner)."""
    c = player.c

    # Start by calculating the player's net worth, converting items to their
    # value in gold according to what the trading post would pay.
    # This is a bit mean for gems as the bank pays 5x this.
    gold_value = c[player.GOLD] + c[player.BANKACCOUNT]

    for idx in range(player.IVENSIZE):
        gold_value += store.item_value(player.iven[idx], player.ivenarg[idx])

    if not Winner:
        # If the player isn't a winner, devalue score value of gold by 1/10.
        gold_value -= cdiv(gold_value, 10)
    else:
        # bonus for winning
        gold_value += 100000 * c[player.HARDGAME]

    # Add score for the deepest level visited
    deepest = 0
    stupidity_penalty = 1
    for dlev in range(dungeon.NLEVELS):
        if dungeon.beenhere[dlev]:
            if dlev == dungeon.MAXLEVEL and deepest == 0:
                # The stupid player went directly into the volcano
                if Winner:
                    # If the player actually managed to WIN doing this (pretty
                    # unlikely) then give a reward
                    gold_value *= 2
                else:
                    stupidity_penalty = 1
            else:
                deepest = dlev

    if stupidity_penalty:
        deepest = 0
        gold_value = cdiv(gold_value, 2)

    # Calculate the final score
    score = gold_value + c[player.EXPERIENCE] + deepest * 50

    return score


def readboard():
    """Read in the scoreboard into the static buffers.

    Returns a negative value if unable to read in the scoreboard, 0 if all is OK.
    """
    _init_boards()
    scorefile = ularn_game.scorefile

    try:
        fp = open(scorefile, "r", encoding="utf-8")
    except OSError:
        ularn_win.Printf("Can't open scorefile '%s' for reading\n", scorefile)
        return -1

    with fp:
        try:
            data = json.load(fp)
            header = data["header"]
            hId = header["Id"]
            hFormat = header["Format"]
        except (ValueError, KeyError, TypeError):
            ularn_win.Print("Can't read score board header\n")
            return -2

        if str(hId)[:4] != CurrentHeader.Id[:4]:
            ularn_win.Print("Not a valid ularn score board\n")
            return -3

        if hFormat != CurrentHeader.Format:
            ularn_win.Print("Incorrect score board version\n")
            return -4

        try:
            sb = data["scoreboard"]
            if len(sb) != SCORESIZE:
                raise ValueError
            for i in range(SCORESIZE):
                ent = sb[i]
                for f in _SCORE_FIELDS:
                    if f not in ent:
                        raise ValueError
                for f in _SCORE_FIELDS:
                    if f == "sciv":
                        scoreboard[i].sciv = [[int(a), int(b)] for a, b in ent[f]]
                    else:
                        setattr(scoreboard[i], f, ent[f])
        except (ValueError, KeyError, TypeError):
            ularn_win.Print("Can't read scoreboard\n")
            return -5

        try:
            wb = data["winboard"]
            if len(wb) != SCORESIZE:
                raise ValueError
            for i in range(SCORESIZE):
                ent = wb[i]
                for f in _WIN_FIELDS:
                    if f not in ent:
                        raise ValueError
                for f in _WIN_FIELDS:
                    setattr(winboard[i], f, ent[f])
        except (ValueError, KeyError, TypeError):
            ularn_win.Print("Can't read scoreboard")
            return -6

    return 0


def writeboard():
    """Write the scoreboard from readboard()'s buffer.

    Returns -1 if unable to write the scoreboard, 0 if all is OK.
    """
    _init_boards()
    scorefile = ularn_game.scorefile

    data = {
        "header": {"Id": CurrentHeader.Id, "Format": CurrentHeader.Format},
        "scoreboard": [{f: getattr(s, f) for f in _SCORE_FIELDS} for s in scoreboard],
        "winboard": [{f: getattr(s, f) for f in _WIN_FIELDS} for s in winboard],
    }

    try:
        fp = open(scorefile, "w", encoding="utf-8")
    except OSError:
        ularn_win.Print("Can't open scorefile for writing\n")
        return -1

    with fp:
        try:
            json.dump(data, fp)
        except (OSError, TypeError, ValueError):
            ularn_win.Print("Can't write scorefile\n")
            return -1

    return 0


def sortboard():
    """Calculate the position of each score in the scoreboard.

    NOTE: Unused score entries must be assigned positions in order for the
    score update function to operate correctly.
    Returns 0 if no sorting done, else returns 1.
    """
    # mark all scores as unsorted
    for i in range(SCORESIZE):
        scoreboard[i].order = -1
        winboard[i].order = -1

    # work out the position of each score in the visitor's board
    for pos in range(SCORESIZE):
        # find the score in position pos
        largest_score = -1
        largest_score_idx = -1
        for i in range(SCORESIZE):
            if scoreboard[i].order < 0 and scoreboard[i].score >= largest_score:
                largest_score_idx = i
                largest_score = scoreboard[i].score

        if largest_score_idx >= 0:
            scoreboard[largest_score_idx].order = pos

    # work out the position of each score in the winner's board
    for pos in range(SCORESIZE):
        # find the score in position pos
        largest_score = -1
        largest_score_idx = -1
        for i in range(SCORESIZE):
            if winboard[i].order < 0 and winboard[i].score >= largest_score:
                largest_score_idx = i
                largest_score = winboard[i].score

        if largest_score_idx >= 0:
            winboard[largest_score_idx].order = pos

    return 1


def newscore(score, winner, died_reason, what):
    """Add entry to scoreboard.

    Returns the new position on the scoreboard if the player made the high
    score list (else -1).
    """
    c = player.c
    userid = ularn_game.userid

    gold = c[player.GOLD] + c[player.BANKACCOUNT]

    if readboard() < 0:
        return -1

    if player.cheat:
        # Cheaters can never get on the scoreboard
        return -1

    if winner:
        # if a winner then delete all non-winning scores
        for i in range(SCORESIZE):
            if scoreboard[i].suid == userid:
                scoreboard[i].score = 0

        # Calculate the amount of tax owing
        taxes = int(player.outstanding_taxes + (gold * store.TAXRATE))
        player.outstanding_taxes = taxes

        # Find where in the winner's score board the player's score is to
        # be stored
        board_idx = -1

        # if he has a slot on the winning scoreboard update it if greater score
        for i in range(SCORESIZE):
            if winboard[i].suid == userid:
                board_idx = i

        if board_idx == -1:
            # he had no entry. look for last entry and see if he has a greater score
            for i in range(SCORESIZE):
                if winboard[i].order == SCORESIZE - 1:
                    if score > winboard[i].score:
                        board_idx = i

        if board_idx >= 0:
            # Update the taxes owed
            winboard[board_idx].taxes = taxes

            if (winboard[board_idx].score < score) or \
               (c[player.HARDGAME] > winboard[board_idx].hardlev):
                # Store the new score in this slot
                winboard[board_idx].who = ularn_game.logname
                winboard[board_idx].char_class = player.char_class
                winboard[board_idx].score = score
                winboard[board_idx].hardlev = c[player.HARDGAME]
                winboard[board_idx].suid = userid
                winboard[board_idx].timeused = cdiv(player.gtime, 100)

    else:
        # Not a winner, so update the visitors score board

        # Find where in the visitor's score board the player's score is to
        # be stores
        board_idx = -1

        # Check if he already has a slot on the scoreboard
        for i in range(SCORESIZE):
            if scoreboard[i].suid == userid:
                board_idx = i

        # he had no entry. look for last entry and see if he has a greater score
        if board_idx == -1:
            for i in range(SCORESIZE):
                if scoreboard[i].order == SCORESIZE - 1:
                    board_idx = i

        if board_idx >= 0:
            if (scoreboard[board_idx].score < score) or \
               (c[player.HARDGAME] > scoreboard[board_idx].hardlev):
                # This is a better score, so store the new score in this slot
                sb = scoreboard[board_idx]
                sb.who = ularn_game.logname
                sb.char_class = player.char_class
                sb.score = score
                sb.reason = died_reason
                sb.what = what
                sb.hardlev = c[player.HARDGAME]
                sb.suid = userid
                sb.level = dungeon.level
                for i in range(player.IVENSIZE):
                    sb.sciv[i][0] = player.iven[i]
                    sb.sciv[i][1] = player.ivenarg[i]
            else:
                # The new score isn't better
                board_idx = -1

    # resort the score board
    sortboard()

    if writeboard() < 0:
        return -1

    return board_idx


def print_died_reason(Reason, Monster, lev):
    """Print the reason a player died (Monster: the monster involved, lev: dungeon level)."""
    if Reason == DIED_MONSTER:
        ch = monster.monster[Monster].name[0]

        if ch in ('a', 'e', 'i', 'o', 'u'):
            mod = "an"
        else:
            mod = "a"
        ularn_win.Printf(" killed by %s %s", mod, monster.monster[Monster].name)
    else:
        if (not player.sex) and (Reason == DIED_KILLED_FAMILY or Reason == DIED_OWN_MAGIC):
            # fix up died string for female characters
            if Reason == DIED_KILLED_FAMILY:
                ularn_win.Printf(" killed her family and committed suicide")
            elif Reason == DIED_OWN_MAGIC:
                ularn_win.Printf(" hit by her own magic")
        else:
            ularn_win.Printf(" %s", whydead[Reason])

    if Reason != DIED_WINNER:
        ularn_win.Printf(" on %s\n", dungeon.levelname[lev])
    else:
        ularn_win.Printf("\n")


def show_winners():
    """Print out the winning scoreboard. Returns the number of entries on it."""
    # is there anyone on the scoreboard?
    win_count = 0
    for i in range(SCORESIZE):
        if winboard[i].score != 0:
            win_count += 1

    if win_count > 0:
        ularn_win.ClearText()
        ularn_ask.clearpager()
        ularn_win.Print("   Score       Diff   Time Needed  Ularn Winners List\n")
        ularn_ask.pager()

        # needed to print out the winners in order
        for i in range(win_count):
            for j in range(SCORESIZE):
                # pointer to the scoreboard entry
                p = winboard[j]

                if p.order == i and p.score > 0:
                    ularn_win.Printf("%-10ld%8d%8d Mobuls  (%s) %s\n",
                                     p.score,
                                     p.hardlev,
                                     p.timeused,
                                     p.char_class,
                                     p.who)
                    ularn_ask.pager()

    # return number of people on scoreboard
    return win_count


def show_visitors(show_inv):
    """Print out the non-winners scoreboard (show_inv: 1 to list inventories too).

    Returns the number of players on scoreboard that were shown.
    """
    c = player.c

    # Make all scrolls and potions known for displaying the scoreboard,
    # storing the old known status for restoration later.
    oscrollknown = list(player.scrollknown)
    for i in range(len(player.scrollknown)):
        player.scrollknown[i] = 1

    opotionknown = list(player.potionknown)
    for i in range(len(player.potionknown)):
        player.potionknown[i] = 1

    c[player.WEAR] = -1
    c[player.WIELD] = -1
    c[player.SHIELD] = -1

    # is the scoreboard empty?
    count = 0
    for i in range(SCORESIZE):
        if scoreboard[i].score != 0:
            count += 1

    if count > 0:
        ularn_win.ClearText()
        ularn_ask.clearpager()
        ularn_win.Print("  Score Diff  Ularn Visitor Log\n")
        ularn_ask.pager()

        for i in range(count):
            for j in range(SCORESIZE):
                if scoreboard[j].order == i and scoreboard[j].score > 0:
                    if j == highlight_pos and not highlight_win:
                        ularn_win.SetFormat(ularn_win.FORMAT_STANDOUT)

                    ularn_win.Printf("%7ld %3ld   (%s) %s ",
                                     scoreboard[j].score,
                                     scoreboard[j].hardlev,
                                     scoreboard[j].char_class,
                                     scoreboard[j].who)

                    print_died_reason(scoreboard[j].reason, scoreboard[j].what,
                                      scoreboard[j].level)

                    if j == highlight_pos and not highlight_win:
                        ularn_win.SetFormat(ularn_win.FORMAT_NORMAL)

                    ularn_ask.pager()

                    if show_inv:
                        for n in range(player.IVENSIZE):
                            player.iven[n] = scoreboard[j].sciv[n][0]
                            player.ivenarg[n] = scoreboard[j].sciv[n][1]

                        for n in range(player.IVENSIZE):
                            if player.iven[n] != itm.ONOTHING:
                                show.show3(n)
                                ularn_ask.pager()
                        ularn_ask.pager()

    # Restore the known scrolls and potions
    player.scrollknown[:] = oscrollknown
    player.potionknown[:] = opotionknown

    return count  # return the number of players just shown


def show_player_score(Reason, Monster, score):
    """Print out the line showing the player when he is killed."""
    c = player.c

    cls = player.class_[c[player.LEVEL]]

    if not player.char_class:
        player.char_class = "<unknown>"

    ularn_win.Print("---------------------------------------------------------------\n")
    ularn_win.Print("                 U L A R N    S C O R E S\n")
    ularn_win.Print("---------------------------------------------------------------\n")
    ularn_win.Printf("Score: %ld  Diff: %d  ", score, c[player.HARDGAME])
    ularn_win.Printf("Level: %s  Char: %s\n", cls, player.char_class)
    ularn_win.Printf("\t%s", ularn_game.logname)

    print_died_reason(Reason, Monster, dungeon.level)

    if player.wizard:
        ularn_win.Print(" (wizard)")

    if player.cheat:
        ularn_win.Print(" (cheater)")

    ularn_win.Print("\n")
    ularn_win.Print("---------------------------------------------------------------")


# =============================================================================
# Exported functions

def makeboard():
    """Create a new scoreboard (wipe out old one). Returns -1 on error, 0 if OK."""
    _init_boards()
    for i in range(SCORESIZE):
        winboard[i].taxes = 0
        winboard[i].score = 0
        winboard[i].hardlev = 0
        winboard[i].order = i

        scoreboard[i].score = 0
        scoreboard[i].hardlev = 0
        scoreboard[i].order = i

    if writeboard():
        return -1

    try:
        os.chmod(ularn_game.scorefile, 0o666)
    except OSError:
        pass

    return 0


def hashewon():
    """Check if the player has previously won the game.

    Also sets c[HARDGAME] (0 if not a winner, else next difficulty level) and
    outstanding_taxes.  Returns 1 if player has won a game before, else 0.
    """
    player.c[player.HARDGAME] = 0

    rt = readboard()

    if rt < 0:
        return 0

    # search through winners scoreboard
    for i in range(SCORESIZE):
        if winboard[i].suid == ularn_game.userid and winboard[i].score > 0:
            player.c[player.HARDGAME] = winboard[i].hardlev + 1
            player.outstanding_taxes = winboard[i].taxes
            return 1

    return 0


def paytaxes(x):
    """Pay taxes if any are due. Returns the amount of tax actually paid."""
    if x <= 0:
        return 0

    if readboard() < 0:
        return 0

    # look for players winning entry
    for i in range(SCORESIZE):
        if winboard[i].suid == ularn_game.userid and winboard[i].score > 0:
            # calculate the amount to pay (making sure the player doesn't overpay
            amt = winboard[i].taxes
            if x < amt:
                amt = x

            winboard[i].taxes -= amt
            player.outstanding_taxes -= amt

            if writeboard() < 0:
                return 0

            return amt

    return 0  # couldn't find user on winning scoreboard


def showscores():
    """Show the scoreboard."""
    if readboard() < 0:
        ularn_win.get_prompt_input("\nPress return to continue", "\015", 0)
        return

    i = show_winners()

    if i > 0:
        ularn_win.get_prompt_input("\nPress return to continue", "\015", 0)

    j = show_visitors(0)

    if (i + j) == 0:
        ularn_win.Print("\nThe scoreboard is empty.\n")
    else:
        ularn_win.Print("\n")

    ularn_win.get_prompt_input("\nPress return to continue", "\015", 0)


def showallscores():
    """Show scores and the iven lists that go with them."""
    if readboard() < 0:
        return

    i = show_winners()
    j = show_visitors(1)

    if (i + j) == 0:
        ularn_win.Print("\nThe scoreboard is empty.\n")
    else:
        ularn_win.Print("\n")

    ularn_win.get_prompt_input("\nPress return to continue", "\015", 0)


def endgame():
    """Call all tidyup procedures and exit the program (raises UlarnExit(0))."""
    # deallocate any allocated memory
    dungeon.free_cells()
    sphere.free_spheres()

    # close the application
    ularn_win.close_app()

    # and exit
    raise UlarnExit(0)


def died(Reason, Monster):
    """Note player death and the reason; called for all end game conditions.

    Only returns if the player is revived by life protection.
    """
    global highlight_pos, highlight_win
    c = player.c

    can_revive = 1

    if c[player.LIFEPROT] > 0:
        # if life protection
        if Reason in (DIED_QUIT,
                      DIED_SUSPENDED,
                      DIED_FELL_INTO_BOTTOMLESS_PIT,
                      DIED_WINNER,
                      DIED_MISSING_SAVE_FILE,
                      DIED_OLD_SAVE_FILE,
                      DIED_GREEDY_CHEATER,
                      DIED_PROTECTED_SAVE_FILE,
                      DIED_KILLED_FAMILY,
                      DIED_FELL_THROUGH_BOTTOMLESS_TRAPDOOR,
                      DIED_INTERNAL_COMPLICATIONS,
                      DIED_POST_MORTEM_DEATH,
                      DIED_MALLOC_FAILURE,
                      DIED_ELEVATOR_TO_HELL,
                      DIED_QUICK_QUIT):
            can_revive = 0

        if can_revive:
            c[player.LIFEPROT] -= 1
            c[player.HP] = c[player.HPMAX]
            c[player.CONSTITUTION] -= 1
            ularn_win.Print("\nYou feel wiiieeeeerrrrrd all over! ")
            ularn_win.UlarnBeep()
            ularn_win.nap(4000)

            # only case where died() returns
            return

    # remove checkpoint file if used
    if ularn_game.ckpflag:
        try:
            os.unlink(ularn_game.ckpfile)
        except OSError:
            pass

    # if we are not to display the scores
    if Reason == DIED_QUICK_QUIT or Reason == DIED_SUSPENDED:
        # for quick exit or saved game
        ularn_win.ClearText()
        ularn_win.Printf("Tidying up...\n")

        endgame()

    win = (Reason == DIED_WINNER)

    # Now calculate the player's final score
    score = calc_score(win)

    ularn_win.set_display(ularn_win.DISPLAY_TEXT)
    ularn_win.ClearText()

    # Show the players final score
    show_player_score(Reason, Monster, score)

    ularn_win.get_prompt_input("\nPress return to continue", "\015", 0)

    if not (player.wizard or player.cheat):
        # wizards and cheaters can't get on the score boards
        highlight_pos = newscore(score, win, Reason, Monster)
        highlight_win = win

    if scorerror == 0:
        # if we updated the scoreboard
        showscores()

    # if (win && mail) mailbill();

    ularn_win.ClearText()
    ularn_win.Print("\n")

    # exit the game
    endgame()
