# py-ularn

A Python port of **Ularn 1.6.3a**, the classic roguelike by Julian Olds (based
on Larn by Noah Morgan), plus an **MCP server** so AI agents can play it.

Ported from the C source at
[R0x7/ularn-1.6.3a](https://github.com/R0x7/ularn-1.6.3a). The port follows
the original UNIX terminal build function by function. Formulas, messages,
monsters, items, shops and level layouts match the C code, including its
known quirks. See [PORTING.md](PORTING.md) for the conventions used.

Pure Python 3.10+, standard library only (plus `windows-curses` on Windows
for the terminal front end).

## Play

```bash
pip install .
pyularn            # or: python -m pyularn
```

It needs a terminal of at least 80x24. The original command-line options
are kept (`pyularn -h`). Scores and save games are stored in `~/.pyularn`;
set `PYULARN_HOME` to use another folder.

Press `?` in the game for help. Move with `hjklyubn` (or the arrow keys).
Capital letters run. Your daughter is dying of dianthroritis: find the potion
that cures her and bring it home before time runs out.

### With graphics

```bash
pyularn --web            # opens http://localhost:8765/ in your browser
```

This plays the same game in a web page, drawn with the original 32x32 sprite
tiles from the X11/Windows versions of Ularn. A terminal cannot show
sprites. The keyboard works as in the terminal. Arrow keys and
Home/PgUp/End/PgDn move, and Ctrl+letter works too. **Tiles / Text**
switches between the sprite map and the classic character screen. **Zoom**
sets the tile size: when the map does not fit, it scrolls with the player,
as in the X11 version.

Options: `--web PORT` (`0` picks a free port), `--web-host 0.0.0.0` to play
from another machine, and `--no-browser`. The usual Ularn options (`-d`,
`-n`, ...) still work. Saves and scores are shared with the terminal
version. The program ends when the game does, or press Ctrl+C in the
terminal.

## MCP server

`pyularn-mcp` (or `python -m pyularn.mcp_server`) runs a Model Context
Protocol server over stdio. It has no dependencies: it implements the
JSON-RPC protocol directly.

Claude Code:

```bash
claude mcp add pyularn -- python -m pyularn.mcp_server
```

Claude Desktop / other clients (`mcpServers` config):

```json
{
  "mcpServers": {
    "pyularn": { "command": "python", "args": ["-m", "pyularn.mcp_server"] }
  }
}
```

### Tools

| Tool | What it does |
|---|---|
| `new_game` | Start a game. Options: `character_class` (a-h or ogre/wizard/klingon/elf/rogue/adventurer/dwarf/rambo), `seed` for a reproducible game, `difficulty` (0 to 100), `player_name`, `skip_intro`. Returns the screen and the player state. |
| `send_keys` | Send keystrokes, e.g. `"i"`, `"qa"`, `"cmle<enter>"`, `"<esc>"`. Special keys: `<esc> <enter> <space> <bs> <tab> <up> <down> <left> <right> <c-r>`. Returns the new screen. |
| `move` | Step or run in a compass direction (`n s e w ne nw se sw`), with an optional `count`. |
| `get_screen` | The current 80x24 screen. |
| `get_state` | JSON: HP, stats, gold, AC/WC, dungeon level, position, turns, inventory, active effects, known spells, plus `seed`, `difficulty`, `time` left, the `deepest` levels visited, the `map`, the `monsters` and `objects` on it, the latest `messages` and, once the game is over, its `outcome`. |
| `key_reference` | Command list, map legend and goal. |
| `end_game` | Stop the current game. |
| `explore` | Skill: explore the level until something needs a decision. Option `until` stops when a target is found. |
| `travel_to` | Skill: walk to a `target` (name or map symbol) or to `x`, `y`. |
| `take_stairs` | Skill: go to the known stairs and take them, `direction` `down` or `up`. |
| `fight` | Skill: attack the nearest visible monster until none is in reach, or HP falls to `min_hp`. |
| `flee` | Skill: step away from visible monsters until none is within `safe_distance`. |
| `buy` | Skill: buy `items` at the DND store in town, or return its price list. |
| `summarize_run` | Write a finished game's post-mortem: `synopsis`, `went_wrong`, `worked`, `next_try`. Needs `--record`. |
| `list_runs` | Recorded games, newest first, with how each ended and its post-mortem. Filters: `difficulty`, `strategy`, `limit`. Needs `--record`. |
| `get_run` | One recorded game's full summary. Needs `--record`. |

Every game has a seed. If `new_game` is not given one it picks one at
random and reports it in the state, so any game can be replayed.

`monsters` lists only what the map already shows (name, symbol, position,
distance), nearest first. It follows the game's own display rules, so a
mimic appears as what it is imitating and unseen monsters are left out.

`map` is the whole play area as the player knows it: 17 strings of 67
characters, where `map[y][x]` is the cell at position `x`, `y`. It is the
map on the screen cell for cell, except that every wall is `#` and explored
floor is `.` (the terminal draws floor and unexplored cells both as
blanks; the graphical versions tell them apart, as this does). A test
checks the state against the screen so the two cannot drift apart.

`objects` lists what is known on the current level (stairs, buildings,
items, known traps) with positions. `messages` holds the message lines
under the map, and `display` is `map` or `text` (shops and other full-screen
text, which `get_screen` shows). `input` says what the game is waiting
for: `{"kind": "command"}` on the map, or
`{"kind": "prompt", "answers": ["g", "i", "<esc>"]}` when it has asked a
question and will only take those keys.

### Skills

A full game is thousands of key presses. The skill tools each do a whole
errand in one call and stop as soon as something needs a decision. Every
skill returns a `result` saying why it stopped, with the steps taken,
position, HP and the monsters in view.

| Skill | Stops with |
|---|---|
| `explore` | `explored` (nothing left to reach), `found` (the `until` target is known) |
| `travel_to` | `arrived` (a question asked by the destination is left for the agent), `not_found`, `no_path` |
| `take_stairs` | `changed_level`, `not_found` (explore first), `refused` |
| `fight` | `clear`, `no_monsters`, `low_hp`, `unreachable`, `max_turns` |
| `flee` | `safe`, `cornered`, `max_steps` |
| `buy` | `done` (with `bought` and `failed`, each with a reason), `listed`, `refused` (taxes owed) |

Any walking skill also stops with `monster_appeared`, `monster_adjacent`,
`hurt`, `level_changed`, `teleported`, `blocked`, `prompt`, `max_steps` or
`game_over`.

What the skills will and will not do:

- They only press keys, so they can do nothing a player could not.
- They use only what the player knows: the map as drawn, and the monsters
  on it. Undiscovered traps and unseen monsters are invisible to them.
- They never route through a known trap, pit or teleporter, they open
  doors, they pick up gold, and they answer "ignore" to anything else they
  walk over.
- They will not start while the game is asking a question, or while the
  character is blind or confused.
- `fight` is melee only, and `flee` looks one step ahead, so it can run
  into a dead end. Spells, potions and scrolls are left to the agent
  (`send_keys`).

The code is in `pyularn/skills.py` and can be used without the MCP server:
each skill is a function that takes a game session.

### How a game ended

When the game is over, the tool results and `get_state` carry an `outcome`:

```json
{"result": "died", "won": false, "reason": "killed by a jackal",
 "killer": "jackal", "score": 12, "seed": 42, "character_class": "Rogue",
 "difficulty": 0, "dungeon_level": "1", "deepest": {"dungeon": 1, "volcano": 0},
 "turns": 312, "mobuls_left": 396, "character_level": 1, "experience": 4}
```

`result` is `won`, `died`, `quit`, `saved`, `stopped` (ended with
`end_game` or a new `new_game`) or `crashed`. The outcome appears as soon
as the character dies, before the score screens are paged through.

Difficulty and the scoreboard: after a win, Ularn starts that player's next
game one level harder and will not go lower. The scoreboard lives in
`PYULARN_HOME`, so give each series of games its own folder to keep them
apart. `new_game` says so when it could not use the difficulty asked for.

### Recording games

Start the server with `--record DIR` (or set `PYULARN_RECORD`) and each
game is written to its own folder, `DIR/<date>-<time>-s<seed>/`:

| File | Contents |
|---|---|
| `meta.json` | Seed, class, difficulty, start and end time, number of actions and the outcome. |
| `events.jsonl` | One JSON object per line: `start` (full state), an `action` for each `move` / `send_keys` call (arguments, the agent's `thought`, and HP, position, level and turn afterwards), a full `state` on each level change and every 200 actions, and `end` (outcome, final state and the last 30 screens). |
| `summary.md` | Written when the game ends: how it ended, the hypotheses it tested, the agent's post-mortem, and what happened (route through the levels, lowest HP, final inventory, last thoughts, final screen). |

`DIR/INDEX.md` lists every run, newest first, with a count of runs and wins
per difficulty.

### Learning from earlier games

With `--record` on, the server asks agents to work in a loop:

1. `list_runs` (and `get_run` for the interesting ones) to read how earlier
   games went and what they said to try next.
2. `new_game` with a `strategy` name and the `hypotheses` this game tests.
   Both are stored with the recording.
3. Play.
4. `summarize_run` with a `synopsis`, what `went_wrong`, what `worked` and
   what the next game will try (`next_try`).

The same information is available outside an agent:

```bash
pyularn-runs                 # list the runs in ./runs (or --dir DIR)
pyularn-runs show RUN_ID     # print one run's summary
pyularn-runs reindex         # rebuild every summary.md and INDEX.md
```

`meta.json` and `events.jsonl` are the source of truth. `summary.md` and
`INDEX.md` are rebuilt from them.

### Watching an agent play live

Start the server with `--watch` (or set `PYULARN_WATCH=8765`) and open
<http://localhost:8765/> in a browser:

```bash
claude mcp add pyularn -- python -m pyularn.mcp_server --watch 8765
```

The page redraws the game, with the same sprite tiles as `pyularn --web`
(or as text), each time the agent's input is handled. It also shows HP, spells, stats, inventory, active effects, known
spells and the agent's recent keys. Under the game, an **Agent thoughts**
roll shows what the agent says it is doing: `new_game`, `move` and
`send_keys` take an optional `thought` string, which the page shows just
before the moves it explains (the server's instructions ask agents to fill
it in). The MCP server never sees the model's private reasoning, so the
roll shows only what the agent chooses to write there. Playback can be **Live**, **Smooth**
(10 frames/s) or **Slow** (4 frames/s), and you can pause it. The page is
view-only, and `new_game` includes the address in its result. Use
`--watch 0` to pick a free port and `--watch-host 0.0.0.0` to allow
viewers from other machines. If the server runs in WSL2, a Windows browser
can open `localhost` too.

To see it without an AI client, `python examples/random_agent.py` starts the
server with the page on and wanders the character around at random.

### How it works

The unmodified game engine runs in a background thread on an in-memory
terminal (`pyularn.term_virtual.VirtualTerminal`). Each tool call feeds keys,
then waits until the game is blocked on input again before it returns.
Because the engine keeps its state in module globals, as the C original does,
one server process runs one game at a time. `new_game` resets the engine
(`pyularn.engine.reset()`).

Saving with `S` writes the save file. The next game started with the same
user name resumes it, as in the original.

## Embedding

```python
import threading
from pyularn import engine, header, term_virtual, ularn

engine.reset()
header.set_seed(1234)            # optional: reproducible game
term = term_virtual.VirtualTerminal()
threading.Thread(target=ularn.run_game, args=(term,), daemon=True).start()
term.wait_for_input(5)
term.feed("e\r")                 # pick Rogue, skip the intro
term.wait_for_input(5)
print(term.text(ascii_walls=True))
```

## Tests

```bash
python -m unittest discover -s tests -t .
python tests/fuzz.py 20 2000        # random-key fuzzing in town
python tests/fuzz.py deep 20 300    # fuzz every dungeon and volcano level
```

## Layout

| Module | From C | Contents |
|---|---|---|
| `ularn.py`, `ularn_game.py`, `ularn_ask.py` | ularn.c, ularn_game.c, ularn_ask.c | main loop, options, prompts |
| `ularn_win.py` | ularn_win.h, ularn_wintty.c | screen layout, input, with pluggable `Terminal` back ends (`term_curses.py`, `term_virtual.py`) |
| `dungeon.py`, `dungeon_obj.py` | dungeon.c, dungeon_obj.c | level generation, map objects |
| `monster.py`, `sphere.py` | monster.c, sphere.c | monsters, combat, spheres of annihilation |
| `player.py`, `object.py`, `itm.py` | player.c, object.c, itm.c | the player, inventory, items |
| `potion.py`, `scroll.py`, `spell.py` | potion.c, scroll.c, spell.c | magic |
| `action.py`, `show.py` | action.c, show.c | player commands, inventory display |
| `store.py`, `scores.py`, `savegame.py`, `saveutils.py` | store.c, scores.c, savegame.c, saveutils.c | shops, the bank and college, scoreboard, save/restore |
| `help.py`, `fortune.py`, `diag.py` | help.c, fortune.c, diag.c | help pages, fortunes, diagnostics |
| `gfx.py` | ularn_winx11.c | sprite tile numbers for the map (the X11 `GetTile`) |
| `mcp_server.py`, `skills.py`, `recorder.py`, `runs.py`, `spectator.py`, `web.py`, `engine.py` | (new) | MCP server, multi-step skills for agents, game recordings, run summaries and index, the web page (watching and `--web` play), engine reset |

The sprite sheet `pyularn/data/ularn_gfx.png` is made from the original
`data/ularn_gfx.xpm` by `tools/make_tiles.py`. That script also bakes in
the transparency masks for the cursor and sparkle tiles, which the X11 code
built at start-up. `data/gfx_guide.txt` lists what each tile is.

## License

GPL-2.0, like Ularn itself; see [LICENSE](LICENSE) and
[COPYRIGHT](COPYRIGHT). Original game © Julian Olds and the Larn/Ularn
authors.
