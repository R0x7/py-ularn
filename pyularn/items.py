"""The item book: what a campaign's games have found out about items.

It lives beside the recorded runs and the campaign (see `pyularn.learn`)::

    DIR/items.json   one entry per kind of item
    DIR/ITEMS.md     the same, for people to read

Nothing in it is handed to the agent from the game's tables.  Every fact
comes from play, in two ways:

* Measured by the server while the agent plays (`snapshot` / `diff`):
  how much WC or AC an item gives, read off the change when it is wielded,
  worn or taken off; what it cost or fetched in town; the levels it was
  seen lying on.
* Written by the agent (`add_note`): what an item does, when it is worth
  using, what to avoid, each note citing the runs that showed it, like the
  playbook's lessons.

The rest of the module is plain data handling, so it can be tested without
a game.  Only `kind_of`, `all_kinds` and `snapshot` read the engine.
"""

import difflib
import json
import os
import time

from . import runs

BOOK_FILE = "items.json"
BOOK_TEXT = "ITEMS.md"
CONFIDENCE = ("confirmed", "tentative")
MAX_PRICES = 12     # latest prices kept per item and direction
STAT_NAMES = {"wc": "WC", "ac": "AC"}


class ItemError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ====================================================================== names

ARTICLES = ("a ", "an ", "the ", "some ")


def plain(name):
    """An item's name without its article, lower case: "a battle axe" -> "battle axe"."""
    name = " ".join(str(name or "").split()).lower()
    for a in ARTICLES:
        if name.startswith(a):
            return name[len(a):]
    return name


def _engine():
    from . import itm, player, potion, scroll
    return itm, player, potion, scroll


def _not_items():
    """Ids that are scenery, not items: walls, doors, stairs, buildings, traps, gold."""
    itm = _engine()[0]
    names = ("OUNKNOWN ONOTHING OWALL OOPENDOOR OCLOSEDDOOR OSTAIRSUP OSTAIRSDOWN "
             "OENTRANCE OVOLDOWN OVOLUP OHOME ODNDSTORE OBANK OBANK2 OSCHOOL OTRADEPOST "
             "OLRS OPAD OELEVATORUP OELEVATORDOWN OALTAR OFOUNTAIN ODEADFOUNTAIN OTHRONE "
             "OTHRONE2 ODEADTHRONE OSTATUE OPIT OIVTELETRAP OTELEPORTER OTRAPARROW "
             "OIVTRAPARROW OTRAPDOOR OIVTRAPDOOR ODARTRAP OIVDARTRAP OGOLDPILE ODGOLD "
             "OKGOLD OMAXGOLD OMIRROR OANNIHILATION OHOMEENTRANCE OEXIT").split()
    ids = {getattr(itm, n) for n in names if hasattr(itm, n)}
    ids |= {i for i in range(itm.OCOUNT) if itm.objnamelist[i] in (" ", "^")}   # traps
    return frozenset(ids)


def _enchantable():
    """Ids whose argument is an enchantment (+n): weapons, armour, rings."""
    itm = _engine()[0]
    names = ("ODAGGER OBELT OSHIELD OPSTAFF OSPEAR OFLAIL OBATTLEAXE OLANCE OLONGSWORD "
             "OVORPAL O2SWORD OSWORDofSLASHING OSLAYER OSWORD OHAMMER OLEATHER "
             "OSTUDLEATHER ORING OCHAIN OSPLINT OPLATE OPLATEARMOR OSSPLATE OELVENCHAIN "
             "OPROTRING ODAMRING OREGENRING ORINGOFEXTRA OENERGYRING ODEXRING OSTRRING "
             "OCLEVERRING").split()
    return frozenset(getattr(itm, n) for n in names if hasattr(itm, n))


def kind_of(obj, arg, identified=True):
    """The name of the kind of item an (object id, argument) pair is, or
    None for scenery and for potions and scrolls not yet identified.
    `identified` False names potions and scrolls only generically."""
    itm, player, potion, scroll = _engine()
    if obj in _not_items():
        return None
    if obj == itm.OPOTION:
        if identified and 0 <= arg < len(player.potionknown) and player.potionknown[arg]:
            return "potion of " + potion.potionname[arg][1:].strip()
        return None
    if obj == itm.OSCROLL:
        if identified and 0 <= arg < len(player.scrollknown) and player.scrollknown[arg]:
            return "scroll of " + scroll.scrollname[arg][1:].strip()
        return None
    name = plain(itm.objectname[obj])
    return name or None


def all_kinds():
    """Every item name the book accepts."""
    itm, player, potion, scroll = _engine()
    names = {plain(itm.objectname[i]) for i in range(itm.OCOUNT) if i not in _not_items()}
    names |= {"potion of " + n[1:].strip() for n in potion.potionname if n[1:].strip()}
    names |= {"scroll of " + n[1:].strip() for n in scroll.scrollname if n[1:].strip()}
    names |= {"magic potion", "magic scroll"}
    names.discard("")
    return sorted(names)


def canonical(name, kinds=None):
    """The book's name for an item the agent typed, or ItemError with suggestions."""
    kinds = kinds if kinds is not None else all_kinds()
    key = plain(name)
    if not key:
        raise ItemError("name the item")
    if key in kinds:
        return key
    hits = [k for k in kinds if key in k]
    starts = [k for k in hits if k.startswith(key)]
    for found in (hits, starts):    # "leather" is leather armor, not studded leather armor
        if len(found) == 1:
            return found[0]
    close = hits[:8] or difflib.get_close_matches(key, kinds, n=5, cutoff=0.5)
    raise ItemError("no item called %r%s" % (
        name, (": did you mean " + ", ".join(close) + "?") if close else ""))


# ====================================================================== storage

def new_book():
    return {"version": 1, "next_note": 1, "items": {}}


def _path(root, name=BOOK_FILE):
    return os.path.join(root, name)


def load(root):
    try:
        with open(_path(root), encoding="utf-8") as f:
            book = json.load(f)
    except FileNotFoundError:
        return new_book()
    book.setdefault("next_note", 1)
    book.setdefault("items", {})
    return book


def save(root, book):
    os.makedirs(root, exist_ok=True)
    tmp = _path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=1, sort_keys=True)
    os.replace(tmp, _path(root))
    with open(_path(root, BOOK_TEXT), "w", encoding="utf-8") as f:
        f.write(render(book))


def entry(book, name):
    e = book["items"].setdefault(name, {})
    e.setdefault("measured", {})     # stat -> {base value: times measured}
    e.setdefault("prices", {})       # "bought"/"sold" -> [{price, plus, run}]
    e.setdefault("found_on", [])     # level names it was seen lying on
    e.setdefault("notes", [])
    return e


# ====================================================================== measuring

def snapshot():
    """What the item book needs to see of the game right now."""
    itm, player, potion, scroll = _engine()
    from . import dungeon, skills

    c = player.c
    ench = _enchantable()

    def item(slot):
        if slot is None or slot < 0 or player.iven[slot] == itm.ONOTHING:
            return None
        obj, arg = player.iven[slot], player.ivenarg[slot]
        name = kind_of(obj, arg)
        return [name, arg if obj in ench else None] if name else ["?", None]

    inv = [item(i) for i in range(player.IVENSIZE) if player.iven[i] != itm.ONOTHING]
    floor = set()
    if dungeon.level != 0:
        for x in range(dungeon.MAXX):
            for y in range(dungeon.MAXY):
                k = skills.seen(x, y)
                if k not in (itm.OUNKNOWN, itm.ONOTHING, itm.OWALL):
                    name = kind_of(k, 0, identified=False) or (
                        "magic potion" if k == itm.OPOTION else
                        "magic scroll" if k == itm.OSCROLL else None)
                    if name:
                        floor.add(name)
    lev = dungeon.level
    return {
        "level": lev,
        "level_name": runs.level_name(lev),
        "money": c[player.GOLD] + c[player.BANKACCOUNT],
        "wc": c[player.WCLASS], "ac": c[player.AC],
        "inv": inv,
        "wield": item(c[player.WIELD]), "wear": item(c[player.WEAR]),
        "shield": item(c[player.SHIELD]),
        "floor": sorted(floor),
    }


def _bag(items):
    out = {}
    for it in items:
        if it is not None:
            key = tuple(it)
            out[key] = out.get(key, 0) + 1
    return out


def _minus(a, b):
    return [k for k, n in a.items() for _ in range(n - b.get(k, 0))]


def diff(before, after, prices=True):
    """What one action showed about items, as a list of observations.

    * ("stat"): an item went into or out of the hand / onto or off the body
      with the pack otherwise unchanged, so the WC or AC change is its doing.
      When it replaced another item, the observation says which; `record`
      works out the value if the book already knows the other one.
    * ("price"): in town, exactly one item came or went and the money
      (gold plus bank) moved the other way.
    * ("found"): an item seen lying on a dungeon level.
    """
    obs = []
    if before is None or after is None:
        return obs
    same_pack = _bag(before["inv"]) == _bag(after["inv"])
    if same_pack and before["level"] == after["level"]:
        changed = [s for s in ("wield", "wear", "shield") if before[s] != after[s]]
        armour = [s for s in changed if s != "wield"]
        for slot in changed:
            if slot != "wield" and len(armour) > 1:
                continue        # two pieces of armour at once: can't tell them apart
            stat = "wc" if slot == "wield" else "ac"
            delta = after[stat] - before[stat]
            new, old = after[slot], before[slot]
            for it, other, sign in ((new, old, 1), (old, new, -1)):
                if it is None or it[0] == "?":
                    continue
                o = {"type": "stat", "item": it[0], "plus": it[1] or 0, "stat": stat,
                     "gives": sign * delta, "slot": slot}
                if other is not None:
                    if other[0] == "?":
                        continue
                    o["other"] = {"item": other[0], "plus": other[1] or 0}
                obs.append(o)
                break   # one observation per change: the incoming item, else the outgoing
    if prices and before["level"] == 0 and after["level"] == 0:
        b, a = _bag(before["inv"]), _bag(after["inv"])
        added, removed = _minus(a, b), _minus(b, a)
        money = after["money"] - before["money"]
        if len(added) == 1 and not removed and money < 0 and added[0][0] != "?":
            obs.append({"type": "price", "item": added[0][0], "plus": added[0][1],
                        "way": "bought", "price": -money})
        elif len(removed) == 1 and not added and money > 0 and removed[0][0] != "?":
            obs.append({"type": "price", "item": removed[0][0], "plus": removed[0][1],
                        "way": "sold", "price": money})
    if after["level"] != 0:
        for name in set(after["floor"]) - (set(before["floor"])
                                           if before["level"] == after["level"] else set()):
            obs.append({"type": "found", "item": name, "where": after["level_name"]})
    return obs


def known_base(e, stat):
    """The base value most often measured for a stat, or None."""
    seen = (e or {}).get("measured", {}).get(stat) or {}
    if not seen:
        return None
    return int(max(seen.items(), key=lambda kv: (kv[1], -abs(int(kv[0]))))[0])


def record(book, observations, run_id=None):
    """Merge observations into the book.  Returns the names it changed."""
    changed = set()
    for o in observations:
        name = o["item"]
        if o["type"] == "stat":
            gives = o["gives"]
            if "other" in o:
                other = book["items"].get(o["other"]["item"])
                base = known_base(other, o["stat"])
                if base is None:
                    continue
                gives += base + o["other"]["plus"]
            e = entry(book, name)
            key = str(gives - o["plus"])
            m = e["measured"].setdefault(o["stat"], {})
            m[key] = m.get(key, 0) + 1
        elif o["type"] == "price":
            e = entry(book, name)
            lst = e["prices"].setdefault(o["way"], [])
            lst.append({"price": o["price"], "plus": o.get("plus"), "run": run_id})
            del lst[:-MAX_PRICES]
        elif o["type"] == "found":
            e = entry(book, name)
            if o["where"] in e["found_on"]:
                continue
            e["found_on"].append(o["where"])
        else:
            continue
        changed.add(name)
    return changed


# ====================================================================== notes

def add_note(root, item, text, evidence=(), confidence="tentative"):
    text = " ".join(str(text or "").split())
    if not text:
        raise ItemError("the note is empty")
    if confidence not in CONFIDENCE:
        raise ItemError("confidence must be confirmed or tentative")
    evidence = [str(e) for e in evidence or ()]
    known = {m["run_id"] for m in runs.list_runs(root)}
    unknown = [e for e in evidence if e not in known]
    if unknown:
        raise ItemError("no such run: " + ", ".join(unknown))
    if confidence == "confirmed" and len(set(evidence)) < 2:
        raise ItemError("a confirmed note must cite at least two runs that showed it")
    name = canonical(item)
    book = load(root)
    e = entry(book, name)
    for note in e["notes"]:
        if note["status"] != "retracted" and note["text"].lower() == text.lower():
            note["evidence"] = sorted(set(note["evidence"]) | set(evidence))
            if confidence == "confirmed":
                note["status"] = "confirmed"
            save(root, book)
            return name, note
    note = {"id": "I%d" % book["next_note"], "text": text, "evidence": evidence,
            "status": confidence, "reason": None, "added": _now()}
    book["next_note"] += 1
    e["notes"].append(note)
    save(root, book)
    return name, note


def retract_note(root, note_id, reason):
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise ItemError("say why the note is wrong")
    book = load(root)
    for name, e in book["items"].items():
        for note in e.get("notes", ()):
            if note["id"] == note_id:
                note["status"] = "retracted"
                note["reason"] = reason
                save(root, book)
                return name, note
    raise ItemError("no item note called %r" % (note_id,))


# ====================================================================== reading

def _stat_text(e):
    parts = []
    for stat, seen in sorted(e.get("measured", {}).items()):
        if not seen:
            continue
        values = sorted(seen.items(), key=lambda kv: -kv[1])
        best = "%s %s" % (STAT_NAMES.get(stat, stat), values[0][0])
        times = sum(seen.values())
        text = "%s base, +1 per enchantment (measured %d time%s" % (
            best, times, "" if times == 1 else "s")
        if len(values) > 1:
            text += "; also seen: " + ", ".join("%s x%d" % kv for kv in values[1:])
        parts.append(text + ")")
    return parts


def _price_text(e):
    parts = []
    for way in ("bought", "sold"):
        lst = e.get("prices", {}).get(way) or []
        plain_ = [p["price"] for p in lst if not p.get("plus")]
        any_ = [p["price"] for p in lst]
        values = plain_ or any_
        if not values:
            continue
        lo, hi = min(values), max(values)
        span = "{:,}".format(lo) if lo == hi else "{:,}-{:,}".format(lo, hi)
        parts.append("%s for %s%s" % (way, span, "" if plain_ else " (enchanted)"))
    return parts


def _levels(e):
    def order(name):
        return (name.startswith("V"), int("".join(ch for ch in name if ch.isdigit()) or 0))
    return sorted(e.get("found_on", []), key=order)


def summary(e, notes=True):
    """One line of what the book knows about an item."""
    parts = _stat_text(e) + _price_text(e)
    if e.get("found_on"):
        parts.append("found on " + ", ".join(_levels(e)))
    if notes:
        parts += ["%s: %s" % (n["id"], n["text"]) for n in e.get("notes", ())
                  if n["status"] != "retracted"]
    return "; ".join(parts)


def facts(book, names):
    """{name: summary} for the named items the book knows something about."""
    out = {}
    for name in names:
        e = book["items"].get(name)
        if e:
            text = summary(e)
            if text:
                out[name] = text
    return out


def lookup(book, query=None):
    """The book as text, or just the items whose name contains `query`."""
    q = plain(query) if query else ""
    names = sorted(n for n in book["items"] if q in n)
    if not names:
        return ("The item book has nothing on %r yet." % query) if q else \
            "The item book is empty: nothing has been measured or noted yet."
    lines = []
    for name in names:
        lines += _entry_lines(name, book["items"][name], retracted=True)
    return "\n".join(lines).strip()


def _entry_lines(name, e, retracted=False):
    lines = ["### " + name, ""]
    facts_ = _stat_text(e) + _price_text(e)
    if e.get("found_on"):
        facts_.append("found on " + ", ".join(_levels(e)))
    lines += ["- " + f for f in facts_]
    for n in e.get("notes", ()):
        if n["status"] == "retracted":
            if retracted:
                lines.append("- %s: ~~%s~~ (retracted: %s)" % (n["id"], n["text"], n["reason"]))
            continue
        cite = " (runs: %s)" % ", ".join(n["evidence"]) if n["evidence"] else ""
        mark = "" if n["status"] == "confirmed" else " _(tentative)_"
        lines.append("- %s: %s%s%s" % (n["id"], n["text"], mark, cite))
    return lines + [""]


def render(book):
    """ITEMS.md."""
    lines = ["# Item book", "",
             "What the games have found out about items: WC/AC measured when an item "
             "was wielded or worn, prices paid and fetched in town, the levels items "
             "were found on, and the agents' own notes.", ""]
    names = sorted(book["items"])
    if not names:
        return "\n".join(lines + ["_Empty._", ""])
    for name in names:
        lines += _entry_lines(name, book["items"][name], retracted=True)
    return "\n".join(lines)


def briefing_lines(book):
    """The item book, compactly, for the briefing."""
    rows = []
    for name in sorted(book["items"]):
        text = summary(book["items"][name])
        if text:
            rows.append("- **%s**: %s" % (name, text))
    lines = ["## Item book", ""]
    if not rows:
        return lines + ["_Empty. It fills in as you play: wield or wear an item and its WC/AC "
                        "is measured, buy or sell one in town and its price is kept. Use "
                        "`note_item` for what an item does and when it is worth having._", ""]
    return lines + ["Measured in earlier games, plus notes from agents. `get_items` "
                    "shows any entry in full.", ""] + rows + [""]
