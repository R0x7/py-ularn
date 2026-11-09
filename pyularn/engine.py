"""Reset the game engine so several games can run in one Python process.

The C game keeps its state in globals that are initialised once per process.
The port does the same with module globals, so before starting a second game
in the same process every game module is re-executed in place.  Modules
refer to each other as ``module.name`` at call time, so in-place reloading
keeps all cross-references valid.

Do not call this while a game thread is running.
"""

import importlib
import sys

# Leaf modules first; the order only matters for import-time side effects.
# header is not reloaded: it holds no game state, only the shared RNG and
# the UlarnExit class that every module star-imports.
GAME_MODULES = [
    "itm", "potion", "scroll", "player", "spell", "monster",
    "dungeon", "dungeon_obj", "sphere", "object", "show", "store", "scores",
    "saveutils", "savegame", "ularn_game", "fortune", "help", "diag",
    "ularn_win", "ularn_ask", "action", "term_virtual", "ularn",
]


def reset():
    """Re-initialise every game module's globals."""
    for name in GAME_MODULES:
        mod = sys.modules.get(__package__ + "." + name)
        if mod is None:
            importlib.import_module("." + name, __package__)
        else:
            importlib.reload(mod)
