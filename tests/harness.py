"""Helpers to drive a headless game from tests (and by hand)."""

import os
import tempfile
import threading

from pyularn import engine, header, term_virtual, ularn


class HeadlessGame:
    def __init__(self, argv=None, seed=None, home=None, reset=True):
        self.home = home or tempfile.mkdtemp(prefix="pyularn-test-")
        os.environ["PYULARN_HOME"] = self.home
        if reset:
            engine.reset()
        if seed is not None:
            header.set_seed(seed)
        self.term = term_virtual.VirtualTerminal()
        self.error = None
        self.exit_code = None
        self.thread = threading.Thread(target=self._run, args=(argv or ["ularn"],), daemon=True)
        self.thread.start()
        self.wait()

    def _run(self, argv):
        try:
            self.exit_code = ularn.run_game(self.term, argv)
        except BaseException as e:  # surface crashes to the test
            import traceback
            self.error = traceback.format_exc()
            self.term.mark_finished()

    def wait(self, timeout=10):
        ok = self.term.wait_for_input(timeout)
        if self.error:
            raise RuntimeError("game crashed:\n" + self.error)
        return ok

    def send(self, keys, timeout=10):
        self.term.feed(keys)
        return self.wait(timeout)

    @property
    def screen(self):
        return self.term.text(ascii_walls=True)

    def close(self):
        self.term.shutdown()
        self.thread.join(5)
