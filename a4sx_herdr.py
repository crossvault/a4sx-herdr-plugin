#!/usr/bin/env python3
"""a4sx plugin for herdr. Version 0.3.3.

One file, standard library only (a4sx itself needs Python 3.10 or newer, so
Python is there). herdr runs it with the plugin directory as working
directory:

  actions (no terminal):    menu | start-cell | peers | join
  panes (with a terminal):  pane-menu | pane-cell-picker | pane-peers | pane-join

herdr has no menu for plugin actions, so `menu` is the one action a person
binds to a key; it offers the other three.

The plugin is a thin launcher. Rules this file keeps:

  * It reads from a4sx only `a4sx mesh cells --json` and
    `a4sx mesh peers MESH --cell NAME --json` (0.3.2: the peers view shows
    names, where each one is and its status; ids only on request).
  * The one file it may write outside its own config is herdr's config.toml,
    and only when the person answers yes in the menu: it then adds the key
    for the menu (a backup first, `herdr config check` after, the backup back
    if that fails).
  * The one folder it may make is ~/projects/NAME (0.3.3), for a cell picked
    from the home folder, which a4sx refuses to run a cell in. NAME is a
    checked cell name; a link or a file there is refused, never followed.
  * The one a4sx command it runs that changes something is
    `a4sx mesh cell stop NAME` (0.3.3), for a cell that already runs on this
    machine, and only after the person answers yes, once every other check
    of the start has passed.
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

# 0.3.3 (#2289): a4sx refuses to run a cell in your home folder (it holds a4sx's state), so a pick from there
# starts the cell in its own folder below this one, made if missing
PROJECTS_DIR = "projects"


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

    Each cell is a JSON object; this file reads its `name`, `instance_id`,
    `mesh_id`, `mesh_name`, `needs_approval`, `default` (true for the
    default cell), `local.state` and `registry.state` (a4sx 0.25 or newer).
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


# ---------------------------------------------------------------- key for the menu

MENU_ACTION = f"{PLUGIN_ID}.menu"
MENU_KEY = "prefix+a"
MENU_BINDING = (
    "\n[[keys.command]]\n"
    f'key = "{MENU_KEY}"\n'
    'type = "plugin_action"\n'
    f'command = "{MENU_ACTION}"\n'
    'description = "a4sx menu"\n'
)


def herdr_config_path():
    """The config.toml herdr reads: $HERDR_CONFIG_PATH when set, else $XDG_CONFIG_HOME/herdr (~/.config/herdr)."""
    if os.environ.get("HERDR_CONFIG_PATH"):
        return os.environ["HERDR_CONFIG_PATH"]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "herdr", "config.toml")


def herdr_prefix():
    """herdr's prefix key as config.toml sets it under [keys] (`prefix = "ctrl+space"`, or the first of
    `prefix = ["ctrl+space", "ctrl+s"]`), shown as "Ctrl+Space"; herdr's default "Ctrl+b" when the file sets none;
    "your herdr prefix key" when it sets one this file can't read."""
    try:
        with open(herdr_config_path(), encoding="utf-8") as f:
            text = f.read(1 << 20)
    except (OSError, ValueError):
        return "Ctrl+b"
    table = re.search(r'(?ms)^\[keys\][ \t]*(?:#[^\n]*)?$(.*?)(?=^\[)', text + "\n[")
    body = table.group(1) if table else ""
    if not re.search(r'(?m)^\s*prefix\s*=', body) and not re.search(r'(?m)^\s*keys\.prefix\s*=', text):
        return "Ctrl+b"
    m = re.search(r'(?m)^\s*prefix\s*=\s*(?:\[\s*)?["\']([A-Za-z0-9+_-]{1,32})["\']', body)
    if not m:
        return "your herdr prefix key"
    return "+".join(part if len(part) == 1 else part[:1].upper() + part[1:] for part in m.group(1).split("+"))


def menu_key_bound():
    """Whether herdr's config.toml binds a key to this plugin's menu (read only)."""
    try:
        with open(herdr_config_path(), encoding="utf-8") as f:
            text = f.read(1 << 20)
    except OSError:
        return False
    return re.search(r'(?m)^\s*command\s*=\s*"' + re.escape(MENU_ACTION) + '"', text) is not None   # not a comment


def bind_menu_key():
    """Add the menu's key to herdr's config.toml, only after a yes: a backup first, `herdr config check` after (the
    backup goes back if it fails), then `herdr server reload-config`."""
    path = herdr_config_path()
    print(f"This adds a key for the a4sx menu to herdr's config, for all your herdr sessions ({path}):")
    print(MENU_BINDING)
    print(f"Then {herdr_prefix()}, then {MENU_KEY.split('+', 1)[1]}, opens this menu in every herdr session. If that key is")
    print("taken, edit the line later; `herdr config check` names a clash.")
    if ask("Add it now? [y/N] ").lower() not in ("y", "yes"):
        return
    try:   # a config herdr already complains about: say so, change nothing (the key couldn't be checked)
        run_herdr(["config", "check"])
    except PluginError as e:
        raise PluginError(f"herdr's config has a problem already, so nothing was changed. Fix it first:\n{e}")
    backup = path + ".a4sx-backup"
    try:
        with open(path, "rb") as f:   # bytes: the file goes back exactly as it was
            old = f.read()
    except FileNotFoundError:
        old = None
    except OSError as e:
        raise PluginError(f"herdr's config can't be read ({e.__class__.__name__}); nothing was changed.")
    try:
        if old is not None:
            with open(backup, "wb") as f:
                f.write(old)
            shutil.copymode(path, backup)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "ab") as f:
            f.write(MENU_BINDING.encode("utf-8"))
    except OSError as e:
        raise PluginError(f"herdr's config can't be written ({e.__class__.__name__}); nothing was changed.")
    try:
        run_herdr(["config", "check"])
    except PluginError as e:
        try:   # put it back exactly as it was
            if old is None:
                os.unlink(path)
            else:
                with open(path, "wb") as f:
                    f.write(old)
        except OSError:
            pass
        raise PluginError(f"herdr didn't accept the key, so the config is as it was:\n{e}")
    try:
        run_herdr(["server", "reload-config"])
        print("\nDone: the key works now in this herdr session; other running herdr sessions get it at their next")
        print("reload or start.")
    except PluginError:
        print("\nAdded. It works after `herdr server reload-config` (or the next herdr start).")
    if old is not None:
        print(f"The config as it was before is in {backup}.")
    wait_close()   # the result stays readable (an error waits in main())


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


def running_here(exe, cell):
    """The cell already runs on this machine: `a4sx mesh cells --json` says so (`local.state`, a4sx 0.25 or newer,
    from this machine's own running proxies). Nothing else is guessed: "online" in the mesh's list can be another
    machine after a start elsewhere. A second start here would be refused."""
    local = cell.get("local")
    return isinstance(local, dict) and local.get("state") == "running"


def still_waiting(exe, cell):
    """`needs_approval` is what a4sx noted when the cell was made, and an a4sx that predates the fix never clears it. The
    mesh's own list says whether the cell is active now (its own row, `a4sx mesh peers --json`); when that can't be
    read, the note stays."""
    reg = cell.get("registry")
    state = reg.get("state") if isinstance(reg, dict) else None
    if state in ("active", "pending", "reserved"):   # `mesh cells --json` asked the server already (signed in)
        return state != "active"
    iid = cell.get("instance_id")
    if not iid or not MESH_REF_RE.fullmatch(str(cell.get("mesh_id") or "")):
        return True
    peers = mesh_peers_json(exe, cell)
    mine = [p for p in peers or [] if isinstance(p, dict) and p.get("instance_id") == iid]
    return not (len(mine) == 1 and mine[0].get("state") == "active")


def cell_folder(cwd, name):
    """(folder, note): where the cell starts. The folder the person was in, unless that is the home folder or one
    above it (a4sx refuses those: the home folder holds a4sx's state), or unknown: then ~/projects/NAME, made if
    missing. `note` says which and why (None when it is the folder they were in)."""
    home = os.path.realpath(os.path.expanduser("~"))
    here = os.path.realpath(cwd) if cwd else ""
    if here and here != home and not home.startswith(here.rstrip(os.sep) + os.sep):
        return cwd, None
    folder = os.path.join(home, PROJECTS_DIR, name)
    shown = os.path.join("~", PROJECTS_DIR, name)
    if os.path.islink(folder) or (os.path.lexists(folder) and not os.path.isdir(folder)):
        raise PluginError(f"{shown} is there but isn't a plain folder, so the cell wasn't started. Move it away, or "
                          "start the cell from a pane in another folder.")
    made = not os.path.isdir(folder)
    if made:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            raise PluginError(f"{shown} couldn't be made ({e.strerror or e}), so the cell wasn't started. Start it "
                              "from a pane in another folder.")
    head = f"The cell starts in {shown}{' (made just now)' if made else ''}: "
    if not here:
        return folder, head + "no folder was known."
    if here == home:
        return folder, head + "a4sx doesn't run a cell in your home folder, which holds a4sx's state."
    return folder, head + "a4sx doesn't run a cell in a folder above your home folder (it holds a4sx's state)."


def stop_command(exe, cell, cells):
    """`a4sx mesh cell stop NAME`; when another cell here has the same name, with `--mesh MESH_ID`, or
    `--mesh standalone` for one in no mesh (a4sx refuses an ambiguous name). None when the mesh id can't be used."""
    name = str(cell["name"])
    same = [c for c in cells if c.get("name") == name]
    if len(same) < 2:
        return [exe, "mesh", "cell", "stop", name]
    mesh = str(cell.get("mesh_id") or "") or "standalone"
    return [exe, "mesh", "cell", "stop", name, "--mesh", mesh] if MESH_REF_RE.fullmatch(mesh) else None


def stop_it_there(exe, cell, cells):
    """0.3.3 (#2289): the cell runs here already (VS Code, another pane): ask, then `a4sx mesh cell stop`. True when
    it was stopped; a4sx's own output is shown either way."""
    name = str(cell["name"])
    print(f"\n«{name}» already runs on this machine (in VS Code or another pane). A second start would be refused.")
    if ask("Stop it there and start it here? [y/N] ").lower() not in ("y", "yes"):
        print("Nothing was stopped or started.")
        return False
    argv = stop_command(exe, cell, cells)
    if argv is None:
        print(f"«{name}» shares its name with another cell here and its mesh id can't be used, so nothing was "
              f"stopped or started. Stop it where it runs (/exit in its Claude Code), then pick it again.")
        return False
    try:
        r = subprocess.run(argv, capture_output=True, text=True, env=child_env(), stdin=subprocess.DEVNULL,
                           timeout=90)
    except subprocess.TimeoutExpired:
        print(f"`{shlex.join(argv[1:])}` didn't finish within 90 seconds, so nothing was started here. It may still "
              f"be stopping: check with `a4sx mesh cells`, then pick it again.")
        return False
    out = redact_text((r.stdout + r.stderr).strip())
    if out:
        print(out[:800] + (" […]" if len(out) > 800 else ""))
    if r.returncode != 0:
        print(f"«{name}» wasn't stopped (or not yet), so nothing was started here. Check with `a4sx mesh cells`; "
              f"once it no longer runs here, pick it again.")
        return False
    return True


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
        if running_here(exe, cell):
            notes.append("running here: pick it to stop it there and start it here")
        if cell.get("needs_approval") and still_waiting(exe, cell):
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
        usable.append(cell)
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
    choice = ask("Number of the cell to start (Enter cancels): ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(usable):
        return
    cell = usable[int(choice) - 1]
    name = str(cell["name"])
    # Everything that can still refuse the start comes first (review: a running cell is stopped only once the
    # start here can go on): its flags, its folder, herdr's pane list.
    # The full path: the same a4sx that listed the cells, whatever the PATH of
    # the new pane's shell says.
    command = shlex.join([exe, "launch", "--cell", name, *load_launch_args(name)])
    cwd, note = cell_folder(cwd, name)
    origin = os.environ.get(ENV_ORIGIN_PANE)
    cwd_args = ["--cwd", cwd] if cwd else []

    def pane_ids():
        ids = existing_pane_ids()
        if not ids or (origin and origin not in ids):
            # Without a readable pane list there is no way to tell a new pane from
            # an old one, so nothing is typed.
            raise PluginError("herdr's pane list could not be read. Run this yourself:\n  " + command)
        return ids
    pane_ids()
    if running_here(exe, cell) and not stop_it_there(exe, cell, cells):
        return wait_close()
    print(note or f"The cell starts in: {cwd}")
    before = pane_ids()   # again: the stop may have closed a pane
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


PEER_STATE = {"active": "active", "pending": "waits for approval", "reserved": "not started yet",
              "revoked": "removed", "unknown": "seen by a running cell here"}


def peer_lines(peers, me, here, details=False):
    """The readable peers list, like VS Code's tree: name, where it is, status; ids only with `details`."""
    rows = []
    for p in peers if isinstance(peers, list) else []:
        if not isinstance(p, dict):
            continue
        iid = str(p.get("instance_id") or "")
        name = printable(p.get("name") or "", 48) or "(no name)"
        if iid and iid == me:
            where = "this cell"
        elif iid in here:
            where = "this machine"
        elif p.get("own") is True:
            where = "your other machine"
        else:
            # an account is all this file knows: one person's second account is never shown as another person
            where = "another account's"
        state = PEER_STATE.get(str(p.get("state") or "unknown"), printable(p.get("state") or "", 24))
        presence = p.get("presence")
        if state == "active" and presence in ("online", "offline", "away"):
            state = "online" if presence == "online" else presence
        if p.get("access") == "blocked":
            state += ", messages blocked"
        rows.append((name, where, state, iid, printable(p.get("aid") or "", 64)))
    rows.sort(key=lambda r: (r[1] != "this cell", r[1] != "this machine", r[0]))
    if not rows:
        return ["  (no sessions listed)"]
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    out = []
    for name, where, state, iid, aid in rows:
        out.append(f"  {name:<{w1}}  {where:<{w2}}  {state}")
        if details:
            out.append(f"  {'':<{w1}}  id {printable(iid, 40) or '?'}" + (f", key {aid}" if aid else ""))
    return out


def mesh_peers_json(exe, cell):
    """`a4sx mesh peers MESH --cell NAME --json` (a4sx 0.25.0 or newer), or None."""
    try:
        r = subprocess.run(
            [exe, "mesh", "peers", str(cell["mesh_id"]), "--cell", str(cell["name"]), "--json", "--no-browser"],
            capture_output=True, text=True, env=child_env(), stdin=subprocess.DEVNULL, timeout=45,
        )
        data = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return data.get("peers") if isinstance(data, dict) else None


def pane_peers():
    details = False
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
        here = {str(c.get("instance_id") or "") for c in cells} - {""}
        for cell in in_mesh:
            mesh_label = printable(cell.get("mesh_name") or "") or cell["mesh_id"]
            print(f"Mesh {mesh_label}, seen from your cell {cell['name']}:\n")
            sys.stdout.flush()
            peers = mesh_peers_json(exe, cell)
            if peers is not None:
                print("\n".join(peer_lines(peers, str(cell.get("instance_id") or ""), here, details)))
            else:
                try:
                    # an older a4sx (or no answer as JSON): its own table, straight to the pane. --no-browser: if
                    # the server wants a sign-in, a4sx prints the link and opens nothing.
                    subprocess.run(
                        [exe, "mesh", "peers", str(cell["mesh_id"]), "--cell", str(cell["name"]), "--no-browser"],
                        env=child_env(), stdin=subprocess.DEVNULL, timeout=45,
                    )
                except subprocess.TimeoutExpired:
                    print("(no answer within 45 seconds)")
            print()
        what = "hides the ids" if details else "shows ids and keys"
        answer = ask(f"Enter refreshes; i then Enter {what}; q then Enter closes: ").lower()
        if answer in ("q", "quit", "exit"):
            return
        if answer == "i":
            details = not details


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
    print("   3  Join a mesh (paste an invitation link)")
    bound = menu_key_bound()
    if not bound:
        print("   4  Open this menu with a key (adds it to herdr's config)")
    print()
    if not bound:
        print("No key opens this menu yet: choose 4, or see the plugin's README.\n")
    choices = {"1": pane_cell_picker, "2": pane_peers, "3": pane_join}
    if not bound:
        choices["4"] = bind_menu_key
    target = choices.get(ask("Number (Enter cancels): "))
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
