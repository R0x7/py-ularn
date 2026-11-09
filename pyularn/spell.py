"""Spells and spell-like effects (port of spell.c / spell.h).

EXPORTED VARIABLES
  splev        : The maximum spell num to be learnt from a book found on each
                 dungeon level
  spelcode     : The three letter codes for the spells
  spelname     : The text name of each spell
  speldescript : The text description of each spell.

EXPORTED FUNCTIONS
  godirect       : Function to process ranged spell effects (including scrolls)
  annihilate     : Function to process the annihilate scroll
  get_spell_code : Function to get the three letter spell code from the player
  cast           : Function to cast a spell
"""

import re

from .header import *
from . import (ularn_game, ularn_win, ularn_ask, sphere, show, dungeon, monster,
               player, itm, scores)

# =============================================================================
# SpellType enumeration

SPELL_PRO = 0   # Protection
SPELL_MLE = 1   # Magic missile
SPELL_DEX = 2   # Dexterity
SPELL_SLE = 3   # Sleep
SPELL_CHM = 4   # Charm monster
SPELL_SSP = 5   # Sonic spear
SPELL_WEB = 6   # Web
SPELL_STR = 7   # Strength
SPELL_ENL = 8   # Enlightenment
SPELL_HEL = 9   # Healing
SPELL_CBL = 10  # Cure blindness
SPELL_CRE = 11  # Create monster
SPELL_PHA = 12  # Phantasmal forces
SPELL_INV = 13  # Invisibility
SPELL_BAL = 14  # Fireball
SPELL_CLD = 15  # Cold
SPELL_PLY = 16  # Polymorph
SPELL_CAN = 17  # Cancellation
SPELL_HAS = 18  # Haste
SPELL_CKL = 19  # Cloud kill
SPELL_VPR = 20  # Vaporise rock
SPELL_DRY = 21  # Dehydration
SPELL_LIT = 22  # Lightning
SPELL_DRL = 23  # Drain life
SPELL_GLO = 24  # Invulnerability
SPELL_FLO = 25  # Flood
SPELL_FGR = 26  # Finger of Death
SPELL_SCA = 27  # Scare monster
SPELL_HLD = 28  # Hold monster
SPELL_STP = 29  # Stop time
SPELL_TEL = 30  # Teleport away
SPELL_MFI = 31  # Magic fire
SPELL_MKW = 32  # Make wall
SPELL_SPH = 33  # Sphere of annihilation
SPELL_GEN = 34  # Genocide
SPELL_SUM = 35  # Summon demon
SPELL_WTW = 36  # Walk through walls
SPELL_ALT = 37  # Alter reality
SPELL_PER = 38  # Permanence
SPELL_COUNT = 39

# The dexterity boost from the DEX spell
SDEXTERITY_BOOST = 3
# The strength boost from the STR spell
SSTRENGTH_BOOST = 3
# The protection boost from the PRO spell
SPELL_PRO_BOOST = 2
# The protection boost from a globe of invulnerability
SPELL_GLOBE_BOOST = 10

# =============================================================================
# Exported variables

# The highest spell number that may be learnt from a book found on each
# level of the dungeon
splev = [
    1, 4, 7, 11, 15,
    20, 24, 28, 30, 32,
    33, 34, 35, 36, 37,
    38, 38, 38, 38, 38,
    38]

spelcode = [
    "pro", "mle", "dex", "sle", "chm", "ssp",                 # 0 - 5
    "web", "str", "enl", "hel", "cbl", "cre", "pha", "inv",   # 6 - 13
    "bal", "cld", "ply", "can", "has", "ckl", "vpr",          # 14 - 20
    "dry", "lit", "drl", "glo", "flo", "fgr",                 # 21 - 26
    "sca", "hld", "stp", "tel", "mfi", "mkw",                 # 27 - 34
    "sph", "gen", "sum", "wtw", "alt", "per",                 # 35 - 38
]

spelname = [
    "protection",   # 0
    "magic missile",
    "dexterity",
    "sleep",
    "charm monster",
    "sonic spear",  # 5
    "web",
    "strength",
    "enlightenment",
    "healing",
    "cure blindness",  # 10
    "create monster",
    "phantasmal forces",
    "invisibility",
    "fireball",
    "cold",     # 15
    "polymorph",
    "cancellation",
    "haste self",
    "cloud kill",
    "vaporize rock",  # 20
    "dehydration",
    "lightning",
    "drain life",
    "invulnerability",
    "flood",    # 25
    "finger of death",
    "scare monster",
    "hold monster",
    "time stop",
    "teleport away",  # 30
    "magic fire",
    "make a wall",
    "sphere of annihilation",
    "genocide",   # 34
    "summon demon",
    "walk through walls",
    "alter reality",
    "permanence",   # 38
]

speldescript = [
    # 1
    "Generates a +2 protection field",
    "Creates and hurls a magic missile equivalent to a +1 magic arrow",
    "Adds +2 to the caster's dexterity",
    "Causes some monsters to go to sleep",
    "Some monsters may be awed at your magnificence",
    "Causes the caster's hands to emit a screeching sound",
    # 7
    "Causes strands of sticky thread to entangle an enemy",
    "Adds +2 to the caster's strength for a time",
    "The caster becomes more aware of things around them",
    "Restores some of the caster's health",
    "Restores sight to one so unfortunate as to be blinded",
    "Creates a monster near to the caster",
    "Creates illusions which, if believed, cause monsters to die",
    "The caster becomes invisible",
    # 15
    "Creates a ball of fire that burns whatever it hits",
    "Sends forth a cone of cold which freezes whatever it touches",
    "You can find out what this does for yourself",
    "Stops a monster from using its special abilities",
    "Speeds up the caster's movements",
    "Creates a fog of poisonous gas which kills all that is within it",
    "Changes rock to air",
    # 22
    "Dries up water in the immediate vicinity",
    "Causes the caster's finger to emit lightning bolts",
    "Subtracts hit points from both you and a monster",
    "This globe helps to protect the player from physical attack",
    "Creates a deluge of water, flooding the immediate chamber",
    "A holy spell calling on your god to back you up",
    # 28
    "Terrifies the monster so that it may not hit the caster",
    "Freezes monsters in their tracks",
    "All movement in the caverns ceases for a limited duration",
    "Teleports a monster",
    "Creates a curtain of fire around the caster",
    # 33
    "Makes a wall in the specified place",
    "Anything caught in this sphere is instantly killed.",
    "Eliminates a species of monster from the game",
    "Summons a demon who may help you out",
    "Allows the player to walk through walls for a short period of time",
    "God only knows what this will do",
    "Makes a character spell permanent, e.g. protection, strength, etc.",
]

# =============================================================================
# Local variables

#  spelweird[ monster ] [ spell ] = [ reaction ]
#
#  spell =  index into spelldescript[] and spellname[]
#  reaction = index into spelmes[]
spelweird = [
    # p m d s c s    w s e h c c p i    b c p c h c v    d l d g f f    s h s t m    s g s w a p
    # None (placeholder)
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # lemming
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # gnome
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # hobgoblin
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # jackal
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # kobold
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # orc
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # snake
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # giant centipede
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # jaculi
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # troglodyte
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # giant ant
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # floating eye
    [0, 0, 0, 8, 0, 10,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # leprechaun
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # nymph
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # quasit
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # rust monster
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # zombie
    [0, 0, 0, 8, 0, 4,  0, 0, 0, 0, 0, 0, 4, 0,  0, 0, 0, 0, 0, 4, 0,  4, 0, 4, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # assassin bug
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # bugbear
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # hell hound
    [0, 6, 0, 0, 0, 0,  12, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # ice lizard
    [0, 0, 0, 0, 0, 0,  11, 0, 0, 0, 0, 0, 0, 0,  0, 15, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # centaur
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # troll
    [0, 7, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  4, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # yeti
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 15, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # white dragon
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 14, 0,  0, 15, 0, 0, 0, 0, 0,  4, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # elf
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 14, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # gelatinous cube
    [0, 13, 0, 8, 0, 10,  2, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4, 0,  0, 0, 0, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # metamorph
    [0, 13, 0, 0, 0, 0,  2, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4, 0,  4, 0, 0, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # vortex
    [0, 13, 0, 0, 0, 10,  1, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4, 0,  4, 0, 0, 0, 4, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # ziller
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # violet fungi
    [0, 0, 0, 8, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # wraith
    [0, 13, 0, 8, 0, 4,  0, 0, 0, 0, 0, 0, 14, 0,  0, 0, 0, 0, 0, 4, 0,  4, 0, 4, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # forvalaka
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # lama nobe
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # osequip
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # rothe
    [0, 7, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # xorn
    [0, 7, 0, 8, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  4, 0, 0, 0, 4, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # vampire
    [0, 0, 0, 0, 0, 4,  2, 0, 0, 0, 0, 0, 14, 0,  0, 0, 0, 0, 0, 4, 0,  0, 0, 4, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # invisible staker
    [0, 0, 0, 0, 0, 0,  1, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # poltergeist
    [0, 13, 0, 8, 0, 4,  1, 0, 0, 0, 0, 0, 0, 0,  0, 4, 0, 0, 0, 4, 0,  4, 0, 4, 0, 4, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # disenchantress
    [0, 0, 0, 8, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # shambling mound
    [0, 0, 0, 0, 0, 10,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # yellow mold
    [0, 0, 0, 8, 0, 10,  1, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 4, 0,  0, 0, 0, 0, 0, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # umber hulk
    [0, 7, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # gnome king
    [0, 7, 0, 0, 3, 0,  0, 0, 0, 0, 0, 0, 0, 5,  0, 0, 9, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # mimic
    [0, 0, 0, 0, 0, 0,  2, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # water lord
    [0, 13, 0, 8, 3, 4,  1, 0, 0, 0, 0, 0, 0, 0,  0, 0, 9, 0, 0, 4, 0,  0, 0, 0, 0, 16, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # bronze dragon
    [0, 7, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # green dragon
    [0, 7, 0, 0, 0, 0,  11, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # purple worm
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # xvart
    [0, 13, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 4, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # spirit naga
    [0, 13, 0, 8, 3, 4,  1, 0, 0, 0, 0, 0, 14, 5,  0, 4, 9, 0, 0, 4, 0,  4, 0, 4, 0, 4, 4,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # silver dragon
    [0, 6, 0, 9, 0, 0,  12, 0, 0, 0, 0, 0, 0, 0,  0, 0, 9, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # platinum dragon
    [0, 7, 0, 9, 0, 0,  11, 0, 0, 0, 0, 0, 14, 0,  0, 0, 9, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # green urchin
    [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # red dragon
    [0, 6, 0, 0, 0, 0,  12, 0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 9, 0, 0, 4, 0,  4, 0, 9, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 9, 0, 0, 4, 0,  4, 0, 9, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 9, 0, 0, 4, 0,  4, 0, 9, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 9, 0, 0, 4, 0,  4, 0, 9, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 9, 0, 0, 4, 0,  4, 0, 9, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 4, 0, 0, 4, 0,  4, 0, 0, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon lord
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 4, 0, 0, 4, 0,  4, 0, 0, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # demon prince
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  0, 0, 4, 0, 0, 4, 0,  4, 0, 4, 0, 4, 4,  3, 0, 0, 9, 4,  9, 0, 0, 0, 0, 0],
    # God of Hellfire
    [0, 13, 0, 8, 3, 10,  1, 0, 0, 0, 0, 0, 14, 5,  18, 0, 9, 0, 0, 4, 0,  4, 18, 4, 0, 0, 4,  4, 4, 0, 9, 4,  9, 0, 17, 0, 0, 0],
]

spelmes = [
    "",                                          # 0  spell has no effect on the monster
    "the web had no effect on the %s",           # 1
    "the %s changed shape to avoid the web",     # 2
    "the %s isn't afraid of you",                # 3
    "the %s isn't affected",                     # 4
    "the %s can see you with his infravision",   # 5
    "the %s vaporizes your missile",             # 6
    "your missile bounces off the %s",           # 7
    "the %s doesn't sleep",                      # 8
    "the %s resists",                            # 9
    "the %s can't hear the noise",               # 10
    "the %s's tail cuts it free of the web",     # 11
    "the %s burns through the web",              # 12
    "your missiles pass right through the %s",   # 13
    "the %s sees through your illusions",        # 14
    "the %s loves the cold!",                    # 15
    "the %s loves the water!",                   # 16
    "the demon is terrified of the %s!",         # 17
    "the %s loves fire and lightning!",          # 18
]

# The C rows only initialise 38 of the SPELL_COUNT (39) entries; the
# remaining entry (permanence) is implicitly 0.
for _row in spelweird:
    _row.extend([0] * (SPELL_COUNT - len(_row)))
del _row

eys = "\nEnter your spell [D for list, ESC to abort]: "


class isave:
    """Used for alter reality spell."""

    def __init__(self, type, id, arg):
        self.type = type   # 0=item,  1=monster
        self.id = id       # item number or monster number
        self.arg = arg     # the type of item or hitpoints of monster


# =============================================================================
# Helpers

_CONV_RE = re.compile(r"%(%|[-+ #0]*\d*(?:\.\d+)?[hlL]*[diouxXeEfFgGcs])")


def _cfmt(fmt, *args):
    """C printf-style formatting that, like C, ignores surplus arguments."""
    n = sum(1 for m in _CONV_RE.finditer(fmt) if m.group(1) != "%")
    return fmt % tuple(args[:n])


def _Printf(fmt, *args):
    """Printf where the format may use fewer conversions than args given."""
    ularn_win.Print(_cfmt(fmt, *args))


def _dirsub():
    """Call ularn_ask.dirsub (C: int dirsub(int *x, int *y)).

    Returns (d, x, y).
    """
    return ularn_ask.dirsub(0, 0)


def _show_adjacent_walls(x1, y1, x2, y2):
    """Redisplay known wall cells in the rectangle (after AnalyseWalls)."""
    for tx in range(x1, x2 + 1):
        for ty in range(y1, y2 + 1):
            if dungeon.checkxy(tx, ty):
                if (dungeon.know[tx][ty] != itm.OUNKNOWN) and (dungeon.item[tx][ty] == itm.OWALL):
                    ularn_win.show1cell(tx, ty)


# =============================================================================
# Local functions

def isconfuse():
    """Check if player is confused; returns confused time remaining."""
    if player.c[player.CONFUSE]:
        ularn_win.Print(" You can't aim your magic!")
        ularn_win.UlarnBeep()
    return player.c[player.CONFUSE]


def nospell(x, monst):
    """Check if a spell affects a monster.

    Returns 0 if the monster is affected, 1 if it is immune (message printed).
    """
    # bad spell or monst
    if (x >= SPELL_COUNT) or (monst >= monster.MONST_COUNT) or (monst < 0) or (x < 0):
        return 0

    tmp = spelweird[monst][x]
    if tmp == 0:
        return 0

    ularn_win.Print("\n")
    _Printf(spelmes[tmp], monster.monster[monst].name)
    return 1


def do_magic_fx(x, y, fx):
    """Display the magic effect on the map."""
    frame_count = ularn_win.magic_effect_frames(fx)

    for frame in range(frame_count):
        ularn_win.magic_effect(x, y, fx, frame)
        ularn_win.nap(75)


def vaporize_rock():
    """Process the vaporize rock spell."""
    c = player.c
    item = dungeon.item
    mitem = dungeon.mitem
    playerx = player.playerx
    playery = player.playery
    level = dungeon.level

    # calculate the area for vaporize rock
    xl = max(playerx - 1, 1)
    yl = max(playery - 1, 1)
    xh = min(playerx + 1, dungeon.MAXX - 2)
    yh = min(playery + 1, dungeon.MAXY - 2)

    frame_count = ularn_win.magic_effect_frames(ularn_win.MAGIC_VAPORIZE)

    # Show fx
    for frame in range(frame_count):
        for i in range(xl, xh + 1):
            for j in range(yl, yh + 1):
                # only show effect on objects/monsters that are rock
                it = item[i][j]
                pm = mitem[i][j].mon

                show_effect = 0
                if it == itm.OWALL:
                    # can't vpr below V2
                    if level < dungeon.VBOTTOM - 2:
                        show_effect = 1
                elif it in (itm.OSTATUE, itm.OTHRONE, itm.OALTAR):
                    show_effect = 1

                # Rock based monsters take damage from vpr
                if pm in (monster.XORN, monster.TROLL):
                    show_effect = 1

                if show_effect:
                    ularn_win.magic_effect(i, j, ularn_win.MAGIC_VAPORIZE, frame)

        ularn_win.nap(75)

    # process spell effect
    for i in range(xl, xh + 1):
        for j in range(yl, yh + 1):
            pm = mitem[i][j].mon
            it = item[i][j]

            if it == itm.OWALL:
                # can't vpr below V2
                if level < dungeon.VBOTTOM - 2:
                    it = itm.ONOTHING
            elif it == itm.OSTATUE:
                if (c[player.HARDGAME] > 3) and (rnd(60) < 30):
                    # Redisplay statue
                    ularn_win.show1cell(i, j)
                else:
                    it = itm.OBOOK
                    dungeon.iarg[i][j] = level
            elif it == itm.OTHRONE:
                # Note: as in C, only the local pm is set (no monster placed)
                pm = monster.GNOMEKING
                it = itm.OTHRONE2
                dungeon.hitp[i][j] = monster.monster[monster.GNOMEKING].hitpoints
            elif it == itm.OALTAR:
                pm = monster.DEMONPRINCE
                dungeon.hitp[i][j] = monster.monster[monster.DEMONPRINCE].hitpoints
                monster.createmonster(monster.DEMONPRINCE)
                monster.createmonster(monster.DEMONPRINCE)
                monster.createmonster(monster.DEMONPRINCE)
                monster.createmonster(monster.DEMONPRINCE)

            # Rock based monsters take damage from vpr
            if pm == monster.XORN:
                monster.ifblind(i, j)
                monster.hitm(i, j, 200, 1)
            elif pm == monster.TROLL:
                monster.ifblind(i, j)
                monster.hitm(i, j, 200, 1)

            item[i][j] = it

    # Work out the new wall tiles for adjacent walls to those vaporised
    dungeon.AnalyseWalls(playerx - 2, playery - 2, playerx + 2, playery + 2)

    _show_adjacent_walls(playerx - 2, playery - 2, playerx + 2, playery + 2)


def direct(spnum, dam, str, arg, fx):
    """Ask for a direction to a spell and then hit the monster.

    str: format; first specifier '%s' for the monster name, second '%d'
         for arg.  Not all specifiers are required.
    """
    # check for bad arguments
    if (spnum < 0) or (spnum >= SPELL_COUNT) or (str is None):
        return

    # check player confusion
    if isconfuse():
        return

    # Ask for direction
    d, x, y = _dirsub()

    if not dungeon.checkxy(x, y):
        # The direction selected is off the map
        return

    m = dungeon.mitem[x][y].mon

    if dungeon.item[x][y] == itm.OMIRROR:
        if spnum == SPELL_SLE:
            # sleep
            ularn_win.Print("You fall asleep! ")
            ularn_win.UlarnBeep()

            arg += 2
            while arg > 0:
                arg -= 1
                monster.parse2()
                ularn_win.nap(1000)

            return
        elif spnum == SPELL_WEB:
            # web
            ularn_win.Print("You get stuck in your own web! ")
            ularn_win.UlarnBeep()

            arg += 2
            while arg > 0:
                arg -= 1
                monster.parse2()
                ularn_win.nap(1000)

            return
        else:
            _Printf(str, "spell caster (that's you)", arg)
            ularn_win.UlarnBeep()
            player.losehp(scores.DIED_OWN_MAGIC, dam)
            return

    if m == monster.MONST_NONE:
        ularn_win.Print("  There wasn't anything there!")
        return

    monster.ifblind(x, y)

    # Do magic fx
    do_magic_fx(x, y, fx)
    ularn_win.show1cell(x, y)

    if nospell(spnum, m):
        monster.last_monst_hx = x
        monster.last_monst_hy = y
        return

    _Printf(str, monster.lastmonst, arg)
    monster.hitm(x, y, dam, 1)


def tdirect(spnum):
    """Ask for a direction to a spell and then teleport away the monster."""
    # check for bad args
    if (spnum < 0) or (spnum >= SPELL_COUNT):
        return

    # check for player confusion
    if isconfuse():
        return

    # Ask for direction
    d, x, y = _dirsub()

    if not dungeon.checkxy(x, y):
        # The direction selected is off the map
        return

    m = dungeon.mitem[x][y].mon
    if m == monster.MONST_NONE:
        ularn_win.Print("  There wasn't anything there!")
        return

    monster.ifblind(x, y)

    if nospell(spnum, m):
        monster.last_monst_hx = x
        monster.last_monst_hy = y
        return

    do_magic_fx(x, y, ularn_win.MAGIC_TELEPORT)
    monster.teleportmonst(x, y, m)


def makewall(spnum):
    """Process the make wall spell."""
    # check for bad args
    if spnum < 0 or spnum >= SPELL_COUNT:
        return

    # check for player confusion
    if isconfuse():
        return

    # Ask for direction
    d, x, y = _dirsub()

    item = dungeon.item

    if dungeon.checkxy(x, y):
        # within bounds
        if item[x][y] != itm.OWALL:
            # can't make anything on walls
            if item[x][y] == itm.ONOTHING:
                # is it free of items?
                if dungeon.mitem[x][y].mon == monster.MONST_NONE:
                    # is it free of monsters?
                    if (dungeon.level != 1) or (x != 33) or (y != dungeon.MAXY - 1):
                        do_magic_fx(x, y, ularn_win.MAGIC_WALL)

                        item[x][y] = itm.OWALL
                        ularn_win.show1cell(x, y)

                        # Work out the new wall tiles for adjacent walls
                        dungeon.AnalyseWalls(x - 1, y - 1, x + 1, y + 1)

                        _show_adjacent_walls(x - 1, y - 1, x + 1, y + 1)
                    else:
                        ularn_win.Print("\nyou can't make a wall there!")
                else:
                    ularn_win.Print("\nthere's a monster there!")
            else:
                ularn_win.Print("\nthere's something there already!")
        else:
            ularn_win.Print("\nthere's a wall there already!")


def omnidirect(spnum, dam, str, fx):
    """Cast a spell and then hit the monsters in all directions.

    str should contain a '%s' for the monster name.
    """
    # check for bad args
    if spnum < 0 or spnum >= SPELL_COUNT or str is None:
        return

    playerx = player.playerx
    playery = player.playery

    # get the area affected
    xl = max(playerx - 1, 0)
    yl = max(playery - 1, 0)
    xh = min(playerx + 1, dungeon.MAXX - 1)
    yh = min(playery + 1, dungeon.MAXY - 1)

    # Show magic effect
    frame_count = ularn_win.magic_effect_frames(fx)
    for frame in range(frame_count):
        for x in range(xl, xh + 1):
            for y in range(yl, yh + 1):
                if (x != playerx) or (y != playery):
                    ularn_win.magic_effect(x, y, fx, frame)
        ularn_win.nap(75)

    # Redisplay cell
    for x in range(xl, xh + 1):
        for y in range(yl, yh + 1):
            if (x != playerx) or (y != playery):
                ularn_win.show1cell(x, y)

    for x in range(xl, xh + 1):
        for y in range(yl, yh + 1):
            m = dungeon.mitem[x][y].mon
            if m != monster.MONST_NONE:
                if nospell(spnum, m) == 0:
                    monster.ifblind(x, y)
                    ularn_win.Printc('\n')
                    _Printf(str, monster.lastmonst)
                    monster.hitm(x, y, dam, 1)
                    ularn_win.nap(800)
                else:
                    monster.last_monst_hx = x
                    monster.last_monst_hy = y


def dirpoly(spnum):
    """Ask for a direction and polymorph a monster."""
    # check for bad args
    if spnum < 0 or spnum >= SPELL_COUNT:
        return

    # check for player confusion
    if isconfuse():
        return

    # Ask for direction
    d, x, y = _dirsub()

    if not dungeon.checkxy(x, y):
        # The direction selected is off the map
        return

    mitem = dungeon.mitem

    if mitem[x][y].mon == monster.MONST_NONE:
        ularn_win.Print("  There wasn't anything there!")
        return

    monster.ifblind(x, y)

    if nospell(spnum, mitem[x][y].mon):
        monster.last_monst_hx = x
        monster.last_monst_hy = y
        return

    # show some magic animation
    do_magic_fx(x, y, ularn_win.MAGIC_SPARKLE)

    # Transform into a non-genocided monster
    while True:
        m = rnd(monster.MAXMONST + 7)
        mitem[x][y].mon = m
        if (monster.monster[m].flags & monster.FL_GENOCIDED) == 0:
            break

    dungeon.hitp[x][y] = monster.monster[m].hitpoints
    ularn_win.show1cell(x, y)  # show the new monster


def genmonst():
    """Ask for a monster and genocide it from the game (sets FL_GENOCIDED)."""
    textmode = 0
    done = 0

    while not done:
        ularn_win.Print("\nEnter the number of the monster to genocide [* for list]: ")
        i = ularn_win.get_num_input(-1)

        if i == -1:
            ularn_win.set_display(ularn_win.DISPLAY_TEXT)
            ularn_win.ClearText()
            textmode = 1

            ularn_win.Print("Monster numbers")
            column = 0
            row = 3
            for j in range(1, monster.DEMONLORD):
                ularn_win.MoveCursor(column * 28 + 1, row)
                # NOTE: the C code tests monster[i] here (i == -1, an
                # out-of-bounds read); Python's monster[-1] is the last entry.
                if (monster.monster[i].flags & monster.FL_GENOCIDED) == 0:
                    ularn_win.Printf("%-2d) %s", j, monster.monster[j].name)
                else:
                    ularn_win.Printf("%-2d) Genocided", j)

                column += 1
                if column > 2:
                    column = 0
                    row += 1

            ularn_win.Print("\n")

        elif (i > 0) and (i < monster.DEMONLORD):
            if ((monster.monster[i].flags & monster.FL_GENOCIDED) == 0) or player.wizard:
                if textmode:
                    ularn_win.set_display(ularn_win.DISPLAY_MAP)
                    textmode = 0

                # genocided from game
                monster.monster[i].flags |= monster.FL_GENOCIDED
                ularn_win.Printf("\n  There will be no more %ss.", monster.monster[i].name)

                # now wipe out monsters on this level
                dungeon.newcavelevel(dungeon.level)
                ularn_win.draws(0, dungeon.MAXX, 0, dungeon.MAXY)
                ularn_win.UpdateStatusAndEffects()
                done = 1
        else:
            if textmode:
                ularn_win.set_display(ularn_win.DISPLAY_MAP)
                textmode = 0

            ularn_win.Print("\n  You sense failure!")
            done = 1

    # Make sure the map is displayed on exit
    if textmode:
        ularn_win.set_display(ularn_win.DISPLAY_MAP)


def speldamage(Spell):
    """Perform spell actions cast by the player.

    Please insure that there are 2 spaces before all messages here.
    """
    c = player.c

    # no such spell
    if Spell >= SPELL_COUNT:
        return

    if c[player.TIMESTOP]:
        # not if time stopped
        ularn_win.Print("\n  It didn't seem to work.")
        return

    if (rnd(23) == 7) or (rnd(18) > c[player.INTELLIGENCE]):
        ularn_win.Print("\n  It didn't work!")
        return

    clev = c[player.LEVEL]
    if (clev * 3 + 2) < Spell:
        ularn_win.Print("\n  Nothing happens.  You seem inexperienced.")
        return

    playerx = player.playerx
    playery = player.playery

    # ----- LEVEL 1 SPELLS -----
    if Spell == SPELL_PRO:
        if c[player.PROTECTIONTIME] == 0:
            c[player.MOREDEFENSES] += SPELL_PRO_BOOST  # protection field +2
        c[player.PROTECTIONTIME] += 250
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_MLE:
        # magic missile
        i = rnd(((clev + 1) << 1)) + clev + 3
        godirect(Spell, i,
                 "  Your missiles hit the %s." if (clev >= 2) else
                 "  Your missile hit the %s.", 100, ularn_win.EFFECT_MLE)
        return

    elif Spell == SPELL_DEX:
        # dexterity
        if c[player.DEXCOUNT] == 0:
            player.adjust_ability(player.DEXTERITY, SDEXTERITY_BOOST)
        c[player.DEXCOUNT] += 400
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_SLE:
        # sleep
        i = rnd(3) + 1
        s = "  While the %s slept, you smashed it %d times."
        direct(Spell, monster.fullhit(i), s, i, ularn_win.MAGIC_SLEEP)
        return

    elif Spell == SPELL_CHM:
        # charm monster
        c[player.CHARMCOUNT] += c[player.CHARISMA] << 1
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_SSP:
        # sonic spear
        godirect(Spell, rnd(10) + 15 + clev,
                 "  The sound damages the %s.", 70, ularn_win.EFFECT_SSP)
        return

    # ----- LEVEL 2 SPELLS -----
    elif Spell == SPELL_WEB:
        # web
        i = rnd(3) + 2
        s = "  While the %s is entangled, you hit it %d times."
        direct(Spell, monster.fullhit(i), s, i, ularn_win.MAGIC_WEB)
        return

    elif Spell == SPELL_STR:
        # strength
        if c[player.STRCOUNT] == 0:
            c[player.STREXTRA] += SSTRENGTH_BOOST
        c[player.STRCOUNT] += 150 + rnd(100)
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_ENL:
        # enlightenment
        yl = playery - 5
        yh = playery + 6
        xl = playerx - 15
        xh = playerx + 16
        # vxy(xl, yl); vxy(xh, yh); -- check bounds
        if xl < 0:
            xl = 0
        if yl < 0:
            yl = 0
        if xl >= dungeon.MAXX:
            xl = dungeon.MAXX - 1
        if yl >= dungeon.MAXY:
            yl = dungeon.MAXY - 1
        if xh < 0:
            xh = 0
        if yh < 0:
            yh = 0
        if xh >= dungeon.MAXX:
            xh = dungeon.MAXX - 1
        if yh >= dungeon.MAXY:
            yh = dungeon.MAXY - 1

        for i in range(yl, yh + 1):  # enlightenment
            for j in range(xl, xh + 1):
                dungeon.know[j][i] = dungeon.item[j][i]

        ularn_win.draws(xl, xh + 1, yl, yh + 1)
        return

    elif Spell == SPELL_HEL:
        # healing
        player.raisehp(20 + (clev << 1))
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_CBL:
        # cure blindness
        c[player.BLINDCOUNT] = 0
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_CRE:
        if player.wizard:
            ularn_win.Printf("Number: ")
            i = ularn_win.get_num_input(-1)
            if i != -1:
                monster.createmonster(i)
                return
        monster.createmonster(monster.makemonst(dungeon.level + 1) + 8)
        return

    elif Spell == SPELL_PHA:
        # illusion
        if rnd(11) + 7 <= c[player.WISDOM]:
            direct(Spell, rnd(20) + 20 + clev, "  The %s believed!", 0,
                   ularn_win.MAGIC_PHANTASMAL)
        else:
            ularn_win.Print("  It didn't believe the illusions!")
        return

    elif Spell == SPELL_INV:
        # if he has the amulet of invisibility then add more time
        j = 0
        for i in range(player.IVENSIZE):
            if player.iven[i] == itm.OAMULET:
                j += 1 + player.ivenarg[i]
        c[player.INVISIBILITY] += (j << 7) + 12
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    # ----- LEVEL 3 SPELLS -----
    elif Spell == SPELL_BAL:
        # fireball
        godirect(Spell, rnd(25 + clev) + 25 + clev,
                 "  The fireball hits the %s.", 40, ularn_win.EFFECT_BAL)
        return

    elif Spell == SPELL_CLD:
        # cold
        godirect(Spell, rnd(25) + 20 + clev,
                 "  The cone of cold strikes the %s.", 60, ularn_win.EFFECT_CLD)
        return

    elif Spell == SPELL_PLY:
        # polymorph
        dirpoly(Spell)
        return

    elif Spell == SPELL_CAN:
        # cancellation
        c[player.CANCELLATION] += 5 + clev
        return

    elif Spell == SPELL_HAS:
        # haste self
        c[player.HASTESELF] += 7 + clev
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_CKL:
        # cloud kill
        omnidirect(Spell, 30 + rnd(10), "  The %s gasps for air!", ularn_win.MAGIC_CLOUD)
        return

    elif Spell == SPELL_VPR:
        vaporize_rock()
        return

    # ----- LEVEL 4 SPELLS -----
    elif Spell == SPELL_DRY:
        # dehydration
        direct(Spell, 100 + clev, "  The %s shrivels up.", 0, ularn_win.MAGIC_DEHYDRATE)
        return

    elif Spell == SPELL_LIT:
        # lightning
        godirect(Spell, rnd(25) + 20 + (clev << 1),
                 "  A lightning bolt hits the %s.", 10, ularn_win.EFFECT_LIT)
        return

    elif Spell == SPELL_DRL:
        # drain life
        i = min(c[player.HP] - 1, cdiv(c[player.HPMAX], 2))
        direct(Spell, i + i, "", 0, ularn_win.MAGIC_DRAIN)
        c[player.HP] -= i
        return

    elif Spell == SPELL_GLO:
        # globe of invulnerability
        if c[player.GLOBE] == 0:
            c[player.MOREDEFENSES] += SPELL_GLOBE_BOOST
        c[player.GLOBE] += 200
        player.adjust_ability(player.INTELLIGENCE, -1)
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_FLO:
        # flood
        omnidirect(Spell, 32 + clev,
                   "  The %s struggles for air in your flood!",
                   ularn_win.MAGIC_FLOOD)
        return

    elif Spell == SPELL_FGR:
        # finger of death
        if rnd(151) == 63:
            ularn_win.UlarnBeep()
            ularn_win.Print("\nYour heart stopped!\n")
            ularn_win.nap(4000)
            scores.died(scores.DIED_ERASED_BY_WAYWARD_FINGER, 0)
            return

        if c[player.WISDOM] > rnd(10) + 10:
            direct(Spell, 2000, "  The %s's heart stopped.", 0, ularn_win.MAGIC_FINGER)
        else:
            ularn_win.Print("  It didn't work.")
        return

    # ----- LEVEL 5 SPELLS -----
    elif Spell == SPELL_SCA:
        # scare monster
        c[player.SCAREMONST] += rnd(10) + clev

        # if have HANDofFEAR make last longer
        for i in range(player.IVENSIZE):
            if player.iven[i] == itm.OHANDofFEAR:
                c[player.SCAREMONST] *= 3
                break

        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_HLD:
        # hold monster
        c[player.HOLDMONST] += rnd(10) + clev
        return

    elif Spell == SPELL_STP:
        # time stop
        c[player.TIMESTOP] += rnd(20) + (clev << 1)
        return

    elif Spell == SPELL_TEL:
        # teleport
        tdirect(Spell)
        return

    elif Spell == SPELL_MFI:
        # magic fire
        omnidirect(Spell, 35 + rnd(10) + clev, "  The %s cringes from the flame.",
                   ularn_win.MAGIC_FIRE)
        return

    # ----- LEVEL 6 SPELLS -----
    elif Spell == SPELL_MKW:
        # make wall
        makewall(Spell)
        return

    elif Spell == SPELL_SPH:
        # sphere of annihilation
        if (rnd(23) == 5) and (player.wizard == 0):
            if not player.player_has_item(itm.OSPHTALISMAN):
                ularn_win.UlarnBeep()
                ularn_win.Print("\nYou have been enveloped by the zone of nothingness!\n")
                ularn_win.nap(4000)
                scores.died(scores.DIED_SELF_ANNIHLATED, 0)
                return

        xl = playerx
        yl = playery
        player.adjust_ability(player.INTELLIGENCE, -1)
        i, xl, yl = _dirsub()  # get direction of sphere
        sphere.newsphere(xl, yl, i, rnd(20) + 11)  # make a sphere
        return

    elif Spell == SPELL_GEN:
        # genocide
        genmonst()
        player.spelknow[SPELL_GEN] -= 1
        player.adjust_ability(player.INTELLIGENCE, -1)
        return

    elif Spell == SPELL_SUM:
        # summon demon
        if rnd(100) > 30:
            direct(Spell, 150, "  The demon strikes at the %s.", 0, ularn_win.MAGIC_DEMON)
            return
        if rnd(100) > 15:
            ularn_win.Print("  Nothing seems to have happened.")
            return
        ularn_win.Print("  The demon turned on you and then vanished!")
        ularn_win.UlarnBeep()
        i = rnd(40) + 30
        player.losehp(scores.DIED_ATTACKED_BY_DEMON, i)  # must say killed by a demon
        return

    elif Spell == SPELL_WTW:
        # walk through walls
        c[player.WTW] += rnd(10) + 5
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    elif Spell == SPELL_ALT:
        # alter reality
        item = dungeon.item
        iarg = dungeon.iarg
        mitem = dungeon.mitem
        hitp = dungeon.hitp
        MAXX = dungeon.MAXX
        MAXY = dungeon.MAXY

        save = []  # item save structures

        # save all items and monsters
        for j in range(MAXY):
            for i in range(MAXX):
                xl = item[i][j]
                if (xl != itm.ONOTHING) and (xl != itm.OWALL) and (xl != itm.OANNIHILATION):
                    save.append(isave(0, item[i][j], iarg[i][j]))
                if mitem[i][j].mon:
                    save.append(isave(1, mitem[i][j].mon, hitp[i][j]))
                item[i][j] = itm.OWALL
                mitem[i][j].mon = monster.MONST_NONE

        dungeon.eat(1, 1)

        if dungeon.level == 1:
            item[33][MAXY - 1] = itm.ONOTHING

        j = rnd(MAXY - 2)
        for i in range(1, MAXX - 1):
            item[i][j] = itm.ONOTHING

        # put objects back in level
        sc = len(save)
        while sc > 0:
            sc -= 1
            if save[sc].type == 0:
                trys = 100
                while True:
                    trys -= 1
                    i = rnd(MAXX - 1)
                    j = rnd(MAXY - 1)
                    if not ((trys > 0) and (item[i][j] != itm.ONOTHING)):
                        break
                if trys:
                    item[i][j] = save[sc].id
                    iarg[i][j] = save[sc].arg
            else:
                # put monsters back in
                trys = 100
                while True:
                    trys -= 1
                    i = rnd(MAXX - 1)
                    j = rnd(MAXY - 1)
                    if not ((trys > 0) and ((item[i][j] == itm.OWALL) or mitem[i][j].mon)):
                        break
                if trys:
                    mitem[i][j].mon = save[sc].id
                    hitp[i][j] = save[sc].arg

        player.adjust_ability(player.INTELLIGENCE, -1)

        dungeon.AnalyseWalls(0, 0, MAXX, MAXY)

        for i in range(MAXX):
            for j in range(MAXY):
                if player.wizard:
                    dungeon.know[i][j] = item[i][j]
                else:
                    dungeon.know[i][j] = itm.OUNKNOWN

        ularn_win.draws(0, MAXX, 0, MAXY)
        if player.wizard == 0:
            player.spelknow[SPELL_ALT] -= 1
        player.positionplayer()
        return

    elif Spell == SPELL_PER:
        # permanence
        player.adjusttime(-99999)
        player.spelknow[SPELL_PER] -= 1  # forget
        player.adjust_ability(player.INTELLIGENCE, -1)
        do_magic_fx(playerx, playery, ularn_win.MAGIC_SPARKLE)
        return

    else:
        ularn_win.Printf("  spell %d not available!", Spell)
        ularn_win.UlarnBeep()
        return


# =============================================================================
# Exported functions

def godirect(spnum, dam, str, delay, cshow):
    """Hit in a direction from a missile weapon and keep going until the
    power is exhausted.

    spnum : spell number, dam : initial damage, str : format for the
    message ('%s' = target name), delay : ms between locations,
    cshow : the DirEffectsType effect to show.
    """
    c = player.c
    item = dungeon.item

    # check for bad args
    if (spnum < 0) or (spnum >= SPELL_COUNT) or (str is None) or (delay < 0):
        return

    # Check player confusion
    if isconfuse():
        return

    # Ask for direction
    dir, x, y = _dirsub()

    playerx = player.playerx
    playery = player.playery

    dx = x - playerx
    dy = y - playery
    x = playerx
    y = playery

    while dam > 0:
        x += dx
        y += dy

        if not dungeon.checkxy(x, y):
            # out of bounds
            break

        # if energy hits player
        if (x == player.playerx) and (y == player.playery):
            ularn_win.Print("\nYou are hit by your own magic!")
            ularn_win.UlarnBeep()

            player.losehp(scores.DIED_OWN_MAGIC, dam)
            return

        # if not blind show effect
        if c[player.BLINDCOUNT] == 0:
            ularn_win.mapeffect(x, y, cshow, dir)
            ularn_win.nap(delay)
            ularn_win.show1cell(x, y)

        # is there a monster there?
        m = dungeon.mitem[x][y].mon
        if m != monster.MONST_NONE:
            monster.ifblind(x, y)

            # cannot cast a missile spell at lucifer!!
            if (m == monster.LUCIFER) or (m >= monster.DEMONLORD and rnd(100) < 10):
                dx *= -1
                dy *= -1
                ularn_win.Print("\n")
                ularn_win.Printf("\nthe %s returns your puny missile!",
                                 monster.monster[m].name)
            else:
                if nospell(spnum, m):
                    monster.last_monst_hx = x
                    monster.last_monst_hy = y
                    return

                ularn_win.Printc('\n')
                _Printf(str, monster.lastmonst)
                dam -= monster.hitm(x, y, dam, 1)
                ularn_win.show1cell(x, y)
                ularn_win.nap(1000)

                x -= dx
                y -= dy
        else:
            it = item[x][y]
            if it == itm.OWALL:
                ularn_win.Printc('\n')
                _Printf(str, "wall")
                if dam >= 50 + c[player.HARDGAME]:
                    # enough damage?
                    if dungeon.level < dungeon.VBOTTOM - 2:
                        # can't break wall below V2
                        if (x < dungeon.MAXX - 1) and (y < dungeon.MAXY - 1) and x and y:
                            ularn_win.Print("  The wall crumbles.")
                            item[x][y] = itm.ONOTHING
                            ularn_win.show1cell(x, y)

                            # Work out the new wall tiles for adjacent walls
                            dungeon.AnalyseWalls(x - 1, y - 1, x + 1, y + 1)

                            _show_adjacent_walls(x - 1, y - 1, x + 1, y + 1)
                dam = 0

            elif it == itm.OCLOSEDDOOR:
                ularn_win.Printc('\n')
                _Printf(str, "door")
                if dam >= 40:
                    ularn_win.Print("  The door is blasted apart.")
                    item[x][y] = itm.ONOTHING
                    ularn_win.show1cell(x, y)
                dam = 0

            elif it == itm.OSTATUE:
                ularn_win.Printc('\n')
                _Printf(str, "statue")
                if dam > 44:
                    if (c[player.HARDGAME] <= 3) and (rnd(60) < 30):
                        # 50% chance of revealing a book if difficulty <= 3
                        ularn_win.Print("  The statue crumbles.")
                        item[x][y] = itm.OBOOK
                        dungeon.iarg[x][y] = dungeon.level
                        ularn_win.show1cell(x, y)
                dam = 0

            elif it == itm.OTHRONE:
                ularn_win.Printc('\n')
                _Printf(str, "throne")
                if dam > 33:
                    # If destroying a throne, a gnome king appears
                    dungeon.mitem[x][y].mon = monster.GNOMEKING
                    dungeon.hitp[x][y] = monster.monster[monster.GNOMEKING].hitpoints
                    item[x][y] = itm.OTHRONE2
                    ularn_win.show1cell(x, y)
                dam = 0

            elif it == itm.OMIRROR:
                dx *= -1
                dy *= -1
                dir = ularn_game.ReverseDir[dir]

        dam -= 3 + (c[player.HARDGAME] >> 1)


def annihilate():
    """Annihilate all monsters around the player.

    Gives player experience, but no dropped objects.
    """
    playerx = player.playerx
    playery = player.playery
    mitem = dungeon.mitem

    # get the area affected
    xl = max(playerx - 1, 0)
    yl = max(playery - 1, 0)
    xh = min(playerx + 1, dungeon.MAXX - 1)
    yh = min(playery + 1, dungeon.MAXY - 1)

    frame_count = ularn_win.magic_effect_frames(ularn_win.MAGIC_ANNIHILATE)
    for frame in range(frame_count):
        for x in range(xl, xh + 1):
            for y in range(yl, yh + 1):
                if (x != playerx) or (y != playery):
                    ularn_win.magic_effect(x, y, ularn_win.MAGIC_ANNIHILATE, frame)
        ularn_win.nap(75)

    xp = 0
    for x in range(xl, xh + 1):
        for y in range(yl, yh + 1):
            monst = mitem[x][y].mon
            if monst != monster.MONST_NONE:
                # if a monster there
                if monst < monster.DEMONLORD:
                    xp += monster.monster[monst].experience
                    mitem[x][y].mon = monster.MONST_NONE
                else:
                    ularn_win.Printf("\nThe %s barely escapes being annihilated!",
                                     monster.monster[monst].name)
                    # lose half hit points
                    dungeon.hitp[x][y] = (dungeon.hitp[x][y] >> 1) + 1

    if xp > 0:
        ularn_win.Print("\nYou hear loud screams of agony!")
        player.raiseexperience(xp)

    # redisplay cells
    for x in range(xl, xh + 1):
        for y in range(yl, yh + 1):
            if (x != playerx) or (y != playery):
                ularn_win.show1cell(x, y)


def get_spell_code(prompt):
    """Get the player to input the three letter spell code.

    Python signature: returns the code as a 3 character str, or "" if the
    entry was aborted with ESC (C sets code[0] = 0).
    """
    code = []

    ularn_win.Print(prompt)

    Pos = 0
    while True:
        a = ularn_win.get_prompt_input("", "abcdefghijklmnopqrstuvwxyzD\033", 1)

        if (Pos == 0) and (a == 'D'):
            show.seemagic(-1)
            ularn_win.Print(prompt)
        elif a != ESC:
            ularn_win.Printc(a)
            code.append(a)
            Pos += 1

        if not ((a != ESC) and (Pos < 3)):
            break

    if a == ESC:
        # to escape casting a spell
        ularn_win.Print("aborted.")
        return ""

    return "".join(code)


def cast():
    """Cast a spell for the player (called by parse)."""
    c = player.c

    if c[player.SPELLS] <= 0:
        ularn_win.Print("\nYou don't have any spells!")
        return

    while True:
        code = get_spell_code(eys)
        if code == "":
            return

        # seq search for his spell
        Found = 0
        i = 0
        while (i < SPELL_COUNT) and not Found:
            if spelcode[i][:3] == code[:3]:
                if player.spelknow[i]:
                    c[player.SPELLS] -= 1
                    ularn_win.Printf(" (%s)", spelname[i])
                    speldamage(i)
                    Found = 1
            i += 1

        if not Found:
            ularn_win.Print(" Unknown spell! Try again.")

        player.recalc()
        ularn_win.UpdateStatusAndEffects()

        if Found:
            break
