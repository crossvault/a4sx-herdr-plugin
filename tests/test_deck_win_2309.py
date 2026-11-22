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


def _ui(rows=(), cells=(), at="12:00:00", peers=None):
    """A deck with these rows. `peers`: what a fresh `mesh peers --json` says now (None: the rows' own presence)."""
    ui = object.__new__(deck.Deck)
    ui.d = types.SimpleNamespace(lock=threading.Lock(), rows=list(rows), cells=list(cells), at=at, ref="msh_x",
                                 seen_limit=0, slow_until=0)
    seen = {}
    ui.note = lambda lines, title="result": seen.update(lines=lines, title=title)
    ui.pdir = lambda n: os.path.join("/nonexistent-deck-test", n)
    ui.running_now = lambda name, iid=None: None
    fresh = peers if peers is not None else [{"name": r["name"], "presence": r["presence"]} for r in rows]

    def jrun(argv, t=30):
        return {"peers": fresh} if argv[-3:-1] == ["peers", "msh_x"] else {}
    for p in (mock.patch.object(deck, "jrun", jrun),
              mock.patch.object(deck.threading, "Thread", lambda target, daemon: types.SimpleNamespace(start=target))):
        p.start()
        ui.__dict__.setdefault("_patches", []).append(p)
    return ui, seen


def tearDownModule():
    mock.patch.stopall()


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

    def tearDown(self):
        mock.patch.stopall()

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

    def tearDown(self):
        mock.patch.stopall()
        deck._PANE_OF_PID.clear()
        deck._SHELL_OF_PANE.clear()

    def test_stored_here_and_online_elsewhere_is_refused_by_s_and_n(self):
        ui, seen = _ui([_row("win-cell", here=True, presence="online")])
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a tab was opened or reused")):
            ui.bring("win-cell", False)
        self.assertIn("is online on another host now", seen["lines"][0])
        seen.clear()
        ui._start_cell = lambda name, argv: self.fail("started in its old tab")
        ui.msg = ""
        ui.start_cell("win-cell", ["a4sx", "launch", "--cell", "win-cell"])
        self.assertIn("is online on another host now", seen["lines"][0])

    def test_a_stale_online_is_read_again_and_a_restart_here_goes_on(self):
        """Review of #9: stopped here a moment ago, the deck's presence (60 s old) still says online; the fresh read
        doesn't, so s starts it."""
        ui, seen = _ui([_row("build", here=True, presence="online")], peers=[{"name": "build", "presence": "offline"}])
        started = []
        ui._start_cell = lambda name, argv: started.append(name)
        ui.msg = ""
        ui.start_cell("build", ["a4sx", "launch", "--cell", "build"])
        self.assertEqual(started, ["build"])
        self.assertNotIn("lines", seen)

    def test_no_fresh_read_possible_refuses_nothing(self):
        ui, seen = _ui([_row("build", here=True, presence="online")])
        ui.d.slow_until = deck.time.time() + 60   # the server said slow down
        started = []
        ui._start_cell = lambda name, argv: started.append(name)
        ui.msg = ""
        ui.start_cell("build", ["a4sx", "launch", "--cell", "build"])
        self.assertEqual(started, ["build"], "the CLI decides in the tab, as before")

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
            ui.load_activity("m", [{"name": "omarchy-cell", "iid": "ins_A", "here": True, "running": True, "presence": "online"},
                                   {"name": "win-cell", "iid": "ins_B", "here": True, "running": False, "presence": "online"},
                                   {"name": "far", "iid": "ins_C", "here": False, "running": False, "presence": "online"}])
        self.assertEqual(asked, ["ins_C", "ins_B"], "remote peers first, then the ones stored here too")

    def test_a_cell_is_found_in_the_pane_its_launch_runs_in(self):
        agents = [{"pane_id": "w1:p2", "cwd": "/home/me/elsewhere"}, {"pane_id": "w1:p3", "cwd": "/home/me/proj"}]
        info = {"w1:p2": 111, "w1:p3": 222}
        calls = []

        def jrun(argv, t=30):
            calls.append(argv[-1])
            return {"result": {"process_info": {"shell_pid": info[argv[-1]]}}}
        with mock.patch.object(deck, "jrun", jrun), mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 500, 222, 1]):
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:p3")
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:p3")
            self.assertEqual(deck.pane_of_pid(4343, agents), "w1:p3")
        self.assertEqual(sorted(calls), ["w1:p2", "w1:p3"], "each pane's shell is asked once")
        self.assertIsNone(deck.pane_of_pid(None, agents))

    def test_a_miss_is_cached_until_the_panes_change(self):
        agents = [{"pane_id": "w1:p2"}]
        calls = []

        def jrun(argv, t=30):
            calls.append(argv[-1])
            return {"result": {"process_info": {"shell_pid": 111}}}
        with mock.patch.object(deck, "jrun", jrun), mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 900]):
            for _ in range(5):   # an agent-host cell: in no pane
                self.assertIsNone(deck.pane_of_pid(4242, agents))
            self.assertEqual(calls, ["w1:p2"])
            self.assertIsNone(deck.pane_of_pid(4242, agents + [{"pane_id": "w1:p9"}]))
        self.assertEqual(calls, ["w1:p2", "w1:p9"], "a new pane: only it is asked")

    def test_the_nearest_ancestor_wins_and_a_taken_one_gives_none(self):
        """Review of #9: launched from another agent's pane (its Bash tool), the chain passes that pane's shell too."""
        agents = [{"pane_id": "w1:outer"}, {"pane_id": "w1:inner"}]
        info = {"w1:outer": 300, "w1:inner": 200}
        with mock.patch.object(deck, "jrun", lambda argv, t=30: {"result": {"process_info": {"shell_pid": info[argv[-1]]}}}), \
                mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 200, 250, 300]):
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:inner")
            deck._PANE_OF_PID.clear()
            self.assertIsNone(deck.pane_of_pid(4242, agents, taken={"w1:inner"}), "never the pane further up")
            deck._PANE_OF_PID.clear()
            self.assertIsNone(deck.pane_of_pid(4242, agents, taken={"w1:inner", "w1:outer"}))

    def test_ancestors_of_this_process_include_it(self):
        up = deck._ancestors(os.getpid())
        if up:   # Linux /proc
            self.assertIn(os.getpid(), up)
            self.assertIn(os.getppid(), up)


if __name__ == "__main__":
    unittest.main()
