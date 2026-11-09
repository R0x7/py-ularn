"""Spheres of annihilation (port of sphere.c / sphere.h).

This module contains functions for maintaining & moving the spheres of
annihilation.

EXPORTED FUNCTIONS

  rmsphere      : Remove a sphere from a location on the map
  newsphere     : Create a new sphere
  movsphere     : Move a sphere
  free_spheres  : Free all allocated spheres
  write_spheres : Write the spheres to the save file
  read_spheres  : Read the spheres from the save file
"""

import pickle

from .header import *
from . import dungeon, itm, monster, player, scores, ularn_game, ularn_win


# =============================================================================
# Local variables

class sphere:
    """struct sphere"""

    __slots__ = ("next", "x", "y", "lev", "dir", "lifetime")

    def __init__(self, x=0, y=0, lev=0, dir=0, lifetime=0, next=None):
        self.next = next          # pointer to next structure
        self.x = x                # location of the sphere
        self.y = y
        self.lev = lev
        self.dir = dir            # direction sphere is going in
        self.lifetime = lifetime  # duration of the sphere


#
# The start of the list of spheres
#
spheres = None

#
# The next sphere to process when processing the movement for list of spheres.
# NOTE:
# This may be changed by rmsphere deleting an unprocessed sphere when
# two spheres collide.
#
sp2 = None


# =============================================================================
# Local functions

def sphboom(x, y):
    """Function to perform the effects of a sphere detonation at x, y."""
    c = player.c
    item = dungeon.item
    know = dungeon.know
    mitem = dungeon.mitem
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    # check if the player has the talisman of the sphere
    have_talisman = player.player_has_item(itm.OSPHTALISMAN)

    # sphere explosion ends hold monster and cancellation
    if c[player.HOLDMONST]:
        c[player.HOLDMONST] = 1
    if c[player.CANCELLATION]:
        c[player.CANCELLATION] = 1

    xl = x - 2
    yl = y - 2
    xh = x + 3
    yh = y + 3

    if dungeon.level == 0:
        # On the home level the boom can go right to the edge of the map
        if xl < 0:
            xl = 0
        if xh > MAXX:
            xh = MAXX
        if yl < 0:
            yl = 0
        if yh > MAXY:
            yh = MAXY
    else:
        # In the dungeon the boom stops at the edge wall
        if xl < 1:
            xl = 1
        if xh > (MAXX - 1):
            xh = MAXX - 1
        if yl < 1:
            yl = 1
        if yh > (MAXY - 1):
            yh = MAXY - 1

    # wipe out everything in the range of the sphere
    for j in range(xl, xh):
        for i in range(yl, yh):
            item[j][i] = itm.ONOTHING

            if not monster.mon_has_item(j, i, itm.OSPHTALISMAN):
                # The monster was caught in the explosion
                mitem[j][i].mon = monster.MONST_NONE
            else:
                # The monster has the talisman, and is unaffected
                ularn_win.Printf("\nThe %s is unaffected by the blast!",
                                 monster.monster[mitem[j][i].mon].name)

            ularn_win.show1cell(j, i)

            if (not have_talisman) and (player.playerx == j) and (player.playery == i):
                # player killed in explosion
                ularn_win.UlarnBeep()
                ularn_win.Print("\nYou were too close to the sphere!")
                ularn_win.nap(3000)
                scores.died(scores.DIED_SPHERE_ANNIHILATION, 0)

    # Analyse wall connections and redisplay
    dungeon.AnalyseWalls(xl - 1, yl - 1, xh, yh)

    for i in range(xl - 1, xh + 1):
        for j in range(yl - 1, yh + 1):
            if dungeon.checkxy(i, j):
                if (know[i][j] != itm.OUNKNOWN) and (item[i][j] == itm.OWALL):
                    ularn_win.show1cell(i, j)


def msphere(sp, create):
    """Move 1 sphere of annihiliation.

    sp     : the sphere to be moved
    create : flag indicating if this is the first creation of the sphere;
             for creation, don't move the sphere, just place it at the
             current position.

    Returns 1 if the sphere moved, 0 if the sphere is removed.
    """
    c = player.c
    item = dungeon.item
    know = dungeon.know
    mitem = dungeon.mitem
    MAXX = dungeon.MAXX
    MAXY = dungeon.MAXY

    if dungeon.level != sp.lev:
        # Not on the correct level for the sphere, so return
        return 1

    # no movement if direction not found
    if sp.dir >= 9:
        sp.dir = 0

    x = sp.x
    y = sp.y

    if not create:
        #
        # The sphere was not just created, so clear the current location
        # and update the sphere position.
        #
        item[x][y] = itm.ONOTHING
        know[x][y] = item[x][y]

        # show the now moved sphere
        ularn_win.show1cell(x, y)

        x += ularn_game.diroffx[sp.dir]
        y += ularn_game.diroffy[sp.dir]

    # don't go out of bounds
    if dungeon.level == 0:
        # on the home level the entire map area is valid
        x, y = dungeon.vxy(x, y)
    else:
        #
        # On dungeon levels don't move onto the edge walls surrounding the
        # dungeon.
        #
        if x < 1:
            x = 1
        if x >= MAXX - 1:
            x = MAXX - 2
        if y < 1:
            y = 1
        if y >= MAXY - 1:
            y = MAXY - 2

    #
    # store the new sphere position back in the sphere record
    #
    sp.x = x
    sp.y = y

    # check if the player has the talisman of the sphere
    have_talisman = player.player_has_item(itm.OSPHTALISMAN)

    m = mitem[x][y].mon
    it = item[x][y]
    if m != monster.MONST_NONE:
        mon_has_talisman = monster.mon_has_item(x, y, itm.OSPHTALISMAN)
    else:
        mon_has_talisman = 0

    # demons dispel spheres if the player doesn't have the talisman
    if (not have_talisman) and (m >= monster.DEMONLORD):
        know[x][y] = item[x][y]
        # show the demon (ha ha)
        ularn_win.show1cell(x, y)
        ularn_win.Printf("\nThe %s dispels the sphere!", monster.monster[m].name)
        ularn_win.UlarnBeep()

        # remove any spheres that are here
        rmsphere(x, y)

        return 0

    # disenchantress cancels spheres if the player doesn't have the talisman
    if (not have_talisman) and (m == monster.DISENCHANTRESS):
        ularn_win.Printf("\nThe %s cancels the sphere!", monster.monster[m].name)
        ularn_win.UlarnBeep()

        sphboom(x, y)   # blow up stuff around sphere
        rmsphere(x, y)  # remove any spheres that are here

        return 0

    # cancellation cancels spheres if the player doesn't have the talisman
    if (not have_talisman) and c[player.CANCELLATION]:
        ularn_win.Print("\nAs the cancellation takes effect, you hear a great earth shaking blast!")
        ularn_win.UlarnBeep()

        sphboom(x, y)   # blow up stuff around sphere
        rmsphere(x, y)  # remove any spheres that are here

        return 0

    #
    # Collision of sphere and player is not good if the player doesn't have the
    # talisman
    #
    if (not have_talisman) and (player.playerx == x) and (player.playery == y):
        ularn_win.Print("\nYou have been enveloped by the zone of nothingness!\n")
        ularn_win.UlarnBeep()
        rmsphere(x, y)  # remove any spheres that are here

        ularn_win.nap(4000)
        scores.died(scores.DIED_SELF_ANNIHLATED, 0)
        return 0

    # collision of spheres detonates spheres
    if item[x][y] == itm.OANNIHILATION:
        ularn_win.Print("\nTwo spheres of annihilation collide! You hear a great earth-shaking blast!")
        ularn_win.UlarnBeep()
        rmsphere(x, y)

        sphboom(x, y)   # blow up stuff around sphere
        rmsphere(x, y)  # remove the other sphere

        return 0

    # The sphere still exists, so put it on the map in the new position
    item[x][y] = itm.OANNIHILATION

    if it == itm.OWALL:
        # Destroyed a wall, so analyse wall connections and redisplay

        dungeon.AnalyseWalls(x - 1, y - 1, x + 1, y + 1)

        for i in range(x - 1, x + 2):
            for j in range(y - 1, y + 2):
                if dungeon.checkxy(i, j):
                    if (know[i][j] != itm.OUNKNOWN) and (item[i][j] == itm.OWALL):
                        ularn_win.show1cell(i, j)

    if mon_has_talisman:
        ularn_win.Printf("\nThe %s is unaffected by the sphere of annihilation!",
                         monster.monster[m].name)
    else:
        mitem[x][y].mon = monster.MONST_NONE

    know[x][y] = item[x][y]

    ularn_win.show1cell(x, y)

    return 1


# =============================================================================
# Exported functions

def rmsphere(x, y):
    """Remove a sphere from a location on the map."""
    global spheres, sp2

    sp = spheres
    prev_sp = None

    while sp is not None:
        if (dungeon.level == sp.lev) and (x == sp.x) and (y == sp.y):
            #
            # The sphere is on this level and at the location of the sphere
            # to be deleted
            #
            dungeon.item[x][y] = itm.ONOTHING
            dungeon.know[x][y] = dungeon.item[x][y]

            # show the now missing sphere
            ularn_win.show1cell(x, y)
            player.c[player.SPHCAST] -= 1

            tmp = sp       # store the ponter to the sphere to be deleted
            sp = sp.next   # get a pointer to the next sphere

            if tmp is spheres:
                # remove from the head of the list
                spheres = sp

            if prev_sp is not None:
                # link over the sphere to be deleted
                prev_sp.next = sp

            if tmp is sp2:
                #
                # The sphere being deleted is the next sphere to move, so
                # update the next sphere to move
                #
                sp2 = sp

            tmp.next = None

            # Found the sphere to be removed, so return
            return
        else:
            # advance to the next sphere
            prev_sp = sp
            sp = sp.next


def newsphere(x, y, dir, life):
    """Create a new sphere at x, y moving in dir with lifetime life."""
    global spheres

    # Allocate the new sphere
    sp = sphere()

    sp.x = x
    sp.y = y
    sp.lev = dungeon.level
    sp.dir = dir
    sp.lifetime = life
    sp.next = spheres
    spheres = sp

    player.c[player.SPHCAST] += 1

    msphere(sp, 1)

    #
    # The new sphere is about to move in movemonst , so give the player
    # a chance to see it in the first position it is cast.
    #
    ularn_win.nap(500)


def movsphere():
    """Move the spheres of annihilation on the current level."""
    global sp2

    sp = spheres

    # look through sphere list
    while sp is not None:
        #
        # Set the next sphere to process
        # Note: This may be changed by msphere if two spheres collide.
        #
        sp2 = sp.next

        # has sphere run out of gas?

        if sp.lev == dungeon.level:
            #
            # Only move spheres on this level.
            # All other spheres are in stasis.
            #
            sp.lifetime -= 1
            if sp.lifetime < 0:
                # delete sphere
                rmsphere(sp.x, sp.y)
            else:
                # time to move the sphere
                if rnd(max(7, player.c[player.INTELLIGENCE] >> 1)) <= 2:
                    # sphere changes direction
                    sp.dir = rnd(8)

                msphere(sp, 0)

        #
        # advance to the next sphere
        # Do it this way as the moved sphere may have been deleted.
        #
        sp = sp2


def free_spheres():
    """Free all allocated spheres."""
    global spheres

    sp = spheres

    # look through sphere list
    while sp is not None:
        next_sp = sp.next
        sp.next = None
        sp = next_sp

    spheres = None


def write_spheres(fp):
    """Write the spheres to the save file (binary fp, via pickle.dump())."""
    # count the number of spheres / collect them in list order
    recs = []
    sp = spheres
    while sp is not None:
        recs.append((sp.x, sp.y, sp.lev, sp.dir, sp.lifetime))
        sp = sp.next

    # write the count followed by the spheres
    pickle.dump({"count": len(recs), "spheres": recs}, fp)


def read_spheres(fp):
    """Read the spheres from the save file (binary fp, via pickle.load()).

    As in C each sphere read is pushed onto the head of the list.
    """
    global spheres

    spheres = None

    data = pickle.load(fp)
    count = data["count"]
    recs = data["spheres"]

    idx = 0
    while count > 0:
        x, y, lev, dir, lifetime = recs[idx]
        idx += 1
        sp = sphere(x, y, lev, dir, lifetime)

        sp.next = spheres
        spheres = sp

        count -= 1
