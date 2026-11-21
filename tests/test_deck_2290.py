"""Stdlib tests (python3 -m unittest discover -s tests) for the deck (a4sx #2290), integrated into the plugin in
0.4.0: the on-start setting, the keys block, the polling budget, and that it reads no credential."""
import importlib.util
import os
import re
import tempfile
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
        return ui, {k: (label, fn) for k, label, fn in ui.host_ops()}

    def test_running_offers_stop_and_runs_the_clis_stop_in_the_background(self):
        ui, ops = self._ops(True)
        self.assertIn("S", ops)
        self.assertNotIn("A", ops)
        seen = {}
        with mock.patch.object(deck.Deck, "bg", lambda self, title, fn: seen.update(title=title, lines=fn())), \
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: seen.update(argv=argv, t=timeout) or (0, "a4sx agent host: stopped (pid 4)\n", "")):
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
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: (1, "", "TimeoutExpired: a4sx agent-host stop")):
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
                mock.patch.object(deck, "run", lambda argv, timeout=30, cwd=None: seen.update(argv=argv) or (0, "stopped\n", "")):
            ops["S"][1]()
        self.assertEqual(seen["argv"][-2:], ["agent-host", "stop"])

    def test_stopped_offers_start_not_stop(self):
        _ui, ops = self._ops(False)
        self.assertIn("A", ops)
        self.assertNotIn("S", ops)


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
