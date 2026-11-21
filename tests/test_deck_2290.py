"""Stdlib tests (python3 -m unittest discover -s tests) for the deck (a4sx #2290), integrated into the plugin in
0.4.0: the on-start setting, the keys block, the polling budget, and that it reads no credential."""
import importlib.util
import os
import re
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "deck.py")
spec = importlib.util.spec_from_file_location("deck", SRC)
deck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deck)


class OnStart(unittest.TestCase):
    def test_focus_by_default_open_or_off_from_the_env_or_the_config_file(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": d}, clear=False):
            os.environ.pop("DECK_ON_START", None)
            self.assertEqual(deck.on_start_mode(), "focus")
            with open(os.path.join(d, "on-start"), "w", encoding="utf-8") as f:
                f.write("off\n")
            self.assertEqual(deck.on_start_mode(), "off")
            with mock.patch.dict(os.environ, {"DECK_ON_START": "open"}):
                self.assertEqual(deck.on_start_mode(), "open")
            with mock.patch.dict(os.environ, {"DECK_ON_START": "weird"}):
                self.assertEqual(deck.on_start_mode(), "focus")

    def test_part_of_the_a4sx_mesh_plugin(self):
        self.assertTrue(deck.PLUGIN_ID in ("a4sx.mesh", os.environ.get("HERDR_PLUGIN_ID")))
        with open(os.path.join(HERE, "..", "herdr-plugin.toml"), encoding="utf-8") as f:
            manifest = f.read()
        self.assertIn('id = "a4sx.mesh"', manifest)
        self.assertIn('command = ["python3", "deck.py", "start"]', manifest)
        self.assertRegex(manifest, r'\[\[panes\]\]\nid = "deck"')


class Keys(unittest.TestCase):
    def test_the_keys_block_reads_only_the_users_keys(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "herdr"))
            with open(os.path.join(d, "herdr", "config.toml"), "w", encoding="utf-8") as f:
                f.write('[ui]\nx = "y"\n[keys]\nprefix = "ctrl+space"\nnew_tab = ["prefix+c"]\n')
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
                self.assertEqual(deck.herdr_keys(), [("prefix", "ctrl+space"), ("prefix c", "new tab")])


class Budget(unittest.TestCase):
    def test_the_polling_budget_of_deck_0_5(self):
        self.assertEqual((deck.T_LOCAL, deck.T_SERVER, deck.T_RARE), (5, 60, 300))
        self.assertGreaterEqual(deck.T_BACKOFF, 60)
        self.assertGreaterEqual(deck.T_BACKOFF_MAX, deck.T_BACKOFF)

    def test_it_reads_no_credential_file(self):
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        for bad in ("apikey", "session.json", ".credentials", "getpass", "Authorization"):
            self.assertNotIn(bad, src, bad)
        self.assertFalse(re.search(r"\.key[\"']", src))



class NoHandOff(unittest.TestCase):
    def test_hand_off_is_hidden_until_a4sx_2292(self):
        """The coordinator, for consistency with the VS Code extension: a scrubbed hand-off changes the moved cell's
        peer names, so no operation reaches it; "bring here" and "Start from a saved session" stay."""
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("self.handoff(", src)
        self.assertNotIn('"hand off: move its work', src)
        self.assertIn("bring it here (starts it on this host)", src)
        self.assertIn("start from a saved session", src)
        self.assertNotIn("def handoff", src)
        self.assertNotIn("hands it off", src)
        self.assertIn("its conversation follows once a4sx #2292 lands", src)


class StopHost(unittest.TestCase):
    """a4sx #2326: a running agent host has "stop" (`a4sx agent-host stop`, the same stop as Ctrl-C); a stopped one "start"."""

    def _ops(self, running, open_=("build (Team mesh)",)):
        ui = object.__new__(deck.Deck)
        ui.d = types.SimpleNamespace(ah={"known": True, "running": running, "address": "ws://127.0.0.1:8765/", "open": list(open_)})
        self._status = {"running": running, "open": list(open_)}
        p = mock.patch.object(deck, "jrun", lambda argv, timeout=30: dict(self._status) if argv[-3:] == ["agent-host", "status", "--json"] else {})
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: (0, "usage", ""))   # never the real a4sx
        q.start()
        self.addCleanup(q.stop)
        return ui, {k: (label, fn) for k, label, fn in ui.host_ops()}

    def test_running_offers_stop_and_runs_the_clis_stop_in_the_background(self):
        ui, ops = self._ops(True)
        self.assertIn("S", ops)
        self.assertNotIn("A", ops)
        seen = {}
        with mock.patch.object(deck.Deck, "bg", lambda self, title, fn: seen.update(title=title, lines=fn())), \
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: (0, "usage", "") if argv[-1] == "--help" else seen.update(argv=argv, t=timeout) or (0, "a4sx agent host: stopped (pid 4)\n", "")):
            with mock.patch.object(deck.Deck, "choose", lambda self, title, items, cb: seen.update(asked=title, items=items) or cb(0)):
                ops["S"][1]()   # asked first; "no" stops nothing
            self.assertNotIn("argv", seen)
            self.assertEqual(seen["items"], ["no", "yes, stop it"])
            self.assertEqual(seen["asked"], "stop the agent host? «build» ends (VS Code is told first)")
            with mock.patch.object(deck.Deck, "choose", lambda self, title, items, cb: cb(1)):
                ops["S"][1]()
        self.assertEqual(seen["argv"][-2:], ["agent-host", "stop"])
        self.assertGreaterEqual(seen["t"], 35, "longer than the CLI's own 30 s wait")
        self.assertEqual(seen["lines"], ["a4sx agent host: stopped (pid 4)"])

    def test_a_stop_that_timed_out_says_the_host_may_still_stop(self):
        ui, ops = self._ops(True)
        seen = {}
        with mock.patch.object(deck.Deck, "bg", lambda self, title, fn: seen.update(lines=fn())), \
                mock.patch.object(deck.Deck, "choose", lambda self, title, items, cb: cb(1)), \
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: (0, "usage", "") if argv[-1] == "--help" else (1, "", "TimeoutExpired: a4sx agent-host stop")):
            ops["S"][1]()
        self.assertIn("may still stop", " ".join(seen["lines"]))

    def test_the_question_reads_a_fresh_status_and_counts_plain_conversations(self):
        _ui, ops = self._ops(True, open_=())
        self._status = {"running": True, "open": ["build (Team mesh)", "docs (Team mesh)", "chat (plain)"]}   # opened since the refresh
        seen = {}
        with mock.patch.object(deck.Deck, "choose", lambda self_, title, items, cb: seen.update(asked=title)):
            ops["S"][1]()
        self.assertEqual(seen["asked"], "stop the agent host? «build», «docs», 1 plain conversation end (VS Code is told first)")
        self._status = {"running": True, "open": ["a (plain)", "b (plain)"]}
        with mock.patch.object(deck.Deck, "choose", lambda self_, title, items, cb: seen.update(asked=title)):
            ops["S"][1]()
        self.assertEqual(seen["asked"], "stop the agent host? 2 plain conversations end (VS Code is told first)")

    def test_no_cell_runs_in_it_no_question(self):
        _ui, ops = self._ops(True, open_=())
        seen = {}
        with mock.patch.object(deck.Deck, "bg", lambda self, title, fn: seen.update(lines=fn())), \
                mock.patch.object(deck.Deck, "choose", lambda *a: self.fail("asked")), \
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: (0, "usage", "") if argv[-1] == "--help" else seen.update(argv=argv) or (0, "stopped\n", "")):
            ops["S"][1]()
        self.assertEqual(seen["argv"][-2:], ["agent-host", "stop"])

    def test_an_older_a4sx_is_told_to_update_and_nothing_is_asked_or_stopped(self):
        ui, ops = self._ops(True)
        ran, seen = [], {}
        old = (2, "", "a4sx agent-host: error: argument agent_host_cmd: invalid choice: 'stop' (choose from 'setup-vscode', 'status')\n")
        with mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: ran.append(argv[-2:]) or old), \
                mock.patch.object(deck.Deck, "choose", lambda *a: self.fail("asked")), \
                mock.patch.object(deck.Deck, "bg", lambda *a: self.fail("stopped")), \
                mock.patch.object(deck.Deck, "note", lambda self_, lines, title="result": seen.update(lines=lines)):
            ops["S"][1]()
        self.assertEqual(ran, [["stop", "--help"]], "only the side-effect-free probe")
        self.assertEqual(seen["lines"], [deck.STOP_NEEDS_UPDATE])
        self.assertIn("needs a4sx 0.59.15 or newer", deck.STOP_NEEDS_UPDATE)

    def test_stopped_offers_start_not_stop(self):
        _ui, ops = self._ops(False)
        self.assertIn("A", ops)
        self.assertNotIn("S", ops)


class LeftoverShell(unittest.TestCase):
    """cell01: after a herdr restart a cell's old pane stays as an empty shell; "s" starts the cell there again instead
    of opening another tab, only when it is that cell's pane (same tab) and no agent runs in it."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(deck, "_marker", lambda: os.path.join(d, "pane-x.txt")).start()
        mock.patch.object(deck, "IN_HERDR", True).start()
        self.ran, self.panes = [], {}

        def jrun(argv, t=30):
            if argv[1:3] == ["pane", "get"]:
                return {"result": {"pane": self.panes[argv[3]]}} if argv[3] in self.panes else {}
            if argv[1:3] == ["tab", "create"]:
                return {"result": {"root_pane": {"pane_id": "w1:p9"}, "tab": {"tab_id": "w1:t9"}}}
            return {}
        mock.patch.object(deck, "jrun", jrun).start()
        mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: self.ran.append(argv[1:]) or (0, "", "")).start()
        self.cwd = d

    def test_a_first_start_opens_a_tab_and_remembers_its_pane(self):
        out = deck.new_tab("build", self.cwd, ["a4sx", "launch", "--cell", "build"], cell="build")
        self.assertIn("opened the tab «build»", out)
        self.assertEqual(deck._cell_panes()["build"], ["w1:p9", "w1:t9"])

    def test_after_a_restart_its_empty_shell_is_used_again(self):
        deck._remember_cell_pane("build", "w1:p3", "w1:t2")
        self.panes["w1:p3"] = {"pane_id": "w1:p3", "tab_id": "w1:t2"}
        out = deck.new_tab("build", self.cwd, ["a4sx", "launch", "--cell", "build"], cell="build", reuse=("w1:p3", "w1:t2"))
        self.assertIn("started in its tab «build» again", out)
        self.assertNotIn(["tab", "create"], [r[:2] for r in self.ran])
        self.assertEqual(self.ran[0][:3], ["pane", "run", "w1:p3"])
        self.assertTrue(self.ran[0][3].startswith("cd ") and self.ran[0][3].endswith("&& a4sx launch --cell build"))
        self.assertEqual(self.ran[1], ["tab", "focus", "w1:t2"])

    def test_a_pane_with_an_agent_another_tab_or_no_answer_is_never_typed_into(self):
        for pane in ({"pane_id": "w1:p3", "tab_id": "w1:t2", "agent": "claude"}, {"pane_id": "w1:p3", "tab_id": "w1:t5"}, None):
            self.ran.clear()
            self.panes.clear()
            if pane:
                self.panes["w1:p3"] = pane
            deck._remember_cell_pane("build", "w1:p3", "w1:t2")
            deck.new_tab("build", self.cwd, ["a4sx", "launch", "--cell", "build"], cell="build", reuse=("w1:p3", "w1:t2"))
            self.assertNotIn("w1:p3", [r[2] for r in self.ran if r[:2] == ["pane", "run"]], pane)

    def test_a_hostile_folder_never_runs_as_a_command(self):
        import shlex
        deck._remember_cell_pane("build", "w1:p3", "w1:t2")
        self.panes["w1:p3"] = {"pane_id": "w1:p3", "tab_id": "w1:t2"}
        odd = os.path.join(self.cwd, "my dir; touch PWNED $(id) `id` 'q' \"d\" &&x")
        deck.new_tab("build", odd, ["a4sx", "launch", "--cell", "build"], cell="build", reuse=("w1:p3", "w1:t2"))
        line = self.ran[0][3]
        words = shlex.split(line)   # how a POSIX shell splits it: the folder is one word, nothing else runs
        self.assertEqual(words, ["cd", odd, "&&", "a4sx", "launch", "--cell", "build"])
        self.assertTrue(line.startswith("cd '"), line)

    def test_a_backslash_or_line_break_is_never_typed(self):
        """Review: fish reads \\\\ and \\' inside single quotes, so shlex quoting isn't enough there."""
        for cwd, argv in ((os.path.join(self.cwd, "a\\'; id; '"), ["a4sx", "launch", "--cell", "build"]),
                          (self.cwd, ["a4sx", "launch", "--cell", "x\nid"]), (self.cwd, ["a4sx", "x\\y"])):
            self.ran.clear()
            out = deck.new_tab("t", cwd, argv)
            self.assertIn("can't be typed into herdr's shell safely, so nothing was started", out)
            self.assertEqual([r for r in self.ran if r[:2] == ["pane", "run"]], [])

    def test_a_name_outside_the_clis_rule_starts_nothing(self):
        for bad in ("x; rm -rf ~", "$(id)", "`id`", "Build", "a b", "-x", "", "a" * 49, "név"):
            self.ran.clear()
            deck._remember_cell_pane("build", "w1:p3", "w1:t2")
            out = deck.new_tab(bad, self.cwd, ["a4sx", "launch", "--cell", bad], cell=bad)
            self.assertIn("isn't a cell name a4sx takes, so nothing was started", out)
            self.assertEqual(self.ran, [], bad)
        self.assertIsNotNone(deck.CELL_NAME_RE.fullmatch("omarchy-vm"))

    def test_without_the_persons_yes_nothing_is_typed_into_the_old_pane(self):
        """Review: herdr can't tell an idle shell from vim or ssh running in it, so the deck asks; "no" (the first
        answer) opens a new tab, and no reuse is ever done without the yes."""
        deck._remember_cell_pane("build", "w1:p3", "w1:t2")
        self.panes["w1:p3"] = {"pane_id": "w1:p3", "tab_id": "w1:t2"}
        deck.new_tab("build", self.cwd, ["a4sx", "launch", "--cell", "build"], cell="build")   # no reuse given
        self.assertNotIn("w1:p3", [r[2] for r in self.ran if r[:2] == ["pane", "run"]])
        ui = object.__new__(deck.Deck)
        ui.pdir = lambda n: self.cwd
        seen = {}
        ui.note = lambda lines, title="result": seen.update(lines=lines)
        for answer, used in ((0, False), (1, True)):
            self.ran.clear()
            deck._remember_cell_pane("build", "w1:p3", "w1:t2")   # a new tab is remembered in its place
            ui.choose = lambda title, items, cb: (seen.update(asked=title, items=items), cb(answer))
            ui._start_cell("build", ["a4sx", "launch", "--cell", "build"])
            self.assertEqual(seen["items"], ["no, open a new tab", "yes, start it in that pane"])
            self.assertIn("Is its pane an empty shell prompt", seen["asked"])
            self.assertEqual("w1:p3" in [r[2] for r in self.ran if r[:2] == ["pane", "run"]], used)

    def test_no_leftover_no_question(self):
        ui = object.__new__(deck.Deck)
        ui.pdir = lambda n: self.cwd
        ui.choose = lambda *a: self.fail("asked")
        seen = {}
        ui.note = lambda lines, title="result": seen.update(lines=lines)
        ui._start_cell("build", ["a4sx", "launch", "--cell", "build"])
        self.assertIn("opened the tab «build»", seen["lines"][0])

    def test_a_failed_run_in_the_old_pane_opens_a_new_tab(self):
        deck._remember_cell_pane("build", "w1:p3", "w1:t2")
        self.panes["w1:p3"] = {"pane_id": "w1:p3", "tab_id": "w1:t2"}
        mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: self.ran.append(argv[1:]) or ((1, "", "gone") if argv[3:4] == ["w1:p3"] else (0, "", ""))).start()
        out = deck.new_tab("build", self.cwd, ["a4sx", "launch", "--cell", "build"], cell="build", reuse=("w1:p3", "w1:t2"))
        self.assertIn("opened the tab «build»", out)

    def test_another_cells_pane_is_not_this_ones(self):
        deck._remember_cell_pane("docs", "w1:p3", "w1:t2")
        self.panes["w1:p3"] = {"pane_id": "w1:p3", "tab_id": "w1:t2"}
        self.assertIsNone(deck._leftover_pane("build"))


class Cell01BringUp(unittest.TestCase):
    """cell01 on Omarchy (2026-11-21): "open" really brings the deck to the front; a cell's name only on its own pane."""

    def test_open_focuses_the_new_tab_with_tab_focus(self):
        ran = []
        with mock.patch.object(deck, "deck_state", side_effect=[(None, None, False), ("w1:p7", "w1:t7", True)]), \
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: ran.append(argv[1:]) or (0, "", "")), \
                mock.patch.object(deck.time, "sleep", lambda s: None):
            self.assertEqual(deck.open_deck(True), 0)
        self.assertEqual(ran[0][:3], ["plugin", "pane", "open"])
        self.assertIn("--focus", ran[0])
        self.assertEqual(ran[1], ["tab", "focus", "w1:t7"])

    def test_the_one_agent_here_is_not_named_after_a_cell(self):
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("agents[0] if len(agents) == 1", src)
        self.assertIn('os.path.basename((x.get("cwd") or "").rstrip("/")) == name', src)


class FewerQuestions(unittest.TestCase):
    """cell01's hand-off round trip: the upload mode is a setting (no question); a hand-off named after a cell here
    goes to it; the move view re-reads the library when it opens."""

    def test_the_upload_mode_is_a_setting_scrubbed_by_default_and_as_it_is_is_not_offered(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": d}, clear=False):
            os.environ.pop("DECK_UPLOAD", None)
            self.assertEqual(deck.upload_mode(), "scrubbed")
            with open(os.path.join(d, "upload"), "w", encoding="utf-8") as f:
                f.write("keep-names\n")
            self.assertEqual(deck.upload_mode(), "keep-names")
            with open(os.path.join(d, "upload"), "w", encoding="utf-8") as f:
                f.write("as-it-is\n")
            self.assertEqual(deck.upload_mode(), "scrubbed", "not offered until a4sx #2292")
        self.assertNotIn("--no-scrub", [v[0] for v in deck.UPLOAD_MODES.values()])
        ui = object.__new__(deck.Deck)
        ui.choose = lambda *a: self.fail("asked")
        got = []
        with mock.patch.object(deck, "upload_mode", lambda: "keep-names"):
            ui.with_scrub("backup", got.append)
        self.assertEqual(got, ["--keep-pii"])

    def test_a_hand_off_named_after_a_cell_here_goes_to_it_without_a_question(self):
        ui = object.__new__(deck.Deck)
        ui.d = types.SimpleNamespace(rows=[{"name": "build", "here": True, "running": False}, {"name": "docs", "here": True, "running": False}])
        ui.choose = lambda *a: self.fail("asked")
        seen = []
        ui.start_seeded = lambda r, saved: seen.append((r["name"], saved))
        ui.takeover("handoff-docs")
        self.assertEqual(seen, [("docs", "handoff-docs")])
        asked = []
        ui.choose = lambda title, items, cb: asked.append(title)
        ui.takeover("handoff-elsewhere")
        self.assertEqual(asked, ["which cell of this host continues «handoff-elsewhere»?"])

    def test_a_running_named_cell_is_asked_about_and_no_stops_nothing(self):
        ui = object.__new__(deck.Deck)
        ui.d = types.SimpleNamespace(rows=[{"name": "docs", "here": True, "running": True}])
        seen, asked = [], []
        ui.start_seeded = lambda r, saved: seen.append(r["name"])
        for answer in (0, 1):
            ui.choose = lambda title, items, cb: (asked.append((title, items)), cb(answer))
            ui.takeover("handoff-docs")
        self.assertEqual(asked[0], ("«docs» runs here: stop it and start it from «handoff-docs»?", ["no", "yes, stop it and continue"]))
        self.assertEqual(seen, ["docs"], "only after the yes")

    def test_the_move_view_reads_the_library_once_when_it_opens(self):
        ui = object.__new__(deck.Deck)
        calls = []
        ui.d = types.SimpleNamespace(seen_limit=0, library=[{"name": "x", "vers": "8"}],
                                     load_library=lambda: calls.append(1) or [{"name": "x", "vers": "9"}])
        with mock.patch.object(deck.threading, "Thread", lambda target, daemon: types.SimpleNamespace(start=target)):
            ui.reload_library()
            ui.d.slow_until = time.time() + 60   # the server said "slow down": no call
            ui.reload_library()
        self.assertEqual(calls, [1])
        self.assertEqual(ui.d.library[0]["vers"], "9")
        with open(SRC, encoding="utf-8") as f:
            self.assertIn('if self.view == "move":', f.read())


class Cell01Omarchy(unittest.TestCase):
    """cell01 on Omarchy with plugin #4: herdr restored the cell, s 11 s later opened a second start; a narrow pane broke
    the layout."""

    def _ui(self, cells, agents=()):
        ui = object.__new__(deck.Deck)
        ui.pdir = lambda n: "/tmp"
        seen = {}
        ui.note = lambda lines, title="result": seen.update(lines=lines)

        def jrun(argv, t=30):
            if argv[-3:] == ["mesh", "cells", "--json"]:
                return {"cells": cells}
            if argv[1:3] == ["agent", "list"]:
                return {"result": {"agents": list(agents)}}
            return {}
        p = mock.patch.object(deck, "jrun", jrun)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(deck, "IN_HERDR", True)
        q.start()
        self.addCleanup(q.stop)
        r = mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("started"))
        r.start()
        self.addCleanup(r.stop)
        th = mock.patch.object(deck.threading, "Thread", lambda target, daemon: types.SimpleNamespace(start=target))
        th.start()
        self.addCleanup(th.stop)
        return ui, seen

    def test_s_and_n_on_a_cell_that_runs_now_say_so_and_start_nothing(self):
        ui, seen = self._ui([{"name": "build", "local": {"state": "running"}}],
                            [{"pane_id": "w1:p4", "cwd": "/home/me/projects/build"}])
        ui.msg = ""
        ui.start_cell("build", ["a4sx", "launch", "--cell", "build"])
        self.assertEqual(seen["lines"], ["«build» is already running on this host, in pane w1:p4: g goes there; nothing was started"])

    def test_a_saved_session_start_on_a_cell_that_runs_now_starts_nothing(self):
        ui, seen = self._ui([{"name": "build", "local": {"state": "running"}}])
        ui.bg = lambda title, fn: seen.update(lines=fn())   # the check runs in the background work
        ui.start_seeded({"name": "build", "running": False}, "handoff-build")
        self.assertEqual(seen["lines"], ["«build» is already running on this host; nothing was started"])

    def test_a_second_press_while_checking_starts_nothing_more(self):
        ui, seen = self._ui([{"name": "build", "local": {"state": "stored"}}])
        ui.msg = ""
        ui.starting = {"build"}   # the first press is being checked
        with mock.patch.object(deck, "new_tab", lambda *a, **k: self.fail("a second tab")):
            ui.start_cell("build", ["a4sx", "launch", "--cell", "build"])

    def test_a_stopped_cell_starts(self):
        ui, seen = self._ui([{"name": "build", "local": {"state": "stored"}}])
        ui.msg = ""
        with mock.patch.object(deck, "new_tab", lambda *a, **k: "opened"), mock.patch.object(deck, "_leftover_pane", lambda c: None):
            ui.start_cell("build", ["a4sx", "launch", "--cell", "build"])
        self.assertEqual(seen["lines"], ["opened"])

    def test_by_instance_id_when_known_and_not_while_slowed_down(self):
        ui, seen = self._ui([{"name": "build", "instance_id": "ins_OTHER", "local": {"state": "running"}}])
        self.assertIsNone(ui.running_now("build", "ins_MINE"), "another mesh's «build» runs, not this one")
        self.assertEqual(ui.running_now("build", "ins_OTHER"), "")
        ui.d = types.SimpleNamespace(seen_limit=0, slow_until=time.time() + 60)
        self.assertIsNone(ui.running_now("build", "ins_OTHER"), "no server call while slowed down")

    def test_in_a_narrow_pane_only_closing_works(self):
        ui = object.__new__(deck.Deck)
        ui.narrow = True
        ui.mode = "browse"
        for k in ("b", "s", "x", "S", "enter", "1"):
            self.assertTrue(ui.key(k), k)   # nothing runs, the deck stays
        self.assertTrue(ui.key("esc"), "Esc doesn't quit the deck elsewhere either")
        self.assertFalse(ui.key("q"))
        self.assertFalse(ui.key("\x03"))

    def test_a_narrow_pane_shows_what_to_do_not_a_broken_layout(self):
        ui = object.__new__(deck.Deck)
        out = []
        with mock.patch.object(deck.shutil, "get_terminal_size", lambda d: os.terminal_size((52, 40))), \
                mock.patch.object(deck.sys, "stdout", types.SimpleNamespace(write=out.append, flush=lambda: None)):
            ui.draw()
        text = deck.ANSI.sub("", "".join(out))
        self.assertIn("this pane is 52×40;", text)
        self.assertIn("make the pane wider", text)
        lines = [ln.replace("\033[K", "") for ln in "".join(out).replace("\033[H", "").replace("\033[J", "").split("\n")]
        self.assertTrue(all(len(ln) <= 51 for ln in lines), lines)


class StaleLabel(unittest.TestCase):
    """cell01: a pane where a cell used to run kept its name after the cell moved away. herdr 0.9.5 clears a label
    with --clear-display-agent for the source that set it (tested by cell01 on Omarchy)."""

    def setUp(self):
        deck.LABELED.clear()
        self.addCleanup(deck.LABELED.clear)
        self.ran = []
        p = mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: self.ran.append(argv[1:]) or (0, "", ""))
        p.start()
        self.addCleanup(p.stop)

    def test_a_pane_whose_cell_left_loses_the_name_of_both_sources(self):
        deck.label_panes([{"name": "build", "pane": "w1:p4"}])
        self.assertEqual(self.ran, [["pane", "report-metadata", "w1:p4", "--source", "a4sx-deck", "--display-agent", "build"]])
        self.ran.clear()
        deck.label_panes([{"name": "build", "pane": "w1:p4"}])
        self.assertEqual(self.ran, [], "set once, not at every refresh")
        deck.label_panes([{"name": "build", "pane": None}], [{"name": "build", "local": {"state": "stored"}}])
        self.assertEqual(self.ran, [["pane", "report-metadata", "w1:p4", "--source", "a4sx-deck", "--clear-display-agent"],
                                    ["pane", "report-metadata", "w1:p4", "--source", "a4sx-launch", "--clear-display-agent"]])
        self.ran.clear()
        deck.label_panes([])
        self.assertEqual(self.ran, [], "cleared once")

    def test_a_failed_agent_list_clears_nothing(self):
        deck.label_panes([{"name": "build", "pane": "w1:p4"}])
        self.ran.clear()
        deck.label_panes([{"name": "build", "pane": None}], [], clear=False)
        self.assertEqual(self.ran, [])
        self.assertEqual(deck.LABELED, {"w1:p4": "build"})

    def test_a_cell_of_another_mesh_that_still_runs_keeps_its_name(self):
        deck.label_panes([{"name": "docs", "pane": "w1:p5"}])
        self.ran.clear()
        deck.label_panes([{"name": "build", "pane": None}], [{"name": "docs", "local": {"state": "running"}}])
        self.assertEqual(self.ran, [])
        self.assertEqual(deck.LABELED, {"w1:p5": "docs"})


class IdleShell(unittest.TestCase):
    """cell01's herdr 0.9.5 `pane process-info --pane <id>` samples: an idle bash, `less` in front, the cell's own pane."""
    IDLE = {"result": {"process_info": {"shell_pid": 246966, "foreground_process_group_id": 246966, "foreground_processes": [
        {"argv": ["bash"], "cmdline": "bash", "cwd": "/home/me/projects/build", "name": "bash", "pid": 246966}]}}}
    LESS = {"result": {"process_info": {"shell_pid": 246966, "foreground_process_group_id": 247056, "foreground_processes": [
        {"argv": ["less", "x"], "cmdline": "less x", "cwd": "/home/me", "name": "less", "pid": 247056}]}}}
    CELL = {"result": {"process_info": {"shell_pid": 246966, "foreground_process_group_id": 250001, "foreground_processes": [
        {"argv": ["python3", "a4sx", "launch"], "cmdline": "python3 a4sx launch --cell build", "cwd": "/home/me/projects/build",
         "name": "python3", "pid": 250001},
        {"argv": ["claude"], "cmdline": "claude", "cwd": "/home/me/projects/build", "name": "claude", "pid": 250010}]}}}

    def _idle(self, answer):
        asked = []
        with mock.patch.object(deck, "jrun", lambda argv, t=30: asked.append(argv[1:]) or answer):
            got = deck.pane_is_idle_shell("w1:p3")
        self.assertEqual(asked, [["pane", "process-info", "--pane", "w1:p3"]])
        return got

    def test_the_samples(self):
        self.assertTrue(self._idle(self.IDLE))
        self.assertFalse(self._idle(self.LESS))
        self.assertFalse(self._idle(self.CELL))

    def test_anything_else_is_not_idle(self):
        import copy
        for change in (lambda i: i.update(shell_pid=None), lambda i: i.update(shell_pid=True),
                       lambda i: i["foreground_processes"].append({"pid": 1, "name": "sleep"}),
                       lambda i: i["foreground_processes"][0].update(name="vim"),
                       lambda i: i["foreground_processes"][0].update(pid=1),
                       lambda i: i.update(foreground_processes="bash")):
            a = copy.deepcopy(self.IDLE)
            change(a["result"]["process_info"])
            self.assertFalse(self._idle(a), a)
        self.assertFalse(self._idle({}))
        self.assertFalse(self._idle({"result": {}}))
        a = copy.deepcopy(self.IDLE)
        a["result"]["process_info"]["foreground_processes"][0]["name"] = "-zsh"   # a login shell
        self.assertTrue(self._idle(a))

    def test_an_idle_shell_is_used_without_a_question_anything_else_asks(self):
        ui = object.__new__(deck.Deck)
        ui.pdir = lambda n: "/tmp"
        seen = {}
        ui.note = lambda lines, title="result": seen.update(lines=lines)
        with mock.patch.object(deck, "_leftover_pane", lambda c: ("w1:p3", "w1:t2")), \
                mock.patch.object(deck, "new_tab", lambda *a, **k: f"reuse={k.get('reuse')}"):
            with mock.patch.object(deck, "pane_is_idle_shell", lambda p: True):
                ui.choose = lambda *a: self.fail("asked")
                ui._start_cell("build", ["a4sx", "launch", "--cell", "build"])
                self.assertEqual(seen["lines"], ["reuse=('w1:p3', 'w1:t2')"])
            with mock.patch.object(deck, "pane_is_idle_shell", lambda p: False):
                asked = []
                ui.choose = lambda title, items, cb: asked.append(title)
                ui._start_cell("build", ["a4sx", "launch", "--cell", "build"])
                self.assertEqual(len(asked), 1)


class StaleMarker(unittest.TestCase):
    """Review: a marker left behind (herdr killed the deck's pane) must never make the deck type into another pane
    that later got the same id."""

    def _with(self, marker, panes):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "pane.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(marker)
        by = {p["pane_id"]: p for p in panes}

        def jrun(argv, t=30):
            if argv[1:3] == ["pane", "get"]:   # what herdr's pane get answers (a4sx's live check reads this shape)
                return {"result": {"pane": by.get(argv[3], {})}} if argv[3] in by else {}
            return {"result": {"panes": panes}}
        return path, mock.patch.object(deck, "_marker", lambda: path), mock.patch.object(deck, "jrun", jrun), \
            mock.patch.object(deck, "_deck_alive", lambda pid: False)

    def test_another_pane_with_the_same_id_is_not_the_deck_and_the_marker_goes(self):
        path, a, b, c = self._with("w1:p3 99999 w1:t2", [{"pane_id": "w1:p3", "tab_id": "w1:t5", "agent": "claude"}])
        with a, b, c:
            self.assertEqual(deck.deck_state(), (None, None, False))
        self.assertFalse(os.path.exists(path))

    def test_the_decks_own_restored_pane_is_taken_back(self):
        path, a, b, c = self._with("w1:p3 99999 w1:t2", [{"pane_id": "w1:p3", "tab_id": "w1:t2"}])
        with a, b, c:
            self.assertEqual(deck.deck_state(), ("w1:p3", "w1:t2", False))
        self.assertTrue(os.path.exists(path))

    def test_a_pane_herdr_cant_answer_for_is_not_typed_into(self):
        path, a, b, c = self._with("w1:p3 99999 w1:t2", [{"pane_id": "w1:p3", "tab_id": "w1:t2"}])
        with a, b, c, mock.patch.object(deck, "_pane_has_agent", lambda pane: True):
            self.assertEqual(deck.deck_state(), (None, None, False))

    def test_an_old_marker_without_a_tab_is_never_trusted(self):
        path, a, b, c = self._with("w1:p3 99999", [{"pane_id": "w1:p3", "tab_id": "w1:t2"}])
        with a, b, c:
            self.assertEqual(deck.deck_state(), (None, None, False))


if __name__ == "__main__":
    unittest.main()
