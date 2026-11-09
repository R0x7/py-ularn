"""Convert the original Ularn tile sheet (ularn_gfx.xpm) to pyularn/data/ularn_gfx.png.

    python tools/make_tiles.py path/to/ularn-1.6.3a/data/ularn_gfx.xpm

The sheet is 16 tiles across, 32x32 pixels each.  The PNG is RGBA so the
browser can draw overlay tiles on top of the map.  The X11 front end builds
masks at start-up (MakeTileMasks in ularn_winx11.c): for each pair of tiles
below, a pixel is transparent where the two tiles differ.  The same masks
are baked into the PNG's alpha channel here.  Standard library only.
"""

import re
import struct
import sys
import zlib

TILE = 32
TILE_CURSOR1, TILE_CURSOR2 = 174, 190
MASK_TILES = [(240 + i, 248 + i) for i in range(8)] + [(TILE_CURSOR1, TILE_CURSOR2)]


def read_xpm(path):
    with open(path, encoding="latin-1") as f:
        strings = re.findall(r'"((?:[^"\\]|\\.)*)"', f.read())
    w, h, ncolors, cpp = (int(v) for v in strings[0].split()[:4])
    colors = {}
    for line in strings[1:1 + ncolors]:
        key, rest = line[:cpp], line[cpp:].split()
        value = rest[rest.index("c") + 1] if "c" in rest else rest[-1]
        if value.lower() == "none":
            colors[key] = (0, 0, 0, 0)
        elif value.startswith("#") and len(value) == 7:
            colors[key] = (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), 255)
        elif value.startswith("#") and len(value) == 13:  # #RRRRGGGGBBBB
            colors[key] = (int(value[1:3], 16), int(value[5:7], 16), int(value[9:11], 16), 255)
        else:
            raise ValueError("unsupported XPM colour %r" % value)
    rows = []
    for line in strings[1 + ncolors:1 + ncolors + h]:
        rows.append([list(colors[line[i:i + cpp]]) for i in range(0, w * cpp, cpp)])
    return w, h, rows


def apply_masks(rows):
    for t1, t2 in MASK_TILES:
        x1, y1 = (t1 % 16) * TILE, (t1 // 16) * TILE
        x2, y2 = (t2 % 16) * TILE, (t2 // 16) * TILE
        for dy in range(TILE):
            for dx in range(TILE):
                if rows[y1 + dy][x1 + dx] != rows[y2 + dy][x2 + dx]:
                    rows[y1 + dy][x1 + dx][3] = 0


def write_png(path, w, h, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for px in row:
            raw.extend(px)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def main(argv):
    if len(argv) not in (2, 3):
        sys.stderr.write(__doc__)
        return 2
    out = argv[2] if len(argv) == 3 else "pyularn/data/ularn_gfx.png"
    w, h, rows = read_xpm(argv[1])
    apply_masks(rows)
    write_png(out, w, h, rows)
    print("%s: %dx%d, %d tiles" % (out, w, h, (w // TILE) * (h // TILE)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
