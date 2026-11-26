"""0.5.0: the deck in the a4sx VS Code extension's terminal (A4SX_DECK_HOST=vscode). A start is one request file in the
extension's channel folder; the deck itself opens no terminal and no herdr tab, and anything outside the starts VS
Code runs is shown to run by hand."""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NONCE = "n" * 32


def _load(env):
    spec = importlib.util.spec_from_file_location("deck_vscode_host", os.path.join(HERE, "..", "deck.py"))
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(mod)
        left = {k: os.environ.get(k) for k in ("A4SX_DECK_CHANNEL", "A4SX_DECK_NONCE")}
    return mod, left


class VSCodeHost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chan = os.path.join(self.tmp.name, "chan")
        os.mkdir(self.chan, 0o700)
        self.work = os.path.join(self.tmp.name, "work")
        self.deck, self.left = _load({"A4SX_DECK_HOST": "vscode", "A4SX_DECK_CHANNEL": self.chan,
                                      "A4SX_DECK_NONCE": NONCE, "HERDR_PANE_ID": "p_1"})
        self.cli = list(self.deck.A4SX_ARGV)
        never = lambda *a, **k: self.fail(f"the deck itself ran something: {a}")   # noqa: E731
        for p in (mock.patch.object(self.deck.subprocess, "Popen", never), mock.patch.object(self.deck, "run", never),
                  mock.patch.object(self.deck, "jrun", never)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def reqs(self):
        names = sorted(os.listdir(self.chan))
        self.assertFalse([n for n in names if n.startswith(".")], "a half-written request was left")
        return [json.load(open(os.path.join(self.chan, n), encoding="utf-8")) for n in names]

    def test_the_mode_and_the_environment(self):
        self.assertTrue(self.deck.VSCODE)
        self.assertFalse(self.deck.IN_HERDR)                  # herdr's variables passed on by VS Code don't count
        self.assertEqual(self.deck.FRONT, "VS Code")
        self.assertEqual(self.left, {"A4SX_DECK_CHANNEL": None, "A4SX_DECK_NONCE": None})   # its a4sx calls don't get them

    def test_every_start_the_deck_sends_is_one_request(self):
        shapes = [["launch", "--cell", "bob-cell"], ["launch", "--cell", "bob-cell", "--new-session"],
                  ["launch", "--cell", "bob-cell", "--a4sx-session", "handoff-bob-cell"], ["launch", "--cell"],
                  ["launch", "--a4sx-session", "my.saved_1"]]
        for i, rest in enumerate(shapes):
            out = self.deck.new_tab("bob-cell", self.work, [*self.cli, *rest], cell="bob-cell")
            self.assertIn("asked VS Code to open the terminal «a4sx: bob-cell» (it shows the outcome): a4sx ", out)
            got = self.reqs()
            self.assertEqual(len(got), i + 1)
            self.assertEqual(got[-1], {"v": 1, "nonce": NONCE, "label": "bob-cell", "cwd": self.work, "args": rest})
        if os.name != "nt":
            for n in os.listdir(self.chan):
                self.assertEqual(os.stat(os.path.join(self.chan, n)).st_mode & 0o777, 0o600)

    def test_anything_else_is_shown_to_run_by_hand_and_sends_nothing(self):
        for rest in (["mesh", "cell", "rename", "a", "b"], ["delete", "x"], ["mesh", "permit", "m", "a", "b", "--none"],
                     ["agent-host"], ["agent-host", "setup-vscode"], ["launch"], ["launch", "--join", "-"],
                     ["launch", "--cell", "a", "--as", "b"], ["launch", "--cell", "a", "--cell", "b"],
                     ["launch", "--cell", "Bad_Name"], ["launch", "--a4sx-session", "has space"],
                     ["launch", "--a4sx-session"], ["launch", "--a4sx-session", "-x"], ["launch", "--new-session"],
                     ["launch", "--cell", "a", "--a4sx-session", "s", "--new-session"]):
            out = self.deck.new_tab("x", self.work, [*self.cli, *rest])
            self.assertTrue(out.startswith(f"run this in a terminal, in {self.work}:  "), (rest, out))
        self.assertEqual(self.reqs(), [])

    def test_a_command_not_through_a4sx_or_a_folder_with_a_line_break_sends_nothing(self):
        self.assertIn("run this in a terminal", self.deck.new_tab("x", self.work, ["/bin/sh", "-c", "launch"]))
        self.assertIn("run this in a terminal", self.deck.new_tab("x", self.work + "\nx", [*self.cli, "launch", "--cell"]))
        self.assertEqual(self.reqs(), [])

    def test_the_label_is_plain_and_short(self):
        self.deck.new_tab("\x1b[31mred\x1b[0m\x07" + "y" * 80, self.work, [*self.cli, "launch", "--cell", "a"])
        self.assertEqual(self.reqs()[0]["label"], "red" + "y" * 37)
        self.deck.new_tab("ev\u202eil\u200b-ok", self.work, [*self.cli, "launch", "--cell", "a"])
        self.assertEqual(self.reqs()[1]["label"], "evil-ok")      # review: no right-to-left or zero-width characters

    def test_a_folder_with_a_format_or_control_character_is_shown_to_run_by_hand(self):
        for bad in ("\t", "\u202e", "\u200b", "\u2028", "\x85"):
            self.assertIn("run this in a terminal", self.deck.new_tab("x", self.work + bad, [*self.cli, "launch", "--cell"]))
        self.assertEqual(self.reqs(), [])

    def test_a_channel_that_is_gone_is_said(self):
        self.tmp.cleanup()
        out = self.deck.new_tab("a", os.path.join(tempfile.gettempdir(), "deck-vsc-w"), [*self.cli, "launch", "--cell", "a"])
        self.assertIn("could not ask VS Code to open a terminal for: a4sx launch --cell a (", out)


class NotVSCode(unittest.TestCase):
    def test_without_a_channel_or_nonce_it_is_the_plain_terminal_as_before(self):
        for env in ({"A4SX_DECK_HOST": "vscode"}, {"A4SX_DECK_HOST": "vscode", "A4SX_DECK_CHANNEL": "/x"},
                    {"A4SX_DECK_HOST": "other", "A4SX_DECK_CHANNEL": "/x", "A4SX_DECK_NONCE": NONCE}):
            with mock.patch.dict(os.environ, {}, clear=False):
                for k in ("A4SX_DECK_HOST", "A4SX_DECK_CHANNEL", "A4SX_DECK_NONCE"):
                    os.environ.pop(k, None)
                deck, _ = _load(env)
            self.assertFalse(deck.VSCODE, env)


if __name__ == "__main__":
    unittest.main()
