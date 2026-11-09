"""Object definitions (port of itm.c and itm.h).

Object ids, display characters, tile numbers and object names.
"""

from .header import *

# ---------------------------------------------------------------- ObjectIdType
OUNKNOWN = 0
ONOTHING = 1
OALTAR = 2
OTHRONE = 3
OTHRONE2 = 4
ODEADTHRONE = 5
OPIT = 6
OSTAIRSUP = 7
OELEVATORUP = 8
OFOUNTAIN = 9
OSTATUE = 10
OTELEPORTER = 11
OMIRROR = 12
OSTAIRSDOWN = 13
OELEVATORDOWN = 14
ODEADFOUNTAIN = 15
OOPENDOOR = 16
OCLOSEDDOOR = 17
OWALL = 18
OGOLDPILE = 19
ODGOLD = 20
OKGOLD = 21
OMAXGOLD = 22
OLARNEYE = 23
OPLATE = 24
OCHAIN = 25
OLEATHER = 26
ORING = 27
OSTUDLEATHER = 28
OSPLINT = 29
OPLATEARMOR = 30
OSSPLATE = 31
OSHIELD = 32
OELVENCHAIN = 33
OSWORDofSLASHING = 34
OHAMMER = 35
OSWORD = 36
O2SWORD = 37
OSPEAR = 38
ODAGGER = 39
OBATTLEAXE = 40
OLONGSWORD = 41
OFLAIL = 42
OLANCE = 43
OVORPAL = 44
OSLAYER = 45
ORINGOFEXTRA = 46
OREGENRING = 47
OPROTRING = 48
OENERGYRING = 49
ODEXRING = 50
OSTRRING = 51
OCLEVERRING = 52
ODAMRING = 53
OBELT = 54
OSCROLL = 55
OPOTION = 56
OBOOK = 57
OCHEST = 58
OORB = 59
OAMULET = 60
OORBOFDRAGON = 61
OSPIRITSCARAB = 62
OCUBEofUNDEAD = 63
ONOTHEFT = 64
OBRASSLAMP = 65
OHANDofFEAR = 66
OSPHTALISMAN = 67
OWWAND = 68
OPSTAFF = 69
OLIFEPRESERVER = 70
ODIAMOND = 71
ORUBY = 72
OEMERALD = 73
OSAPPHIRE = 74
OSCHOOL = 75
ODNDSTORE = 76
OBANK2 = 77
OBANK = 78
OENTRANCE = 79
OVOLDOWN = 80
OVOLUP = 81
OHOME = 82
OTRADEPOST = 83
OLRS = 84
OPAD = 85
OTRAPARROWIV = 86
OTRAPARROW = 87
OIVDARTRAP = 88
ODARTRAP = 89
OTRAPDOOR = 90
OIVTRAPDOOR = 91
OIVTELETRAP = 92
OANNIHILATION = 93
OCOOKIE = 94
OURN = 95
OSPEED = 96
OACID = 97
OHASH = 98
OSHROOMS = 99
OCOKE = 100
OCOUNT = 101

# ---------------------------------------------------------------- How enchantment happened
ENCH_SCROLL = 0  # Enchantment from reading a scroll
ENCH_ALTAR = 1   # Enchantment from an altar

# Character code for each item
objnamelist = [
     ' ', ' ',
     #  Dungeon features 
     'A', 'T', 'T', 'T', 'P', '%', '~', 'F',
     '&', '^', '=', '%', '~', 'f', 'O', 'D',
     '#',
     #  gold piles 
     '*', '*', '*', '*',
     #  eye of larn 
     'o',
     #  armour 
     '[', '[', '[', '[', '[', '[', '[', '[',
     '[', '[',
     #  weapons 
     '(', '(', '(', '(', '(', '(', '(', '(',
     '(', '(', '(', '(',
     #  rings 
     '=', '=', '=', '=', '=', '=', '=', '=',
     #  magic items 
     ')', '?', '!', 'B', 'C', 'o', '"', 'o',
     '.', '.', '.', '.', '.', '.', '/', '/',
     '"',
     #  gems 
     '<', '<', '<', '<',
     #  buildings/entrances 
     'M', 'S', '$', '$', 'E', 'V', 'V', 'H',
     'T', 'L', 'P',
     #  traps 
     ' ', '^', ' ', '^', '^', ' ', ' ',
     #  misc 
     's', 'c', 'u',
     #  drugs 
     ':', ':', ':', ':', ':'
]

objtilelist = [
     175, 191,
     #  Dungeon features 
      64,  65, 142, 144,  67,  68,  69,  70,
      71,  72,  74,  76,  77,  80,  82,  83,
      84,
      #  Gold piles 
      81, 133, 134, 135,
     #  The eye of larn 
      85,
     #  armour 
       86,  87,  88, 123, 124, 125, 126, 127,
      131, 155,
     #  weapons 
      89,  90,  91,  92,  93,  94, 120, 121,
      122, 128, 153, 154,
     #  rings 
      95,  96,  97,  98,  99, 100, 101, 102,
     #  magic items 
     103, 104, 105, 106, 107,  66, 108, 109,
     110, 111, 112, 148, 149, 150, 151, 152,
     162,
     #  gems 
     113, 114, 115, 116,
     #  buildings/entrances 
      73,  75,  79,  78, 117, 118, 119, 132,
     140, 145, 161,
     #  Traps 
     191, 129, 191, 136, 138, 191, 191,
     #  Misc 
     143, 146, 147,
     #  Drugs 
     156, 157, 158, 159, 160
]

# Description for each item
objectname = [
    "",
    "",
    #  Dungeon features 
    "a holy altar",
    "a handsome, jewel-encrusted throne",
    "a handsome, jewel-encrusted throne",
    "a massive throne",
    "a pit",
    "a staircase leading upwards",
    "an elevator going up",
    "a bubbling fountain",
    "a great marble statue",
    "a teleport trap",
    "a mirror",
    "a staircase going down",
    "an elevator going down",
    "a dead fountain",
    "an open door",
    "a closed door",
    "a wall",
    #  Gold piles 
    "gold",
    "gold",
    "gold",
    "gold",
    #  The eye of larn 
    "The Eye of Larn",
    #  armour 
    "plate mail",
    "chain mail",
    "leather armor",
    "ring mail",
    "studded leather armor",
    "splint mail",
    "plate armor",
    "stainless plate armor",
    "a shield",
    "elven chain",
    #  weapons 
    "a sword of slashing",
    "Bessman's flailing hammer",
    "a sunsword",
    "a two-handed sword",
    "a spear",
    "a dagger",
    "a battle axe",
    "a longsword",
    "a flail",
    "a lance of death",
    "the Vorpal Blade",
    "Slayer",
    #  rings 
    "a ring of extra regeneration",
    "a ring of regeneration",
    "a ring of protection",
    "an energy ring",
    "a ring of dexterity",
    "a ring of strength",
    "a ring of cleverness",
    "a ring of increase damage",
    #  magic items 
    "a belt of striking",
    "a magic scroll",
    "a magic potion",
    "a book",
    "a chest",
    "an orb of enlightenment",
    "an amulet of invisibility",
    "an orb of dragon slaying",
    "a scarab of negate spirit",
    "a cube of undead control",
    "a device of theft-prevention",
    "a brass lamp",
    "The Hand of Fear",
    "The Talisman of the Sphere",
    "a wand of wonder",
    "a staff of power",
    "an amulet of life preservation",
    #  gems 
    "a brilliant diamond",
    "a ruby",
    "an enchanting emerald",
    "a sparkling sapphire",
    #  Buildings.entrances 
    "the College of Larn",
    "the DND store",
    "the 8th branch of the Bank of Larn",
    "the Bank of Larn",
    "the dungeon entrance",
    "a volcanic shaft leaning downward",
    "the base of a volcanic shaft",
    "your home",
    "the local trading post",
    "the Larn Revenue Service",
    "Dealer McDope's Pad",
    #  traps 
    "an arrow trap",
    "an arrow trap",
    "a dart trap",
    "a dart trap",
    "a trapdoor",
    "a trapdoor",
    "a teleport trap",
    #  misc 
    "a sphere of annihilation",
    "a fortune cookie",
    "a golden urn",
    #  drugs 
    "some speed",
    "some LSD",
    "some hashish",
    "some magic mushrooms",
    "some cocaine",
]
