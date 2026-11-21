"""Stdlib tests (python3 -m unittest discover -s tests) for the cell picker's folder and its "stop it there, start
it here" (a4sx #2289), against a fake a4sx and a fake herdr in a temporary HOME: never the real ones."""
import importlib.util
import io
import json
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

FAKE_A4SX = """#!{py}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(["a4sx"] + sys.argv[1:]) + "\\n")
if sys.argv[1:4] == ["mesh", "cells", "--json"]:
    print(open(os.environ["FAKE_CELLS"]).read())
    sys.exit(0)
if sys.argv[1:4] == ["mesh", "cell", "stop"]:
    print("stopped «" + sys.argv[4] + "»")
    sys.exit(int(open(os.environ["FAKE_STOP_RC"]).read()))
sys.exit(0)
"""


class Picker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.home = os.path.realpath(self.tmp.name)
        os.makedirs(os.path.join(d, "bin"))
        exe = self.a4sx = os.path.join(d, "bin", "a4sx")
        with open(exe, "w") as f:
            f.write(FAKE_A4SX.format(py=sys.executable))
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR)
        self.log, self.cells, self.stop_rc = (os.path.join(d, n) for n in ("calls", "cells.json", "stop_rc"))
        self.set_cells([{"name": "cell01", "mesh_id": "m-1", "mesh_name": "testmesh"}])
        with open(self.stop_rc, "w") as f:
            f.write("0")
        self.herdr_calls = []
        env = {"HOME": d, "FAKE_LOG": self.log, "FAKE_CELLS": self.cells, "FAKE_STOP_RC": self.stop_rc,
               "PATH": os.path.join(d, "bin") + os.pathsep + os.environ.get("PATH", ""),
               plugin.ENV_ORIGIN_PANE: "w1:p1", plugin.ENV_ORIGIN_CWD: d, "XDG_CONFIG_HOME": os.path.join(d, "cfg")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

        def run_herdr(args):
            self.herdr_calls.append(args)
            if args[:2] == ["pane", "list"]:
                return {"result": {"panes": [{"pane_id": "w1:p1"}]}}
            if args[:2] == ["pane", "split"]:
                return {"result": {"pane": {"pane_id": "w1:p9"}}}
            return {}
        p = mock.patch.object(plugin, "run_herdr", run_herdr)
        p.start()
        self.addCleanup(p.stop)

    def set_cells(self, cells):
        with open(self.cells, "w") as f:
            json.dump({"v": 1, "cells": cells}, f)

    def a4sx_calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(x) for x in f]

    def pick(self, answers):
        out = io.StringIO()
        with mock.patch.object(plugin, "ask", side_effect=list(answers) + [""] * 3), redirect_stdout(out):
            plugin.pane_cell_picker()
        return out.getvalue()

    def split_cwd(self):
        (split,) = [c for c in self.herdr_calls if c[:2] == ["pane", "split"]]
        return split[split.index("--cwd") + 1]

    # ---- item 1: never the home folder --------------------------------------------------------------------------
    def test_from_the_home_folder_the_cell_starts_in_its_projects_folder_made_now(self):
        out = self.pick(["1"])
        want = os.path.join(self.home, "projects", "cell01")
        self.assertTrue(os.path.isdir(want))
        self.assertEqual(self.split_cwd(), want)
        self.assertIn("The cell starts in ~/projects/cell01 (made just now): a4sx doesn't run a cell in your home "
                      "folder, which holds a4sx's state.", out)
        self.assertIn(["pane", "run", "w1:p9"], [c[:3] for c in self.herdr_calls])

    def test_an_existing_projects_folder_is_used_and_not_called_new(self):
        os.makedirs(os.path.join(self.home, "projects", "cell01"))
        out = self.pick(["1"])
        self.assertIn("The cell starts in ~/projects/cell01: a4sx doesn't run", out)

    def test_from_another_folder_the_cell_starts_there_as_before(self):
        work = os.path.join(self.home, "work")
        os.makedirs(work)
        with mock.patch.dict(os.environ, {plugin.ENV_ORIGIN_CWD: work}):
            out = self.pick(["1"])
        self.assertEqual(self.split_cwd(), work)
        self.assertIn(f"The cell starts in: {work}", out)
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects")))

    def test_a_projects_entry_that_is_no_plain_folder_starts_nothing(self):
        os.makedirs(os.path.join(self.home, "projects"))
        os.symlink("/", os.path.join(self.home, "projects", "cell01"))
        with self.assertRaises(plugin.PluginError) as e:
            self.pick(["1"])
        self.assertIn("isn't a plain folder", str(e.exception))
        self.assertFalse([c for c in self.herdr_calls if c[:2] == ["pane", "split"]])

    def test_from_above_the_home_folder_it_says_so(self):
        with mock.patch.dict(os.environ, {plugin.ENV_ORIGIN_CWD: os.path.dirname(self.home)}):
            out = self.pick(["1"])
        self.assertIn("a4sx doesn't run a cell in a folder above your home folder (it holds a4sx's state).", out)

    def test_without_a_known_folder_too(self):
        with mock.patch.dict(os.environ, {plugin.ENV_ORIGIN_CWD: ""}):
            out = self.pick(["1"])
        self.assertIn("The cell starts in ~/projects/cell01 (made just now): no folder was known.", out)

    # ---- item 2: stop it there, start it here --------------------------------------------------------------------
    def running(self):
        self.set_cells([{"name": "cell01", "mesh_id": "m-1", "mesh_name": "testmesh", "local": {"state": "running"}}])

    def test_a_running_cell_is_stopped_after_a_yes_then_started_here(self):
        self.running()
        out = self.pick(["1", "y"])
        self.assertIn("running here: pick it to stop it there and start it here", out)
        self.assertIn("stopped «cell01»", out)
        stops = [c for c in self.a4sx_calls() if c[1:4] == ["mesh", "cell", "stop"]]
        self.assertEqual(stops, [["a4sx", "mesh", "cell", "stop", "cell01"]])
        self.assertIn(["pane", "run", "w1:p9"], [c[:3] for c in self.herdr_calls])

    def test_no_stops_and_starts_nothing(self):
        self.running()
        out = self.pick(["1", "n"])
        self.assertIn("Nothing was stopped or started.", out)
        self.assertFalse([c for c in self.a4sx_calls() if c[1:3] == ["mesh", "cell"]])
        self.assertFalse([c for c in self.herdr_calls if c[:2] == ["pane", "split"]])

    def test_a_stop_that_fails_starts_nothing(self):
        self.running()
        with open(self.stop_rc, "w") as f:
            f.write("1")
        out = self.pick(["1", "y"])
        self.assertIn("«cell01» wasn't stopped (or not yet), so nothing was started here. Check with `a4sx mesh "
                      "cells`; once it no longer runs here, pick it again.", out)
        self.assertFalse([c for c in self.herdr_calls if c[:2] == ["pane", "split"]])

    def stops(self):
        return [c for c in self.a4sx_calls() if c[1:4] == ["mesh", "cell", "stop"]]

    def test_a_running_cell_with_a_broken_launch_args_file_is_never_stopped(self):
        self.running()
        cfg = os.path.join(self.home, "cfg", "herdr", "plugins", "a4sx.mesh")
        os.makedirs(cfg, exist_ok=True)
        with mock.patch.object(plugin, "launch_args_path", return_value=os.path.join(cfg, "launch-args.json")):
            with open(os.path.join(cfg, "launch-args.json"), "w") as f:
                f.write('{"default": ["--yes"]}')
            with self.assertRaises(plugin.PluginError):
                self.pick(["1", "y"])
        self.assertEqual(self.stops(), [])   # review: stopped only once the start here can go on

    def test_a_running_cell_whose_folder_cant_be_used_is_never_stopped(self):
        self.running()
        os.makedirs(os.path.join(self.home, "projects"))
        os.symlink("/", os.path.join(self.home, "projects", "cell01"))
        with self.assertRaises(plugin.PluginError):
            self.pick(["1", "y"])
        self.assertEqual(self.stops(), [])

    def test_a_folder_that_cant_be_made_starts_nothing(self):
        with open(os.path.join(self.home, "projects"), "w") as f:
            f.write("a file, not a folder")
        with self.assertRaises(plugin.PluginError) as e:
            self.pick(["1"])
        self.assertIn("couldn't be made", str(e.exception))

    def test_a_link_to_the_home_folder_counts_as_home(self):
        link = os.path.join(self.home, "work-link")
        os.symlink(self.home, link)
        with mock.patch.dict(os.environ, {plugin.ENV_ORIGIN_CWD: link}):
            self.pick(["1"])
        self.assertEqual(self.split_cwd(), os.path.join(self.home, "projects", "cell01"))

    def test_a_stop_that_times_out_starts_nothing_and_says_what_next(self):
        self.running()
        import subprocess
        with mock.patch.object(plugin.subprocess, "run", side_effect=subprocess.TimeoutExpired("a4sx", 90)), \
                mock.patch.object(plugin, "own_cells", return_value=[
                    {"name": "cell01", "mesh_id": "m-1", "local": {"state": "running"}}]):
            out = self.pick(["1", "y"])
        self.assertIn("didn't finish within 90 seconds, so nothing was started here. It may still be stopping", out)
        self.assertFalse([c for c in self.herdr_calls if c[:2] == ["pane", "split"]])

    def test_a_standalone_cell_sharing_its_name_is_stopped_as_standalone(self):
        cells = [{"name": "cell01", "mesh_id": "m-1"}, {"name": "cell01", "mesh_id": None}]
        self.assertEqual(plugin.stop_command("a4sx", cells[1], cells),
                         ["a4sx", "mesh", "cell", "stop", "cell01", "--mesh", "standalone"])
        self.assertIsNone(plugin.stop_command("a4sx", {"name": "cell01", "mesh_id": "-x"}, cells))

    def test_two_cells_with_one_name_stop_the_picked_one_by_its_mesh(self):
        cells = [{"name": "cell01", "mesh_id": "m-1"}, {"name": "cell01", "mesh_id": "m-2"}]
        self.assertEqual(plugin.stop_command("a4sx", cells[1], cells), ["a4sx", "mesh", "cell", "stop", "cell01",
                                                                       "--mesh", "m-2"])
        self.assertEqual(plugin.stop_command("a4sx", cells[0], cells[:1]), ["a4sx", "mesh", "cell", "stop", "cell01"])


if __name__ == "__main__":
    unittest.main()
