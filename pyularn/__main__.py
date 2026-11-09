"""Entry point: ``python -m pyularn [options]`` runs Ularn in curses.

``--web [PORT]`` plays it in a web browser with sprite graphics instead
(see pyularn.web).
"""

import sys

from . import ularn


def main():
    from . import web

    opts, argv = web.split_args(sys.argv)
    if opts is not None:
        return web.run(argv, **opts)
    return ularn.main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
