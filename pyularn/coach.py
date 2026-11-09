"""Run a learning campaign: one agent session per game, again and again.

    pyularn-coach --dir runs --cycles 5

Each cycle starts a fresh agent with the same short instruction: read the
briefing, play one game, write the post-mortem, record what was learned.
Everything the agent needs to do better than the last game is in the
campaign folder (see `pyularn.learn` and `pyularn.runs`), not in the
agent's memory, so cycles can be run days apart, or by different agents.

The agent is any command that can use an MCP server.  The default is
Claude Code in headless mode::

    claude -p PROMPT --mcp-config DIR/agent-mcp.json --strict-mcp-config
           --allowedTools mcp__pyularn

Use ``--agent-cmd`` for another one; ``{prompt}`` and ``{mcp_config}`` in
it are replaced.  The coach itself makes no decisions about the game: it
starts agents, checks that each left a finished, written-up run behind,
and stops when asked to, when the game is won, or when agents keep failing.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time

from . import learn, runs

PROMPT = """\
You are playing the roguelike Ularn through the pyularn MCP tools, as one \
cycle of a learning campaign in which each game builds on the ones before.

Call get_briefing first and do exactly the cycle it sets out: start one \
game under the strategy it names, play until that game is over, then \
write the post-mortem with summarize_run and record what you learned.

Play one game only. Do not ask questions: nobody is there to answer. \
Narrate with the `thought` argument as you go. When the cycle is done, \
reply with two or three sentences on how the game went."""

DEFAULT_AGENT = ("claude -p {prompt} --mcp-config {mcp_config} --strict-mcp-config "
                 "--allowedTools mcp__pyularn")


def write_mcp_config(root, watch=None):
    """The MCP config handed to the agent: this package's server, recording
    into the campaign folder, with a scoreboard of its own.  The scoreboard
    decides the difficulty after a win, so campaigns must not share one."""
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = ["-m", "pyularn.mcp_server", "--record", root]
    if watch is not None:
        args += ["--watch", str(watch)]
    env = {"PYULARN_HOME": os.path.join(root, "home"),
           "PYTHONPATH": os.pathsep.join(p for p in (package_parent, os.environ.get("PYTHONPATH")) if p)}
    config = {"mcpServers": {"pyularn": {"type": "stdio", "command": sys.executable,
                                         "args": args, "env": env}}}
    path = os.path.join(root, "agent-mcp.json")
    runs._write_text(path, json.dumps(config, indent=1) + "\n")
    return path


def agent_command(template, prompt, mcp_config, extra=()):
    words = [w.replace("{prompt}", prompt).replace("{mcp_config}", mcp_config)
             for w in shlex.split(template)]
    return words + list(extra)


def run_cycle(root, number, command, timeout, out=sys.stdout):
    """Start one agent and wait for it.  Returns the finished runs it left
    (newest first) and whether the agent itself exited cleanly."""
    before = {m["run_id"] for m in runs.list_runs(root)}
    log_dir = os.path.join(root, "coach-logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "cycle-%03d.log" % number)
    started = time.time()
    ok = True
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            code = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=timeout).returncode
            if code != 0:
                ok = False
                out.write("  the agent exited with code %d (see %s)\n" % (code, log_path))
        except subprocess.TimeoutExpired:
            ok = False
            out.write("  the agent was stopped after %d seconds\n" % timeout)
        except OSError as e:
            ok = False
            out.write("  could not start the agent: %s\n" % e)
    new = [m for m in runs.list_runs(root) if m["run_id"] not in before]
    out.write("  %d game%s in %.0f seconds\n" % (
        len(new), "" if len(new) == 1 else "s", time.time() - started))
    return new, ok


def describe(meta):
    prog = meta.get("progress") or learn.progress(meta.get("outcome"))
    text = "%s [%s] %s; got to: %s" % (meta["run_id"], meta.get("strategy") or "no strategy",
                                        runs.headline(meta), prog["milestone"])
    if not meta.get("notes"):
        text += " (no post-mortem written)"
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pyularn-coach",
        description="Run a learning campaign: one agent session per game of Ularn.")
    ap.add_argument("--dir", default=os.environ.get("PYULARN_RECORD") or "runs",
                    help="the campaign folder (default: $PYULARN_RECORD, else ./runs)")
    ap.add_argument("--cycles", type=int, default=1, help="games to play (default 1)")
    ap.add_argument("--difficulty", type=int, default=None,
                    help="difficulty of a NEW campaign (default 0); an existing one keeps its own")
    ap.add_argument("--agent-cmd", default=os.environ.get("PYULARN_AGENT_CMD") or DEFAULT_AGENT,
                    help="the agent command; {prompt} and {mcp_config} are replaced "
                         "(default: Claude Code in headless mode)")
    ap.add_argument("--model", help="passed to the agent as --model")
    ap.add_argument("--max-budget-usd", type=float,
                    help="passed to the agent as --max-budget-usd, a spending cap per game")
    ap.add_argument("--timeout", type=int, default=3600,
                    help="seconds before a game's agent is stopped (default 3600)")
    ap.add_argument("--watch", type=int, metavar="PORT",
                    help="have the agent's game server show the live page on PORT")
    ap.add_argument("--status", action="store_true",
                    help="print the campaign (playbook and strategies) and exit")
    ap.add_argument("--print-command", action="store_true",
                    help="print the agent command that would be run, and exit")
    args = ap.parse_args(argv)
    out = sys.stdout
    root = os.path.abspath(os.path.expanduser(args.dir))

    if args.status:
        if not learn.exists(root):
            out.write("No campaign in %s yet.\n" % root)
            return 1
        out.write(learn.render(root))
        return 0

    if args.cycles < 1:
        ap.error("--cycles must be at least 1")
    if args.difficulty is not None and not 0 <= args.difficulty <= 100:
        ap.error("--difficulty is 0 to 100")
    new_campaign = not learn.exists(root)
    campaign = learn.load(root, difficulty=args.difficulty or 0)
    if not new_campaign and args.difficulty not in (None, campaign["difficulty"]):
        ap.error("this campaign is at difficulty %d; start another folder for difficulty %d"
                 % (campaign["difficulty"], args.difficulty))

    extra = []
    if args.model:
        extra += ["--model", args.model]
    if args.max_budget_usd is not None:
        extra += ["--max-budget-usd", str(args.max_budget_usd)]
    command = agent_command(args.agent_cmd, PROMPT, write_mcp_config(root, args.watch), extra)
    if args.print_command:
        out.write(" ".join(shlex.quote(w) for w in command) + "\n")
        return 0

    out.write("%s campaign in %s, difficulty %d\n" % (
        "New" if new_campaign else "Continuing the", root, campaign["difficulty"]))
    failures = 0
    for number in range(1, args.cycles + 1):
        campaign = learn.load(root)
        sid = learn.choose_next(campaign, learn.stats(campaign, runs.list_runs(root)))
        out.write("Cycle %d of %d: strategy %s %s\n" % (
            number, args.cycles, sid, campaign["strategies"][sid]["title"]))
        out.flush()
        new, ok = run_cycle(root, number, command, args.timeout, out)
        for meta in new:
            out.write("  " + describe(meta) + "\n")
        finished = [m for m in new if (m.get("outcome") or {}).get("result") in learn.COUNTED]
        if any((m.get("outcome") or {}).get("won") for m in new):
            out.write("The game was won at difficulty %d.\n" % campaign["difficulty"])
            break
        if finished and ok:
            failures = 0
        else:
            failures += 1
            if not finished:
                out.write("  no game was played to its end this cycle\n")
            if failures >= 2:
                out.write("Stopping: two cycles in a row went wrong.\n")
                return 1
        out.flush()
    out.write("Done. See %s\n" % os.path.join(root, "CAMPAIGN.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
