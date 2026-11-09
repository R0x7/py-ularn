"""The skills (explore, travel_to, take_stairs, fight, flee, buy) on real
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
