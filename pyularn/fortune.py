"""Fortune cookie messages (port of fortune.c / fortune.h).

EXPORTED FUNCTIONS
  fortune       - Returns a random fortune string.
  free_fortunes - Frees the fortunes data.
"""

from .header import *

# =============================================================================
# Local variables

MAX_FORTUNE_LEN = 80

# The C code keeps a linked list where each new line is pushed on the front.
# ``fortunes`` keeps the same order: fortunes[0] is the head of that list
# (i.e. the LAST line read from the file).
fortunes = []
fortune_read = 0   # true if we have loaded the fortune info
nlines = 0         # number of lines in fortune database


def _fgets(fp, n):
    """Emulate C fgets(buf, n, fp): read at most n-1 chars up to newline.

    Returns None at end of file.
    """
    s = fp.readline(n - 1)
    if s == "":
        return None
    return s


def fortune(file=None):
    """Return a random fortune from the fortune file, or None.

    On the first call the fortune file is read and the fortunes stored in
    memory.  ``file`` defaults to data_path("Ufortune") when empty/None.
    """
    global fortune_read, nlines

    if fortune_read == 0:
        if not file:
            file = data_path("Ufortune")
        # open the file
        try:
            fp = open(file, "r", encoding="latin-1")
        except OSError:
            # can't find file
            return None

        with fp:
            # Read the fortune lines from the file
            while True:
                Line = _fgets(fp, MAX_FORTUNE_LEN)
                if Line is None:
                    break
                # trim white space and CR/LF from the end of the line
                Buffer = list(Line)
                Len = len(Buffer) - 1
                while (Len > 0) and Buffer[Len].isspace():
                    del Buffer[Len]
                    Len -= 1

                # Allocate a new fortune (pushed on the front of the list)
                fortunes.insert(0, "".join(Buffer))
                nlines += 1

        fortune_read = 1

    if fortune_read:
        if nlines > 0:
            Pos = rund(nlines)
            if Pos >= len(fortunes):
                # C would dereference a freed/NULL list here (after
                # free_fortunes); return no fortune instead of crashing.
                return None
            return fortunes[Pos]
        return None
    return None


def free_fortunes():
    """Deallocate any memory allocated by fortune()."""
    # C only frees the list; fortune_read and nlines are left unchanged.
    del fortunes[:]
