"""Utilities used in loading and saving games (port of saveutils.c / saveutils.h).

Exported variables:
  FileSum : The current checksum for the file being written/read.

Exported functions:
  sum    : Checksum calculation function
  bwrite : Binary write with checksum update
  bread  : Binary read with checksum update.

Python port: files are opened in binary mode and the buffers are ``bytes``.
"""

from .header import *
from . import ularn_win, scores

# =============================================================================
# Local variables

# The number of characters written
w = 0

# The number of characters read
r = 0

# static call counters of bwrite / bread
_bwrite_ncalls = 0
_bread_ncalls = 0

# =============================================================================
# Exported variables

FileSum = 0


# =============================================================================
# Exported functions

def sum(data, n=None):
    """Checksum of the first n bytes of data (16 bit rotating sum)."""
    if n is None:
        n = len(data)
    s = 0
    nb = 0
    while nb < n:
        ch = data[nb]
        nb += 1
        if s & 0o1:
            s = (s >> 1) + 0x8000
        else:
            s >>= 1
        s += ch
        s &= 0xFFFF
    return s


def bwrite(fp, buf, num=None):
    """Binary write of buf (bytes) to fp with FileSum update."""
    global w, _bwrite_ncalls, FileSum

    if num is None:
        num = len(buf)
    buf = bytes(buf[:num])

    _bwrite_ncalls += 1
    try:
        nwrote = fp.write(buf)
        if nwrote is None:
            nwrote = len(buf)
    except OSError:
        nwrote = 0

    w += nwrote

    if nwrote != num:
        ularn_win.Printf("Error writing to save file\n")
        ularn_win.Printf("wrote %d, wanted %d\n", nwrote, num)
        ularn_win.Printf("    Wrote %d bytes so far\n", w)
        ularn_win.Printf("        Call: %d\n", _bwrite_ncalls)

        ularn_win.nap(4000)
        scores.died(scores.DIED_POST_MORTEM_DEATH, 0)

    FileSum += sum(buf, num)


def bread(fp, num):
    """Binary read of num bytes from fp with FileSum update.

    New signature: returns the bytes read (C filled a buffer).
    """
    global r, _bread_ncalls, FileSum

    _bread_ncalls += 1
    try:
        buf = fp.read(num)
    except OSError:
        buf = b""
    nread = len(buf)

    r += nread

    if nread != num:
        ularn_win.Printf("Error reading from save file\n")
        ularn_win.Printf("  Got %d, wanted %d bytes\n", nread, num)
        ularn_win.Printf("    Read %d bytes so far\n", w)
        ularn_win.Printf("        Call: %d\n", _bread_ncalls)

        ularn_win.nap(4000)
        scores.died(scores.DIED_POST_MORTEM_DEATH, 0)

    FileSum += sum(buf, nread)
    return buf
