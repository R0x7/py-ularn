# Porting conventions (C Ularn 1.6.3a -> pyularn)

The goal is a **faithful, function-by-function port** of the UNIX TTY build of
Ularn 1.6.3a. Game behaviour (formulas, messages, probabilities, level
generation) must match the C code. Do not redesign or "improve" mechanics.

The build that is ported is the one in `src/makefile.tty`:

    ularn ularn_wintty ularn_game ularn_ask store sphere spell show scroll
    scores saveutils savegame potion player object monster itm help fortune
    dungeon_obj dungeon diag action

(`bill.c`, `bio.c`, X11/Win32/Amiga front ends and `getopt.c` are not ported.)
Follow the `UNIX` / `UNIX_TTY` branches of every `#ifdef`; drop the others.

## 1. Module mapping

* `foo.c` + `foo.h` -> `pyularn/foo.py`. Everything *defined* by those two
  files (macros, enums, globals, tables, structs, functions) lives there.
* `header.h`, `config.h`, `patchlevel.h` -> `pyularn/header.py` (already written).
* `ularn_win.h` + `ularn_wintty.c` -> `pyularn/ularn_win.py`.
* A symbol lives in the module of the file that **defines** it: a `#define`
  or enum lives with the header it is written in; a global variable or
  function lives with the `.c` file that defines it (not the one that only
  declares it `extern`). When unsure: `grep -n` the C source.
* Keep the **same names** as C for functions, globals, constants and struct
  fields, so other modules can find them without coordination. If a C name is
  a Python keyword (`lambda`, `pass`, `in`, ...) append `_` (`pass_`).

## 2. Imports (avoid circular-import breakage)

    from .header import *            # the only allowed star import
    from . import monster, player, dungeon, ularn_win   # modules, not names

Always reference other modules' symbols at call time as `module.name`
(`player.c[player.HP]`, `monster.monster[i].name`, `ularn_win.Print(...)`).
Never `from .x import name`. If a module name clashes with a local name in
your file, alias the import with a trailing underscore
(`from . import potion as potion_`).

## 3. Globals and data

* C globals are module-level variables. Inside the owning module use
  `global`; other modules assign through the module: `dungeon.playerx = 3`.
* Arrays keep C index order: `item[MAXX][MAXY]` ->
  `item = [[0] * MAXY for _ in range(MAXX)]`, accessed `item[x][y]`.
  Arrays that are reset in C with memset/loops should be reset **in place**
  (slice assignment / loops) so references held elsewhere stay valid.
* Structs -> small classes with the same field names (plain attributes;
  a `__init__` taking all fields positionally is handy for tables).
* Static tables (monster list, object names, spell names, store inventory,
  scroll/potion names, ...) are ported verbatim, including text.
* `char` used as a number stays an `int`. Keys / characters read from the
  user are 1-character `str` (`if i == 'y':`). Map display characters are str.

## 4. Arithmetic

* C integer `/` and `%`: use `//` and `%` only when both operands are known
  non-negative; otherwise use `cdiv(a, b)` / `cmod(a, b)` from header.
* `rnd(x)` (1..x), `rund(x)` (0..x-1), `rand()`, `srand()` come from header
  and share one RNG. Never call `random` directly.
* Ignore C integer overflow except where the C code relies on it explicitly.

## 5. Output / input (the UI contract — implemented in `ularn_win.py`)

All screen I/O goes through `ularn_win` exactly as in C:

    ularn_win.Print(s)               ularn_win.Printc(ch)
    ularn_win.Printf(fmt, *args)     # does fmt % args (C %ld etc. work in Python)
    ularn_win.Standout(s)            ularn_win.SetFormat(ularn_win.FORMAT_BOLD)
    ularn_win.MoveCursor(x, y)       ularn_win.ClearText()  ularn_win.ClearToEOL()
    ularn_win.ClearToEOPage(x, y)    ularn_win.UlarnBeep()  ularn_win.nap(ms)
    ularn_win.set_display(ularn_win.DISPLAY_MAP | DISPLAY_TEXT)
    ularn_win.UpdateStatus() / UpdateEffects() / UpdateStatusAndEffects()
    ularn_win.show1cell(x,y) showcell(x,y) showplayer() drawscreen() draws(a,b,c,d)
    ularn_win.mapeffect(x, y, effect, dir)
    ularn_win.magic_effect_frames(fx) / magic_effect(x, y, fx, frame)
    ularn_win.get_normal_input()     -> int ACTION_* constant
    ularn_win.get_prompt_input(prompt, answers, show_cursor) -> 1-char str
    ularn_win.get_password_input(maxlen) -> str      (C fills a buffer)
    ularn_win.get_num_input(default) -> int
    ularn_win.get_dir_input(prompt, show_cursor) -> int ACTION_* constant
    ularn_win.GetUser() -> (username, uid)            (C fills two out-params)

Enum values (`FORMAT_*`, `DISPLAY_*`, `EFFECT_*`, `MAGIC_*`, `ACTION_*`) are
plain int constants in `ularn_win.py`, numbered exactly as in `ularn_win.h`.
C functions with out-parameters return a value or tuple instead; note the new
signature in the function docstring.

## 6. Exits, files, saves

* `exit(n)` / game-ending paths -> `raise UlarnExit(n)` (from header). The
  main loop catches it.
* Read-only data files (`Umaps`, `Uhelp`, `Ufortune`) -> `data_path("Umaps")`.
* Score file and save files -> `user_path(...)` (default dir `~/.pyularn`).
* Save games use `pickle` of a dict of every game-state global (enumerate the
  same state the C `savegame.c` writes). Binary struct layout is not kept.

## 7. Style

* Python 3.10+, standard library only.
* Brief docstring per function (one line is fine). Keep important C comments.
* Each module must import cleanly: `python3 -c "import pyularn.foo"`.
