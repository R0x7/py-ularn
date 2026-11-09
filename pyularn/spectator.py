"""Live spectator web page for games driven through the MCP server.

A tiny HTTP server (standard library only) that serves one page and a
Server-Sent Events stream.  Every time the game is about to wait for a key,
the game's owner publishes a frame (screen with colours, the map as sprite
tiles, player state, the key that was just pressed); connected browsers draw
it.  Watching an MCP game, the page is read-only.  With an `on_keys` handler
(``pyularn --web``) the page is also the game's keyboard.

    GET  /               the page
    GET  /events         text/event-stream of JSON frames (and the agent's
                         thoughts: {"type": "thought", ...})
    GET  /frame          the latest frame as JSON
    GET  /ularn_gfx.png  the tile sheet
    POST /keys           {"keys": [...]} (only with on_keys)
"""

import collections
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ularn_win
from .header import data_path

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


# Special keys the page may send (as named by the curses terminal).
SPECIAL_KEYS = {"KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
                "KEY_A1", "KEY_A3", "KEY_B2", "KEY_C1", "KEY_C3"}


def make_frame(term, game, status, state):
    """A frame for the page: screen runs, the map as tiles and the state."""
    from . import gfx

    try:
        tiles = gfx.map_frame()
    except Exception:  # never let the view break the game
        tiles = None
    return {
        "game": game,
        "status": status,
        "key": key_label(term.last_key),
        "rows": screen_runs(term),
        "map": tiles,
        "state": state,
        "t": now_ms(),
    }


_tile_sheet = None


def tile_sheet():
    """The PNG tile sheet bytes (cached)."""
    global _tile_sheet
    if _tile_sheet is None:
        with open(data_path("ularn_gfx.png"), "rb") as f:
            _tile_sheet = f.read()
    return _tile_sheet


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # A browser closing a connection early is normal; stay quiet.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class Spectator:
    def __init__(self, host="127.0.0.1", port=8765, history=1500, on_keys=None,
                 title="live"):
        self.on_keys = on_keys
        self.title = title
        self.frames = collections.deque(maxlen=history)
        self.last_frame = None   # the newest screen frame (not a thought)
        self.thoughts = collections.deque(maxlen=200)
        self.seq = 0
        # Tells a page that reconnects whether it found the same server (and
        # can skip what it has seen) or a new one (the next agent's run).
        self.instance = uuid.uuid4().hex[:12]
        self.cond = threading.Condition()
        self.closed = False
        spectator = self

        class Handler(SpectatorHandler):
            owner = spectator

        self.httpd = _Server((host, port), Handler)
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
            data = json.dumps(frame, separators=(",", ":"))
            self.frames.append(data)
            if frame.get("type") == "thought":
                self.thoughts.append((frame.get("game"), data))
            else:
                self.last_frame = data
            self.cond.notify_all()

    def latest(self):
        with self.cond:
            return self.last_frame

    def backlog(self):
        """What a newly connected page needs: the current game's recent
        thoughts and the latest screen, and the sequence number they reach."""
        with self.cond:
            game = json.loads(self.last_frame)["game"] if self.last_frame else None
            if self.thoughts and (game is None or self.thoughts[-1][0] > game):
                game = self.thoughts[-1][0]  # a new game's thought, before its screen
            out = [d for g, d in self.thoughts if g == game]
            if self.last_frame:
                out.append(self.last_frame)
            return out, self.seq

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
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            page = PAGE.replace("__CONFIG__", json.dumps({
                "play": self.owner.on_keys is not None, "title": self.owner.title}))
            self._send(200, "text/html; charset=utf-8", page)
        elif path == "/ularn_gfx.png":
            try:
                self._send(200, "image/png", tile_sheet())
            except OSError:
                self._send(404, "text/plain", "tile sheet missing")
        elif path == "/frame":
            self._send(200, "application/json", self.owner.latest() or "null")
        elif path == "/events":
            self.events()
        else:
            self._send(404, "text/plain", "not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/keys" or self.owner.on_keys is None:
            self._send(404, "text/plain", "not found")
            return
        # Only the page itself may type: a JSON content type cannot be sent
        # cross-site without a CORS preflight (which is never answered), and
        # a browser's Origin, when given, must be this server.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        if ctype != "application/json" or (
                origin and origin.split("://", 1)[-1] != host):
            self._send(403, "text/plain", "forbidden")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
            keys = body.get("keys", [])
            if not isinstance(keys, list) or len(keys) > 256:
                raise ValueError
            keys = [k for k in keys if isinstance(k, str)
                    and (len(k) == 1 or k in SPECIAL_KEYS)]
        except (ValueError, AttributeError):
            self._send(400, "text/plain", "bad request")
            return
        if keys:
            self.owner.on_keys(keys)
        self._send(200, "application/json", "{}")

    def events(self):
        sp = self.owner
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            backlog, seq = sp.backlog()
            hello = json.dumps({"type": "hello", "server": sp.instance})
            self.wfile.write(b"retry: 2000\n\ndata: " + hello.encode() + b"\n\n")
            for f in backlog:
                self.wfile.write(b"data: " + f.encode() + b"\n\n")
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


def start(port, host="127.0.0.1", on_keys=None, title="live"):
    """Start a spectator, or return None (with a message on stderr) on error."""
    try:
        sp = Spectator(host, port, on_keys=on_keys, title=title)
    except OSError as e:
        sys.stderr.write("pyularn: spectator disabled, cannot listen on %s:%s (%s)\n"
                         % (host, port, e))
        return None
    sys.stderr.write("pyularn: %s the game at %s\n"
                     % ("play" if on_keys else "watch", sp.url))
    return sp


def now_ms():
    return int(time.time() * 1000)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ularn</title>
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
.controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.controls label { color: var(--muted); }
select, button { background: var(--panel); color: var(--text);
  border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; font: inherit; cursor: pointer; }
button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.seg { display: inline-flex; }
.seg button { border-radius: 0; }
.seg button:first-child { border-radius: 6px 0 0 6px; }
.seg button:last-child { border-radius: 0 6px 6px 0; border-left: 0; }
main { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px;
  padding: 16px; align-items: start; max-width: 1640px; margin: 0 auto; }
.game { background: #000; border: 1px solid var(--line); border-radius: 8px;
  padding: 12px; min-width: 0; }
#mapwrap { width: 100%; display: none; justify-content: center; margin-bottom: 10px; }
#mapwrap.on { display: flex; }
#map { display: block; image-rendering: pixelated; background: #000; }
.term-scroll { overflow-x: auto; }
#term { margin: 0; font: 15px/1.25 ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace;
  white-space: pre; color: #e5e7eb; }
#term .b { font-weight: 700; }
#term .r { background: currentColor; }
#term .r > i { color: #000; font-style: normal; }
#term .u { text-decoration: underline; }
.left { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
#thoughts { display: flex; flex-direction: column; height: 220px; padding: 0; }
body.play #thoughts { display: none; }
#thoughts h2 { margin: 0; padding: 10px 12px; border-bottom: 1px solid var(--line);
  display: flex; align-items: center; gap: 8px; }
#thoughts h2 .count { font-weight: 400; text-transform: none; letter-spacing: 0; }
#roll { flex: 1; overflow-y: auto; padding: 8px 12px; }
.th { padding: 4px 0 4px 10px; border-left: 2px solid var(--line); margin: 0 0 8px; }
.th:last-child { border-left-color: var(--accent); }
.th p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.th .meta { font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.th .meta code { font: 12px ui-monospace, Consolas, monospace; color: var(--text); }
.th.new { animation: thin .35s ease-out; }
@keyframes thin { from { opacity: 0; transform: translateY(6px); } }
.divider { text-align: center; font-size: 12px; color: var(--muted); margin: 8px 0; }
#roll .empty { padding: 4px 0; }
#roll code { font: 12px ui-monospace, Consolas, monospace; }
#jump { display: none; margin-left: auto; font-size: 12px; padding: 1px 8px;
  text-transform: none; letter-spacing: 0; }
#jump.on { display: inline-block; }
@media (prefers-reduced-motion: reduce) { .th.new { animation: none; } }
#hint { margin: 10px 0 0; color: var(--muted); font-size: 12px; display: none; }
body.play #hint { display: block; }
body.play .watch-only { display: none; }
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
  <h1><span>ULARN</span> <span id="title" style="color:inherit"></span></h1>
  <span id="conn" class="pill">connecting</span>
  <span id="where" class="pill">-</span>
  <div class="spacer"></div>
  <div class="controls">
    <span class="seg" role="group" aria-label="View">
      <button id="v-tiles" aria-pressed="true">Tiles</button><button id="v-text" aria-pressed="false">Text</button>
    </span>
    <label for="zoom">Zoom</label>
    <select id="zoom">
      <option value="auto" selected>Auto</option>
      <option value="fit">Fit width</option>
      <option value="32">32 px</option>
      <option value="48">48 px</option>
    </select>
    <label for="speed" class="watch-only">Playback</label>
    <select id="speed" class="watch-only">
      <option value="0">Live</option>
      <option value="100" selected>Smooth (10/s)</option>
      <option value="250">Slow (4/s)</option>
    </select>
    <button id="pause" class="watch-only" aria-pressed="false">Pause</button>
  </div>
</header>
<main>
  <div class="left">
  <div class="game">
    <div id="mapwrap"><canvas id="map" width="0" height="0"></canvas></div>
    <div class="term-scroll"><pre id="term">Waiting for a game to start...</pre></div>
    <p id="hint">Your keyboard goes to the game: letters as in the terminal version, arrow keys and
      Home/PgUp/End/PgDn to move, Enter, Esc, Backspace, Ctrl+letter. Press ? in the game for help.</p>
  </div>
  <section id="thoughts" class="card" aria-label="Agent thoughts">
    <h2>Agent thoughts <span class="count" id="tcount"></span>
      <button id="jump" type="button">Latest &darr;</button></h2>
    <div id="roll" aria-live="polite"><div class="empty">No thoughts yet. The agent can narrate by
      passing <code>thought</code> with its moves.</div></div>
  </section>
  </div>
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
const CONFIG = __CONFIG__;
const $ = id => document.getElementById(id);
const queue = [];
let paused = false, lastGame = null, keys = [], timer = null, current = null, over = false;
const MAP_ROWS = 17;   // the map window is the top 17 lines of the screen

function load(k, d) { try { return localStorage.getItem("ularn." + k) || d; } catch (e) { return d; } }
function save(k, v) { try { localStorage.setItem("ularn." + k, v); } catch (e) {} }
let view = load("view", "tiles");
$("zoom").value = load("zoom", "auto");

document.title = CONFIG.play ? "Ularn" : "Ularn live";
$("title").textContent = CONFIG.play ? "" : "live";
if (CONFIG.play) { document.body.classList.add("play"); $("speed").value = "0"; }

const sheet = new Image();
sheet.onload = () => { if (current) render(current, true); };
sheet.src = "ularn_gfx.png";

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

function tileSize(m, width) {
  const fit = width / m.w, z = $("zoom").value;
  if (z === "fit") return fit;
  if (z === "auto") return fit >= 20 ? Math.min(fit, 48) : 32;
  return +z;
}

// Draw the map as sprites.  When it does not fit, show a window centred on
// the player, as the X11 version scrolls its map.
function drawMap(m) {
  const wrap = $("mapwrap"), cv = $("map");
  const ts = tileSize(m, wrap.clientWidth);
  const cols = Math.max(1, Math.min(m.w, Math.floor(wrap.clientWidth / ts + 1e-6)));
  const th = $("thoughts");
  const below = th.offsetParent ? th.offsetHeight + 16 : 0;
  const maxH = Math.max(8 * ts, window.innerHeight - 330 - below);
  const rows = Math.max(1, Math.min(m.h, Math.floor(maxH / ts)));
  const [px, py] = m.player;
  const left = Math.max(0, Math.min(m.w - cols, px - Math.floor(cols / 2)));
  const top = Math.max(0, Math.min(m.h - rows, py - Math.floor(rows / 2)));
  const dpr = window.devicePixelRatio || 1;
  const W = Math.round(cols * ts * dpr), H = Math.round(rows * ts * dpr);
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  cv.style.width = (cols * ts) + "px"; cv.style.height = (rows * ts) + "px";
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
  if (!sheet.complete || !sheet.naturalWidth) return;
  const edge = i => Math.round(i * ts * dpr);
  const put = (tile, sx, sy) => {
    const x0 = edge(sx), y0 = edge(sy);
    ctx.drawImage(sheet, (tile % 16) * 32, Math.floor(tile / 16) * 32, 32, 32,
                  x0, y0, edge(sx + 1) - x0, edge(sy + 1) - y0);
  };
  for (let y = 0; y < rows; y++)
    for (let x = 0; x < cols; x++)
      put(m.tiles[(top + y) * m.w + left + x], x, y);
  if (px >= left && px < left + cols && py >= top && py < top + rows)
    put(m.cursor, px - left, py - top);
}

function list(el, items, empty) {
  el.innerHTML = items && items.length
    ? items.map(i => `<li>${esc(i)}</li>`).join("")
    : `<li class="empty">${empty}</li>`;
}

function render(f, redraw) {
  current = f;
  if (!redraw) {
    if (f.game !== lastGame) { keys = []; lastGame = f.game; }
    if (f.key) { keys.push(f.key); if (keys.length > 24) keys.shift(); }
  }
  const tiles = view === "tiles" && f.map;
  $("mapwrap").classList.toggle("on", !!tiles);
  if (tiles) { drawMap(f.map); drawScreen(f.rows.slice(MAP_ROWS)); }
  else drawScreen(f.rows);
  over = f.status === "game over";
  $("conn").textContent = over ? "game over" : (CONFIG.play ? "playing" : "live");
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

// ---- the agent's thoughts, in step with playback
// The roll follows the newest thought unless the viewer scrolls up.
let thoughtGame = null, nThoughts = 0, stuck = true;
const roll = $("roll");
function nearBottom() { return roll.scrollHeight - roll.scrollTop - roll.clientHeight < 40; }
function addThought(m) {
  if (!nThoughts) roll.innerHTML = "";
  if (thoughtGame !== null && m.game !== thoughtGame) {
    const d = document.createElement("div");
    d.className = "divider"; d.textContent = "new game";
    roll.appendChild(d);
  }
  thoughtGame = m.game;
  const el = document.createElement("div");
  el.className = "th new";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = "turn " + (m.turn || 0) + (m.action ? " \u00b7 " : "");
  if (m.action) { const c = document.createElement("code"); c.textContent = m.action; meta.appendChild(c); }
  const p = document.createElement("p");
  p.textContent = m.text;
  el.append(meta, p);
  roll.appendChild(el);
  while (roll.children.length > 200) roll.removeChild(roll.firstChild);
  nThoughts++;
  $("tcount").textContent = "\u00b7 " + nThoughts;
  if (stuck) roll.scrollTop = roll.scrollHeight;
}
roll.addEventListener("scroll", () => {
  stuck = nearBottom();
  $("jump").classList.toggle("on", !stuck);
});
$("jump").onclick = e => { stuck = true; roll.scrollTop = roll.scrollHeight; e.currentTarget.blur(); };

function passOver(f) {  // a frame skipped while catching up: keep its key
  if (f.game !== lastGame) { keys = []; lastGame = f.game; }
  if (f.key) keys.push(f.key);
}

function tick() {
  timer = null;
  if (paused || !queue.length) return;
  const delay = +$("speed").value;
  // Live mode, or far behind: jump to the newest frame (keeping the keys).
  const jump = delay === 0 || queue.length > 300;
  let f = null;
  while (queue.length) {
    const m = queue.shift();
    if (m.type === "thought") { addThought(m); continue; }
    if (f) passOver(f);
    f = m;
    if (!jump) break;
  }
  if (f) { render(f); keys = keys.slice(-24); }
  if (queue.length) timer = setTimeout(tick, delay);
}
function kick() { if (!timer) timer = setTimeout(tick, 0); }

function setView(v) {
  view = v; save("view", v);
  $("v-tiles").setAttribute("aria-pressed", v === "tiles");
  $("v-text").setAttribute("aria-pressed", v === "text");
  if (current) render(current, true);
}
setView(view);
$("v-tiles").onclick = e => { setView("tiles"); e.currentTarget.blur(); };
$("v-text").onclick = e => { setView("text"); e.currentTarget.blur(); };
$("zoom").onchange = e => { save("zoom", e.target.value); e.target.blur(); if (current) render(current, true); };
window.addEventListener("resize", () => { if (current) render(current, true); });

$("pause").onclick = e => {
  paused = !paused;
  $("pause").setAttribute("aria-pressed", paused);
  $("pause").textContent = paused ? "Resume" : "Pause";
  e.currentTarget.blur();
  if (!paused) kick();
};
$("speed").onchange = e => { e.target.blur(); kick(); };

// ---- playing: send the keyboard to the game
if (CONFIG.play) {
  const NAMED = {
    ArrowUp: "KEY_UP", ArrowDown: "KEY_DOWN", ArrowLeft: "KEY_LEFT", ArrowRight: "KEY_RIGHT",
    Home: "KEY_A1", PageUp: "KEY_A3", End: "KEY_C1", PageDown: "KEY_C3", Clear: "KEY_B2",
    Enter: "\r", Escape: "\x1b", Backspace: "\x08", Tab: "\t",
  };
  let pending = [], sending = false;
  function flush() {
    if (sending || !pending.length) return;
    sending = true;
    const batch = pending; pending = [];
    fetch("keys", { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ keys: batch }) })
      .catch(() => {})
      .finally(() => { sending = false; flush(); });
  }
  document.addEventListener("keydown", e => {
    if (e.metaKey || e.altKey || e.isComposing) return;
    if (e.target.tagName === "SELECT") return;
    let k = null;
    if (e.ctrlKey) {
      if (/^[a-z]$/i.test(e.key)) k = String.fromCharCode(e.key.toUpperCase().charCodeAt(0) - 64);
    } else if (NAMED[e.key]) k = NAMED[e.key];
    else if (e.key.length === 1) k = e.key;
    if (k === null) return;
    e.preventDefault();
    if (over) return;
    pending.push(k); flush();
  });
}

// The page outlives any one server: agents run back to back, each bringing
// up its own server on this port.  Keep reconnecting, and when a different
// server answers, start over for its run.
let server = null, lastSeq = 0;
function newRun() {
  queue.length = 0; lastSeq = 0; keys = []; lastGame = null; over = false;
  if (nThoughts) {
    const d = document.createElement("div");
    d.className = "divider"; d.textContent = "new run";
    roll.appendChild(d);
    if (stuck) roll.scrollTop = roll.scrollHeight;
  }
  thoughtGame = null;
}
function connect() {
  const es = new EventSource("events");
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === "hello") {
      if (server !== null && m.server !== server) newRun();
      server = m.server;
      return;
    }
    if (m.seq <= lastSeq) return;  // the backlog again, after a reconnect
    lastSeq = m.seq;
    queue.push(m); kick();
  };
  es.onerror = () => {
    $("conn").textContent = over ? "game over · waiting for the next run" : "reconnecting";
    $("conn").className = "pill" + (over ? " over" : "");
    if (es.readyState === EventSource.CLOSED) setTimeout(connect, 2000);
  };
}
connect();
</script>
</body>
</html>
"""
