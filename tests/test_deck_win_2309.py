"""a4sx #2309 WIN items in the deck (plugin 0.4.4): F6, bring a cell here that is online elsewhere; (bb), a fresh host."""
import importlib.util
import json
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
        with mock.patch.object(deck, "jrun", jrun), mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 500, 222, 1]), \
                mock.patch.object(deck, "_in_foreground", lambda pid, pane: True):
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
                mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 200, 250, 300]), \
                mock.patch.object(deck, "_in_foreground", lambda pid, pane: True):
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:inner")
            deck._PANE_OF_PID.clear()
            self.assertIsNone(deck.pane_of_pid(4242, agents, taken={"w1:inner"}), "never the pane further up")
            deck._PANE_OF_PID.clear()
            self.assertIsNone(deck.pane_of_pid(4242, agents, taken={"w1:inner", "w1:outer"}))

    def test_a_descendant_outside_the_panes_foreground_is_not_its_cell(self):
        """Review of #9: an agent host started in a Claude pane runs its cells in other process groups."""
        agents = [{"pane_id": "w1:p1"}]
        with mock.patch.object(deck, "jrun", lambda argv, t=30: {"result": {"process_info": {"shell_pid": 200, "foreground_process_group_id": 999}}}), \
                mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 300, 200]), \
                mock.patch.object(deck.os, "getpgid", lambda pid: 4242):
            self.assertIsNone(deck.pane_of_pid(4242, agents))
        deck._PANE_OF_PID.clear()
        with mock.patch.object(deck, "jrun", lambda argv, t=30: {"result": {"process_info": {"shell_pid": 200, "foreground_process_group_id": 4242}}}), \
                mock.patch.object(deck, "_ancestors", lambda pid, n=16: [pid, 200]), \
                mock.patch.object(deck.os, "getpgid", lambda pid: 4242):
            self.assertEqual(deck.pane_of_pid(4242, agents), "w1:p1")

    def test_a_failed_process_info_is_asked_again(self):
        answers = iter([{}, {"result": {"process_info": {"shell_pid": 7}}}])
        with mock.patch.object(deck, "jrun", lambda argv, t=30: next(answers)):
            self.assertIsNone(deck._shell_pid_of("w1:p1"))
            self.assertEqual(deck._shell_pid_of("w1:p1"), 7)

    def test_bring_running_here_says_so_and_a_second_press_does_nothing(self):
        ui, seen = _ui([_row("build", here=True, presence="online", running=True)])
        ui.running_now = lambda name, iid=None: "w1:p4"
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a tab")):
            ui.bring("build", False)
        self.assertIn("is already running on this host", seen["lines"][0])
        ui.starting = {"other"}
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a second tab")):
            ui.bring("other", False)

    def test_ancestors_of_this_process_include_it(self):
        up = deck._ancestors(os.getpid())
        if up:   # Linux /proc
            self.assertIn(os.getpid(), up)
            self.assertIn(os.getppid(), up)


class Deck046(unittest.TestCase):
    """0.4.6, a4sx #2309 (q) and (r) from cell01's move round trip."""

    def tearDown(self):
        mock.patch.stopall()

    def test_the_restore_list_is_newest_first_with_this_cells_saves_marked(self):
        lib = [{"name": "old", "updated": "2026-11-20 10:00"}, {"name": "build-backup", "updated": "2026-11-22 09:00"},
               {"name": "handoff-build", "updated": "2026-11-21 12:00"}, {"name": "other-backup", "updated": "2026-11-22 10:00"}]
        self.assertEqual([x["name"] for x in deck.restore_order(lib, "build")],
                         ["other-backup", "build-backup", "handoff-build", "old"])
        self.assertTrue(deck.of_cell("build-backup", "build") and deck.of_cell("handoff-build", "build"))
        self.assertFalse(deck.of_cell("builder-x", "build") or deck.of_cell("other-backup", "build"))
        # review: exact names only: another cell's backup or a save named build-notes is not marked
        self.assertFalse(deck.of_cell("build-x-backup", "build") or deck.of_cell("build-notes", "build"))
        ui, _seen = _ui()
        ui.d.library = [dict(x, vers="1", size="1k") for x in lib]
        got = {}
        ui.choose = lambda title, items, cb: got.update(items=items)
        ui.restore({"name": "build"})
        shown = [deck.ANSI.sub("", x) for x in got["items"]]
        self.assertTrue(shown[0].startswith("  other-backup") and shown[1].startswith("◆ build-backup"))

    def test_r_reuses_the_idle_old_tab_and_refuses_while_online_elsewhere(self):
        ui, seen = _ui([_row("build", here=True)])
        ui.bg = lambda title, fn: seen.update(lines=fn())
        got = {}
        with mock.patch.object(deck, "_leftover_pane", lambda c: ("w1:p4", "w1:t2")), \
                mock.patch.object(deck, "pane_is_idle_shell", lambda p: True), \
                mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(reuse=reuse) or "ok"):
            ui.start_seeded({"name": "build", "running": False}, "build-backup")
        self.assertEqual(got["reuse"], ("w1:p4", "w1:t2"))
        # review: the real bg() path, as the deck runs it: the refusal is what the result pane shows last, never "None"
        ui2, _seen2 = _ui([_row("win-cell", here=True, presence="online")])
        ui2.d.refresh = lambda what: None
        notes = []
        ui2.note = lambda lines, title="result": notes.append(list(lines))
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("started")):
            ui2.start_seeded({"name": "win-cell", "running": False}, "handoff-win-cell")
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("is online on another host now", notes[-1][0])
        self.assertIn("can't be started here from a saved conversation yet", notes[-1][0])
        self.assertNotIn("None", notes[-1])
        self.assertEqual(ui2.starting, set())   # the double-press guard is released after the check

    def test_r_second_enter_while_checking_starts_nothing_more(self):
        ui, _seen = _ui([_row("build", here=True)])
        ui.d.refresh = lambda what: None
        ui.starting = {"build"}   # a first Enter is still being checked
        ui.bg = lambda title, fn: self.fail("a second start was run")
        ui.start_seeded({"name": "build", "running": False}, "build-backup")

    def test_bg_keeps_a_note_the_operation_showed_itself(self):
        ui, _seen = _ui()
        ui.d.refresh = lambda what: None
        notes = []
        ui.note = lambda lines, title="result": notes.append(list(lines))
        ui.bg("x", lambda: ui.note(["own note"]))
        self.assertEqual(notes, [["own note"]])

    def test_a_cell_stored_here_and_running_elsewhere_says_so(self):
        ui, _seen = _ui()
        ui.d.ah = {"open": []}
        where = deck.ANSI.sub("", ui.where({"pane": None, "here": True, "running": False, "mine": True, "presence": "online", "name": "w"}))
        self.assertEqual(where, "● runs elsewhere")   # 0.4.7: fits the where column (17)
        self.assertLessEqual(len(where), 17)
        where = deck.ANSI.sub("", ui.where({"pane": None, "here": True, "running": False, "mine": True, "presence": "offline", "name": "w"}))
        self.assertEqual(where, "◇ stored here")


class Deck046Remarks(unittest.TestCase):
    """0.4.6, cell01's remarks on the 0.4.5 recheck."""

    def tearDown(self):
        mock.patch.stopall()

    def test_reading_until_the_first_read(self):
        d = types.SimpleNamespace(lock=threading.Lock(), activity=[], activity_read=False)
        self.assertEqual(deck.own_messages(d, "x"), ["reading this host's delivery records …"])
        d.activity_read = True
        self.assertEqual(deck.own_messages(d, "x"), ["no messages recorded on this host for this cell yet"])
        with open(os.path.join(HERE, "..", "deck.py"), encoding="utf-8") as f:
            self.assertIn("reading this host's delivery records …", f.read())

    def test_m_on_a_running_cell_shows_its_own_deliveries(self):
        d = types.SimpleNamespace(lock=threading.Lock(), activity_read=True, activity=[
            (1763800000, "out", "omarchy-cell", "win-cell", "delivered"), (1763700000, "in", "other", "win-cell", "inbox")])
        got = deck.own_messages(d, "omarchy-cell")
        self.assertEqual(len(got), 1)
        self.assertIn("to   win-cell  delivered", got[0])

    def test_view_5_lists_a_cell_running_elsewhere_with_the_other_hosts(self):
        ui, _seen = _ui([_row("win-cell", here=True, presence="online"), _row("omarchy-cell", here=True, presence="online", running=True)])
        ui.d.library = []
        ui.view = "move"
        kinds = {x["name"]: x["kind"] for x in ui.items()}
        self.assertEqual(kinds, {"win-cell": "away", "omarchy-cell": "cell"})
        self.assertTrue(deck.runs_elsewhere(_row("win-cell", here=True, presence="online")))
        self.assertFalse(deck.runs_elsewhere(_row("x", here=True, presence="online", running=True)))
        self.assertFalse(deck.runs_elsewhere(_row("x", here=False, presence="online")))


if __name__ == "__main__":
    unittest.main()


class Deck047Restore(unittest.TestCase):
    """0.4.7, cell01's Omarchy check of 0.4.6: r on a stopped cell whose tab is in another folder."""

    def tearDown(self):
        mock.patch.stopall()

    def test_r_starts_in_the_recorded_folder_reuses_its_idle_shell_and_runs_no_stop(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": demo}}}, f)
            ui, _seen = _ui([_row("omarchy-cell", here=True)])
            ui.d.refresh = lambda what: None
            ran, got = [], {}
            with mock.patch.object(deck, "STATE", st), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: None), \
                    mock.patch.object(deck, "_pane_in_folder", lambda cwd, skip=None, skip_pane=None: ("w1:p9", "w1:t3") if cwd == demo else None), \
                    mock.patch.object(deck, "deck_state", lambda: ("w1:p1", "w1:t1", True)), \
                    mock.patch.object(deck, "run", lambda argv, *a, **k: ran.append(argv) or (0, "", "")), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(cwd=cwd, reuse=reuse) or "ok"):
                # a stale row says running; the fresh check says it doesn't run here: no stop is run or shown
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": True}, "omarchy-cell-backup")
                # review: a shell found only by its folder may be the person's own: asked first, never taken by itself
                self.assertEqual(got, {})
                self.assertEqual(ui.pick[1], "yes, start it in that shell")
                ui.pick_cb(1)
            self.assertEqual(got, {"cwd": demo, "reuse": ("w1:p9", "w1:t3")})
            self.assertFalse(any("stop" in a for a in ran), ran)

    def test_r_a_non_cell_shell_in_that_folder_is_not_typed_into_on_no(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": demo}}}, f)
            ui, _seen = _ui([_row("omarchy-cell", here=True)])
            ui.d.refresh = lambda what: None
            got = {}
            with mock.patch.object(deck, "STATE", st), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: None), \
                    mock.patch.object(deck, "_pane_in_folder", lambda cwd, skip=None, skip_pane=None: ("w1:p5", "w1:t5")), \
                    mock.patch.object(deck, "deck_state", lambda: ("w1:p1", "w1:t1", True)), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(reuse=reuse) or "ok"):
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": False}, "x")
                ui.pick_cb(0)
            self.assertEqual(got, {"reuse": None})

    def test_r_esc_on_a_running_cell_leaves_it_running(self):
        """Coordinator: the tab question comes BEFORE the stop: Esc stops nothing and starts nothing."""
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": demo}}}, f)
            ui, _seen = _ui([_row("omarchy-cell", here=True, running=True)])
            ui.d.refresh = lambda what: None
            ui.running_now = lambda name, iid=None: "w1:p2"   # it runs here, in pane w1:p2
            ui.mode, ran, got = "browse", [], {}
            with mock.patch.object(deck, "STATE", st), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: None), \
                    mock.patch.object(deck, "_pane_in_folder", lambda cwd, skip=None, skip_pane=None: ("w1:p5", "w1:t5")), \
                    mock.patch.object(deck, "deck_state", lambda: ("w1:p1", "w1:t1", True)), \
                    mock.patch.object(deck, "run", lambda argv, *a, **k: ran.append(argv) or (0, "", "")), \
                    mock.patch.object(deck.time, "sleep", lambda s: None), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(reuse=reuse) or "ok"):
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": True}, "x")
                self.assertEqual(ui.mode, "pick")
                self.assertIn("(the cell is stopped first)", ui.pick_title)
                self.assertEqual(ran, [], "nothing is stopped before the answer")
                ui.key("esc")
                self.assertEqual(ran, [])
                self.assertEqual(got, {})
                # and "yes": the stop runs then, and its line is shown with the start
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": True}, "x")
                ui.pick_cb(1)
            self.assertTrue(any(a[-3:-1] == ["cell", "stop"] for a in ran), ran)
            self.assertEqual(got, {"reuse": ("w1:p5", "w1:t5")})

    def test_r_the_decks_own_idle_record_pane_is_reused_without_a_question_and_never_asked_about(self):
        """Review of 1fc8b2f: the record pane sits in the recorded folder too; it is reused as in 0.4.6, no question;
        and a folder match is never the record pane itself."""
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": demo}}}, f)
            ui, _seen = _ui([_row("omarchy-cell", here=True)])
            ui.d.refresh = lambda what: None
            ui.choose = lambda *a, **k: self.fail("asked about the deck's own pane")
            got, skipped = {}, []
            with mock.patch.object(deck, "STATE", st), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: ("w1:p4", "w1:t2")), \
                    mock.patch.object(deck, "pane_is_idle_shell", lambda p: True), \
                    mock.patch.object(deck, "_pane_in_folder", lambda cwd, skip=None, skip_pane=None: skipped.append(skip_pane)), \
                    mock.patch.object(deck, "deck_state", lambda: ("w1:p1", "w1:t1", True)), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(reuse=reuse) or "ok"):
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": False}, "x")
            self.assertEqual(got, {"reuse": ("w1:p4", "w1:t2")})
            self.assertEqual(skipped, [], "no folder search when the record pane is idle")

    def test_r_no_after_the_question_opens_a_new_tab_even_with_a_record_pane(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": demo}}}, f)
            ui, _seen = _ui([_row("omarchy-cell", here=True, running=True)])
            ui.d.refresh = lambda what: None
            ui.running_now = lambda name, iid=None: "w1:p4"
            idle = {"v": False}   # the record pane runs the cell (not idle) until the stop
            got, skipped = {}, []

            def run(argv, *a, **k):
                idle["v"] = True
                return 0, "", ""
            with mock.patch.object(deck, "STATE", st), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: ("w1:p4", "w1:t2")), \
                    mock.patch.object(deck, "pane_is_idle_shell", lambda p: idle["v"]), \
                    mock.patch.object(deck, "_pane_in_folder", lambda cwd, skip=None, skip_pane=None: skipped.append(skip_pane) or ("w1:p5", "w1:t5")), \
                    mock.patch.object(deck, "deck_state", lambda: ("w1:p1", "w1:t1", True)), \
                    mock.patch.object(deck, "run", run), mock.patch.object(deck.time, "sleep", lambda s: None), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(reuse=reuse) or "ok"):
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": True}, "x")
                ui.pick_cb(0)   # no, open a new tab
            self.assertEqual(skipped, ["w1:p4"], "the record pane is never the folder match")
            self.assertEqual(got, {"reuse": None})

    def test_recorded_cwd_refuses_a_fifo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st:
            rec = os.path.join(st, "a4sx", "agents", "c1", "state")
            os.makedirs(rec)
            os.mkfifo(os.path.join(rec, "cell-last-session.json"))
            with mock.patch.object(deck, "STATE", st):
                self.assertIsNone(deck.recorded_cwd("c1", "ins_A"))

    def test_recorded_cwd_only_a_folder_of_this_cells_own_record(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st:
            with mock.patch.object(deck, "STATE", st):
                self.assertIsNone(deck.recorded_cwd("omarchy-cell", "ins_A"))      # no record
                self.assertIsNone(deck.recorded_cwd("../x", "ins_A"))              # not a cell name
                rec = os.path.join(st, "a4sx", "agents", "c1", "state")
                os.makedirs(rec)
                with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                    json.dump({"cells": {"ins_A": {"cwd": "/nonexistent-deck-folder"}, "ins_B": {"cwd": st}}}, f)
                self.assertIsNone(deck.recorded_cwd("c1", "ins_A"))                # gone folder
                self.assertEqual(deck.recorded_cwd("c1", "ins_B"), st)
                self.assertIsNone(deck.recorded_cwd("c1", "ins_C"))                # another cell's entry only

    def test_pane_in_folder_takes_only_an_idle_shell_there_without_an_agent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as demo:
            panes = [{"pane_id": "p1", "tab_id": "t1"}, {"pane_id": "p2", "tab_id": "t2"}, {"pane_id": "p3", "tab_id": "t3"}]
            pids = {"p1": None, "p2": os.getpid(), "p3": os.getpid()}
            os.chdir(demo)
            try:
                with mock.patch.object(deck, "jrun", lambda argv, t=30: {"result": {"panes": panes}}), \
                        mock.patch.object(deck, "_idle_shell_pid", lambda p: pids[p]), \
                        mock.patch.object(deck, "_pane_has_agent", lambda p: p == "p2"):
                    self.assertEqual(deck._pane_in_folder(demo), ("p3", "t3"))
                    self.assertIsNone(deck._pane_in_folder(demo, skip_tab="t3"))
                    self.assertIsNone(deck._pane_in_folder(HERE))
            finally:
                os.chdir(HERE)

    def test_r_says_online_elsewhere_before_the_picker(self):
        ui, seen = _ui([_row("win-cell", here=True, presence="online")])
        ui.choose = lambda *a, **k: self.fail("the picker was shown")
        ui.restore({"name": "win-cell", "here": True, "mine": True, "presence": "online", "running": False})
        self.assertIn("can't be started here from a saved conversation yet", seen["lines"][0])


class Deck048(unittest.TestCase):
    """0.4.8, cell01's Omarchy check of 0.4.7."""

    def tearDown(self):
        mock.patch.stopall()

    def test_r_on_a_running_cell_uses_its_own_tab_and_folder_not_the_record(self):
        import tempfile
        with tempfile.TemporaryDirectory() as st, tempfile.TemporaryDirectory() as demo, tempfile.TemporaryDirectory() as old:
            rec = os.path.join(st, "a4sx", "agents", "omarchy-cell", "state")
            os.makedirs(rec)
            with open(os.path.join(rec, "cell-last-session.json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "cells": {"ins_A": {"sid": "s", "cwd": old}}}, f)   # a stale record
            ui, _seen = _ui([_row("omarchy-cell", here=True, running=True)])
            ui.d.refresh = lambda what: None
            ui.choose = lambda *a, **k: self.fail("no question for the cell's own tab")

            def running_now(name, iid=None):
                ui.__dict__.setdefault("run_cwd", {})[name] = demo
                return "w1:p7"
            ui.running_now = running_now
            idle = {"v": False}
            got = {}

            def jrun(argv, t=30):
                return {"result": {"panes": [{"pane_id": "w1:p7", "tab_id": "w1:t7"}, {"pane_id": "w1:p2", "tab_id": "w1:t2"}]}} \
                    if argv[1:3] == ["pane", "list"] else {}
            with mock.patch.object(deck, "STATE", st), mock.patch.object(deck, "jrun", jrun), \
                    mock.patch.object(deck, "_leftover_pane", lambda c: ("w1:p2", "w1:t2")), \
                    mock.patch.object(deck, "pane_is_idle_shell", lambda p: idle["v"] and p == "w1:p7"), \
                    mock.patch.object(deck, "run", lambda argv, *a, **k: idle.update(v=True) or (0, "", "")), \
                    mock.patch.object(deck.time, "sleep", lambda s: None), \
                    mock.patch.object(deck, "new_tab", lambda label, cwd, argv, cell=None, reuse=None: got.update(cwd=cwd, reuse=reuse) or "ok"):
                ui.start_seeded({"name": "omarchy-cell", "iid": "ins_A", "running": True}, "x")
            # its own running tab (not the other «omarchy-cell» tab the deck recorded) and that tab's folder
            self.assertEqual(got, {"cwd": demo, "reuse": ("w1:p7", "w1:t7")})

    def test_the_selection_stays_on_the_same_cell_when_the_list_reorders(self):
        ui = object.__new__(deck.Deck)
        ui.view, ui.sel = "mesh", {"mesh": 0}
        a, b = {"name": "a", "iid": "ins_a"}, {"name": "b", "iid": "ins_b"}
        ui.d = types.SimpleNamespace(rows=[a, b], library=[])
        ui.sel["mesh"] = 1
        self.assertEqual(ui.cur()["name"], "b")
        ui.d.rows = [b, a]   # after a stop, b sorts first
        self.assertEqual(ui.cur()["name"], "b")
        ui.d.rows = [a]      # b is gone: the index stays in range
        self.assertEqual(ui.cur()["name"], "a")

    def test_a_cells_pane_is_found_by_its_launch_before_a_folder_named_like_it(self):
        src = open(os.path.join(HERE, "..", "deck.py"), encoding="utf-8").read()
        i = src.index("def row(name, iid, presence, own=None):")
        body = src[i:src.index("return {", i)]
        self.assertLess(body.index("pane_of_pid("), body.index("os.path.basename((x.get(\"cwd\")"))

