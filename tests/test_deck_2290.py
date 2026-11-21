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


if __name__ == "__main__":
    unittest.main()
