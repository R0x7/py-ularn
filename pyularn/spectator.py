"""Live spectator web page for games driven through the MCP server.

A tiny HTTP server (standard library only) that serves one page and a
Server-Sent Events stream.  Every time the game is about to wait for a key,
the MCP server publishes a frame (screen with colours, player state, the key
that was just pressed); connected browsers draw it.  The page is read-only.

    GET /         the viewer page
    GET /events   text/event-stream of JSON frames
    GET /frame    the latest frame as JSON
"""

import collections
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ularn_win

# Curses colour numbers -> CSS colours that read well on a dark background.
CSS_COLORS = ["#6b7280", "#f87171", "#4ade80", "#facc15",
              "#60a5fa", "#e879f9", "#22d3ee", "#e5e7eb"]

KEY_LABELS = {
    "\r": "Enter", "\n": "Enter", "\x1b": "Esc", " ": "Space", "\x08": "Bksp",
    "\t": "Tab", "KEY_UP": "Up", "KEY_DOWN": "Down", "KEY_LEFT": "Left",
    "KEY_RIGHT": "Right", "KEY_A1": "Home", "KEY_A3": "PgUp", "KEY_C1": "End",
    "KEY_C3": "PgDn", "KEY_B2": "Center",
}


def key_label(k):
    if k is None:
        return None
    if k in KEY_LABELS:
        return KEY_LABELS[k]
    if len(k) == 1 and ord(k) < 32:
        return "^" + chr(ord(k) + 64)
    return k


def screen_runs(term, ascii_walls=True):
    """The terminal as rows of [text, color, flags] runs (flags: b=bold,
    r=reverse/standout, u=underline)."""
    from .term_virtual import ACS_TO_ASCII

    rows = []
    with term._lock:
        for y in range(term.rows):
            runs = []
            cur = None
            for x in range(term.cols):
                ch = term.chars[y][x]
                if ascii_walls:
                    ch = ACS_TO_ASCII.get(ch, ch)
                a = term.attrs[y][x]
                pair = ularn_win.PAIR_NUMBER(a)
                fg = term.pairs.get(pair, (ularn_win.C_WHITE, 0))[0] if pair else ularn_win.C_WHITE
                flags = ""
                if a & ularn_win.A_BOLD:
                    flags += "b"
                if a & (ularn_win.A_REVERSE | ularn_win.A_STANDOUT):
                    flags += "r"
                if a & ularn_win.A_UNDERLINE:
                    flags += "u"
                color = CSS_COLORS[fg % 8]
                # A plain blank looks the same in any plain run, so it never
                # splits one (but must not join a reversed/underlined run).
                blank = ch == " " and "r" not in flags and "u" not in flags
                if cur is not None and (
                        (blank and "r" not in cur[2] and "u" not in cur[2])
                        or (color == cur[1] and flags == cur[2])):
                    cur[0] += ch
                else:
                    cur = [ch, color, flags]
                    runs.append(cur)
            rows.append(runs)
    return rows


class Spectator:
    def __init__(self, host="127.0.0.1", port=8765, history=4000):
        self.frames = collections.deque(maxlen=history)
        self.seq = 0
        self.cond = threading.Condition()
        self.closed = False
        spectator = self

        class Handler(SpectatorHandler):
            owner = spectator

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.host, self.port = self.httpd.server_address[:2]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       name="ularn-spectator", daemon=True)
        self.thread.start()

    @property
    def url(self):
        host = "localhost" if self.host in ("127.0.0.1", "0.0.0.0", "::") else self.host
        return "http://%s:%d/" % (host, self.port)

    def publish(self, frame):
        with self.cond:
            self.seq += 1
            frame["seq"] = self.seq
            self.frames.append(json.dumps(frame, separators=(",", ":")))
            self.cond.notify_all()

    def latest(self):
        with self.cond:
            return self.frames[-1] if self.frames else None

    def since(self, seq, timeout=15):
        """Frames with a sequence number above `seq` (waits up to `timeout`)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > seq or self.closed, timeout)
            n = self.seq - seq
            if n <= 0:
                return [], seq
            frames = list(self.frames)[-min(n, len(self.frames)):]
            return frames, self.seq

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()
        self.httpd.shutdown()
        self.httpd.server_close()


class SpectatorHandler(BaseHTTPRequestHandler):
    owner = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stderr quiet
        pass

    def _send(self, code, ctype, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif path == "/frame":
            self._send(200, "application/json", self.owner.latest() or "null")
        elif path == "/events":
            self.events()
        else:
            self._send(404, "text/plain", "not found")

    def events(self):
        sp = self.owner
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            latest = sp.latest()
            seq = sp.seq
            if latest:
                self.wfile.write(b"data: " + latest.encode() + b"\n\n")
                self.wfile.flush()
            while not sp.closed:
                frames, seq2 = sp.since(seq)
                if not frames:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    for f in frames:
                        self.wfile.write(b"data: " + f.encode() + b"\n\n")
                seq = seq2
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def start(port, host="127.0.0.1"):
    """Start a spectator, or return None (with a message on stderr) on error."""
    try:
        sp = Spectator(host, port)
    except OSError as e:
        sys.stderr.write("pyularn: spectator disabled, cannot listen on %s:%s (%s)\n"
                         % (host, port, e))
        return None
    sys.stderr.write("pyularn: watch the game at %s\n" % sp.url)
    return sp


def now_ms():
    return int(time.time() * 1000)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ularn Live</title>
<style>
:root {
  --bg: #0b0d10; --panel: #13161b; --line: #232831; --text: #e5e7eb;
  --muted: #8b93a1; --accent: #facc15; --hp: #4ade80; --hp-low: #f87171;
  --mp: #60a5fa;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
header { display: flex; align-items: center; gap: 12px; padding: 12px 16px;
  border-bottom: 1px solid var(--line); flex-wrap: wrap; }
h1 { font-size: 16px; margin: 0; letter-spacing: .04em; }
h1 span { color: var(--accent); }
.pill { font-size: 12px; padding: 2px 10px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted); }
.pill.live { color: #0b0d10; background: var(--hp); border-color: var(--hp); }
.pill.over { color: #0b0d10; background: var(--hp-low); border-color: var(--hp-low); }
.spacer { flex: 1; }
.controls { display: flex; gap: 8px; align-items: center; }
select, button { background: var(--panel); color: var(--text);
  border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; font: inherit; cursor: pointer; }
button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
main { display: grid; grid-template-columns: minmax(0, auto) 300px; gap: 16px;
  padding: 16px; align-items: start; justify-content: center; }
.term-wrap { background: #000; border: 1px solid var(--line); border-radius: 8px;
  padding: 12px; overflow-x: auto; }
#term { margin: 0; font: 15px/1.25 ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace;
  white-space: pre; color: #e5e7eb; }
#term .b { font-weight: 700; }
#term .r { background: currentColor; }
#term .r > i { color: #000; font-style: normal; }
#term .u { text-decoration: underline; }
aside { display: flex; flex-direction: column; gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.card h2 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .08em; color: var(--muted); font-weight: 600; }
.bar { height: 8px; background: #000; border-radius: 4px; overflow: hidden; margin: 4px 0 10px; }
.bar > div { height: 100%; width: 0; transition: width .15s; }
.row { display: flex; justify-content: space-between; font-variant-numeric: tabular-nums; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px 10px;
  font-variant-numeric: tabular-nums; }
.grid div { display: flex; justify-content: space-between; }
.grid span, .row span:first-child { color: var(--muted); }
ul { margin: 0; padding-left: 0; list-style: none; font: 13px/1.5 ui-monospace, Consolas, monospace; }
#keys { display: flex; flex-wrap: wrap; gap: 4px; }
kbd { font: 12px ui-monospace, Consolas, monospace; padding: 1px 6px; border-radius: 4px;
  border: 1px solid var(--line); background: #000; }
kbd:last-child { border-color: var(--accent); color: var(--accent); }
.empty { color: var(--muted); font-style: italic; }
@media (max-width: 1080px) { main { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 720px) { #term { font-size: 11px; } main { padding: 12px; } }
</style>
</head>
<body>
<header>
  <h1><span>ULARN</span> live</h1>
  <span id="conn" class="pill">connecting</span>
  <span id="where" class="pill">-</span>
  <div class="spacer"></div>
  <div class="controls">
    <label for="speed" style="color:var(--muted)">Playback</label>
    <select id="speed">
      <option value="0">Live</option>
      <option value="100" selected>Smooth (10/s)</option>
      <option value="250">Slow (4/s)</option>
    </select>
    <button id="pause" aria-pressed="false">Pause</button>
  </div>
</header>
<main>
  <div class="term-wrap"><pre id="term">Waiting for a game to start...</pre></div>
  <aside>
    <div class="card">
      <h2>Vitals</h2>
      <div class="row"><span>HP</span><b id="hp">-</b></div>
      <div class="bar"><div id="hpbar"></div></div>
      <div class="row"><span>Spells</span><b id="sp">-</b></div>
      <div class="bar"><div id="spbar" style="background:var(--mp)"></div></div>
      <div class="grid" id="stats"></div>
    </div>
    <div class="card"><h2>Inventory</h2><ul id="inv"></ul></div>
    <div class="card"><h2>Effects &amp; spells</h2><ul id="fx"></ul></div>
    <div class="card"><h2>Recent keys</h2><div id="keys"></div></div>
  </aside>
</main>
<script>
const $ = id => document.getElementById(id);
const queue = [];
let paused = false, lastGame = null, keys = [], timer = null;

function esc(s) { return s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }

function drawScreen(rows) {
  const out = [];
  for (const runs of rows) {
    let line = "";
    for (const [text, color, flags] of runs) {
      const cls = flags.split("").join(" ");
      const t = esc(text);
      line += flags.includes("r")
        ? `<span class="${cls}" style="color:${color}"><i>${t}</i></span>`
        : `<span class="${cls}" style="color:${color}">${t}</span>`;
    }
    out.push(line);
  }
  $("term").innerHTML = out.join("\n");
}

function list(el, items, empty) {
  el.innerHTML = items && items.length
    ? items.map(i => `<li>${esc(i)}</li>`).join("")
    : `<li class="empty">${empty}</li>`;
}

function render(f) {
  if (f.game !== lastGame) { keys = []; lastGame = f.game; }
  if (f.key) { keys.push(f.key); if (keys.length > 24) keys.shift(); }
  drawScreen(f.rows);
  const over = f.status === "game over";
  $("conn").textContent = over ? "game over" : "live";
  $("conn").className = "pill " + (over ? "over" : "live");
  const s = f.state;
  if (s) {
    const st = s.stats;
    $("where").textContent = `Level ${s.dungeon_level} · turn ${s.turns} · ${s.rank}`;
    $("hp").textContent = `${st.hp} / ${st.hp_max}`;
    const hpPct = st.hp_max ? Math.max(0, Math.min(100, 100 * st.hp / st.hp_max)) : 0;
    $("hpbar").style.width = hpPct + "%";
    $("hpbar").style.background = hpPct < 30 ? "var(--hp-low)" : "var(--hp)";
    $("sp").textContent = `${st.spells} / ${st.spells_max}`;
    $("spbar").style.width = (st.spells_max ? 100 * st.spells / st.spells_max : 0) + "%";
    const names = [["STR","str"],["INT","int"],["WIS","wis"],["CON","con"],["DEX","dex"],["CHA","cha"],
                   ["AC","ac"],["WC","wc"],["Lvl","level"],["Exp","experience"],["Gold","gold"],["Bank","bank"]];
    $("stats").innerHTML = names.map(([l,k]) => `<div><span>${l}</span>${st[k]}</div>`).join("");
    list($("inv"), s.inventory, "empty pack");
    list($("fx"), [...s.effects, ...s.known_spells.map(x => "spell: " + x)], "none");
  }
  $("keys").innerHTML = keys.map(k => `<kbd>${esc(k)}</kbd>`).join("");
}

function tick() {
  timer = null;
  if (paused || !queue.length) return;
  const delay = +$("speed").value;
  if (delay === 0 || queue.length > 300) {
    // Live mode, or far behind: jump to the newest frame but keep the keys.
    while (queue.length > 1) { const f = queue.shift(); if (f.key && f.game === lastGame) { keys.push(f.key); } }
    keys = keys.slice(-24);
  }
  render(queue.shift());
  if (queue.length) timer = setTimeout(tick, delay);
}
function kick() { if (!timer) timer = setTimeout(tick, 0); }

$("pause").onclick = () => {
  paused = !paused;
  $("pause").setAttribute("aria-pressed", paused);
  $("pause").textContent = paused ? "Resume" : "Pause";
  if (!paused) kick();
};
$("speed").onchange = kick;

function connect() {
  const es = new EventSource("events");
  es.onmessage = e => { queue.push(JSON.parse(e.data)); kick(); };
  es.onerror = () => { $("conn").textContent = "reconnecting"; $("conn").className = "pill"; };
}
connect();
</script>
</body>
</html>
"""
