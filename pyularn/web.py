"""Play in a web browser with the original sprite graphics.

    pyularn --web [PORT]            # default port 8765, opens the browser
    pyularn --web 0 --no-browser    # any free port, print the address only
    pyularn --web --web-host 0.0.0.0 -d 3

The game runs exactly as in the terminal, on an in-memory terminal; the page
(the same one used to watch an MCP game) draws the map with the X11 tile
sheet and sends your keyboard to the game.  Other options are the usual
Ularn options.  The program ends when the game does.
"""

import sys
import time

from . import spectator

DEFAULT_PORT = 8765


def split_args(argv):
    """Pull the web options out of `argv`.

    Returns (options, rest) where options is None if --web is not given,
    else {"port", "host", "browser"}; rest is argv without them.
    """
    opts = {"port": DEFAULT_PORT, "host": "127.0.0.1", "browser": True}
    web = False
    rest = [argv[0]] if argv else ["ularn"]
    args = list(argv[1:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--web" or a.startswith("--web="):
            web = True
            if "=" in a:
                opts["port"] = int(a.split("=", 1)[1])
            elif i + 1 < len(args) and args[i + 1].isdigit():
                i += 1
                opts["port"] = int(args[i])
        elif a == "--web-host" and i + 1 < len(args):
            i += 1
            opts["host"] = args[i]
        elif a.startswith("--web-host="):
            opts["host"] = a.split("=", 1)[1]
        elif a == "--no-browser":
            opts["browser"] = False
        else:
            rest.append(a)
        i += 1
    return (opts if web else None), rest


def run(argv, port=DEFAULT_PORT, host="127.0.0.1", browser=True):
    """Serve the game on http://host:port/ and play it there.  Returns the
    game's exit code."""
    from .mcp_server import GameSession

    session = GameSession()

    def on_keys(keys):
        term = session.term
        if term is not None and not term.finished:
            term.feed(keys)

    sp = spectator.start(port, host, on_keys=on_keys, title="")
    if sp is None:
        return 1
    session.spectator = sp
    if browser:
        try:
            import webbrowser
            webbrowser.open(sp.url)
        except Exception:
            pass
    sys.stderr.write("pyularn: press Ctrl+C here to quit\n")

    code = 0
    try:
        session.start(argv=argv)
        while session.running:
            session.thread.join(0.5)
        code = session.exit_code or 0
        time.sleep(1.5)  # let the page show the final screen
    except KeyboardInterrupt:
        session.stop()
        code = 1
    finally:
        if session.error:
            sys.stderr.write(session.error)
            code = 1
        sp.close()
    return code
