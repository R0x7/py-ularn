"""Diagnostic dump module (port of diag.c / diag.h).

EXPORTED FUNCTIONS
  diag - Print diagnostic information
"""

from .header import *
from . import ularn_game, itm, dungeon, monster, player, potion, scroll, spell, ularn_win

# =============================================================================
# Local variables

# Character attribute strings.
# The strings must match the order of the AttributeType enumeration
cdef = [
    "STRENGTH", "INTELLIGENCE", "WISDOM", "CONSTITUTION", "DEXTERITY",
    "CHARISMA", "HPMAX", "HP", "GOLD", "EXPERIENCE",
    "LEVEL", "REGEN", "WCLASS", "AC", "BANKACCOUNT",
    "SPELLMAX", "SPELLS", "ENERGY", "ECOUNTER", "MOREDEFENSES",
    "WEAR", "PROTECTIONTIME", "WIELD", "AMULET", "REGENCOUNTER",
    "MOREDAM", "DEXCOUNT", "STRCOUNT", "BLINDCOUNT", "CAVELEVEL",
    "CONFUSE", "ALTPRO", "HERO", "CHARMCOUNT", "INVISIBILITY",
    "CANCELLATION", "HASTESELF", "EYEOFLARN", "AGGRAVATE ", "GLOBE",
    "TELEFLAG", "SLAYING", "NEGATESPIRIT", "SCAREMONST ", "AWARENESS",
    "HOLDMONST", "TIMESTOP", "HASTEMONST", "CUBEofUNDEAD", "GIANTSTR",
    "FIRERESISTANCE", "BESSMANN", "NOTHEFT", "HARDGAME", "",
    "", "", "", "", "VORPAL",
    "LANCEDEATH", "SPIRITPRO", "UNDEADPRO", "SHIELD ", "STEALTH",
    "ITCHING", "LAUGHING", "DRAINSTRENGTH", "CLUMSINESS", "INFEEBLEMENT",
    "HALFDAM", "SEEINVISIBLE", "FILLROOM", "", "SPHCAST",
    "WTW", "STREXTRA", "TMP", "LIFEPROT", "ORB",
    "ELVUP", "ELVDOWN", "HAND", "CUBEUNDEAD", "DRAGSLAY",
    "NEGATE", "URN", "LAMP", "TALISMAN", "WAND",
    "STAFF", "DEVICE", "SLASH", "ELVEN", "VORP",
    "SLAY", "PAD", "COKED", "", ""]

# Names for inventory items
ivendef = [
    "",
    "OALTAR", "OTHRONE", "OORB", "OPIT", "OSTAIRSUP",
    "OELEVATORUP", "OFOUNTAIN", "OSTATUE", "OTELEPORTER", "OSCHOOL",
    "OMIRROR", "ODNDSTORE", "OSTAIRSDOWN", "OELEVATORDOWN", "OBANK2",
    "OBANK", "ODEADFOUNTAIN", "OGOLDPILE", "OOPENDOOR", "OCLOSEDDOOR",
    "OWALL", "OTRAPARROW", "OTRAPARROWIV", "OLARNEYE", "OPLATE",
    "OCHAIN", "OLEATHER", "ORING", "OSTUDLEATHER", "OSPLINT",
    "OPLATEARMOR", "OSSPLATE", "OSHIELD", "OSWORDofSLASHING", "OHAMMER",
    "OSWORD", "O2SWORD", "OSPEAR", "ODAGGER", "OBATTLEAXE",
    "OLONGSWORD", "OFLAIL", "OLANCE", "ORINGOFEXTRA", "OREGENRING",
    "OPROTRING", "OENERGYRING", "ODEXRING", "OSTRRING", "OCLEVERRING",
    "ODAMRING", "OBELT", "OSCROLL", "OPOTION", "OBOOK",
    "OCHEST", "OAMULET", "OORBOFDRAGON", "OSPIRITSCARAB", "OCUBEofUNDEAD",
    "ONOTHEFT", "ODIAMOND", "ORUBY", "OEMERALD", "OSAPPHIRE",
    "OENTRANCE", "OVOLDOWN", "OVOLUP", "OHOME", "OMAXGOLD",
    "OKGOLD", "ODGOLD", "OIVDARTRAP", "ODARTRAP", "OTRAPDOOR",
    "OIVTRAPDOOR", "OTRADEPOST", "OIVTELETRAP", "ODEADTHRONE", "OANNIHILATION",
    "OTHRONE2", "OLRS", "OCOOKIE", "OURN", "OBRASSLAMP",
    "OHANDofFEAR", "OSPHTALISMAN", "OWWAND", "OPSTAFF", "OVORPAL",
    "OSLAYER", "OELVENCHAIN", "OSPEED", "OACID", "OHASH",
    "OSHROOMS", "OCOKE", "OPAD", ""]

# The debug output file
dfile = None


def _fprintf(fmt, *args):
    dfile.write(fmt % args if args else fmt)


# =============================================================================
# Local functions

def diagdrawscreen():
    """Draw the ASCII map to the diag file."""
    for i in range(dungeon.MAXY):
        for j in range(dungeon.MAXX):
            Monst = dungeon.mitem[j][i].mon
            if Monst != monster.MONST_NONE:
                _fprintf("%c", monster.monstnamelist[Monst])
            else:
                _fprintf("%c", itm.objnamelist[dungeon.item[j][i]])
        _fprintf("\n")


# =============================================================================
# Exported functions

def diag():
    """Print out data for debugging (written to user_path(diagfile))."""
    global dfile

    try:
        dfile = open(user_path(ularn_game.diagfile), "w", encoding="latin-1")
    except OSError:
        return

    c = player.c

    ularn_win.Print("\nDiagnosing . . .\n")

    _fprintf("\n-------- Beginning of DIAG diagnostics ---------\n\n")

    _fprintf("Hit points: %2ld(%2ld)\n", c[player.HP], c[player.HPMAX])

    _fprintf("gold: %ld  Experience: %ld  Character level: %ld  Level in caverns: %d\n",
             c[player.GOLD],
             c[player.EXPERIENCE],
             c[player.LEVEL],
             dungeon.level)

    _fprintf("\nFor the c[] array:\n")
    dfile.flush()

    for j in range(100):
        # C reads past the end of c[] if ATTRIBUTE_COUNT < 100; print 0 there.
        _fprintf("c[%d]\t%-20s\t= %ld\n", j, cdef[j], c[j] if j < len(c) else 0)
    _fprintf("\n\n")
    dfile.flush()

    _fprintf("Inventory\n")
    for j in range(player.IVENSIZE):
        _fprintf("iven[%d] %-12s = %d",
                 j, ivendef[player.iven[j]], player.iven[j])
        _fprintf("\t%s", itm.objectname[player.iven[j]])
        _fprintf("\t+ %d\n", player.ivenarg[j])

    _fprintf("\nHere are the maps:\n\n")

    i = dungeon.level
    for j in range(dungeon.NLEVELS):
        dungeon.newcavelevel(j)
        _fprintf("\n-------------------------------------------------------------------\n")
        _fprintf("Map %s    level %d\n", dungeon.levelname[dungeon.level], dungeon.level)
        _fprintf("-------------------------------------------------------------------\n")
        diagdrawscreen()
        dfile.flush()
    dungeon.level = i
    dungeon.getlevel()

    _fprintf("\n\nNow for the monster data:\n\n")
    _fprintf("\nTotal types of monsters: %d\n\n", monster.MAXMONST + 8)
    _fprintf("   Monster Name      LEV  AC   DAM  ATT  GOLD   HP     EXP\n")
    _fprintf("-----------------------------------------------------------------\n")
    dfile.flush()

    for Monst in range(monster.MONST_NONE, monster.MONST_COUNT):
        m = monster.monster[Monst]
        _fprintf("%19s  %2d  %3d ", m.name, m.level, m.armorclass)
        _fprintf(" %3d  %3d ", m.damage, m.attack)
        _fprintf("%6d  %3d   %6ld\n", m.gold, m.hitpoints, m.experience)

        dfile.flush()

    _fprintf("\nAvailable potions:\n\n")
    for i in range(potion.MAXPOTION):
        _fprintf("%20s\n", potion.potionname[i][1:])
    dfile.flush()

    _fprintf("\nAvailable scrolls:\n\n")
    for i in range(scroll.MAXSCROLL):
        _fprintf("%20s\n", scroll.scrollname[i][1:])
    dfile.flush()

    _fprintf("\nSpell list:\n\n")
    _fprintf("spell#  name           description\n")
    _fprintf("-------------------------------------------------\n\n")

    for j in range(spell.SPELL_COUNT):
        _fprintf("%-10s", spell.spelcode[j])
        _fprintf(" %21s\n", spell.spelname[j])
        _fprintf("%s\n", spell.speldescript[j])
    dfile.flush()

    _fprintf("\nObject list\n\n")
    _fprintf("\nj \tObject \tName\n")
    _fprintf("---------------------------------\n")
    for j in range(itm.OCOUNT):
        _fprintf("%d \t%c \t%s\n", j, itm.objnamelist[j], itm.objectname[j])
    dfile.flush()

    _fprintf("\n-------- End of DIAG diagnostics ---------\n")
    dfile.flush()
    dfile.close()
    dfile = None

    ularn_win.Print("\nDone Diagnosing.\n")
