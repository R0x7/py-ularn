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
| `new_game` | Start a game. Options: `character_class` (a-h or ogre/wizard/klingon/elf/rogue/adventurer/dwarf/rambo), `seed` for a reproducible game, `player_name`, `skip_intro`. Returns the screen and the player state. |
| `send_keys` | Send keystrokes, e.g. `"i"`, `"qa"`, `"cmle<enter>"`, `"<esc>"`. Special keys: `<esc> <enter> <space> <bs> <tab> <up> <down> <left> <right> <c-r>`. Returns the new screen. |
| `move` | Step or run in a compass direction (`n s e w ne nw se sw`), with an optional `count`. |
| `get_screen` | The current 80x24 screen. |
| `get_state` | JSON: HP, stats, gold, AC/WC, dungeon level, position, turns, inventory, active effects, known spells. |
| `key_reference` | Command list, map legend and goal. |
| `end_game` | Stop the current game. |

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
| `mcp_server.py`, `spectator.py`, `web.py`, `engine.py` | (new) | MCP server, the web page (watching and `--web` play), engine reset |

The sprite sheet `pyularn/data/ularn_gfx.png` is made from the original
`data/ularn_gfx.xpm` by `tools/make_tiles.py`. That script also bakes in
the transparency masks for the cursor and sparkle tiles, which the X11 code
built at start-up. `data/gfx_guide.txt` lists what each tile is.

## License

GPL-2.0, like Ularn itself; see [LICENSE](LICENSE) and
[COPYRIGHT](COPYRIGHT). Original game © Julian Olds and the Larn/Ularn
authors.
