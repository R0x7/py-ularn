"""Tile numbers for the graphical map (from the X11 front end, ularn_winx11.c).

The terminal build draws characters, so `ularn_win.GetTile` returns
characters.  The X11 and Windows builds draw 32x32 sprites from
``data/ularn_gfx.png`` (converted from ``ularn_gfx.xpm``) instead.  This module
holds their tile tables and a read-only version of their ``GetTile`` so the
web page can draw the same map with sprites.

Tile n is at column n % 16, row n // 16 of the sheet.
"""

from . import dungeon, itm, monster, player, ularn_win

TILE_WIDTH = 32
TILE_HEIGHT = 32
TILES_PER_ROW = 16

# Tiles for different character classes, (female, male)
PlayerTiles = [
    [165, 181],  # Ogre
    [166, 182],  # Wizard
    [167, 183],  # Klingon
    [168, 184],  # Elf
    [169, 185],  # Rogue
    [170, 186],  # Adventurer
    [171, 187],  # Dwarf
    [172, 188],  # Rambo
]

TILE_CURSOR1 = 174
TILE_CURSOR2 = 190
WALL_TILES = 352


def player_tile():
    """The sprite for the player's class and sex."""
    cls = player.class_num if 0 <= player.class_num < len(PlayerTiles) else 0
    return PlayerTiles[cls][1 if player.sex else 0]


def GetTile(x, y):
    """The tile to draw at (x, y), as in the X11 GetTile.

    Unlike the C function this never calls rnd(): a mimic shows the monster
    that the terminal display last picked (ularn_win.mimicmonst), so looking
    at the map does not change the game's random numbers.
    """
    c = player.c
    know = dungeon.know
    objtilelist = itm.objtilelist

    if x == player.playerx and y == player.playery and c[player.BLINDCOUNT] == 0:
        return player_tile()

    kn = know[x][y]
    if kn == itm.OUNKNOWN:
        TileId = objtilelist[itm.OUNKNOWN]
    else:
        k = dungeon.mitem[x][y].mon
        if k != 0:
            st = dungeon.stealth[x][y]
            if c[player.BLINDCOUNT] == 0 and \
                    ((st & dungeon.STEALTH_SEEN) or (st & dungeon.STEALTH_AWAKE)):
                if k == monster.MIMIC:
                    mm = ularn_win.mimicmonst
                    TileId = monster.monsttilelist[mm if mm else monster.MIMIC]
                elif k == monster.INVISIBLESTALKER and c[player.SEEINVISIBLE] == 0:
                    TileId = objtilelist[kn]
                elif monster.DEMONLORD <= k <= monster.LUCIFER and c[player.EYEOFLARN] == 0:
                    # demons are invisible if not have the eye
                    TileId = objtilelist[kn]
                else:
                    TileId = monster.monsttilelist[k]
            else:
                TileId = objtilelist[kn]
        else:
            TileId = objtilelist[kn]

    # Handle walls
    if TileId == objtilelist[itm.OWALL]:
        TileId = WALL_TILES + dungeon.iarg[x][y]
    return TileId


def map_frame():
    """The map as tiles, or None when the game is not showing the map.

    Returns {"w", "h", "tiles" (row-major, h rows of w), "player": [x, y],
    "cursor": tile drawn over the player's square}.
    """
    if ularn_win.CurrentDisplayMode != ularn_win.DISPLAY_MAP:
        return None
    w, h = dungeon.MAXX, dungeon.MAXY
    try:
        tiles = [GetTile(x, y) for y in range(h) for x in range(w)]
    except (IndexError, TypeError, AttributeError):
        return None  # level storage not set up yet
    return {"w": w, "h": h, "tiles": tiles,
            "player": [player.playerx, player.playery], "cursor": TILE_CURSOR1}
