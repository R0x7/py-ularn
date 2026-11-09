# History and copyright

py-ularn is a Python port of Julian Olds' Ularn 1.6.3a, translated from
the C source kept in [R0x7/ularn-1.6.3a](https://github.com/R0x7/ularn-1.6.3a).
The game itself is the work of the people below; this repository adds the
Python translation, the web front end and the MCP server.

## Where the game comes from

This history follows Derek Newhall's
[The History of Larn and Ularn](https://larn.org/history/history) on larn.org.
Only the line that leads to this code is given here. See that page for the
whole family tree, the other ports and the Larn-likes, and for what is still
unknown. Corrections are welcome there.

### Larn

| Version | Date | By | Notes |
|---|---|---|---|
| Larn 11.0 | 1986 (June?) | Noah Morgan | The earliest version on public record. It was released, but no copy is known to survive. |
| Larn 12.0 | 8 Aug 1986 | Noah Morgan, with James D. McNamara | Posted to Usenet. The root of every later Larn and Ularn, and Morgan's last version. McNamara handled distribution and patches. |

### Ularn

| Version | Date | By | Notes |
|---|---|---|---|
| Ularn (Ultra-Larn) | 1987, posted to Usenet 1989 | Phil Cordier | Based on Larn 12.0. Added character classes, more demon lords, dungeon levels 10–15, volcano levels 3–5, artifacts and drugs. Patch 1 fixed bugs; Scott S. Snyder's patch 2 added MS-DOS support. |
| Ularn 2.0 | 1992 | Phil Cordier | Cordier's last version ("The Addiction of Ularn"). He worked on it until 1997, then passed it on. |
| Ularn 1.5 | 2000–2001 | David Richerby, Josh Brandt | Based on Cordier's code. Added the Vorpal Blade and removed the door traps that drained a level. 1.5.1 by Richerby; 1.5.2 to 1.5.4 by Brandt (1.5.4 added Cygwin support). Josh Bressers took over as maintainer in 2005 ([ularn/ularn](https://github.com/ularn/ularn)). |
| **Ularn 1.6** | 2003–2004 | **Julian Olds** | Based on 1.5.4, rewritten almost throughout, with a tiled graphical display. Added the amulet of life preservation. 1.6.1: Windows, with the "enhanced interface"; 1.6.2: X11; 1.6.3: better tiles, the TTY and Amiga versions; **1.6.3a** (3 May 2004): a Windows-only fix. |
| Web Ularn 1.6.3a | 2014 | David Peng | 1.6.3a compiled to JavaScript with Emscripten for the browser ([davidpeng/ularn](https://github.com/davidpeng/ularn)). |

Other people named in the 1.6 sources: Craig Spencer drew new tiles for
1.6.3, and the Debian packaging of 1.6.3a (2009) is by kitchen666.

## Copyright

**This repository does not claim copyright in Larn or Ularn.** The game
belongs to its authors: Noah Morgan (Larn), Phil Cordier (Ularn), David
Richerby, Josh Brandt and Josh Bressers (Ularn 1.5), Julian Olds (Ularn 1.6)
and the others named above. Only the new work in this repository (its own
code, tools and documentation) is by the repository's contributors.

**The license is not clear-cut.** Larn 12.0 was released by Noah Morgan with
permission to use, change and port the sources, on the condition that no one
makes a profit from Larn, its sources or that work without his permission.
As larn.org explains, every version that comes from Larn's code, Ularn
included, is still bound by that condition. Julian Olds released Ularn 1.6
under the GNU GPL (see `COPYRIGHT`), but larn.org notes that the
Free Software Foundation does not accept a no-profit condition as compatible
with the GPL, so the GPL notice may not be enough on its own.

So this project is shared **for free and non-commercially only**, in keeping
with Noah Morgan's terms. Do not sell it or make money from it. The GPL text
is included because the 1.6 sources carry it, not as a claim that the whole
game is free software. This note is not legal advice. If you are the holder
of any of these rights and want something changed or removed, please open an
issue.
