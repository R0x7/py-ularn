"""Turn recorded runs into replays that a static web page can play.

A run folder (``pyularn-mcp --record``) keeps every tool call the agent made
but only the last few screens.  The game is deterministic for a given seed,
so this module plays the recorded calls again, in this process, and keeps
every frame the live view would have shown, with the agent's thoughts in
between.  After each call the game's state is checked against the one the
recording saved; if they ever differ, the replay stops there and says so.

    python3 -m pyularn.replay SITE_DIR RUN_DIR [RUN_DIR ...]

writes, under SITE_DIR (a folder of a static web site)::

    index.html      the replay player (the live view's page, fed from files)
    ularn_gfx.png   the tile sheet
    runs/<run id>.json.gz   one replay per run
    runs/index.json         the list of replays the player offers

Running it again for more runs adds them to the list.

Frames are stored as differences from the frame before (changed screen
rows, changed map tiles, the state only when it changed), so a long game
stays a few megabytes before compression.
"""

import argparse
import gzip
import json
import os
import shutil
import sys
import tempfile

from .recorder import compact_state

# The parts of the full state the page shows.
PAGE_STATE = ("dungeon_level", "turns", "rank", "stats", "inventory",
              "effects", "known_spells")
PLAYER_NAME = "Agent"


class ReplayError(Exception):
    pass


class _Collector:
    """Stands in for the live view's server: keeps what would be sent."""

    url = "(replay)"

    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)

    def close(self):
        pass


def _load_run(run_dir):
    try:
        with open(os.path.join(run_dir, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError) as e:
        raise ReplayError("%s: not a readable run (%s)" % (run_dir, e))
    if not events or events[0].get("type") != "start":
        raise ReplayError("%s: the recording has no start event" % run_dir)
    return meta, events


def rebuild(run_dir, log=None):
    """Play a recorded run again.  Returns (messages, report): the live
    view's messages in order, and how far the replay matched the recording:
    {"actions", "replayed", "mismatch" (None, or where it went wrong)}."""
    from . import mcp_server as ms, skills

    meta, events = _load_run(run_dir)
    actions = [e for e in events if e.get("type") == "action"]
    session = ms.SESSION
    collector = _Collector()
    saved = (session.record_dir, session.watch, session.spectator,
             os.environ.get("PYULARN_HOME"), os.environ.get("USER"))
    home = tempfile.mkdtemp(prefix="pyularn-replay-")
    report = {"actions": len(actions), "replayed": 0, "mismatch": None}
    try:
        # An empty home: no scoreboard, so the difficulty is the one asked for.
        os.environ["PYULARN_HOME"] = home
        # The game names the player after the login; replays are for sharing.
        os.environ["USER"] = PLAYER_NAME
        session.record_dir, session.watch, session.spectator = None, None, collector
        args = {"seed": meta["seed"],
                "character_class": str(meta.get("character_class") or "").lower()}
        if meta.get("difficulty") is not None:
            args["difficulty"] = meta["difficulty"]
        # Skills recorded before the current skills_version behaved differently.
        skills.behave_as(meta.get("skills_version") or 1)
        ms.tool_new_game(args)
        want, got = compact_state(events[0]["state"]), compact_state(session.state())
        if want != got:
            report["mismatch"] = {"n": 0, "tool": "new_game", "want": want, "got": got}
            return collector.messages, report
        for ev in actions:
            call = dict(ev.get("args") or {})
            if ev["tool"] in ("send_keys", "move"):
                # Recorded before the batch could stop when hurt: send it whole.
                call.setdefault("stop_when_hurt", False)
            if ev.get("thought"):
                call["thought"] = ev["thought"]
            tool = ms.TOOLS_BY_NAME.get(ev["tool"])
            if tool is None:
                report["mismatch"] = {"n": ev["n"], "tool": ev["tool"], "error": "unknown tool"}
                break
            try:
                tool["handler"](call)
            except ms.ToolError as e:
                report["mismatch"] = {"n": ev["n"], "tool": ev["tool"], "error": str(e)}
                break
            got = compact_state(session.state())
            if got != ev["s"]:
                report["mismatch"] = {"n": ev["n"], "tool": ev["tool"], "want": ev["s"], "got": got}
                break
            report["replayed"] += 1
            if log and report["replayed"] % 500 == 0:
                log("  %d / %d actions" % (report["replayed"], len(actions)))
    finally:
        skills.behave_as()
        session.stop()
        session.record_dir, session.watch, session.spectator = saved[:3]
        for name, value in (("PYULARN_HOME", saved[3]), ("USER", saved[4])):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(home, ignore_errors=True)
    return collector.messages, report


def encode(messages):
    """The live view's messages as compact replay entries.

    A thought:  {"th": text, "a": action, "turn": n}
    A frame:    {"k": key, "over": 1,
                 "r": all screen rows | "d": [[row index, row], ...],
                 "m": full map | 0 (no map) | "md": {"t": [i, tile, ...], "p": [x, y], "c": cursor},
                 "s": the page state's fields that changed ("st": changed stats)}
    Fields left out are unchanged from the frame before; the first frame's
    state is whole.
    """
    out = []
    rows0 = map0 = state0 = None
    for m in messages:
        if m.get("type") == "thought":
            out.append({"th": m.get("text", ""), "a": m.get("action"), "turn": m.get("turn")})
            continue
        if "rows" not in m:
            continue
        f = {}
        if m.get("key"):
            f["k"] = m["key"]
        if m.get("status") == "game over":
            f["over"] = 1
        rows = m["rows"]
        if rows0 is None or len(rows) != len(rows0):
            f["r"] = rows
        else:
            changed = [[i, r] for i, r in enumerate(rows) if r != rows0[i]]
            if changed:
                f["d"] = changed
        rows0 = rows
        mp = m.get("map")
        if mp is None:
            if map0 is not None:
                f["m"] = 0
        elif map0 is None or (mp["w"], mp["h"]) != (map0["w"], map0["h"]):
            f["m"] = mp
        else:
            diff = []
            for i, (a, b) in enumerate(zip(map0["tiles"], mp["tiles"])):
                if a != b:
                    diff += [i, b]
            if diff or mp["player"] != map0["player"] or mp["cursor"] != map0["cursor"]:
                f["md"] = {"t": diff, "p": mp["player"], "c": mp["cursor"]}
        map0 = mp
        state = m.get("state")
        if state:
            slim = {k: state.get(k) for k in PAGE_STATE}
            if state0 is None:
                f["s"] = slim
            else:
                changed = {k: v for k, v in slim.items() if k != "stats" and v != state0[k]}
                stats, stats0 = slim["stats"] or {}, state0["stats"] or {}
                st = {k: v for k, v in stats.items() if stats0.get(k) != v}
                if st:
                    changed["st"] = st
                if changed:
                    f["s"] = changed
            state0 = slim
        if f:
            out.append(f)
    return out


def run_summary(meta, report):
    """The run as the player's list shows it."""
    outcome = meta.get("outcome") or {}
    notes = meta.get("notes") or {}
    deepest = outcome.get("deepest") or {}
    return {
        "id": meta.get("run_id"),
        "started": meta.get("started"),
        "seed": meta.get("seed"),
        "class": meta.get("character_class"),
        "difficulty": meta.get("difficulty"),
        "strategy": meta.get("strategy"),
        "result": outcome.get("result") or "unfinished",
        "won": bool(outcome.get("won")),
        "reason": outcome.get("reason"),
        "turns": outcome.get("turns"),
        "deepest": deepest.get("dungeon"),
        "volcano": deepest.get("volcano"),
        "synopsis": notes.get("synopsis"),
        "actions": report["actions"],
        "complete": report["mismatch"] is None,
    }


def page_html():
    """The live view's page, changed to play replay files instead."""
    from .spectator import PAGE

    start = PAGE.index("// The page outlives any one server")
    end = PAGE.index("</script>", start)
    page = PAGE[:start] + PLAYER_JS + PAGE[end:]
    page = page.replace("__CONFIG__", json.dumps({"play": False, "title": "replay"}))
    page = page.replace('document.title = CONFIG.play ? "Ularn" : "Ularn live";',
                        'document.title = "Ularn replays";')
    page = page.replace('$("title").textContent = CONFIG.play ? "" : "live";',
                        '$("title").textContent = "replays";')
    page = page.replace('(CONFIG.play ? "playing" : "live")', '"replay"')
    page = page.replace('<option value="0">Live</option>',
                        '<option value="0">Instant</option>')
    page = page.replace('<option value="100" selected>Smooth (10/s)</option>',
                        '<option value="30">Fast (30/s)</option>\n'
                        '      <option value="100" selected>Smooth (10/s)</option>')
    page = page.replace("No thoughts yet. The agent can narrate by\n      passing "
                        "<code>thought</code> with its moves.",
                        "No thoughts yet.")
    page = page.replace("</style>", PLAYER_CSS + "</style>", 1)
    page = page.replace("<main>", PLAYER_HTML + "<main>", 1)
    return page


PLAYER_CSS = r"""
#picker { max-width: 1640px; margin: 0 auto; padding: 16px 16px 0; }
#picker[hidden], #scrub[hidden] { display: none; }
#runs { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
#runs a { display: block; color: inherit; text-decoration: none; background: var(--panel);
  border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
#runs a:hover, #runs a:focus-visible { border-color: var(--accent); }
#runs a[aria-current="true"] { border-color: var(--accent); }
#runs b { display: block; }
#runs small { color: var(--muted); display: block; }
#runs .won { color: var(--hp); }
#picker h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); font-weight: 600; margin: 0 0 8px; }
#scrub { display: flex; gap: 10px; align-items: center; max-width: 1640px; margin: 0 auto;
  padding: 12px 16px 0; color: var(--muted); font-variant-numeric: tabular-nums; }
#seek { flex: 1; accent-color: var(--accent); min-width: 0; }
"""

PLAYER_HTML = r"""<section id="picker" aria-label="Recorded games">
  <h2>Recorded games</h2>
  <div id="runs"><div class="empty">Loading the list...</div></div>
</section>
<div id="scrub" hidden>
  <button id="back" type="button">All games</button>
  <input id="seek" type="range" min="0" max="0" value="0" aria-label="Position in the game">
  <span id="pos">0 / 0</span>
</div>
"""

# Replaces the live view's connection code.  Replay entries are decoded into
# full frames up front (unchanged rows and map tiles are shared, so this is
# cheap); playback feeds them through the same queue as the live view.
PLAYER_JS = r"""// ---- replays: load a recorded game from a file instead of a live server
let frames = [], at = 0;
async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.status + " " + url);
  if (!url.endsWith(".gz")) return res.json();
  // The file is plain gzip (Pages serves it as is), so unpack it here.
  const text = await new Response(res.body.pipeThrough(new DecompressionStream("gzip"))).text();
  return JSON.parse(text);
}
function decode(entries) {
  const out = [];
  let rows = [], map = null, state = null;
  for (const e of entries) {
    if (e.th !== undefined) {
      out.push({ type: "thought", game: 1, text: e.th, action: e.a, turn: e.turn });
      continue;
    }
    if (e.r) rows = e.r;
    else if (e.d) { rows = rows.slice(); for (const [i, r] of e.d) rows[i] = r; }
    if (e.m === 0) map = null;
    else if (e.m) map = e.m;
    else if (e.md) {
      const tiles = e.md.t.length ? map.tiles.slice() : map.tiles;
      for (let i = 0; i < e.md.t.length; i += 2) tiles[e.md.t[i]] = e.md.t[i + 1];
      map = { w: map.w, h: map.h, tiles, player: e.md.p, cursor: e.md.c };
    }
    if (e.s) {
      // The first state is whole; later ones carry only what changed.
      const { st, ...rest } = e.s;
      state = state ? { ...state, ...rest } : rest;
      if (st) state.stats = { ...state.stats, ...st };
    }
    out.push({ game: 1, key: e.k || null, status: e.over ? "game over" : "playing",
               rows, map, state, i: out.length + 1 });
  }
  return out;
}
function describe(r) {
  const end = r.won ? "Won" : r.result === "died" ? (r.reason || "Died") : (r.reason || r.result);
  const depth = r.deepest != null ? "DL" + r.deepest + (r.volcano ? " + V" + r.volcano : "") : "";
  return [r.class, r.difficulty != null ? "diff " + r.difficulty : "", depth,
          r.turns != null ? r.turns + " turns" : ""].filter(Boolean).join(" · ")
    + "|" + end;
}
async function showList(selected) {
  let list;
  try { list = await fetchJson("runs/index.json"); }
  catch (e) { $("runs").innerHTML = '<div class="empty">No recorded games here yet.</div>'; return; }
  list.sort((a, b) => (b.started || "").localeCompare(a.started || ""));
  $("runs").innerHTML = "";
  for (const r of list) {
    const a = document.createElement("a");
    a.href = "?run=" + encodeURIComponent(r.id);
    if (r.id === selected) a.setAttribute("aria-current", "true");
    const [line, end] = describe(r).split("|");
    const b = document.createElement("b");
    b.textContent = (r.started || r.id).slice(0, 16).replace("T", " ");
    const s1 = document.createElement("small"); s1.textContent = line;
    const s2 = document.createElement("small"); s2.textContent = end + (r.complete ? "" : " (replay ends early)");
    if (r.won) s2.className = "won";
    a.append(b, s1, s2);
    a.onclick = ev => { ev.preventDefault(); history.pushState(null, "", a.href); route(); };
    $("runs").appendChild(a);
  }
}
function feed() {
  // Hand the queue the next stretch of frames; tick() plays them.
  while (queue.length < 200 && at < frames.length) queue.push(frames[at++]);
  kick();
}
function showPos() {
  const n = current && current.i ? current.i : 0;
  $("seek").value = n;
  $("pos").textContent = n + " / " + frames.length;
}
function resetView() {
  queue.length = 0; keys = []; lastGame = null; over = false; current = null;
  if (timer) { clearTimeout(timer); timer = null; }
}
function seek(n) {
  // Jump: replay the thoughts up to here, then show the frame there.
  resetView();
  roll.innerHTML = ""; nThoughts = 0; thoughtGame = null; $("tcount").textContent = "";
  let last = null;
  for (let i = 0; i < n; i++) {
    const m = frames[i];
    if (m.type === "thought") addThought(m);
    else { if (last) passOver(last); last = m; }
  }
  if (last) render(last);
  else { $("term").textContent = ""; }
  at = n; showPos(); feed();
}
const plainTick = tick;
tick = function () {
  plainTick(); showPos();
  if (at < frames.length && queue.length < 100) feed();
};
async function route() {
  const id = new URLSearchParams(location.search).get("run");
  $("scrub").hidden = !id;
  if (!id) {
    $("picker").hidden = false; resetView(); frames = [];
    $("conn").textContent = "pick a game"; $("conn").className = "pill";
    $("term").textContent = "Pick a recorded game above.";
    showList(null);
    return;
  }
  $("picker").hidden = true;
  $("conn").textContent = "loading"; $("conn").className = "pill";
  try {
    const data = await fetchJson("runs/" + encodeURIComponent(id) + ".json.gz");
    frames = decode(data.msgs);
  } catch (e) {
    $("conn").textContent = "could not load this game";
    return;
  }
  $("seek").max = frames.length;
  $("conn").textContent = "replay"; $("conn").className = "pill live";
  seek(0);
}
$("seek").oninput = e => seek(+e.target.value);
$("back").onclick = () => { history.pushState(null, "", location.pathname); route(); };
window.addEventListener("popstate", route);
route();
"""


def export(site_dir, run_dirs, log=print):
    """Build replays of `run_dirs` into the static site at `site_dir`."""
    runs_dir = os.path.join(site_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    index_path = os.path.join(runs_dir, "index.json")
    try:
        with open(index_path, encoding="utf-8") as f:
            index = {r["id"]: r for r in json.load(f)}
    except (OSError, ValueError):
        index = {}
    ok = True
    for run_dir in run_dirs:
        run_dir = os.path.abspath(run_dir)
        try:
            meta, _ = _load_run(run_dir)
            log("%s: replaying" % meta.get("run_id"))
            messages, report = rebuild(run_dir, log=log)
        except ReplayError as e:
            log(str(e))
            ok = False
            continue
        if report["mismatch"]:
            log("  stopped at action %d of %d: %s" % (
                report["replayed"], report["actions"], json.dumps(report["mismatch"])))
        summary = run_summary(meta, report)
        data = {"v": 1, "run": summary, "msgs": encode(messages)}
        out = os.path.join(runs_dir, summary["id"] + ".json.gz")
        with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        log("  %d frames, %.1f MB" % (len(data["msgs"]), os.path.getsize(out) / 1e6))
        index[summary["id"]] = summary
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sorted(index.values(), key=lambda r: r["id"]), f, indent=1)
        f.write("\n")
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page_html())
    from .spectator import tile_sheet
    with open(os.path.join(site_dir, "ularn_gfx.png"), "wb") as f:
        f.write(tile_sheet())
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m pyularn.replay",
                                 description="Build web replays of recorded runs.")
    ap.add_argument("site", help="folder of the static site to write into")
    ap.add_argument("runs", nargs="+", help="run folders (from pyularn-mcp --record)")
    args = ap.parse_args(argv)
    return 0 if export(args.site, args.runs) else 1


if __name__ == "__main__":
    sys.exit(main())
