# Ularn master strategy

This is how to win pyularn almost every game. It is distilled from about 50 recorded games (`runs/`) and the campaign playbook (`runs/CAMPAIGN.md`, lessons L1-L183). The difficulty ladder this produced:

| Difficulty | Games | Result | Winning run |
|---|---|---|---|
| 0 | 35 | won | 20261110-221422-s1025457465 |
| 1 | 1 | won | 20261111-203922-s814986881 |
| 2 | 7 | won (1st and 7th) | 20261111-221208-s190626044, 20261112-103927-s1480664053 |
| 3 | 7 | won on the 5th ladder game | 20261112-134712-s1807377592 |
| 4 | 1 | stopped on DL2 at turn 6,624 | — |

Here is where the 13 ladder games at d2-d3 were lost. Each cause now has a rule below.

- Early game on DL1-3: 4 games. Explored without healing, used `fight` among lemmings, cornered by gnomes or kobolds.
- Altar mistakes: 2 games. A cheapskate gift, or an "ignore", brought a demon prince.
- The climb home with the cure: 3 games. Chained Z into rock, an unscouted route, an invisible prince met under Aggravate.
- Volcano below V1 without the kit: 2 games. A trap door on V5, two dragons on V2.

The rules that matter most are marked **MUST**.

---

## 1. The plan in one paragraph

Play a Rogue. Survive DL1 on missiles and lemmings, and sell the first finds for healing and armour. Find an altar on DL1-3 and run the **altar money engine**: give 50-gold prayers while wielding things, which enchants them to +9 or more, then sell them at the trading post (×1.4 per plus). A dungeon chest, then the store chest and amulet, then a sunsword at +10 pays for the **lance of death** and the whole volcano kit. Under **stealth**, lance the sleeping lairs on V1 (CL6 → CL15+) and sell the V1 chest (~300k). Go down to V5, read the map to find the cure, lure **Lucifer** off it with **hold monsters**, and take it. Then **climb home on a route you scouted on the way down**, holding monsters still and stepping only on squares you have checked.

---

## 2. Setup

- **Class: Rogue.** It starts with leather armour, a dagger and DEX 14. Never play Rambo (1 HP) or a class with no armour (Ogre, Dwarf, Wizard). Klingon is a workable second choice.
- **Difficulty.** The scoreboard (`~/.pyularn/Uscore` in WSL) forces each new game to the last win + 1. To replay a lower difficulty, back the file up and clear its `winboard`.
- **Taxes.** A previous win may leave a tax bill (anything from 0 to ~20k). Until it is paid, the bank and the DND store are closed and only the trading post buys. Check with `P` in town and pay it out of the first sale, before anything else.
- **Effects of difficulty k (from the code):**
  - monster HP ×(6+k)/6, monster damage ×(6+k)/5, monster AC −k;
  - your to-hit −k, and your melee damage per hit is rnd(WC/2 + STR − 12 − k) + 1;
  - at k ≥ 3, unique deep items appear only 1 time in 4, and statues stop turning into books;
  - smart movement starts at monster intelligence > 10 − k.

  In practice: from d3 on, early melee does about 2 a hit, and the altar engine plus the lance are the only real power.

---

## 3. Early game, DL1-DL3 (where most deaths happen)

**MUST: hard rules until you have healing and AC 6+**
1. Once you hold a chest, a gem or 150+ gold, stop and go to town. Sell, then buy 2+ potions of healing, then armour (chain or ring mail plus a shield).
   - Exception: if DL1/DL2 may still hold an altar, keep the first chest. At +9 it sells for ~29k, against 1,745 plain.
2. Below CL5, or with no known healing, fight only lemmings. Walk away from anything else.
3. Back off at the first failed spell, or the first 3+ damage hit, while you are still above 70% HP. Retreat over short ground you already know.
   - Never retreat with `take_stairs` or `travel_to` set to `ignore_monsters`: they take long loops past new monsters.
4. Rest to full before every `explore` call, and call `explore` with `ignore_monsters=false`.
5. Hit the monster that is actually hurting you, with its direction key. Never call `fight` when lemmings and a real attacker are both adjacent: it swings at the lemmings.
6. If you are cornered and have a straight line to the attacker, read unknown scrolls before drinking unknown potions. Pulverization and teleport are common.

**Other early-game knowledge**
- **Magic missile is the early weapon.** At INT 12 it fails about 1 cast in 3, so never count on it as a rescue.
- **Lemmings** never hurt you, and farming them with `fight` reach 2 gets you to CL6-7.
  - Every melee hit breeds another 40% of the time.
  - Farm in an open room, never in a corridor (lemmings plug it permanently) and never near the stairs (they follow you into town, and shops won't open while a monster is adjacent).
  - One magic missile kills a whole line of them without breeding.
- **Giant ants and centipedes** drain STR permanently. Kill them at range. A potion of strength resets STR to 12.
- **Rust monsters** (DL3+ at d3) and **gelatinous cubes** dull your weapon and armour. Use missiles, or walk away.
- **Nymphs** steal carried items, but not worn or wielded ones; AC 15+ makes them miss. **Leprechauns** steal gold: bank it before DL3+.
- **White dragons** can appear by DL3-6: leave the level. **Wraiths and vampires** drain levels: leave the level, or read undead protection.
- **Arrow and dart traps** hit you every turn you stand on them. After a "hurt" result, step off before resting.
- **Unknown items.**
  - Never read unknown scrolls in the dungeon. Carry them to town and buy one scroll of identify (3,400), which names everything you carry.
  - Before reading any unknown scroll, take off or unwield +9 gear: an enchant scroll crumbles a +9 item 90% of the time.
  - Unknown potions are a last resort.

---

## 4. The altar money engine (has worked in every game that ran it)

**Mechanics (dungeon_obj.py):**
- Pray with `p`, then `m`, then the amount.
- The gods are insulted if the gift is less than (gold left after paying) ÷ 10. Insult means a 50% chance of a demon prince plus 1,500 turns of Aggravate, which is certain death early.
- Each paid prayer gives:
  - 1 in 8: the wielded item +1 or +2;
  - 1 in 8: worn armour or shield +2;
  - often: +3 AC for 800 turns.
- Armour stops at +9 and is never destroyed. A wielded item past +9 still gains about 2.4% per prayer.
- Never pray free (`j`) at d3+: it brings centipedes and rust monsters. Never answer "ignore", and never press Esc (that also counts as ignore).

**MUST: the altar invariant (two games died from breaking it)**
1. Keep spare gold in piles 4+ squares from the altar.
2. A refill is always its own `send_keys` call:
   1. walk to the pile;
   2. drop everything but 450 (`d.<pile−450><Enter>`);
   3. step off the pile at once (dropped gold is picked up again the moment you spend a turn on its square);
   4. walk back without crossing the altar.
3. Then call `get_state` and check that gold is **≤ 509** and that your position is the altar square.
4. Only then send a prayer batch of at most 9 prayers. Each prayer is `pm50<Enter>` followed by a step off and back on (e.g. `hl`), because the prompt only comes back after you step off and on.
5. Never combine a refill and prayers in one call.

**What to wield while praying (sale price is ×2 base, ×1.4 per plus):**
- Any item gains about +1 per 5-7 prayers up to +9. Past +9 it can take 40-180 prayers per plus, so don't plan beyond +10.
- Proven order:
  1. a dungeon chest to +9 (~29k), or a sword of slashing to +9 (87k), which pays the tax;
  2. the store chest (+3 when bought) and the amulet of invisibility (+5 when bought), each to +9 (~29k and ~21k);
  3. a store sunsword to +10 (295,771). That alone pays for the lance and the kit.
- Jackpots seen: Bessman's hammer +9 = 314,503; a store chest at +18 = 602,961; sunsword +12/+13 ≈ 580k.
- Wield rings at the altar as well: cleverness, dexterity, protection and energy each reach +9 in 9-18 prayers. Wear plate and shield while you do it, so armour blessings land on them at the same time. That gave AC 45 and INT 23+ by CL7 for about 6k gold. INT 18+ means spells never fizzle.
- The walking skills (version 7) route round known altars and stop on an unknown altar with its prompt pending. Answer it yourself, giving at least max(50, gold ÷ 10).

---

## 5. Shopping and the gate before the volcano

**The DND store never restocks.** Per game at d3 it holds 1 raise level, 2 stealth, 2 hold monsters, 2 teleport, 2 time warp, 1 heroism, 4 enlightenment and 2 magic mapping. Buy all the volcano consumables in your first big purchase.

**Buy:**
- lance of death (200k): every hit does 10,000 to non-demons;
- stainless or plate armour, shield, enchant armour;
- raise level;
- energy ring;
- every stealth, hold monsters and time warp scroll;
- every enlightenment and magic mapping scroll;
- 3+ teleport;
- 2+ instant healing;
- heroism;
- aggravate monsters (for the Lucifer lure);
- identify, before reading anything you found.

**MUST: the gate.** Don't take the volcano shaft until all of these are true:
- CL6+ (the raise level potion);
- AC 25+;
- the lance;
- 2 hold monsters, 2+ teleport, 2+ instant healing, 2 stealth, magic mapping;
- full HP;
- gold banked: it weighs about 1 lb per 1,000, and the shaft slips you (30-50 damage) above 45 + 3×STR.

Read stealth at the top of the shaft in town. The landing square is random and can be next to an awake dragon.

**Time warp** extends every running effect by 100 turns per mobul it goes back. But 25% of reads go forward instead, which cuts 100 turns per mobul (and ends a running hold at once). Read stealth, then warp, in town, never while hold is what protects you.

---

## 6. V1: levels, books and the second fortune

- Under stealth, sleeping monsters stay asleep unless you hit them; misses wake nothing.
- Read magic mapping, then stand next to each sleeping lair and call `fight` with reach 1 (`min_hp` ~0.8). It lances every adjacent sleeper. Three lairs take you from CL5-6 to CL15-16.
  - Never use reach 3.
  - `fight` misses diagonal sleepers between wall corners; finish those with single keys.
- **Sleepers worth knowing:**
  - Spirit nagas have AC −20, so expect about 1 hit in 4 swings; pulverization kills them.
  - Platinum dragons (150 HP) survive a pulverization.
  - Purple worms (130) and red dragons (120) are good pulverization targets, with a wall behind the ray.
- **Read every book.** You want, in order of value:
  - **permanence** (`per`): adds 99,999 turns to every running effect, once;
  - **walk through walls** (`wtw`);
  - **hold monster** (`hld`);
  - **time stop** (`stp`);
  - **teleport other / sleep / web**, which mark Lucifer.
- **Take Slayer** if you see it. With it wielded, any hit on a demon does 10,000. A sleeping demon prince under stealth dies in 18-51 swings and takes you to CL18.
- **The V1 chest** sells for ~300k. Carry it up the V1 shaft-up (not where the town shaft dropped you; find it with enlightenment), and spend it on a second kit trip.
- V1's up stairs are a dead end. The ways out are the shaft-up, a teleport (25% to town), or Z (25% to town).

---

## 7. Descending V2 → V5

- **Volcano levels** are canned maps from `pyularn/data/Umaps` about half the time. Match the cells round you (or a magic-mapped level) against the file to get the layout, the sealed pockets and, on V5, the cure square (`!`). Stairs and items are placed at random.
- **Use stairs where they exist** (V1→V2→V3). V3 and V4 drop by pit; lower DEX makes pits drop you (take the DEX ring off). A volcano pit fall does up to 3×level+3 damage, so cross at full HP.
- **Z (innate teleport, CL10+)** lands you 1 level up to 2 down. Each press has about a 1.3-2% chance of killing you in solid rock, unless wtw is running.
  - **MUST: never press Z twice in a row** to dodge something.
  - Teleport scrolls carry no rock risk.
- **MUST: scout the road home on the way down.**
  - Climbing from V5 or V4 puts you at the same x,y on the level above.
  - On each level, find the up stairs and clear the sleepers on and beside the route while stealth is up.
  - Note the coordinates.
- **Keep the mapping scrolls for later:** one enlightenment and one magic mapping for V5, plus one enlightenment for each climb level. Don't spend them all on V2-V4.
- **Doors.** A failed open can add Aggravate, which overrides stealth and wakes everything within 10 columns and 5 rows.
  - The skills (v7) route round closed volcano doors.
  - Blast doors instead: lightning, cone of cold or pulverization (40+ damage). Lightning and pulverization also crumble walls on V1/V2 (52+ damage).
  - Or open a door by hand only when no sleeper is in your 11×7 window.
- **Demons.** On V3-V5, wield Slayer while moving; the lance does only 300 to demons.
  - "D" may be a dragon or a demon prince: read the monster name in `get_state` before coming within 2 squares.
  - A demon prince did 95-193 a turn at d2.
  - "You missed the demon prince" means an invisible one is sleeping on that square: don't step in again.
- **Monster window.** Without Aggravate, only monsters within 5 columns and 3 rows of you move. Anything further away can't come to you, so plan rests and detours around that box.

---

## 8. V5: the cure

- **MUST: trap doors.** V3-V5 have invisible trap doors. On V5 a trap door is an unrevivable death "to HELL", and one can lie under a monster you just killed.
  - Minimise floor steps on V5 above everything else.
  - With wtw (1 SP, 6-15 turns; recast before each wall band), travel inside wall cells and step onto floor only at the cure square and the stairs.
  - A wand of wonder protects you completely; keep one if you find it.
  - A teleport scroll is a good V5 opener: it lands near the target with fewer steps.
- On arrival, read magic mapping (or match the 8 cells round you), then run the Umaps matcher to find the cure square.
- Under stealth, lance the cure room and your route.
- **Lucifer** (invisible, 32,767 HP, hits for 121-220 plus a level drain) sits on the potion. Make him take exactly one step, then freeze him. His step is deterministic: the first of S, E, N, W, NE, NW, SE, SW that lowers his distance to you. He walks through walls.
  - **Method A (proven at d3, no marking spell):**
    1. Drink heroism (INT 24, no fizzles).
    2. Cast wtw and stand in the wall beside him.
    3. Read hold, then cast `tel`/`sle`/`web` at him. "Resists" or "no effect" means he is marked.
    4. Go back inside the wall to distance 3.
    5. When hold ends, he steps once. Read hold #2 immediately.
    6. Probe the cure square with a spell ("There wasn't anything there!").
    7. Take the potion from a wall cell.
  - **Method B:** wait 6+ columns from him on his row until stealth ends, then step to distance 3-5. Every monster in the window moves once, so he steps off. Read hold at once, probe, and take the potion.
  - **Method C:** from 2+ squares away inside a wall, read aggravate monsters. He steps once; hold, take the potion.
  - **Never step toward him unheld,** and never wait at distance 2.
- **Right after taking the potion:**
  - If you know permanence, cast it with hold + stealth + wtw + globe all running (check effects first: Aggravate would become permanent too). Then walk home inside walls; nothing moves unless you hit it.
  - Otherwise, cast globe, keep hold running, and start the climb.

---

## 9. The climb home (three cure-carrying games died here)

**MUST:**
1. With the cure, on volcano levels: no `fight`, `explore`, `travel_to`, `pick_up` or `rest`. Use single-step keys, 1-2 per call, onto squares you have checked in `get_state` (no altars, traps, unknown "D"s). Plan routes with a BFS that treats altars and closed doors as walls.
2. Keep hold running all the way: recast the `hld` spell with a few turns to spare, with hold scrolls as backup.
   - Never read time warp while relying on hold.
   - Hitting any monster ends the hold.
3. Wield Slayer if you have it.
4. On each arrival, read enlightenment, then walk the planned route to the up stairs.

**Tactics:**
- **Hold is a heal window.** When an awake monster hits hard (platinum psionics 54), read hold, drink instant healing, then strike at full HP.
- **Two or more awake attackers adjacent:** heal or hold first, then fight from a 1-wide corridor.
- **Blocked by a sleeper** on the route while under a permanent hold: kill it, take one round (with AC 30+ dragons do 0-13), then re-read a hold scroll. Never Z around it.
- **Invisible prince** plugging the route: hold, then go round inside walls, or read a teleport.
- **Doors:** stepping onto a closed door asks "(o)pen or (i)gnore", and opening it puts you in the doorway. Count your keys so the next one isn't an attack.
- **Fast exits:**
  - an up elevator goes to a random higher level (from V4, 25% to town);
  - from V1, a teleport scroll lands in town 25% of the time;
  - the V1 shaft-up.

  Keep one teleport for V1.

---

## 10. Tools and habits

- **Send one prompt-answering item per call.** Item, stair, door, shop and altar prompts swallow queued keys, and the prompt on a stairs or shop square comes back after every action there.
- **Cast spells in two calls:** `c` plus the code, then the direction only after "In What Direction?". A fizzled cast turns a queued direction into a move or an attack.
- **Rest in batches of 10-20** (5-10 in the volcano), and read HP and monsters between batches. Never rest at low HP on a teleport landing square or next to a known dragon.
- **Use `take_stairs` with care on DL1:** going down, it can route over the dungeon entrance and return you to town. Use `travel_to` to the stairs' x,y instead.
- **`pick_up` with no target** also re-takes items you dropped.
- **Pack slots** are 15 + CL/2. Sell junk before a big buy.
- **To see a chest's plus,** wield something else, then the chest again.
- **Helper scripts** from these games (BFS routes, Umaps matcher, effect timers, wall-preferring routes) are in the session scratchpad, not in the repo: `umatch.py`, `upath.py`, `bfs.py`, `wallpath.py`, `timers.py`. Worth turning into proper tools.

---

## 11. What should change for difficulty 4 and up (untested)

- **The early game is the bottleneck.** Monster damage is ×2 at d4 while your melee does almost nothing. Lean harder on missiles, lemmings and an early town trip for healing and armour, and get the altar AC (+9 armour and shield, protection ring) before fighting anything.
- **The engine depends on an altar on DL1-3.** If none turns up, the fallback is selling found chests, gems and unique weapons, and a stealthy V1 trip for its chest.
- **HP pools stay small** (60-95) while monster damage grows. Instant healing and hold discipline matter more, and you should enter V3+ only at CL16+ with Slayer.
- **Store stock is the hard ceiling** on stealth and hold. Without permanence, wtw or hold-monster books, a climb has to fit inside 2 stealth + 2 hold + time warps. Read every book, and keep a teleport for V1.
