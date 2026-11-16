#!/usr/bin/env python3
"""a4sx plugin for herdr. Version 0.3.1.

One file, standard library only (a4sx itself needs Python 3.10 or newer, so
Python is there). herdr runs it with the plugin directory as working
directory:

  actions (no terminal):    menu | start-cell | peers | join
  panes (with a terminal):  pane-menu | pane-cell-picker | pane-peers | pane-join

herdr has no menu for plugin actions, so `menu` is the one action a person
binds to a key; it offers the other three.

The plugin is a thin launcher. Rules this file keeps:

  * The only thing it reads from a4sx itself is `a4sx mesh cells --json`.
    Peers are shown by a4sx's own `a4sx mesh peers`, in a pane.
  * It starts a cell only as `a4sx launch --cell NAME`, plus flags from the
    person's own config file. Only the flags in ALLOWED_FLAGS are passed on,
    so the file cannot pick another cell, cannot let a cell act without
    asking, and cannot pass anything through to Claude Code.
  * It types the launch command only into a pane that herdr has just made.
  * It never sees an invitation code. Joining is `a4sx mesh join -` in a
    pane with the person at the keyboard: a4sx reads the code hidden, shows
    the invitation and asks before it joins.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

PLUGIN_ID = "a4sx.mesh"
HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
A4SX = "a4sx"

# The a4sx CLI's own rule for cell names (0.30.2).
CELL_NAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?")
MESH_REF_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}")
INVITE_RE = re.compile(r"a4sx_minv_[A-Za-z0-9_-]{16,128}")

# On a host without its sandbox (most hosts today), a4sx starts a mesh cell
# only with this flag. It is the person's own statement to a4sx; the plugin
# never adds it.
ISOLATION_FLAG = "--mesh-reduced-isolation"

# The only flags the plugin passes on to `a4sx launch`. None: the flag takes no
# value. A pattern: the flag must be written as --flag=VALUE and VALUE must
# match. Everything else in the config file is refused, among it
# --auto-allow-ipc-messages, --config, --env, --profile, --reasoning-proxy,
# --cell, --mesh, --yes, `--` and any plain word.
ALLOWED_FLAGS = {
    ISOLATION_FLAG: None,
    "--local-login": None,
    "--model": re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,127}"),
}

# herdr describes where an action was called in these variables (selected
# text and a clicked link can be in there). They are removed from the
# environment of every process this file starts.
SCRUB_ENV = ("HERDR_PLUGIN_CLICKED_URL", "HERDR_PLUGIN_CONTEXT_JSON", "HERDR_PLUGIN_EVENT_JSON")

ENV_ORIGIN_PANE = "A4SX_HERDR_ORIGIN_PANE"
ENV_ORIGIN_CWD = "A4SX_HERDR_ORIGIN_CWD"


class PluginError(Exception):
    pass


# ---------------------------------------------------------------- helpers


def child_env():
    return {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}


def redact_text(text):
    """Error texts are shown and logged; an invitation code must not be in them."""
    return INVITE_RE.sub("a4sx_minv_[hidden]", text)


def run_herdr(args):
    try:
        r = subprocess.run(
            [HERDR, *args], capture_output=True, text=True, env=child_env(),
            stdin=subprocess.DEVNULL, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PluginError(f"herdr {' '.join(args[:2])}: {e.__class__.__name__}")
    if r.returncode != 0:
        detail = redact_text((r.stderr or r.stdout).strip())[:300]
        raise PluginError(f"herdr {' '.join(args[:2])} failed: {detail}")
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}


def a4sx_path():
    """a4sx as the herdr server sees it; its PATH can be shorter than a shell's."""
    exe = shutil.which(A4SX)
    if not exe:
        candidate = os.path.expanduser("~/.local/bin/a4sx")
        if os.access(candidate, os.X_OK):
            exe = candidate
    if not exe:
        raise PluginError("a4sx is not installed, or not on the PATH of the herdr server.")
    # An absolute path, so a relative PATH entry can never pick up an `a4sx`
    # that lies in the project folder the new pane starts in.
    return os.path.abspath(exe)


def own_cells():
    """This machine's cells, from `a4sx mesh cells --json`.

    Each cell is a JSON object; this file reads its `name`, `mesh_id`,
    `mesh_name`, `needs_approval` and `default` (true for the default cell).
    """
    exe = a4sx_path()
    try:
        r = subprocess.run(
            [exe, "mesh", "cells", "--json"], capture_output=True, text=True, env=child_env(),
            stdin=subprocess.DEVNULL, timeout=45,
        )
    except subprocess.TimeoutExpired:
        raise PluginError("`a4sx mesh cells --json` did not answer within 45 seconds.")
    if r.returncode != 0:
        detail = redact_text((r.stderr or r.stdout).strip())[:600]
        raise PluginError(f"`a4sx mesh cells --json` failed:\n{detail}")
    try:
        data = json.loads(r.stdout)
        return [c for c in (data.get("cells") or []) if isinstance(c, dict) and c.get("name")]
    except (ValueError, AttributeError, TypeError):
        raise PluginError("`a4sx mesh cells --json` did not print the expected JSON. Is a4sx older than 0.30?")


def find_all(obj, key):
    """Every string stored under `key` anywhere in a JSON object, in order."""
    found = []
    if isinstance(obj, dict):
        if isinstance(obj.get(key), str):
            found.append(obj[key])
        for v in obj.values():
            found += find_all(v, key)
    elif isinstance(obj, list):
        for v in obj:
            found += find_all(v, key)
    return found


def find_key(obj, key):
    """First string stored under `key` anywhere in a JSON object."""
    return next(iter(find_all(obj, key)), None)


def printable(text, limit=80):
    """A name that someone else chose (a mesh name), safe to print in a terminal."""
    return "".join(ch for ch in str(text) if ch.isprintable())[:limit]


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def wait_close():
    ask("\nPress Enter to close. ")


def clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def open_pane(entrypoint, env=None):
    """Called from an action: open one of this plugin's panes."""
    # No --workspace or --target-pane: herdr puts an overlay over the active pane.
    args = ["plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", entrypoint, "--focus"]
    for k, v in (env or {}).items():
        if v:
            args += ["--env", f"{k}={v}"]
    run_herdr(args)


def origin_env():
    """Where the person was when they called the action."""
    env = {ENV_ORIGIN_PANE: os.environ.get("HERDR_PANE_ID", "")}
    try:
        context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        context = {}
    for key in ("focused_pane_cwd", "workspace_cwd"):
        cwd = find_key(context, key)
        if cwd and os.path.isdir(cwd):
            env[ENV_ORIGIN_CWD] = cwd
            break
    return env


# ---------------------------------------------------------------- start a cell


def existing_pane_ids():
    """The ids of all panes herdr has now (empty if herdr's list reads differently)."""
    return set(find_all(run_herdr(["pane", "list"]), "pane_id"))


def launch_args_path():
    config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    return os.path.join(config_dir, "launch-args.json") if config_dir else None


def check_launch_args(args, path):
    """Raise PluginError unless every entry is an allowed flag.

    The check is a list of what is allowed, not of what is forbidden: a4sx
    accepts shortened option names, has options that pick another cell or
    change what a cell may do, and hands every other word on to Claude Code as
    a prompt. So an entry passes only if it is an allowed flag spelled in
    full, with its value (if it has one) in the same entry after `=`.
    """
    for a in args:
        if not isinstance(a, str):
            raise PluginError(f"{path}: every entry must be a string.")
        name, equals, value = a.partition("=")
        if name not in ALLOWED_FLAGS:
            shown = printable(a) or "(empty)"
            raise PluginError(
                f"{path} contains `{shown}`.\n"
                "This plugin passes only these flags to a4sx launch, spelled in full:\n"
                f"  {ISOLATION_FLAG}, --local-login, --model=NAME\n"
                "For anything else, start the cell yourself in a terminal."
            )
        pattern = ALLOWED_FLAGS[name]
        if pattern is None and equals:
            raise PluginError(f"{path}: {name} takes no value, but the file has `{printable(a)}`.")
        if pattern is not None and not equals:
            raise PluginError(f"{path}: write {name} with its value in one entry, as {name}=VALUE.")
        if pattern is not None and not pattern.fullmatch(value):
            raise PluginError(f"{path}: `{printable(value)}` is not a usable value for {name}.")


def load_launch_args(cell):
    """Extra flags for `a4sx launch`, from the person's own config file.

    <config dir>/launch-args.json:
      {"default": ["--mesh-reduced-isolation"], "cells": {"desk": ["--local-login"]}}
    Returns the flags for all cells followed by the flags for this cell.
    """
    path = launch_args_path()
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        default = config.get("default", [])
        own = config.get("cells", {}).get(cell, [])
    except (OSError, ValueError, AttributeError, TypeError) as e:
        raise PluginError(f"Cannot read {path}: {e}")
    if not isinstance(default, list) or not isinstance(own, list):
        raise PluginError(f"{path}: flags must be given as a list, like [\"{ISOLATION_FLAG}\"].")
    check_launch_args(default, path)
    check_launch_args(own, path)
    return default + own


def pane_cell_picker():
    print("a4sx: start a cell in a new pane\n")
    exe = a4sx_path()
    cells = own_cells()
    if not cells:
        print("No cells on this machine yet. Create one with a4sx first.")
        return wait_close()

    cwd = os.environ.get(ENV_ORIGIN_CWD, "")
    usable = []
    flag_missing = False
    for cell in cells:
        name = str(cell["name"])
        if not CELL_NAME_RE.fullmatch(name):
            print(f"   -  {name!r}: not a valid cell name, left out")
            continue
        notes = []
        if cell.get("needs_approval"):
            notes.append("waits for approval in its mesh")
        if cell.get("default") is True:
            notes.append("default")
        try:
            flags = load_launch_args(name)
        except PluginError:
            flags = None  # the full message comes when this cell is picked
        if flags is None:
            notes.append("problem in launch-args.json")
        elif cell.get("mesh_id") and ISOLATION_FLAG not in flags:
            flag_missing = True
        usable.append(name)
        mesh = printable(cell.get("mesh_name") or "") or "no mesh"
        note = f"  ({', '.join(notes)})" if notes else ""
        flag_text = f"   flags: {shlex.join(flags)}" if flags else ""
        print(f"  {len(usable):>2}  {name}   mesh: {mesh}{note}{flag_text}")
    if not usable:
        return wait_close()

    if flag_missing:
        # The plugin never adds this flag itself: it is the person's own
        # statement to a4sx. It only says where the flag goes.
        print(
            "\nNote: on a host without a4sx's sandbox (most hosts today), a4sx starts a\n"
            f"cell in a mesh only with {ISOLATION_FLAG}. Without the flag a4sx\n"
            "refuses there in the new pane, explains the risk and starts nothing. If that\n"
            "happens and you accept the risk, put the flag into your own file:\n"
            f"  {launch_args_path() or '<herdr plugin config-dir a4sx.mesh>/launch-args.json'}\n"
            f'  {{"default": ["{ISOLATION_FLAG}"]}}'
        )
    print()
    if cwd:
        print(f"The cell starts in: {cwd}")
    choice = ask("Number of the cell to start (Enter cancels): ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(usable):
        return
    name = usable[int(choice) - 1]
    # The full path: the same a4sx that listed the cells, whatever the PATH of
    # the new pane's shell says.
    command = shlex.join([exe, "launch", "--cell", name, *load_launch_args(name)])

    origin = os.environ.get(ENV_ORIGIN_PANE)
    cwd_args = ["--cwd", cwd] if cwd else []
    before = existing_pane_ids()
    if not before or (origin and origin not in before):
        # Without a readable pane list there is no way to tell a new pane from
        # an old one, so nothing is typed.
        raise PluginError("herdr's pane list could not be read. Run this yourself:\n  " + command)
    before |= {origin} if origin else set()
    if origin:
        result = run_herdr(["pane", "split", origin, "--direction", "right", *cwd_args, "--focus"])
    else:
        result = run_herdr(["tab", "create", "--label", f"cell {name}", *cwd_args, "--focus"])
    # The command is typed only into a pane that was not there before, so it
    # can never land in a session that is already running.
    new = sorted(set(find_all(result, "pane_id")) - before)
    if len(new) != 1:
        raise PluginError("herdr did not say which pane it created. Run this yourself:\n  " + command)
    run_herdr(["pane", "run", new[0], command])


# ---------------------------------------------------------------- peers


def pane_peers():
    while True:
        clear()
        print("a4sx: mesh peers\n")
        cells = own_cells()
        in_mesh = [
            c for c in cells
            if CELL_NAME_RE.fullmatch(str(c["name"])) and MESH_REF_RE.fullmatch(str(c.get("mesh_id") or ""))
        ]
        if not in_mesh:
            print("None of this machine's cells is in a mesh.")
            return wait_close()
        exe = a4sx_path()
        for cell in in_mesh:
            mesh_label = printable(cell.get("mesh_name") or "") or cell["mesh_id"]
            print(f"Mesh {mesh_label}, seen from your cell {cell['name']}:\n")
            sys.stdout.flush()
            try:
                # a4sx's own table, straight to the pane. --no-browser: if the
                # server wants a sign-in, a4sx prints the link and opens nothing.
                subprocess.run(
                    [exe, "mesh", "peers", str(cell["mesh_id"]), "--cell", str(cell["name"]), "--no-browser"],
                    env=child_env(), stdin=subprocess.DEVNULL, timeout=45,
                )
            except subprocess.TimeoutExpired:
                print("(no answer within 45 seconds)")
            print()
        if ask("Enter refreshes, q closes: ").lower() in ("q", "quit", "exit"):
            return


# ---------------------------------------------------------------- join a mesh


def pane_join():
    print("a4sx: join a mesh from an invitation\n")
    exe = a4sx_path()
    print("a4sx asks for the invitation link next. Paste it and press Enter; it is not shown.")
    print("a4sx then shows the invitation and asks before it joins. Ctrl+C cancels.\n")
    sys.stdout.flush()
    try:
        # The terminal goes straight to a4sx. This file never reads the code.
        result = subprocess.run([exe, "mesh", "join", "-"], env=child_env())
        print(f"\na4sx ended with status {result.returncode}.")
    except KeyboardInterrupt:
        print("\nCancelled.")
    wait_close()


# ---------------------------------------------------------------- menu


def pane_menu():
    print("a4sx\n")
    print("   1  Start a cell in a new pane")
    print("   2  Show mesh peers")
    print("   3  Join a mesh (paste an invitation link)\n")
    target = {"1": pane_cell_picker, "2": pane_peers, "3": pane_join}.get(ask("Number (Enter cancels): "))
    if target:
        clear()
        target()


# ---------------------------------------------------------------- entry


ACTIONS = {
    "menu": lambda: open_pane("menu", origin_env()),
    "start-cell": lambda: open_pane("cell-picker", origin_env()),
    "peers": lambda: open_pane("peers"),
    "join": lambda: open_pane("join"),
}
PANES = {
    "pane-menu": pane_menu,
    "pane-cell-picker": pane_cell_picker,
    "pane-peers": pane_peers,
    "pane-join": pane_join,
}


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command in ACTIONS:
        try:
            ACTIONS[command]()
        except PluginError as e:
            print(redact_text(str(e)), file=sys.stderr)
            return 1
        return 0
    if command in PANES:
        try:
            PANES[command]()
        except PluginError as e:
            print("\n" + redact_text(str(e)))
            wait_close()
            return 1
        except KeyboardInterrupt:
            return 130
        return 0
    print(f"usage: a4sx_herdr.py {{{'|'.join([*ACTIONS, *PANES])}}}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
