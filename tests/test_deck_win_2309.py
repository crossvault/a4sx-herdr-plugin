"""a4sx #2309 WIN items in the deck (plugin 0.4.4): F6, bring a cell here that is online elsewhere; (bb), a fresh host."""
import importlib.util
import os
import threading
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("deck_win_2309", os.path.join(HERE, "..", "deck.py"))
deck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deck)


def _ui(rows=(), cells=(), at="12:00:00"):
    ui = object.__new__(deck.Deck)
    ui.d = types.SimpleNamespace(lock=threading.Lock(), rows=list(rows), cells=list(cells), at=at)
    seen = {}
    ui.note = lambda lines, title="result": seen.update(lines=lines, title=title)
    ui.pdir = lambda n: os.path.join("/nonexistent-deck-test", n)
    return ui, seen


def _row(name, here=False, mine=True, presence="offline", running=False):
    return {"name": name, "here": here, "mine": mine, "presence": presence, "running": running}


class BringOnlineElsewhere(unittest.TestCase):
    """F6 (cell01): s on a cell online on another host made ~/projects/<cell>, opened a tab, and then failed."""

    def test_online_elsewhere_says_so_first_and_creates_nothing(self):
        ui, seen = _ui([_row("build", presence="online")])
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a tab was opened")), \
                mock.patch.object(deck.os, "makedirs", lambda *a, **k: self.fail("a folder was made")):
            ui.bring("build", False)
            ui.bring("build", True)
        self.assertEqual(seen["lines"][0], "«build» is online on another host now, so it can't be brought here yet: stop "
                                           "it there first (on that host's deck: x stops it), then bring it here")
        self.assertIn("nothing was created or started", seen["lines"][1])

    def test_offline_elsewhere_or_unknown_starts_as_before(self):
        for rows in ([_row("build")], [], [_row("build", presence="online", mine=False)],
                     [_row("build", here=True, presence="online", running=True)]):
            ui, seen = _ui(rows)
            with mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: f"tab {argv[-1]}"):
                ui.bring("build", False)
            self.assertEqual(seen["lines"][0], "tab build", rows)


class FirstCell(unittest.TestCase):
    """(bb) cell01: a fresh machine showed MESH —, PEOPLE 0, CELLS 0 and no next step."""

    def test_due_only_once_read_and_with_nothing_here(self):
        self.assertTrue(_ui()[0].first_cell_due())
        self.assertFalse(_ui(at=None)[0].first_cell_due(), "before the first read: no advice yet")
        self.assertFalse(_ui(rows=[_row("x")])[0].first_cell_due())
        self.assertFalse(_ui(cells=[{"name": "x"}])[0].first_cell_due())

    def test_the_lines_name_the_clis_own_first_command(self):
        text = "\n".join(deck.FIRST_CELL_LINES)
        self.assertIn("      a4sx launch --cell\n", text + "\n")
        self.assertIn("`a4sx launch --cell -` starts one with a code from the console", text)

    def test_f_starts_it_in_a_new_tab_in_the_named_project_folder(self):
        ui, seen = _ui()
        asked = {}
        ui.ask = lambda title, cb, empty_ok=False: asked.update(title=title, cb=cb)
        got = {}
        ui.first_cell()
        with mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(cwd=cwd, argv=argv) or "opened"):
            asked["cb"]("studio")
        self.assertEqual(got["cwd"], os.path.join("/nonexistent-deck-test", "studio"))
        self.assertEqual(got["argv"][-2:], ["launch", "--cell"])
        self.assertEqual(seen["lines"], ["opened"])
        self.assertEqual(got.get("label", "studio"), "studio")

    def test_the_tab_is_named_like_the_folder(self):
        ui, seen = _ui()
        asked, got = {}, {}
        ui.ask = lambda title, cb, empty_ok=False: asked.update(cb=cb)
        ui.first_cell()
        with mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(label=label) or "ok"):
            asked["cb"]("first-cell")
        self.assertEqual(got["label"], "first-cell", "0.4.5 (cell01): not «first cell»")

    def test_a_bad_folder_name_starts_nothing(self):
        ui, seen = _ui()
        asked = {}
        ui.ask = lambda title, cb, empty_ok=False: asked.update(cb=cb)
        ui.first_cell()
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("started")):
            for bad in ("../x", "a b", "", "X", "a;rm"):
                asked["cb"](bad)
                self.assertIn("nothing was started", seen["lines"][0])




class FirstCellOnScreen(unittest.TestCase):
    """Review of #8: the screen itself, per view: the lines show where f works, and only there."""

    def _draw(self, view, rows=(), at="12:00:00"):
        ui = deck.Deck()
        ui.d.at, ui.d.rows = at, list(rows)
        ui.view = view
        out = []
        with mock.patch.object(deck.sys.stdout, "write", out.append), mock.patch.object(deck.sys.stdout, "flush", lambda: None), \
                mock.patch.object(deck.shutil, "get_terminal_size", lambda *a: os.terminal_size((200, 60))), \
                mock.patch.object(deck, "run", lambda *a, **k: (0, "", "")), mock.patch.object(deck, "jrun", lambda *a, **k: {}):
            ui.draw()
        return ui, deck.ANSI.sub("", "".join(out))

    def test_mesh_and_host_show_the_step_and_bind_f(self):
        for view in ("mesh", "host"):
            ui, screen = self._draw(view)
            self.assertIn("No cell on this host yet", screen, view)
            self.assertIn("f", [k for k, _lbl, _fn in ui.ops], view)

    def test_rules_shows_neither(self):
        ui, screen = self._draw("rules")
        self.assertNotIn("No cell on this host yet", screen)
        self.assertNotIn("f", [k for k, _lbl, _fn in ui.ops])

    def test_not_before_the_first_read_nor_with_cells(self):
        for kw in ({"at": None}, {"rows": [{"name": "x", "here": False, "mine": True, "presence": "online", "owner": "me",
                                            "role": "", "state": "", "running": False, "pane": None, "cwd": None}]}):
            ui, screen = self._draw("mesh", **kw)
            self.assertNotIn("No cell on this host yet", screen, kw)


class Recheck045(unittest.TestCase):
    """0.4.5, cell01's Omarchy recheck of 0.4.4."""

    def test_stored_here_and_online_elsewhere_is_refused_by_s_and_n(self):
        ui, seen = _ui([_row("win-cell", here=True, presence="online")])
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a tab was opened or reused")):
            ui.bring("win-cell", False)
        self.assertIn("is online on another host now", seen["lines"][0])
        seen.clear()
        ui.running_now = lambda name, iid=None: None
        ui._start_cell = lambda name, argv: self.fail("started in its old tab")
        ui.msg = ""
        with mock.patch.object(deck.threading, "Thread", lambda target, daemon: types.SimpleNamespace(start=target)):
            ui.start_cell("win-cell", ["a4sx", "launch", "--cell", "win-cell"])
        self.assertIn("is online on another host now", seen["lines"][0])

    def test_running_here_is_not_elsewhere(self):
        ui, _seen = _ui([_row("build", here=True, presence="online", running=True)])
        self.assertIsNone(ui.online_elsewhere("build"))

    def test_the_result_lines_claim_no_start(self):
        with open(os.path.join(HERE, "..", "deck.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn('return f"started in its tab', src)
        self.assertIn("the tab shows the outcome", src)

    def test_messages_are_read_for_peers_stored_here_too(self):
        ui = object.__new__(deck.Data)
        asked = []
        with mock.patch.object(deck, "jrun", lambda argv, t=30: asked.append(argv[argv.index("deliveries") + 1]) or {}):
            ui.load_activity("m", [{"name": "omarchy-cell", "iid": "ins_A", "here": True, "running": True},
                                   {"name": "win-cell", "iid": "ins_B", "here": True, "running": False},
                                   {"name": "far", "iid": "ins_C", "here": False, "running": False}])
        self.assertEqual(asked, ["ins_B", "ins_C"])

    def test_a_cell_is_found_in_the_pane_its_launch_runs_in(self):
        deck._PANE_OF_PID.clear()
        agents = [{"pane_id": "w1:p2", "cwd": "/home/me/elsewhere"}, {"pane_id": "w1:p3", "cwd": "/home/me/proj"}]
        info = {"w1:p2": 111, "w1:p3": 222}
        calls = []

        def jrun(argv, t=30):
            calls.append(argv[-1])
            return {"result": {"process_info": {"shell_pid": info[argv[-1]]}}}
        with mock.patch.object(deck, "jrun", jrun), mock.patch.object(deck, "_ancestors", lambda pid, n=16: {pid, 500, 222, 1}):
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:p3")
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:p3")
        self.assertEqual(calls, ["w1:p2", "w1:p3"], "cached: herdr is asked once per pid")
        self.assertIsNone(deck.pane_of_pid(None, agents))
        with mock.patch.object(deck, "jrun", lambda *a, **k: self.fail("asked")), mock.patch.object(deck, "_ancestors", lambda pid, n=16: set()):
            self.assertIsNone(deck.pane_of_pid(7, agents))

    def test_ancestors_of_this_process_include_it(self):
        up = deck._ancestors(os.getpid())
        if up:   # Linux /proc
            self.assertIn(os.getpid(), up)
            self.assertIn(os.getppid(), up)


if __name__ == "__main__":
    unittest.main()
