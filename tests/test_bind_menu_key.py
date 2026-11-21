"""Stdlib tests (python3 -m unittest discover -s tests) for the menu key's write path, against a fake herdr and a
config COPY under XDG_CONFIG_HOME: never the real ~/.config/herdr/config.toml."""
import importlib.util
import io
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("a4sx_herdr", os.path.join(HERE, "..", "a4sx_herdr.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

FAKE = """#!{py}
import os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["config", "check"] and os.path.exists(os.environ["FAKE_REFUSE"]):
    sys.stderr.write("warning: unknown key ui.foo\\n")
    sys.exit(1)
print("{{}}")
"""
CONFIG = b'[keys]\nprefix = "ctrl+space"\n[ui]\nx = 1\r\n'


class BindMenuKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.herdr = os.path.join(d, "herdr")
        with open(self.herdr, "w") as f:
            f.write(FAKE.format(py=sys.executable))
        os.chmod(self.herdr, os.stat(self.herdr).st_mode | stat.S_IXUSR)
        self.log, self.refuse = os.path.join(d, "calls"), os.path.join(d, "refuse")
        os.makedirs(os.path.join(d, "cfg", "herdr"))
        self.config = os.path.join(d, "cfg", "herdr", "config.toml")
        with open(self.config, "wb") as f:
            f.write(CONFIG)
        os.chmod(self.config, 0o640)
        env = {"XDG_CONFIG_HOME": os.path.join(d, "cfg"), "FAKE_LOG": self.log, "FAKE_REFUSE": self.refuse}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        os.environ.pop("HERDR_CONFIG_PATH", None)
        self.herdr_patch = mock.patch.object(plugin, "HERDR", self.herdr)
        self.herdr_patch.start()

    def tearDown(self):
        self.herdr_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def run_bind(self, answers):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=answers), redirect_stdout(out):
            plugin.bind_menu_key()
        return out.getvalue()

    def calls(self):
        return open(self.log).read().splitlines() if os.path.exists(self.log) else []

    def test_yes_adds_exactly_the_block_keeps_a_byte_exact_backup_and_waits(self):
        out = self.run_bind(["y", ""])          # the last answer: "Press Enter to close" (wait_close)
        self.assertEqual(open(self.config, "rb").read(), CONFIG + plugin.MENU_BINDING.encode())
        self.assertEqual(open(self.config + ".a4sx-backup", "rb").read(), CONFIG)
        self.assertEqual(stat.S_IMODE(os.stat(self.config + ".a4sx-backup").st_mode), 0o640)
        self.assertIn("Ctrl+Space, then a", out)
        self.assertIn("other running herdr sessions get it at their next", out)
        self.assertEqual(self.calls(), ["config check", "config check", "server reload-config"])
        self.assertTrue(plugin.menu_key_bound())

    def test_a_config_herdr_already_rejects_is_left_untouched(self):
        open(self.refuse, "w").close()
        with self.assertRaises(plugin.PluginError) as e:
            self.run_bind(["y"])
        self.assertIn("has a problem already, so nothing was changed", str(e.exception))
        self.assertEqual(open(self.config, "rb").read(), CONFIG)
        self.assertFalse(os.path.exists(self.config + ".a4sx-backup"))
        self.assertEqual(self.calls(), ["config check"])

    def test_no_changes_nothing(self):
        self.run_bind(["n"])
        self.assertEqual(open(self.config, "rb").read(), CONFIG)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
