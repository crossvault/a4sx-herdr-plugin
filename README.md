# a4sx for herdr

A [herdr](https://herdr.dev) plugin for [a4sx](https://session-exchange.com) meshes. One key opens a small menu:

1. start one of your a4sx cells in a new pane,
2. show the peers of your meshes,
3. join a mesh from an invitation link.

Version 0.3.1, early. Made by crossVault GmbH, the company behind a4sx. Not affiliated with herdr.

## What you need

- Linux, or WSL on Windows. This plugin does not support macOS yet.
- herdr 0.9.1 or newer. Omarchy 4.5.0 ships 0.9.1.
- Python 3 as `python3`.
- Claude Code, started once so you are signed in.
- The a4sx CLI, signed in with `a4sx login`, and at least one cell on this machine. The guide is at https://session-exchange.com/guide/meshes.

## Install

```
herdr plugin install crossvault/a4sx-herdr-plugin
herdr plugin action list --plugin a4sx.mesh
```

To pin a version, give `--ref` a branch, a tag or the FULL commit id: herdr hands it to `git fetch`, which can't fetch a short commit id.

herdr shows what the plugin declares and asks before it installs. Over SSH, with no terminal to answer in (`herdr --remote … plugin install`), add `--yes`. The second command lists six actions: `menu`, `start-cell`, `peers`, `join`, `deck`, `deck-label`.

## The deck (0.4.0)

`herdr plugin action invoke --plugin a4sx.mesh deck` opens the deck: the mesh, its cells, your library, the mesh's rules, this host and moving a cell (keys 1 to 5), with each selected row's operations one key away. It opens by itself when a herdr session starts; to change that, put one word into `on-start` in this plugin's config folder (`focus`, the default; `open`; or `off`) or set `DECK_ON_START`. It reads locally every 5 seconds and asks the server about once a minute (a manual refresh with `.` asks at once; when the server says "slow down", it waits longer each time). It needs herdr 0.9.5 or newer for its start hook. A backup uploads the conversation as the `upload` setting says: `scrubbed` (the default: secrets, personal data, host names and paths removed) or `keep-names` (only secrets removed). Set it with one word in the file `upload` in the same folder, or with `DECK_UPLOAD`. The deck shows the setting next to the operation and in the result. "As it is" isn't offered yet: until a4sx #2292 the server scrubs every upload.

To work on the plugin, clone the repository and run `herdr plugin link /path/to/a4sx-herdr-plugin` instead.

**Bind a key first.** herdr has no menu for plugin actions, so one key opens the plugin's menu. The easiest way: open the menu once (below) and choose **4**; the plugin adds the key to herdr's config (for all your herdr sessions; named sessions have none of their own) after you say yes (it backs the file up first and checks it with `herdr config check`). Or add this to `~/.config/herdr/config.toml` yourself:

```toml
[[keys.command]]
key = "prefix+a"
type = "plugin_action"
command = "a4sx.mesh.menu"
description = "a4sx menu"
```

Then run `herdr server reload-config`. Your herdr prefix key (herdr's default is `Ctrl+b`; Omarchy's is `Ctrl+Space`), then `a`, opens the menu. If `a` is taken, pick another key; `herdr config check` names a clash.

Without a key, the menu also opens from a pane. herdr itself then prints its JSON answer to the command first; with the key, nothing is printed:

```
herdr plugin action invoke a4sx.mesh.menu
```

If you linked a clone, run `herdr plugin link` on the folder again after you update it. To remove a linked plugin: `herdr plugin unlink a4sx.mesh`.

## What the menu does

| Choice | What happens |
|---|---|
| **1 Start a cell** | Lists the cells on this machine. You type a number. The plugin splits the pane you were in and types `a4sx launch --cell NAME` there, in the same folder. From your home folder (which a4sx refuses: it holds a4sx's state) the cell starts in `~/projects/NAME`, made if missing, and the picker says so. A cell that already runs on this machine (in VS Code or another pane) is marked; pick it, answer yes, and the plugin runs `a4sx mesh cell stop NAME` first, then starts it here. |
| **2 Mesh peers** | For each of your cells in a mesh: every session by name, where it is (this cell, this machine, your other machine, another account's) and its status (online, offline, waits for approval, …). `i` then Enter shows the ids and keys, Enter refreshes, `q` then Enter closes. An a4sx older than 0.25 shows its own table instead. |
| **3 Join a mesh** | Opens a pane and runs `a4sx mesh join -`. You paste the invitation link there. a4sx shows the invitation and asks before it joins. |
| **4 Open this menu with a key** | Shown only while no key opens the menu. Adds the key to herdr's config.toml after you say yes (see above). |

Enter alone closes the menu.

## Launch flags

The plugin starts a cell as `a4sx launch --cell NAME`. Extra flags come only from your own file `launch-args.json` in the plugin's config directory (`herdr plugin config-dir a4sx.mesh` prints it). The plugin passes on exactly three flags, spelled in full, and refuses the file if it holds anything else:

- `--mesh-reduced-isolation`
- `--local-login`
- `--model=NAME`

So the file cannot start a different cell than the one you pick, cannot turn on `--auto-allow-ipc-messages`, and cannot pass anything through to Claude Code. For any other flag, start the cell yourself in a terminal. Your own a4sx launch profile applies as it does in a terminal.

Example (`launch-args.example.json`):

```json
{"default": ["--mesh-reduced-isolation"], "cells": {"desk": ["--local-login"]}}
```

`default` applies to every cell, `cells` adds flags for one cell by name.

On a host without a4sx's sandbox (most hosts today), a4sx starts a mesh cell only with `--mesh-reduced-isolation`. The plugin never adds that flag. It is your statement to a4sx that you know the cell runs without the sandbox there: its shell commands can change your system and its agent can read your Claude login. Put it in `launch-args.json` yourself once you accept that. Without it a4sx refuses in the new pane, explains why, and starts nothing.

## What it runs and what it sends

The plugin is one Python file with no dependencies. It runs:

- `a4sx mesh cells --json`, to list your cells. It reads only `name`, `instance_id`, `mesh_name`, `mesh_id`, `needs_approval` and `default` from the answer, and shows no key fields.
- `a4sx mesh peers MESH --cell NAME --json --no-browser`, for the peers view, and in the cell picker for a cell a4sx notes as waiting for approval (that note can be out of date: the mesh's own list says whether the cell is active now). An a4sx without `--json` gets its own table shown instead.
- Only when you choose **4** and say yes: it appends the key block to herdr's `config.toml` (after a copy to `config.toml.a4sx-backup`), runs `herdr config check` (and puts the file back if that fails) and `herdr server reload-config`.
- `a4sx launch --cell NAME` with your flags, typed into the new pane.
- `a4sx mesh join -` in a pane, with you at the keyboard.
- `herdr plugin pane open`, `herdr pane list`, `herdr pane split`, `herdr tab create`, `herdr pane run`. The launch command is typed only into a pane that was not there before, with a4sx's full path.

It sends nothing anywhere itself and fetches nothing. The a4sx CLI it starts talks to session-exchange.com.

It never sees an invitation code: you paste the link into a4sx itself, which reads it without showing it. It also removes herdr's context variables (selected text, a clicked link) from the environment of everything it starts.

## Known limits

- **Invoking the menu twice opens two menus** on top of each other. Close each with Enter.
- **After herdr restarts,** a pane that held a cell can come back as plain Claude Code, outside the mesh (seen with herdr 0.9.1, which can't restore cells). Start the cell again from the menu.
- **No click on invitation links.** Without a terminal, `a4sx mesh join` cannot ask "Join?", and a plugin that answers for you would hide the invitation from the person who is about to join. So joining always happens in a pane where you see the invitation and answer yourself.
- This plugin does not support **macOS** yet.

## Tested

| Where | What | Result |
|---|---|---|
| herdr 0.9.5, Arch Linux in WSL, a4sx CLI 0.30.1 | Peers; start a cell without and with `--mesh-reduced-isolation` | Works; a4sx refuses the start without the flag |
| herdr 0.9.1, Omarchy 4.5.0 | Link, key binding, menu, all three choices, against a stand-in for the a4sx CLI | Works |

Not tested yet: joining a mesh through the plugin with a real a4sx CLI, and getting cells back after a herdr restart (herdr 0.9.1 brings them back as plain Claude Code, see Known limits).

## Licence

MIT. See `LICENSE`.
