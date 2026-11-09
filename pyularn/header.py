"""Common macros and helpers (port of header.h, config.h and patchlevel.h).

This module has NO imports from other pyularn modules, so every module may
safely do ``from .header import *``.
"""

import os
import random

# ---------------------------------------------------------------- patchlevel.h
LARN_VERSION = "1.6"
LARN_PATCHLEVEL = "3"
LARN_DATE = "26 Mar 2004"
PYULARN_VERSION = "0.1.0"

# ---------------------------------------------------------------- random
# A single shared RNG so games can be seeded / reproduced.
RNG = random.Random()

# When not None, every srand() call (including the clock-based one in
# ularn_game.newgame) uses this seed instead, so a game can be replayed.
forced_seed = None


def srand(seed):
    RNG.seed(seed if forced_seed is None else forced_seed)


def set_seed(seed):
    """Make the game reproducible: seed now and pin later srand() calls.
    Pass None to restore the C behaviour (seed from the clock)."""
    global forced_seed
    forced_seed = seed
    if seed is not None:
        RNG.seed(seed)


def rand():
    """Equivalent of C rand(): non-negative 31-bit integer."""
    return RNG.getrandbits(31)


def rnd(x):
    """Random number between 1 and x (inclusive)."""
    return (rand() % x) + 1


rndl = rnd


def rund(x):
    """Random number between 0 and x-1."""
    return rand() % x


rundl = rund


# ---------------------------------------------------------------- C semantics
def cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def cmod(a, b):
    """C remainder (sign follows the dividend)."""
    return a - b * cdiv(a, b)


def plural(x):
    return "" if x == 1 else "s"


ESC = "\033"


class UlarnExit(Exception):
    """Raised instead of calling C exit(); caught by the main loop.

    ``code`` mirrors the exit status passed to exit().
    """

    def __init__(self, code=0):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------- file paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def data_path(name):
    """Path of a read-only data file shipped with the package (Umaps, Uhelp...)."""
    return os.path.join(DATA_DIR, name)


def user_dir():
    """Writable per-user directory for scores and save files (~/.pyularn).

    Overridable with the PYULARN_HOME environment variable.
    """
    d = os.environ.get("PYULARN_HOME") or os.path.join(os.path.expanduser("~"), ".pyularn")
    os.makedirs(d, exist_ok=True)
    return d


def user_path(name):
    return os.path.join(user_dir(), name)
