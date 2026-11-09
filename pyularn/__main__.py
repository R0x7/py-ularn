"""Entry point: ``python -m pyularn [options]`` runs Ularn in curses."""

import sys

from . import ularn


def main():
    return ularn.main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
