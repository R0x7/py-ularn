"""The skills (explore, travel_to, pick_up, take_stairs, fight, flee, rest, buy) on real
seeded games, driven inside one process (run: python3 -m unittest)."""

import os
import tempfile
import unittest

ESC = "\x1b"


class SkillsTest(unittest.TestCase):
    SEED = 7

    def setUp(self):
        from pyularn import mcp_server, skills
        self.old_home = os.environ.get("PYULARN_HOME")
        os.environ["PYULARN_HOME"] = tempfile.mkdtemp()
        self.skills = skills
        self.E = skills.E
        self.s = mcp_server.GameSession()
        self.s.start(seed=self.SEED)
        self.s.send("g")     # dwarf
        self.s.send("\r")    # past the welcome text
        self.assertEqual(self.kind(), "command")

    def tearDown(self):
        self.s.stop()
        if self.old_home is None:
            del os.environ["PYULARN_HOME"]
        else:
            os.environ["PYULARN_HOME"] = self.old_home

    # ------------------------------------------------------------ helpers
    def kind(self):
        return self.s.input_state()["kind"]

    def pos(self):
        return (self.E.player.playerx, self.E.player.playery)

    def level(self):
        return self.E.dungeon.levelname[self.E.dungeon.level].strip()

    def toughen(self):
        """Make the character unkillable, so a test is about the skill."""
        p = self.E.player
        p.c[p.HP] = p.c[p.HPMAX] = 9000

    def free_cells_east(self, n):
        """n cells of open floor east of the player, in town."""
        x, y = self.pos()
        cells = [(x + i, y) for i in range(1, n + 1)]
        for cx, cy in cells:
            self.assertEqual(self.skills.seen(cx, cy), self.E.itm.ONOTHING, (cx, cy))
        return cells

    def put_monster(self, cell, mon, awake=False, hp=1):
        d = self.E.dungeon
        x, y = cell
        d.mitem[x][y].mon = mon
        d.hitp[x][y] = hp
        d.stealth[x][y] = d.STEALTH_SEEN | (d.STEALTH_AWAKE if awake else 0)

    # ------------------------------------------------------------ town
    def test_town_is_known_and_walkable(self):
        sk, s = self.skills, self.s
        symbols = {o["symbol"] for o in sk.known_objects()}
        self.assertLessEqual({"E", "S", "$", "H", "M", "L", "V"}, symbols)
        state = s.state()
        self.assertEqual(state["input"], {"kind": "command"})
        self.assertEqual(state["objects"], sk.known_objects(1000))

        r = sk.explore(s)
        self.assertEqual((r["result"], r["steps"]), ("explored", 0))

        r = sk.travel_to(s, target="bank")
        self.assertEqual(r["result"], "arrived")
        self.assertGreater(r["steps"], 0)
        self.assertEqual(sk.seen(*self.pos()), self.E.itm.OBANK)
        # The bank's question is left for the agent...
        self.assertIn("bank", s.screen())
        waiting = s.state()["input"]
        self.assertEqual(waiting["kind"], "prompt")
        self.assertEqual(waiting["answers"], ["g", "i", "<esc>"])
        # ...and no skill will run over it.
        with self.assertRaises(sk.SkillError):
            sk.explore(s)
        s.send(ESC)
        self.assertEqual(self.kind(), "command")
        self.assertEqual(sk.travel_to(s, target="bank")["note"], "already there")

        # By coordinates, and by map symbol.
        hx, hy = next((o["x"], o["y"]) for o in sk.known_objects() if o["symbol"] == "H")
        self.assertEqual(sk.travel_to(s, x=hx, y=hy)["result"], "arrived")
        self.assertEqual(self.pos(), (hx, hy))
        s.send(ESC)
        self.assertEqual(sk.travel_to(s, target="L")["result"], "arrived")
        s.send(ESC)

        self.assertEqual(sk.travel_to(s, target="stairs_down")["result"], "not_found")
        for bad in ({"target": "nonsense"}, {"x": 1}, {"x": 99, "y": 1}, {}):
            with self.assertRaises(sk.SkillError):
                sk.travel_to(s, **bad)
        with self.assertRaises(sk.SkillError):
            sk.take_stairs(s, "up")          # no way up from town
        with self.assertRaises(sk.SkillError):
            sk.take_stairs(s, "sideways")

    def test_paths_avoid_known_traps_only(self):
        sk, itm, d = self.skills, self.E.itm, self.E.dungeon
        cells = self.free_cells_east(4)
        start, goal = self.pos(), cells[3]
        x, y = cells[1]

        def wall_of(obj):
            for cy in (y - 1, y, y + 1):
                d.item[x][cy] = d.know[x][cy] = obj
            cost, came = sk.reach(start, goal)
            return cost[goal], sk.path_to(came, start, goal)

        straight, cells_walked = wall_of(itm.ONOTHING)
        self.assertEqual((straight, len(cells_walked)), (4, 4))

        # A pit the player knows of is walked around...
        around, cells_walked = wall_of(itm.OPIT)
        self.assertEqual(around, straight)   # a diagonal detour costs no more
        self.assertFalse({(x, y - 1), (x, y), (x, y + 1)} & set(cells_walked))
        self.assertIsNone(sk.step_cost(x, y))
        # ...unless it is where the agent asked to go.
        _, came = sk.reach(start, (x, y))
        self.assertEqual(sk.path_to(came, start, (x, y))[-1], (x, y))

        # A trap not yet discovered looks like floor, to skills as on screen.
        hidden, cells_walked = wall_of(itm.OIVTRAPDOOR)
        self.assertEqual(hidden, straight)
        self.assertEqual(sk.seen(x, y), itm.ONOTHING)
        self.assertNotIn((x, y), {(o["x"], o["y"]) for o in sk.known_objects(1000)})

        # Things that ask a question are passed only when there is no way round.
        costly, cells_walked = wall_of(itm.OALTAR)
        self.assertNotIn((x, y), cells_walked)

    # ------------------------------------------------------------ shopping
    def test_buy(self):
        sk, s, p = self.skills, self.s, self.E.player
        r = sk.buy(s)
        self.assertEqual(r["result"], "listed")
        self.assertEqual(self.kind(), "command")          # back outside
        self.assertEqual(sk.seen(*self.pos()), self.E.itm.ODNDSTORE)
        stock = {i["name"]: i for i in r["stock"]}
        self.assertIn("leather armor", stock)
        self.assertFalse(any(i["affordable"] for i in r["stock"]))  # no gold yet

        dear = max(r["stock"], key=lambda i: i["price"])
        price = stock["leather armor"]["price"]
        p.c[p.GOLD] = price + 5
        carried = len(s.state()["inventory"])
        # Standing on the store already: the skill steps off and back in.
        r = sk.buy(s, items=["Leather Armor", "a unicorn", "potion", dear["name"], "leather armor"])
        self.assertEqual(r["result"], "done")
        self.assertEqual(r["bought"], [{"name": "leather armor", "price": price}])
        self.assertEqual(r["gold"], 5)
        self.assertEqual(p.c[p.GOLD], 5)
        why = {f["item"]: f["why"] for f in r["failed"]}
        self.assertEqual(why["a unicorn"], "the store does not sell that")
        self.assertIn("matches several items", why["potion"])
        self.assertEqual(why[dear["name"]], "costs %d gold, you have 5" % dear["price"])
        self.assertEqual(why["leather armor"], "costs %d gold, you have 5" % price)
        inventory = s.state()["inventory"]
        self.assertEqual(len(inventory), carried + 1)
        self.assertTrue(any("leather armor" in line for line in inventory), inventory)
        self.assertEqual(self.kind(), "command")

        # An item on a later page of the store's list.
        last = r["stock"][-1] if "stock" in r else None
        listing = sk.buy(s)["stock"]
        last = listing[-1]
        p.c[p.GOLD] = last["price"]
        r = sk.buy(s, items=[last["name"]], leave=False)
        self.assertEqual(r["bought"], [{"name": last["name"], "price": last["price"]}])
        self.assertEqual(s.state()["input"]["kind"], "prompt")   # still at the counter
        r = sk.buy(s, items=[])                                   # works from inside too
        self.assertEqual(r["result"], "listed")
        self.assertEqual(self.kind(), "command")

    # ------------------------------------------------------------ fighting
    def test_fight(self):
        sk, s, p, monster = self.skills, self.s, self.E.player, self.E.monster
        self.assertEqual(sk.fight(s)["result"], "no_monsters")
        self.toughen()
        cells = self.free_cells_east(3)

        self.put_monster(cells[2], monster.JACKAL)          # asleep, three cells away
        self.assertEqual(sk.fight(s, reach_distance=2)["result"], "no_monsters")
        r = sk.fight(s)                                     # walks up and kills it
        self.assertEqual(r["result"], "clear")
        self.assertGreaterEqual(r["turns"], 2)   # at least one step and one blow
        self.assertGreater(r["experience_gained"], 0)
        self.assertEqual(r["monsters"], [])
        self.assertEqual(self.E.dungeon.mitem[cells[2][0]][cells[2][1]].mon, 0)

        # Too hurt to fight: it stops before the first blow.
        x, y = self.pos()
        self.put_monster((x + 1, y), monster.JACKAL, hp=500)
        p.c[p.HP], p.c[p.HPMAX] = 3, 12
        r = sk.fight(s)
        self.assertEqual((r["result"], r["turns"]), ("low_hp", 0))
        with self.assertRaises(sk.SkillError):
            sk.fight(s, min_hp=1.5)

    def test_fight_does_not_roam(self):
        sk, s, monster = self.skills, self.s, self.E.monster
        self.toughen()
        x, y = self.pos()
        cells = self.free_cells_east(4)
        self.put_monster(cells[0], monster.JACKAL)               # next to you
        self.put_monster(cells[3], monster.JACKAL, hp=500)       # further off, asleep
        r = sk.fight(s)
        self.assertEqual(r["result"], "clear", r)
        self.assertGreater(r["experience_gained"], 0)
        self.assertEqual(self.pos(), (x, y))                     # it did not walk off after the next one

    def test_fight_stops_before_a_blow_it_cannot_take(self):
        sk, s, p, monster = self.skills, self.s, self.E.player, self.E.monster
        import pyularn.ularn as ularn
        x, y = self.pos()
        self.put_monster((x + 1, y), monster.JACKAL, awake=True, hp=5000)
        p.c[p.HP] = p.c[p.HPMAX] = 100
        orig = ularn.parse

        def parse(action):           # every turn something hits for 30
            orig(action)
            p.c[p.HP] -= 30
        ularn.parse = parse
        try:
            r = sk.fight(s, min_hp=0.05)
        finally:
            ularn.parse = orig
        # 100 -> 70 -> 40: a third blow of 30 could leave 10, a fourth would kill.
        self.assertEqual(r["result"], "low_hp", r)
        self.assertLessEqual(r["hp"], r["biggest_hit"])
        self.assertGreater(r["hp"], 0)

    def test_fight_adds_up_the_blows(self):
        sk, s, p, monster = self.skills, self.s, self.E.player, self.E.monster
        import pyularn.ularn as ularn
        x, y = self.pos()
        self.put_monster((x + 1, y), monster.JACKAL, awake=True, hp=5000)
        p.c[p.HP] = p.c[p.HPMAX] = 100
        orig = ularn.parse
        turns = []

        def parse(action):           # 10 lost each turn; on the second, a level gained
            orig(action)
            turns.append(action)
            if len(turns) == 2:
                p.c[p.HP] += 100
                p.c[p.HPMAX] += 100
            else:
                p.c[p.HP] -= 10
        ularn.parse = parse
        try:
            r = sk.fight(s, max_turns=4, min_hp=0.05)
        finally:
            ularn.parse = orig
        self.assertEqual(r["result"], "max_turns", r)
        self.assertGreater(r["hp"], 100)                 # better off than at the start...
        self.assertGreaterEqual(r["hp_lost"], 30, r)     # ...and still it took three blows

    def test_fight_stops_when_hurt_from_afar(self):
        sk, s, p, monster = self.skills, self.s, self.E.player, self.E.monster
        import pyularn.ularn as ularn
        self.toughen()
        cells = self.free_cells_east(4)
        self.put_monster(cells[3], monster.JACKAL, hp=500)
        orig = ularn.parse

        def parse(action):           # something unseen hits as you walk
            orig(action)
            p.c[p.HP] -= 5
        ularn.parse = parse
        try:
            r = sk.fight(s)
        finally:
            ularn.parse = orig
        self.assertEqual((r["result"], r["turns"]), ("hurt_at_range", 1), r)

    def test_walks_stop_safely(self):
        sk, s, itm, d, monster = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.monster
        self.toughen()
        cells = self.free_cells_east(4)

        # The goal, cells[1], can only be reached through cells[0].
        gx, gy = cells[1]
        walls = [(gx + dx, gy + dy) for dx, dy in sk.STEPS if (gx + dx, gy + dy) != cells[0]]
        for wx, wy in walls:
            d.item[wx][wy] = d.know[wx][wy] = itm.OWALL

        # An invisible monster in the way: one try, not four blows.
        self.put_monster(cells[0], monster.INVISIBLESTALKER, awake=True, hp=5000)
        self.E.player.c[self.E.player.HOLDMONST] = 1000
        r = sk.travel_to(s, x=cells[1][0], y=cells[1][1])
        self.assertEqual((r["result"], r["steps"]), ("blocked", 1), r)
        self.assertIn("cannot see", r["note"])
        d.mitem[cells[0][0]][cells[0][1]].mon = 0

        # A visible monster plugging the only way: no_path names it.
        self.put_monster(cells[0], monster.JACKAL, hp=500)
        r = sk.travel_to(s, x=cells[1][0], y=cells[1][1])
        self.assertEqual(r["result"], "no_path", r)
        self.assertEqual([(m["x"], m["y"]) for m in r["blocked_by"]], [cells[0]])
        d.mitem[cells[0][0]][cells[0][1]].mon = 0
        self.E.player.c[self.E.player.HOLDMONST] = 0

        # An arrow trap you did not know of, on the only way: the walk
        # stops after it hurts you, and not standing on it.
        d.item[cells[0][0]][cells[0][1]] = itm.OTRAPARROW
        r = sk.travel_to(s, x=cells[1][0], y=cells[1][1])
        self.assertEqual(r["result"], "hurt", r)
        self.assertEqual(r["stepped_off_trap"], {"x": cells[0][0], "y": cells[0][1]})
        self.assertNotEqual(self.pos(), cells[0])
        for wx, wy in walls:
            d.item[wx][wy] = d.know[wx][wy] = itm.ONOTHING

        # A known express elevator is walked around like a trap.
        d.item[cells[2][0]][cells[2][1]] = d.know[cells[2][0]][cells[2][1]] = itm.OELEVATORUP
        self.assertIsNone(sk.step_cost(*cells[2]))

    def test_walks_stop_only_for_monsters_that_matter(self):
        sk, s, itm, d, monster = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.monster
        self.toughen()
        self.E.player.c[self.E.player.HOLDMONST] = 100000      # nothing moves
        cells = self.free_cells_east(4)
        x, y = self.pos()

        # One seen far across the map (a detection potion, say) is no reason to stop.
        far = (x - 20, y)
        self.assertEqual(sk.seen(*far), itm.ONOTHING)
        watch = sk.Watch(sk.Runner(s))
        self.put_monster(far, monster.JACKAL, hp=500)
        self.assertIsNone(watch.reason())
        # One that is near with a way to you is.
        self.put_monster(cells[3], monster.JACKAL, hp=500)
        self.assertEqual(watch.reason(), "monster_appeared")
        self.assertIsNone(watch.reason())                       # ...once
        d.mitem[cells[3][0]][cells[3][1]].mon = 0
        d.mitem[far[0]][far[1]].mon = 0

        # One sealed behind walls, three cells off, is left out too.
        box = cells[2]
        for dx, dy in sk.STEPS:
            d.item[box[0] + dx][box[1] + dy] = d.know[box[0] + dx][box[1] + dy] = itm.OWALL
        watch = sk.Watch(sk.Runner(s))
        self.put_monster(box, monster.JACKAL, hp=500)
        self.assertIsNone(watch.reason())
        d.mitem[box[0]][box[1]].mon = 0
        for dx, dy in sk.STEPS:
            d.item[box[0] + dx][box[1] + dy] = d.know[box[0] + dx][box[1] + dy] = itm.ONOTHING

        # Walking past a monster that stays put stops once, when it first
        # comes next to you, and not again at every step beside it.
        self.put_monster((cells[1][0], y - 1), monster.JACKAL, hp=500)
        r = sk.travel_to(s, x=cells[3][0], y=y)
        self.assertIn(r["result"], ("monster_appeared", "monster_adjacent"), r)
        results = [r["result"]]
        for _ in range(6):
            if self.pos() == cells[3]:
                break
            results.append(sk.travel_to(s, x=cells[3][0], y=y)["result"])
        self.assertEqual(self.pos(), cells[3], results)
        self.assertEqual(results.count("monster_adjacent"), 1, results)
        self.assertLessEqual(len(results), 3, results)

        # ...and not at all when told to ignore monsters.
        r = sk.travel_to(s, x=x, y=y, ignore_monsters=True)
        self.assertEqual((r["result"], self.pos()), ("arrived", (x, y)), r)

    def test_forgotten_map(self):
        sk, s, itm, d = self.skills, self.s, self.E.itm, self.E.dungeon
        x, y = self.pos()

        def forget():           # what a potion of forgetfulness does
            for i in range(d.MAXX):
                for j in range(d.MAXY):
                    d.know[i][j] = itm.OUNKNOWN

        # A place read off the old map can be walked to through the unknown...
        goal = self.free_cells_east(4)[3]
        forget()
        r = sk.travel_to(s, x=goal[0], y=goal[1])
        self.assertEqual(r["result"], "no_path")
        self.assertIn("through_unknown", r["reason"])
        r = sk.travel_to(s, x=goal[0], y=goal[1], through_unknown=True)
        self.assertEqual((r["result"], self.pos()), ("arrived", goal), r)

        # ...and in town the buildings are found again by looking for them.
        def insist(call):
            """Call a skill again when a wandering monster interrupts it."""
            for tries in range(1, 12):
                self.clear_monsters()
                r = call()
                if r["result"] not in ("monster_adjacent", "monster_appeared", "hurt"):
                    return r, tries
            self.fail(r)

        self.toughen()
        forget()
        r, tries = insist(lambda: sk.travel_to(s, target="bank"))
        self.assertEqual(r["result"], "arrived", r)
        if tries == 1:
            self.assertIn("forgotten", r["note"])
        self.assertEqual(sk.seen(*self.pos()), itm.OBANK)
        s.send(ESC)
        forget()
        r, _ = insist(lambda: sk.buy(s))
        self.assertEqual(r["result"], "listed", r)
        forget()
        r, _ = insist(lambda: sk.take_stairs(s, "down"))
        self.assertEqual((r["result"], r.get("level")), ("changed_level", "1"), r)

    def test_flee(self):
        sk, s, monster = self.skills, self.s, self.E.monster
        self.assertEqual(sk.flee(s)["result"], "safe")       # nothing to flee from
        self.toughen()
        p = self.E.player
        x, y = self.pos()
        self.put_monster((x + 2, y), monster.JACKAL, hp=500)
        p.c[p.HOLDMONST] = 1000                              # it stays where it is
        r = sk.flee(s, max_steps=30)
        self.assertEqual(r["result"], "safe", r)
        self.assertGreaterEqual(r["monsters"][0]["distance"] if r["monsters"] else 99, 8)
        self.assertGreaterEqual(r["steps"], 6)
        self.assertLess(self.pos()[0], x)                    # it went the other way

        # A jackal that gives chase is as fast as you are: flee says so.
        p.c[p.HOLDMONST] = 0
        x, y = self.pos()
        self.put_monster((x + 2, y), monster.JACKAL, awake=True, hp=500)
        r = sk.flee(s, max_steps=10)
        self.assertIn(r["result"], ("max_steps", "cornered"), r)

    def test_flee_plans_a_way_out(self):
        sk, s, itm, d, monster = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.monster
        self.toughen()
        self.E.player.c[self.E.player.HOLDMONST] = 100000      # the monster stays put
        x, y = self.pos()
        # A wall at your back.  Every free cell next to you is as near the
        # monster as you are; the way out is two steps along the wall, then
        # round its end.
        wall = [(x - 1, y - 1), (x - 1, y), (x - 1, y + 1)]
        free = [(x, y - 1), (x, y - 2), (x - 1, y - 2), (x - 2, y - 2), (x, y + 1), (x, y + 2),
                (x - 1, y + 2), (x - 2, y + 2), (x + 1, y), (x + 2, y), (x + 3, y)]
        for cell in wall + free:
            self.assertEqual(sk.seen(*cell), itm.ONOTHING, cell)
        for wx, wy in wall:
            d.item[wx][wy] = d.know[wx][wy] = itm.OWALL
        self.put_monster((x + 3, y), monster.JACKAL, hp=500)

        sk.behave_as(3)                # as it was: one step ahead, so stuck at once
        try:
            r = sk.flee(s, max_steps=30)
        finally:
            sk.behave_as()
        self.assertEqual((r["result"], r["steps"]), ("cornered", 0), r)

        r = sk.flee(s, max_steps=30)
        self.assertEqual(r["result"], "safe", r)
        self.assertLess(self.pos()[0], x - 1)                  # round the wall and away
        self.assertIn("toward", r)
        self.assertGreaterEqual(r["monsters"][0]["distance"] if r["monsters"] else 99, 8)

        # Walled in with it, there is nowhere better to go: it says so.
        px, py = self.pos()
        d.mitem[x + 3][y].mon = 0
        ring = [(px + dx, py + dy) for dx, dy in sk.STEPS if (dx, dy) != (1, 0)]
        ring += [(px + 2, py - 1), (px + 2, py + 1), (px + 3, py - 1), (px + 3, py),
                 (px + 3, py + 1)]
        for wx, wy in ring:
            d.item[wx][wy] = d.know[wx][wy] = itm.OWALL
        self.put_monster((px + 2, py), monster.JACKAL, hp=500)
        r = sk.flee(s)
        self.assertEqual((r["result"], r["steps"]), ("cornered", 0), r)

    def test_flee_prefers_the_unknown_to_a_dead_end(self):
        sk, s, itm, d, monster = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.monster
        self.toughen()
        self.E.player.c[self.E.player.HOLDMONST] = 100000
        x, y = self.pos()
        # A corridor running north and south of you, the monster off to the
        # east.  South is a known dead end two cells long; north, one cell
        # on, is the edge of what you have seen.
        free = [(x, y - 1), (x, y + 1), (x, y + 2), (x + 1, y), (x + 2, y), (x + 3, y)]
        unseen = [(x - 1, y - 2), (x, y - 2), (x + 1, y - 2)]
        for cell in free + unseen:
            self.assertEqual(sk.seen(*cell), itm.ONOTHING, cell)
        walls = [(x - 1, y - 1), (x - 1, y), (x - 1, y + 1), (x - 1, y + 2), (x + 1, y - 1),
                 (x + 1, y + 1), (x + 1, y + 2), (x - 1, y + 3), (x, y + 3), (x + 1, y + 3)]
        for wx, wy in walls:
            d.item[wx][wy] = d.know[wx][wy] = itm.OWALL
        for ux, uy in unseen:
            d.know[ux][uy] = itm.OUNKNOWN
        self.put_monster((x + 3, y), monster.JACKAL, hp=500)
        # The dead end's far cell is the furthest known place from the
        # monster, but running there is running into a trap.
        r = sk.flee(s, max_steps=30)
        self.assertEqual(r["result"], "safe", r)
        self.assertLess(self.pos()[1], y - 1, r)

    # ------------------------------------------------------------ items
    def put_item(self, cell, obj, arg=0):
        d = self.E.dungeon
        x, y = cell
        d.item[x][y] = d.know[x][y] = obj
        d.iarg[x][y] = arg

    def test_pick_up(self):
        sk, s, itm, d, p = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.player
        self.assertEqual(sk.pick_up(s)["result"], "not_found")     # nothing lies about in town
        self.toughen()
        p.c[p.HOLDMONST] = 100000
        x, y = self.pos()
        cells = self.free_cells_east(4)
        carried = len(s.state()["inventory"])
        gold = p.c[p.GOLD]

        # Everything known, nearest first, in one call.
        self.put_item(cells[0], itm.OPOTION)
        self.put_item(cells[1], itm.OGOLDPILE, 50)
        self.put_item(cells[3], itm.ODAGGER, 1)
        r = sk.pick_up(s)
        self.assertEqual(r["result"], "done", r)
        self.assertEqual([(t["x"], t["y"]) for t in r["taken"]], [cells[0], cells[1], cells[3]])
        self.assertEqual(r["gold_gained"], 50)
        self.assertEqual(p.c[p.GOLD], gold + 50)
        self.assertNotIn("slot", r["taken"][1])                    # gold goes to the purse
        inventory = s.state()["inventory"]
        self.assertEqual(len(inventory), carried + 2)
        for t in (r["taken"][0], r["taken"][2]):                   # named as the pack lists it
            self.assertIn("%s)   %s" % (t["slot"], t["name"]), inventory)
        self.assertIn("dagger", r["taken"][2]["name"])
        self.assertEqual(self.kind(), "command")
        self.assertEqual([sk.seen(*c) for c in cells], [itm.ONOTHING] * 4)
        self.assertNotIn("left", r)

        # One kind only; then the thing at one cell, which you are standing on.
        self.assertEqual(sk.travel_to(s, x=x, y=y)["result"], "arrived")
        self.put_item(cells[0], itm.OSCROLL)
        self.put_item(cells[1], itm.OBOOK)
        self.put_item(cells[2], itm.OPOTION)
        r = sk.pick_up(s, target="book")
        self.assertEqual((r["result"], [(t["x"], t["y"]) for t in r["taken"]]),
                         ("done", [cells[1]]), r)
        self.assertEqual(sk.seen(*cells[0]), itm.OSCROLL)          # walked over, not taken
        self.assertEqual(self.pos(), cells[1])
        self.put_item(cells[1], itm.OBOOK)
        r = sk.pick_up(s, x=cells[1][0], y=cells[1][1])            # steps off and back on
        self.assertEqual((r["result"], len(r["taken"])), ("done", 1), r)
        self.assertEqual(sk.pick_up(s, x=cells[3][0], y=cells[3][1])["result"], "not_found")

        # What cannot be fetched is listed with the reason.
        self.put_monster(cells[2], self.E.monster.JACKAL, hp=500)  # asleep on the potion
        r = sk.pick_up(s, target="!")
        self.assertEqual(r["result"], "no_path", r)
        self.assertEqual([(o["x"], o["y"], o["why"]) for o in r["left"]],
                         [cells[2] + ("a monster is standing on it",)])
        d.mitem[cells[2][0]][cells[2][1]].mon = 0

        # Interrupted on the way, it says what is still lying there.
        self.assertEqual(sk.travel_to(s, x=x, y=y)["result"], "arrived")
        import pyularn.ularn as ularn
        orig = ularn.parse

        def parse(action):
            orig(action)
            p.c[p.HP] -= 1
        ularn.parse = parse
        try:
            r = sk.pick_up(s)
        finally:
            ularn.parse = orig
        # (The scroll was one step away: reaching it counts before the hurt.)
        self.assertEqual((r["result"], [(t["x"], t["y"]) for t in r["taken"]]),
                         ("hurt", [cells[0]]), r)
        self.assertEqual([(o["x"], o["y"]) for o in r["left"]], [cells[2]])
        self.assertIn("stopped first (hurt)", r["left"][0]["why"])

        # A full pack: it does not walk to what it could not carry, but it
        # still fetches gold, and lists the rest.
        self.assertEqual(sk.travel_to(s, x=x, y=y)["result"], "arrived")
        for i in range(p.IVENSIZE):
            if p.iven[i] == itm.ONOTHING:
                p.iven[i] = itm.OCOOKIE
        r = sk.pick_up(s)
        self.assertEqual((r["result"], r["taken"], r["steps"]), ("pack_full", [], 0), r)
        self.assertEqual([(o["x"], o["y"], o["why"]) for o in r["left"]],
                         [cells[2] + ("your pack is full",)])
        self.put_item(cells[3], itm.OGOLDPILE, 7)
        r = sk.pick_up(s)
        self.assertEqual((r["result"], r["gold_gained"]), ("pack_full", 7), r)
        self.assertEqual([(t["x"], t["y"]) for t in r["taken"]], [cells[3]])
        self.assertEqual(len(r["left"]), 1)
        self.assertEqual(sk.seen(*cells[2]), itm.OPOTION)
        self.assertEqual(self.kind(), "command")

        for bad in ({"x": 1}, {"x": 1, "y": 1, "target": "potion"}, {"x": 99, "y": 1},
                    {"target": "stairs_down"}, {"target": "nonsense"}):
            with self.assertRaises(sk.SkillError):
                sk.pick_up(s, **bad)

    def test_rest(self):
        sk, s, itm, d, p, monster = (self.skills, self.s, self.E.itm, self.E.dungeon,
                                     self.E.player, self.E.monster)
        import pyularn.ularn as ularn
        r = sk.rest(s)
        self.assertEqual((r["result"], r["turns"]), ("rested", 0), r)   # nothing to recover

        # It stops as soon as HP is full, not after a fixed batch.
        p.c[p.HPMAX] = 40
        p.c[p.HP] = 39
        r = sk.rest(s, max_turns=500)
        self.assertEqual((r["result"], r["hp"], r["hp_gained"]), ("rested", 40, 1), r)
        self.assertEqual(r["turns"], r["steps"])
        self.assertLess(r["turns"], 500)
        turn = p.gtime
        r = sk.rest(s, turns=3)                                         # plain waiting
        self.assertEqual((r["result"], r["turns"], p.gtime), ("waited", 3, turn + 3), r)

        # Until an effect ends.  A time stop holds the clock, so the waits
        # are counted in steps and no game time passes.
        p.c[p.STEALTH] = 4
        r = sk.rest(s, effect="stealth")
        self.assertEqual((r["result"], r["effect"], r["turns"]), ("effect_ended", "Stealth", 4), r)
        self.assertEqual(sk.rest(s, effect="Stealth")["note"], "that effect is not running")
        p.c[p.TIMESTOP] = 5
        turn = p.gtime
        r = sk.rest(s, effect="Time  Stop")
        self.assertEqual((r["result"], r["turns"], r["steps"], p.gtime),
                         ("effect_ended", 0, 5, turn), r)
        p.c[p.HOLDMONST] = 50
        self.assertEqual(sk.rest(s, effect="hold monst", max_turns=3)["result"], "max_turns")
        p.c[p.HOLDMONST] = 0
        for bad in ({"effect": "luck"}, {"effect": "stealth", "turns": 2}):
            with self.assertRaises(sk.SkillError):
                sk.rest(s, **bad)
        # Effects the game announces but does not list are named too.
        p.c[p.HASTEMONST] = p.c[p.AGGRAVATE] = 9
        self.assertLessEqual({"Haste Monsters", "Aggravate"}, set(s.state()["effects"]))
        p.c[p.HASTEMONST] = p.c[p.AGGRAVATE] = 0
        self.assertEqual(s.state()["effects"], [])
        p.c[p.HP] = 1
        self.assertEqual(sk.rest(s, max_turns=2)["result"], "max_turns")

        # Hurt while resting: it stops that turn.
        orig = ularn.parse

        def parse(action):
            orig(action)
            p.c[p.HP] -= 1
        p.c[p.HP] = 20
        ularn.parse = parse
        try:
            r = sk.rest(s)
        finally:
            ularn.parse = orig
        self.assertEqual((r["result"], r["turns"]), ("hurt", 1), r)

        # A monster walking up: it stops when it comes into view nearby.
        x, y = self.pos()
        cells = self.free_cells_east(4)
        state = {"turns": 0}

        def parse(action):
            orig(action)
            state["turns"] += 1
            if state["turns"] == 3:
                self.put_monster(cells[2], monster.JACKAL, hp=500)
        p.c[p.HOLDMONST] = 100000
        ularn.parse = parse
        try:
            r = sk.rest(s)
        finally:
            ularn.parse = orig
        self.assertEqual((r["result"], r["turns"]), ("monster_appeared", 3), r)
        self.assertEqual(sk.rest(s, turns=4, ignore_monsters=True)["result"], "waited")
        d.mitem[cells[2][0]][cells[2][1]].mon = 0

        # Never on a known arrow trap: each turn there is another arrow.
        self.toughen()
        d.item[x][y] = d.know[x][y] = itm.OTRAPARROW
        p.c[p.HP] = p.c[p.HPMAX] - 1
        r = sk.rest(s, max_turns=3)
        self.assertEqual(r["stepped_off_trap"], {"x": x, "y": y}, r)
        self.assertNotEqual(self.pos(), (x, y))
        self.assertNotEqual(r["result"], "hurt")
        d.item[x][y] = d.know[x][y] = itm.ONOTHING

        # Blind, the walking skills refuse; waiting it out is what rest is for.
        p.c[p.BLINDCOUNT] = 50
        with self.assertRaises(sk.SkillError):
            sk.explore(s)
        self.assertEqual(sk.rest(s, turns=2)["result"], "waited")
        p.c[p.BLINDCOUNT] = 0
        with self.assertRaises(sk.SkillError):
            sk.rest(s, until="mana")

    def test_direction_question_is_a_prompt(self):
        sk, s, p = self.skills, self.s, self.E.player
        p.spelknow[1] = 1                       # magic missile
        p.c[p.INTELLIGENCE] = 18
        for _ in range(8):                      # a cast can fizzle before it asks
            p.c[p.SPELLS] = 5
            s.send("c")
            s.send("mle")
            if self.kind() != "command":
                break
        self.assertIn("In What Direction?", s.screen())
        # The key is read the way a command is, but it answers the question:
        # the status says so, and no skill starts by answering it.
        self.assertEqual(s.state()["input"], {"kind": "prompt", "answers": list("hjklyubn")})
        self.assertIn("waiting for an answer", s.status_line())
        turn = p.gtime
        for skill in (sk.rest, sk.explore):
            with self.assertRaises(sk.SkillError):
                skill(s)
        self.assertEqual(p.gtime, turn)
        sk.behave_as(4)                         # as it was: taken for a command
        try:
            self.assertEqual(sk.Runner(s).kind(), "command")
        finally:
            sk.behave_as()
        s.send("x")                             # not a direction: still asking
        self.assertEqual(self.kind(), "prompt")
        s.send("h")
        self.assertEqual(self.kind(), "command")

    def test_what_is_in_the_way(self):
        sk, s, itm, d, monster = self.skills, self.s, self.E.itm, self.E.dungeon, self.E.monster
        self.toughen()
        self.E.player.c[self.E.player.HOLDMONST] = 100000
        cells = self.free_cells_east(4)

        # A goal behind a known pit: no_path names the pit.
        gx, gy = cells[1]
        walls = [(gx + dx, gy + dy) for dx, dy in sk.STEPS if (gx + dx, gy + dy) != cells[0]]
        for wx, wy in walls:
            d.item[wx][wy] = d.know[wx][wy] = itm.OWALL
        d.item[cells[0][0]][cells[0][1]] = d.know[cells[0][0]][cells[0][1]] = itm.OPIT
        r = sk.travel_to(s, x=gx, y=gy)
        self.assertEqual(r["result"], "no_path", r)
        self.assertEqual([(h["x"], h["y"]) for h in r["hazards"]], [cells[0]])
        self.assertIn("pit", r["hazards"][0]["name"])
        self.assertIn("hazards", r["reason"])
        r = sk.travel_to(s, x=gx, y=gy, through_unknown=True)      # the same when feeling the way
        self.assertEqual([(h["x"], h["y"]) for h in r.get("hazards", ())], [cells[0]], r)
        # Sealed off altogether, the map just does not connect.
        d.item[cells[0][0]][cells[0][1]] = d.know[cells[0][0]][cells[0][1]] = itm.OWALL
        r = sk.travel_to(s, x=gx, y=gy)
        self.assertEqual((r["result"], "hazards" in r), ("no_path", False), r)
        self.assertIn("does not connect", r["reason"])

        # On a level barely seen, monsters all round you: explore does not
        # call that explored.
        self.clear_monsters()
        self.assertEqual(sk.take_stairs(s, "down")["result"], "changed_level")
        self.clear_monsters()
        x, y = self.pos()
        ring = [(x + dx, y + dy) for dx, dy in sk.STEPS if sk.step_cost(x + dx, y + dy) is not None]
        self.assertTrue(ring)
        for cell in ring:
            self.put_monster(cell, monster.JACKAL, hp=500)
        r = sk.explore(s, ignore_monsters=True)
        self.assertEqual(r["result"], "no_path", r)
        self.assertLessEqual(r["steps"], 1)
        self.assertTrue(r["blocked_by"])
        self.assertLessEqual({(m["x"], m["y"]) for m in r["blocked_by"]}, set(ring))
        self.assertIn("more to explore", r["reason"])
        # The same cells as known pits: explored as far as a skill goes, and it says so.
        self.clear_monsters()
        for cx, cy in ring:
            d.item[cx][cy] = d.know[cx][cy] = itm.OPIT
        r = sk.explore(s)
        self.assertEqual(r["result"], "explored", r)
        self.assertTrue(r["beyond"])
        self.assertLessEqual({(h["x"], h["y"]) for h in r["beyond"]}, set(ring))

    # ------------------------------------------------------------ the dungeon
    def clear_monsters(self):
        d = self.E.dungeon
        for column in d.mitem:
            for cell in column:
                cell.mon = 0

    def errand(self, direction, want):
        """Take the stairs to level `want`, exploring as an agent would when
        a skill stops early.  Monsters are removed as they turn up: this is
        about finding the way, and fighting has a test of its own."""
        sk, s = self.skills, self.s
        log = []
        for _ in range(200):
            self.toughen()
            self.clear_monsters()
            self.assertIsNone(s.final_outcome(), log)
            if self.level() == want:
                return
            if self.kind() != "command":
                s.send(ESC)
                continue
            p = self.E.player
            if p.c[p.CONFUSE] or p.c[p.BLINDCOUNT]:
                s.send(".")
                continue
            r = sk.take_stairs(s, direction)
            if r["result"] == "not_found":
                r = sk.explore(s, until="stairs_" + direction)
                self.assertNotEqual(r["result"], "explored", s.screen())
            log.append(r["result"])
        self.fail("never reached level %s: %s\n%s" % (want, log[-30:], s.screen()))

    def assert_state_shows_the_screen(self):
        """Every cell of the map on the screen is in get_state, and the
        state shows nothing the screen does not."""
        s = self.s
        s.send("\x12")                        # ^R: redraw, so the screen is current
        state = s.state()
        screen = s.term.snapshot(ascii_walls=True)
        grid = state["map"]
        self.assertEqual((len(grid), {len(row) for row in grid}), (17, {67}))
        walls = 0
        for y in range(17):
            for x in range(67):
                shown, told = screen[y][x], grid[y][x]
                if told == "#":
                    walls += 1
                    self.assertIn(shown, "#-|+", (x, y))
                elif told in (" ", "."):      # the terminal draws both as blank
                    self.assertEqual(shown, " ", (x, y, told))
                else:
                    self.assertEqual(shown, told, (x, y))
        # The lists agree with the map, cell for cell.
        px, py = state["position"]["x"], state["position"]["y"]
        self.assertEqual(grid[py][px], "@")
        listed = {(o["x"], o["y"]): o["symbol"] for o in state["objects"]}
        listed.update({(m["x"], m["y"]): m["symbol"] for m in state["monsters"]})
        listed[(px, py)] = "@"
        on_map = {(x, y): grid[y][x] for y in range(17) for x in range(67)
                  if grid[y][x] not in " .#DO"}
        self.assertEqual(listed, on_map)
        # Status lines and messages.
        self.assertEqual(state["display"], "map")
        text = [line.strip() for line in screen[19:] if line.strip()]
        self.assertEqual(state["messages"], text)
        stats = state["stats"]
        self.assertRegex(screen[18], r"^HP: +%d \(%d\) " % (stats["hp"], stats["hp_max"]))
        self.assertIn("Gold: %d" % stats["gold"], screen[18])
        return state, walls

    def test_state_shows_the_whole_play_area(self):
        sk, s, d, itm = self.skills, self.s, self.E.dungeon, self.E.itm
        state, walls = self.assert_state_shows_the_screen()       # the town
        self.assertEqual(walls, 0)
        self.assertNotIn(" ", "".join(state["map"]))              # all of it is known

        sk.take_stairs(s, "down")
        state, walls = self.assert_state_shows_the_screen()       # a level just entered
        self.assertGreater(walls, 0)
        self.assertGreater("".join(state["map"]).count(" "), 800)  # mostly unexplored

        for _ in range(40):                                        # explore it
            self.toughen()
            self.clear_monsters()
            if self.kind() != "command":
                s.send(ESC)
            elif sk.explore(s)["result"] == "explored":
                break
        self.clear_monsters()       # explore no longer stops for one seen far off
        state, walls = self.assert_state_shows_the_screen()
        self.assertGreater(walls, 150)
        flat = "".join(state["map"])
        self.assertGreater(flat.count("."), 200)
        self.assertTrue(state["messages"])

        # Monsters: those on the screen, and only those.
        x, y = self.pos()
        spots = [(x + dx, y + dy) for dx, dy in sk.STEPS
                 if sk.seen(x + dx, y + dy) == itm.ONOTHING]
        self.assertGreaterEqual(len(spots), 2, s.screen())
        self.put_monster(spots[0], self.E.monster.JACKAL, hp=500)
        self.put_monster(spots[1], self.E.monster.JACKAL, hp=500)
        d.stealth[spots[1][0]][spots[1][1]] = 0                    # asleep, never seen
        p = self.E.player
        p.c[p.HOLDMONST] = 1000
        state, _ = self.assert_state_shows_the_screen()
        self.assertEqual([(m["x"], m["y"]) for m in state["monsters"]], [spots[0]])
        self.assertEqual(state["map"][spots[0][1]][spots[0][0]], "J")
        self.assertEqual(state["map"][spots[1][1]][spots[1][0]], ".")

        # A trap not yet found is floor; once found it is on the map.
        tx, ty = spots[1]
        d.mitem[tx][ty].mon = 0
        d.item[tx][ty] = d.know[tx][ty] = itm.OIVDARTRAP
        state, _ = self.assert_state_shows_the_screen()
        self.assertEqual(state["map"][ty][tx], ".")
        for obj, symbol in ((itm.ODARTRAP, "^"), (itm.OCLOSEDDOOR, "D"),
                            (itm.OOPENDOOR, "O"), (itm.OSTAIRSDOWN, "%")):
            d.item[tx][ty] = d.know[tx][ty] = obj
            state, _ = self.assert_state_shows_the_screen()
            self.assertEqual(state["map"][ty][tx], symbol)
        d.item[tx][ty] = d.know[tx][ty] = itm.ONOTHING

        # In a shop the screen is text, and the state says so.
        self.clear_monsters()
        self.errand("up", "H")
        sk.buy(s, leave=False)
        state = s.state()
        self.assertEqual((state["display"], state["messages"]), ("text", []))
        self.assertEqual(state["input"]["kind"], "prompt")

    def test_dungeon_round_trip(self):
        sk, s = self.skills, self.s
        r = sk.take_stairs(s, "down")
        self.assertEqual((r["result"], r["was"], r["level"]), ("changed_level", "H", "1"))
        self.assertEqual(s.state()["deepest"], {"dungeon": 1, "volcano": 0})
        # A fresh level is mostly unknown, and the stairs are not in view.
        self.assertEqual(sk.take_stairs(s, "down")["result"], "not_found")

        self.errand("down", "2")
        self.errand("down", "3")
        self.errand("up", "2")
        self.errand("up", "1")
        self.errand("up", "H")                 # out through the gap in the wall
        entrance = next(o for o in sk.known_objects() if o["symbol"] == "E")
        self.assertLessEqual(entrance["distance"], 2)   # put down beside it


if __name__ == "__main__":
    unittest.main()
