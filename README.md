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
| `send_keys` | Send keystrokes, e.g. `"i"`, `"qa"`, `"cmle<enter>"`, `"<esc>"`. Special keys: `<esc> <enter> <space> <bs> <tab> <up> <down> <left> <right> <c-r>`. Returns the new screen. Stops sending the rest of the keys as soon as HP drops, and says which were not sent (`stop_when_hurt: false` sends the whole batch). |
| `move` | Step or run, with an optional `count`: give `direction`, a compass name (`n s e w ne nw se sw`), or `key`, the game's own movement key (`h j k l y u b n`, where `n` is south-east). Like `send_keys`, a `count` stops early when HP drops. |
| `get_screen` | The current 80x24 screen. |
| `get_state` | JSON: HP, stats, gold, AC/WC, dungeon level, position, turns, inventory, active effects, known spells, plus `seed`, `difficulty`, `time` left, the `deepest` levels visited, the `map`, the `monsters` and `objects` on it, the latest `messages`, `attacked_by` (who hit you in the last few turns and whether the map showed them, so an invisible attacker is named) and, once the game is over, its `outcome`. |
| `key_reference` | Command list, map legend and goal. |
| `end_game` | Stop the current game. |
| `explore` | Skill: explore the level until something needs a decision. Option `until` stops when a target is found; `ignore_monsters` walks on past monsters. |
| `travel_to` | Skill: walk to a `target` (name or map symbol) or to `x`, `y`. Options: `ignore_monsters`, and `through_unknown` to cross cells not yet seen on the way to `x`, `y`. |
| `pick_up` | Skill: walk to things lying on the level and take them, nearest first: everything known, one kind (`target`), or the thing at `x`, `y`. |
| `take_stairs` | Skill: go to the known stairs and take them, `direction` `down` or `up`. |
| `fight` | Skill: attack the nearest visible monster, then only what is next to you, until none is left or HP falls to `min_hp`. |
| `flee` | Skill: run from visible monsters, by a planned route, until none is within `safe_distance`. |
| `rest` | Skill: wait until HP is full (`until`: `hp`, `spells` or `both`), for a set number of `turns`, or until a timed `effect` such as a time stop has ended, stopping at the first sign of trouble. |
| `buy` | Skill: buy `items` at the DND store in town, or return its price list. |
| `summarize_run` | Write a finished game's post-mortem: a one-sentence `takeaway`, then `synopsis`, `went_wrong`, `worked`, `next_try`. Needs `--record`. |
| `list_runs` | Recorded games, newest first, with how each ended and its one-line takeaway (`full` adds the synopsis and the rest). Filters: `difficulty`, `strategy`, `limit`. Needs `--record`. |
| `get_run` | One recorded game's full summary. Needs `--record`. |

Every game has a seed. If `new_game` is not given one it picks one at
random and reports it in the state, so any game can be replayed.

Arguments are checked against each tool's schema before the call runs. An
argument the tool does not have is refused, with the nearest name it does
have (`explore has no argument 'ignore_monster' (did you mean
'ignore_monsters'?)`), so a misspelt option is never silently dropped and
the call run with the default. Values of the wrong type or out of range are
refused the same way. A `thought` is accepted by every tool.

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
| `explore` | `explored` (nothing left that a skill can walk to; `beyond` lists known traps with more of the level past them), `no_path` (more is left, but the monsters in `blocked_by` stand in the only known way), `found` (the `until` target is known) |
| `travel_to` | `arrived` (a question asked by the destination is left for the agent), `not_found`, `no_path` (with what is in the way: `blocked_by`, the monsters; `hazards`, the known traps; or a `reason` saying the known map does not connect) |
| `pick_up` | `done`, `pack_full`, `not_found` (nothing known to pick up), `no_path` (none of it can be reached). Whatever the result, `taken` lists each thing picked up with its pack slot, and `left` what is still lying there and why |
| `take_stairs` | `changed_level`, `not_found` (explore first), `refused` |
| `fight` | `clear`, `no_monsters`, `low_hp` (HP at `min_hp`, or no more than the biggest blow taken so far), `hurt_at_range` (hurt with nothing visible next to you: a breath, a spell or something invisible), `unreachable`, `max_turns` |
| `flee` | `safe`, `cornered` (nowhere you can reach before the monsters is further from them), `blocked`, `max_steps` |
| `rest` | `rested` (nothing left to recover), `waited` (the `turns` asked for have passed), `max_turns`, `blocked` (on a trap with nowhere to step) |
| `buy` | `done` (with `bought` and `failed`, each with a reason), `listed`, `refused` (taxes owed) |

Any walking skill also stops with `monster_appeared`, `monster_adjacent`,
`hurt`, `level_changed`, `teleported`, `blocked`, `prompt`, `max_steps` or
`game_over`. It stops for a monster once: when a new one shows up within
six cells with a known way to reach you (one seen across the level, or
sealed behind walls, is passed over), and when one first comes next to
you, not at every step taken beside a monster that stays put. With
`ignore_monsters` it does not stop for monsters at all, which is for
walking past sleepers; it still goes round them and stops when HP drops.
A skill's report lists `unseen_attackers` when something the map does not
show hit you in the last few turns.

What the skills will and will not do:

- They only press keys, so they can do nothing a player could not.
- They use only what the player knows: the map as drawn, and the monsters
  on it. Undiscovered traps and unseen monsters are invisible to them.
- They never route through a known trap, pit, teleporter or express
  elevator, they open doors, they pick up gold, and they answer "ignore"
  to anything else they walk over.
- A walk that is hurt while standing on a trap steps off it before
  stopping (`stepped_off_trap`). A step that does not happen, other than
  at a stuck door, stops the walk at once with `blocked`: something unseen
  is there, and walking into it again would attack it.
- Once `fight` has killed something it never walks off after another
  target; it only goes on against monsters already next to you. It cannot
  stop a single blow bigger than your HP.
- `pick_up` only takes. It answers "take" where the game offers it, and
  stops with `pack_full` when the game will not let you carry more; with a
  full pack it fetches only gold, and does not walk to the rest. To drink,
  read or open something where it lies, use `travel_to` and answer the
  question yourself. With no arguments it takes everything, including
  what you dropped on the level: it cannot tell the difference.
- `rest` presses `.` one turn at a time, where a batch of `.` keys would
  keep passing turns after HP is full or with a monster walking up. It
  stops when HP drops or a monster comes near, and it will not rest on a
  known arrow or dart trap, which fires every turn you stand on it: it
  steps off first.
- `flee` heads for the place furthest from the monsters in view among the
  places you can get to before any of them could, and plans again after
  each step. So it leaves a room by the door where stepping straight away
  from the monster would back into a corner, and it prefers an unexplored
  edge of the map to a known dead end. It still knows only what you can
  see.
- They will not start while the game is asking a question, or while the
  character is blind or confused (`rest` can: waiting it out is the cure).
- In town, where every building is there to be found, a skill that needs
  one the player no longer knows of (after a potion of forgetfulness)
  explores until it turns up. Elsewhere an unknown target is `not_found`.
- `fight` is melee only. Spells, potions and scrolls are left to the agent
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
| `meta.json` | Seed, class, difficulty, start and end time, number of actions, number of calls refused (`errors`) and the outcome. |
| `events.jsonl` | One JSON object per line: `start` (full state), an `action` for each `move` / `send_keys` / skill call (arguments, the agent's `thought`, and HP, position, level and turn afterwards; a skill's `result` too), a full `state` on each level change and every 200 actions, an `error` for each call the server refused or that failed (the tool, its arguments and the message the agent got), and `end` (outcome, final state and the last 30 screens). |
| `summary.md` | Written when the game ends: how it ended, the hypotheses it tested, the agent's post-mortem, and what happened (route through the levels, lowest HP, final inventory, the calls the server refused, last thoughts, final screen). |

`DIR/INDEX.md` lists every run, newest first, with a count of runs and wins
per difficulty.

### Learning from earlier games

With `--record` on, the recordings folder also holds a campaign: what the
games so far have learned, kept in `campaign.json` and written out for
people as `CAMPAIGN.md`.

- **Playbook.** Lessons, each citing the runs that showed it. A lesson is
  `tentative` when seen once and `confirmed` when more than one run agrees.
  A lesson found to be wrong is retracted, not deleted, so it is not
  learned again by mistake. A lesson is one short instruction with a
  topic, and the playbook has a size budget: see "Keeping it short" below.
- **Strategy tree.** Every strategy is a proven strategy plus one change,
  so the effect of that change shows when the two are compared. The root,
  `S1`, is a baseline with no fixed plan.
- **Progress.** Wins are too rare to learn from at first, so each game is
  scored on how far it got: 1 point per dungeon level, 2 per volcano level,
  10 for holding the cure, 30 for winning. A strategy's results are worked
  out from its recorded games and are never stored separately.

#### Keeping it short

Every agent starts from nothing but the briefing, so what it carries has to
stay small as the games pile up. Three things are distilled as play goes
on, so that nobody has to read the games one by one:

- **A game, in one line.** `summarize_run` takes a `takeaway`: one sentence
  (at most 200 characters) on what ended the game and the decision that
  would have changed it. Lists of games show only that. A game written up
  without one shows the first thing that went wrong.
- **A strategy, in one page.** `get_strategy` gives a strategy whole: what
  it changes, its numbers, its field notes and a line for each of its
  games. The briefing carries the same for the strategy about to be
  played and the ones it builds on.
  - The numbers are worked out from the recordings: games, wins, how often
    the cure was held, average progress, what ended the games and on which
    levels, and how long a game lasted.
  - The field notes are the agents' own account of how the strategy plays,
    how it dies and what to do differently, in at most 1,200 characters.
    After its game each agent rewrites them whole with `note_strategy`
    (`summarize_run` shows them as they stand), so they stay one short text
    however many games are played. Earlier versions are kept in
    `campaign.json`. The notes say how many of the strategy's games they
    cover, so stale ones show.
- **The playbook, within a budget.** A lesson is at most 300 characters and
  has a topic of a word or two (`dragons`, `volcano`, `town`).
  `merge_lessons` folds lessons that overlap into one, which carries all
  their evidence and so is confirmed once more than one run stands behind
  it; with a single id it rewrites a lesson. The originals stay on record
  as merged. `get_lessons` looks a subject up.

  The playbook's budget is the `playbook_budget` rule (12,000 characters by
  default). While it is over, the briefing says so, and it lists the
  lessons seen only once under their topics, to be read with `get_lessons`
  when the subject comes up, instead of carrying their text. Confirmed
  lessons, and any lesson not yet given a topic, are always carried in
  full.

The field notes are only as good as the agent that rewrote them, which is
why the computed numbers sit beside them and the earlier versions are kept.

A game started under a name that is not one of the campaign's strategies
counts towards none of them, and `new_game` says so. A slip such as
`S1 Baseline` for `S1` is read as the strategy.

#### After a win

A won game shows that its strategy can win, but the how is in that one
game. So a win is turned into a strategy of its own, a **winning line**,
which later games follow and correct:

1. **The run sheet.** Every game's `summary.md` (and so `get_run`) has a
   table of what the character was on first reaching each level: turn,
   character level, HP, AC, WC, gold, spells, and what was worn and
   wielded. Under it are the shopping, trip by trip, the spells in the
   order learned, when the cure was taken and the levels passed on the way
   home. It is worked out from the recording, for won games and lost ones
   alike.
2. **The line.** When a game is won under an ordinary strategy, the
   campaign makes a new strategy that follows it: a child of that strategy,
   with the winner's class, the won game as its model, and seeds of its own
   that nobody has played. It is played next, ahead of everything else.
3. **The recipe.** Writing the win up, `summarize_run` asks for the line's
   recipe and shows the run sheet to write it from; `write_recipe` saves it
   (2,500 characters at most). A recipe is the plan in stages: what to do
   in each, what to buy or learn, what to have before going on, in numbers,
   and the killers met with the answer to each. Nothing about where things
   lay on that map. The briefing for a line carries its recipe and the
   winner's run sheet, to measure oneself against level by level.
4. **Revision.** After each game under the line, `summarize_run` sets that
   game beside the one that won, level by level, names the first place it
   fell behind, and asks for the recipe to be rewritten whole. Earlier
   versions are kept.
5. **The verdict.** A line is judged on wins, not on average progress. It
   is proven, and becomes the base, as soon as it wins on one of its unseen
   seeds. If it plays them all (as many as a trial has games) and wins
   none, it is abandoned: the win it followed was not one it could repeat.
   A second win under the same strategy while its line is being tried
   joins the line as another game to follow.

One win is one sample, and part of any win is what the dungeon happened to
hand out, so a first recipe is over-fitted. What makes a line worth
following is step 4 on seeds nobody has played: each game knocks out a part
that was luck.

**A seed already won does not count again.** Games are deterministic, so a
won seed can be won again by sending the same keys, which shows nothing
about the strategy. A win on a seed that an earlier game won at that
difficulty is not counted as a win by the ladder, makes no line, and is
scored as a game that held the cure when strategies are compared.

#### Trying, keeping and backing out of strategies

One game says little, because a roguelike death is mostly luck. So a new
strategy is on trial for a fixed number of games, and the campaign decides
what happens to it from the results:

| Rule | Default | Meaning |
|---|---|---|
| `budget` | 5 | Games in a trial. Every strategy plays the same seeds, so two strategies are compared on the same dungeons. |
| `margin` | 1.0 | Average progress a strategy must beat its parent by: one dungeon level deeper. |
| `holdout` | 3 | Games on seeds nobody has played, which a strategy that passed its trial must then get through without falling below its parent's average. Fixed seeds can be learned by heart; this catches that. |
| `patience` | 3 | Failed ideas in a row on top of a proven strategy before that line counts as stalled. |

- A strategy that passes both tests is **proven** and becomes the base that
  new ideas build on.
- One that does not is **abandoned**, with the numbers, and listed under
  "Tried and failed" so it is not proposed again. An abandoned idea can be
  retried only with a `retry_reason` saying what has changed.
- When a line has **stalled**, the base steps back to the proven strategy it
  grew from, and the next idea branches off from there.
- The baseline is measured first, so there is something to beat.
- Games that were stopped, crashed, or played at another difficulty or on
  other seeds do not count towards a trial.

Every verdict is logged with its numbers under "Decisions" in
`CAMPAIGN.md`. The rules, including the ladder's below, are set when a
campaign starts (`pyularn-coach --budget 5 --margin 1 --holdout 3
--patience 3 --window 5 --wins 3 --top 5`) and then stay fixed, so all its
strategies are judged the same way.

#### The difficulty ladder

A campaign plays one difficulty at a time and climbs:

| Rule | Default | Meaning |
|---|---|---|
| `window` | 5 | The ladder looks at this many of the latest finished games at the current difficulty. |
| `wins` | 3 | When this many of them were won, the campaign moves up one difficulty. |
| `top` | 5 | The difficulty at which the campaign is complete. Ularn goes up to 100. |

What carries over to the next difficulty and what does not:

- The playbook carries over. Lessons from an easier difficulty are marked
  with where they were learned, and the briefing warns that some may stop
  working.
- The strategy tree and the base carry over, but their results do not:
  games are only ever compared within one difficulty. The base is measured
  again on new seeds, strategies that were mid-trial start again, and a
  stalled line gets another chance. Ideas abandoned earlier stay abandoned
  unless proposed again with a reason.
- Each campaign game runs with a scoreboard of its own. Ularn itself
  remembers a win and starts that player's next game one difficulty up,
  owing taxes; a campaign needs several wins at one difficulty and games
  that do not affect each other.

`CAMPAIGN.md` and the briefing show where the campaign stands: the
difficulty, games and wins there, and each difficulty cleared so far.

#### One cycle

The server asks agents to follow this loop:

1. `get_briefing`: the strategy to play and why, the playbook, every
   strategy with how far it got, what was tried and failed, the latest
   decisions and the latest games. When no idea is waiting, it asks for a
   new one first.
2. `new_game` with that `strategy`. The game takes its hypotheses, class,
   seed and difficulty from the strategy.
3. Play to the end.
4. `summarize_run`: a one-sentence `takeaway`, a `synopsis`, what
   `went_wrong`, what `worked` and what the next game will try
   (`next_try`). Then `note_strategy`, to bring the strategy's field notes
   up to date.
5. `add_lesson` for what the game showed that the playbook does not already
   say (`merge_lessons` where it overlaps a lesson that is there,
   `retract_lesson` for a lesson it disproved), and `propose_strategy` if
   there is one specific change worth testing next.

| Tool | What it does |
|---|---|
| `get_briefing` | What to read before a game; starts the campaign if there is none. A long briefing comes in pages: its first line says how many, and `page` asks for the next. |
| `get_strategy` | One `strategy` whole: what it changes, its numbers, its field notes, and a line for each of its games. |
| `note_strategy` | Rewrite a `strategy`'s field notes (`text`, at most 1,200 characters). |
| `write_recipe` | Write or rewrite the recipe of a winning line (`text`, at most 2,500 characters; `strategy` defaults to the line this session's game belongs to). |
| `propose_strategy` | Put a strategy on trial: `title`, the one `change`, optional `parent`, `character_class` and `retry_reason`. |
| `add_lesson` | Add a lesson: `text` (at most 300 characters), `topic`, `evidence` (run ids), `confidence`. |
| `merge_lessons` | Replace `lesson_ids` with one lesson (`text`, optional `topic`) that carries their evidence. |
| `get_lessons` | The lessons in full, all of them or those `about` a topic or word. |
| `retract_lesson` | Mark lesson `lesson_id` as wrong, with a `reason`. |

#### Running the loop

`pyularn-coach` plays a campaign without anyone at the keyboard. It starts
one fresh agent per game and gives each the same short instruction: read
the briefing and do one cycle. What carries over between games is the
campaign folder, not the agent's memory.

```bash
pyularn-coach --dir runs --cycles 5 --max-budget-usd 3
pyularn-coach --dir runs --status      # print the playbook and strategies
```

The agent is Claude Code in headless mode by default (`claude -p ...`, see
`--print-command`). `--agent-cmd` swaps in any other command that can use
an MCP server; `{prompt}` and `{mcp_config}` in it are replaced. Other
options: `--model`, `--max-budget-usd` (a spending cap per game),
`--timeout`, `--watch PORT` for the live page, and `--difficulty` for a new
campaign.

Before the first game the coach checks whether the campaign needs tidying:
a playbook over its budget, lessons with no topic, a strategy that has
been played but has no field notes, or a winning line with no recipe. If so it first starts one agent as an
editor, which plays no game: it merges and shortens lessons until the
playbook fits, and writes the missing notes from the strategy's games.
`pyularn-coach --tidy` runs the editor alone, and `--no-tidy` skips it. A
new campaign's budget is set with `--playbook-budget`. The editor runs at
most once per invocation; if it does not finish, the coach says what is
left and play goes on.

The coach writes each agent's output to `DIR/coach-logs/` and prints every
decision the campaign makes as it happens. It stops after the cycles asked
for, when the top of the ladder is cleared, or when two cycles in a row
fail to finish a game. Run it again later to carry on where it left off.

The recordings are also readable outside an agent:

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

### Replays on a static web site

A recorded game can be turned into a replay that any static host (GitHub
Pages, for one) can serve, with no server running:

```bash
python -m pyularn.replay SITE_DIR runs/20261110-072818-s1776500909 [more runs...]
```

The recording keeps the agent's calls, not every screen. Games are
deterministic for a seed, so this plays the calls again and keeps every
frame the live view would have shown, plus the agent's thoughts. After each
call it checks the game against the state the recording saved. If they
ever differ, it stops there and marks the replay as ending early. The
player is named "Agent" rather than after your login.

`SITE_DIR` gets `index.html` (the live view's page, playing from files, with
a list of games and a seek bar), the tile sheet, and `runs/<run id>.json.gz`
plus `runs/index.json`. Frames are stored as changes from the frame before,
so a 600-call game is about 0.3 MB. Run the command again with more runs to
add them to the list.

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
| `mcp_server.py`, `skills.py`, `recorder.py`, `runs.py`, `learn.py`, `coach.py`, `spectator.py`, `web.py`, `replay.py`, `engine.py` | (new) | MCP server, multi-step skills for agents, game recordings, run summaries and index, the playbook and strategy tree, the loop that runs a campaign, the web page (watching and `--web` play), static web replays of recorded games, engine reset |

The sprite sheet `pyularn/data/ularn_gfx.png` is made from the original
`data/ularn_gfx.xpm` by `tools/make_tiles.py`. That script also bakes in
the transparency masks for the cursor and sparkle tiles, which the X11 code
built at start-up. `data/gfx_guide.txt` lists what each tile is.

## History, credits and license

Ularn is the work of Noah Morgan (Larn, 1986), Phil Cordier (Ularn), David
Richerby, Josh Brandt and Josh Bressers (Ularn 1.5) and Julian Olds
(Ularn 1.6). [HISTORY.md](HISTORY.md) gives the game's history, from
[larn.org](https://larn.org/history/history), and a copyright note.

This project claims no copyright in the game and is shared free and
non-commercially only: Larn's original terms forbid making a profit from it.
The 1.6 sources are released under the GPL v2 (see [LICENSE](LICENSE) and
[COPYRIGHT](COPYRIGHT)), but larn.org notes that this does not lift Larn's
no-profit condition; see [HISTORY.md](HISTORY.md#copyright).
