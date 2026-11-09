"""Write each MCP game to disk so it can be studied afterwards.

With ``pyularn-mcp --record DIR`` every game gets its own folder::

    DIR/<run id>/meta.json      seed, class, difficulty and, once the game
                                is over, its outcome
    DIR/<run id>/events.jsonl   one JSON object per line, in order

When a game ends, `pyularn.runs` adds ``summary.md`` to its folder and
refreshes ``DIR/INDEX.md``.

Event types in ``events.jsonl``:

``start``   the full player state when the game began
``action``  one tool call: the tool, its arguments, the agent's `thought`
            and a compact state (`s`) after the game handled it
``state``   the full player state, written when the dungeon level changes
            and every `STATE_EVERY` actions
``end``     the outcome, the final full state and the last `TAIL_SCREENS`
            screens, which show what led up to the end

The recorder only writes files.  It never reads game globals itself: the
MCP server hands it plain dicts taken while the game was waiting for input.
"""

import collections
import json
import os
import time

STATE_EVERY = 200    # actions between full state snapshots
TAIL_SCREENS = 30    # screens kept for the `end` event


def _now_ms():
    return int(time.time() * 1000)


def compact_state(state):
    """The few numbers worth keeping for every single action."""
    stats = state.get("stats", {})
    pos = state.get("position", {})
    return {
        "turn": state.get("turns"),
        "lvl": state.get("level_index"),
        "x": pos.get("x"), "y": pos.get("y"),
        "hp": stats.get("hp"), "hpmax": stats.get("hp_max"),
        "sp": stats.get("spells"),
        "xl": stats.get("level"), "exp": stats.get("experience"),
        "gold": stats.get("gold"),
        "seen": len(state.get("monsters", ())),
    }


class RunRecorder:
    """Records one game.  Every method is safe to call after close()."""

    def __init__(self, root, meta, state):
        root = os.path.abspath(os.path.expanduser(root))
        base = "%s-s%s" % (time.strftime("%Y%m%d-%H%M%S"), meta.get("seed"))
        run_id, n = base, 1
        while True:
            try:
                os.makedirs(os.path.join(root, run_id))
                break
            except FileExistsError:
                n += 1
                run_id = "%s-%d" % (base, n)
        self.run_id = run_id
        self.dir = os.path.join(root, run_id)
        self.meta = dict(meta, run_id=run_id,
                         started=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         started_ms=_now_ms(),
                         ended=None, actions=0, outcome=None)
        self.actions = 0
        self.closed = False
        self._level = state.get("level_index")
        self._tail = collections.deque(maxlen=TAIL_SCREENS)
        self._events = open(os.path.join(self.dir, "events.jsonl"), "w",
                            encoding="utf-8", newline="\n")
        self._write_meta()
        self._event("start", state=state)

    # ------------------------------------------------------------ files
    def _write_meta(self):
        tmp = os.path.join(self.dir, "meta.json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.meta, f, indent=1)
            f.write("\n")
        os.replace(tmp, os.path.join(self.dir, "meta.json"))

    def _event(self, kind, **data):
        self._events.write(json.dumps(dict(type=kind, t=_now_ms(), **data),
                                      ensure_ascii=False) + "\n")
        self._events.flush()

    # ------------------------------------------------------------ recording
    def action(self, tool, args, thought, state, screen, result=None):
        """Record one tool call and the state the game was left in.  A skill
        also records its `result` (why it stopped, how many steps it took)."""
        if self.closed:
            return
        self.actions += 1
        ev = {"n": self.actions, "tool": tool, "args": args, "s": compact_state(state)}
        if thought:
            ev["thought"] = thought
        if result is not None:
            ev["result"] = {k: v for k, v in result.items()
                            if k not in ("monsters", "discovered", "stock")}
        self._event("action", **ev)
        self._tail.append({"n": self.actions, "turn": state.get("turns"), "screen": screen})
        level = state.get("level_index")
        if level != self._level or self.actions % STATE_EVERY == 0:
            self._level = level
            self._event("state", n=self.actions, state=state)

    def close(self, outcome, state, screen):
        """Write the outcome and stop recording."""
        if self.closed:
            return
        self.closed = True
        self._tail.append({"n": self.actions, "turn": state.get("turns"), "screen": screen})
        self._event("end", outcome=outcome, state=state, last_screens=list(self._tail))
        self._events.close()
        self.meta.update(ended=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         actions=self.actions, outcome=outcome)
        for key in ("character_class", "difficulty"):
            if outcome.get(key) is not None:
                self.meta[key] = outcome[key]
        self._write_meta()
        from . import runs
        runs.finish_run(self.dir)  # summary.md and INDEX.md
