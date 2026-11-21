"""Stdlib tests (python3 -m unittest discover -s tests) for the deck (a4sx #2290), integrated into the plugin in
0.4.0: the on-start setting, the keys block, the polling budget, and that it reads no credential."""
import importlib.util
import os
import re
import tempfile
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


class StaleMarker(unittest.TestCase):
    """Review: a marker left behind (herdr killed the deck's pane) must never make the deck type into another pane
    that later got the same id."""

    def _with(self, marker, panes):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "pane.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(marker)
        answer = {"result": {"panes": panes}}
        return path, mock.patch.object(deck, "_marker", lambda: path), mock.patch.object(deck, "jrun", lambda argv, t=30: answer), \
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

    def test_an_old_marker_without_a_tab_is_never_trusted(self):
        path, a, b, c = self._with("w1:p3 99999", [{"pane_id": "w1:p3", "tab_id": "w1:t2"}])
        with a, b, c:
            self.assertEqual(deck.deck_state(), (None, None, False))


if __name__ == "__main__":
    unittest.main()
