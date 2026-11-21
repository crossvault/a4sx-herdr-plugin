# Changelog

## 0.4.2 - 2026-11-21

Follow-ups from cell01's Omarchy recheck (herdr 0.9.5, a4sx #2309):
- **Leftover tabs.** After a herdr restart, the tabs the deck once started cells in can pile up as empty shells. In the host view (4), **L** lists the ones in which every pane shows a bare shell prompt (herdr's `pane process-info`), names their cells and asks. It closes them only after a yes, and only those still all bare prompts by then (`herdr tab close`). The deck's own tab is never closed.
- Before the start line is typed into a cell's old pane, a half-typed line there is cleared with Ctrl-U (`herdr pane send-keys … ctrl+u`). That happens only when process-info shows the bare shell, because in less or vim the key means something else.
- The pane reused is only ever the one the deck last started that cell in, never another idle pane of its folder; a test pins this.

## 0.4.1 - 2026-11-21

From cell01's round trip with a real Claude Code (a4sx #2309):
- **Fewer questions.** A backup (b) no longer asks how to upload, and it uploads at once. The deck's `upload` setting decides: `scrubbed` (the default) or `keep-names`, set in the file `upload` or with `DECK_UPLOAD`. The operation and its result show it. `keep-names` keeps names, hosts and paths on this computer; the server still redacts them until a4sx #2292. "As it is" is no longer offered: until a4sx #2292 the server scrubs every upload, so it wasn't as it is.
- Starting from a hand-off named after a cell stored here (`handoff-<cell>`) goes to that cell without asking which one. If that cell is running, the deck asks first, because it is stopped before the start.
- From cell01's Omarchy check of 0.4.0: before **s**, **n** or a start from a saved session, the deck reads the cell's state again (`a4sx mesh cells --json`, by its instance id, in the background, and not while the server says "slow down"). After a herdr restart herdr restores a running cell by itself, and the deck's rows can be seconds old, so a cell that already runs is no longer started a second time. It says instead: "«cell» is already running on this host, in pane …: g goes there; nothing was started".
- A pane narrower than 101 columns or shorter than 20 lines no longer breaks the layout. The deck shows its size, the size it needs, "make the pane wider (or zoom it in herdr)", and that q closes it. Only q and Ctrl-C work there, so no operation runs unseen.
- A cell's old pane from before a herdr restart is used without a question when herdr's `pane process-info` shows a bare shell prompt there: the foreground process group is the shell's own, it is the only foreground process, and it is bash, zsh, fish or sh. In any other case, or when process-info doesn't answer, the deck asks as in 0.4.0.
- A pane whose cell left it (moved away or stopped) loses the cell's name in herdr's agents list. The deck clears the name it set and the one `a4sx launch` set (`herdr pane report-metadata … --clear-display-agent`, once per source). It sets a cell's name once rather than at every refresh. A name set before this deck started (by `a4sx launch` or an earlier deck) isn't cleared; nor is any name while herdr's agent list doesn't answer.
- The move view (5) reads your library again when you switch to it (one `a4sx list`, none while the server says "slow down"), so a version pushed meanwhile is listed.

## 0.4.0 - 2026-11-21

- **The deck** (a4sx issue #2290). One pane shows the mesh, its cells, your a4sx library, the mesh's rules, this host and moving a cell (keys 1 to 5), with the selected row's operations on the right, each one key. Short commands run in place; anything you answer, or that opens the browser, runs in a new herdr tab. Everything it runs is an ordinary `a4sx` or `herdr` command; the deck stores only the id of its own pane.
- The deck is the first thing a herdr session shows. Set `on-start` to `focus` (the default), `open` (a tab, not in front) or `off` (only the cells' names go into the agents list), with `DECK_ON_START` or one word in the file `on-start` in this plugin's config folder. After a herdr restart it starts again in its restored pane.
- It reads locally every 5 seconds and asks the server about once a minute (some things every 5 minutes; a manual refresh asks at once), and waits longer each time the server says "slow down".
- **herdr 0.9.5 or newer** is needed now (the deck's start hook). On herdr 0.9.1, keep plugin 0.3.3.
- If you installed cell01's standalone `a4sx.deck` plugin, uninstall it: both would open a deck at start. The `on-start` file now lives in the `a4sx.mesh` config folder. It never reads or shows a key or a sign-in.
- New actions: `deck` (open the deck) and `deck-label` (the cells' names in the agents list).
- This host (view 4): while the agent host runs, **S** stops it with `a4sx agent-host stop`, the same stop as Ctrl-C in its tab (VS Code is told first, then the cells it started end). It asks first, naming the cells and counting the plain conversations open in it (read fresh); with none it stops at once. This needs a4sx 0.59.15 or newer: with an older a4sx, S asks nothing and stops nothing, and says to run `a4sx update` or to use Ctrl-C in the host's tab.
- From cell01's bring-up on Omarchy: a cell's name goes only on the pane of an agent whose folder is named after the cell, never on "the one agent in this herdr session" (it had named a plain Claude Code pane after a cell). **open** now really brings the deck to the front (herdr 0.9.5 needs `tab focus` after opening the pane).
- After a herdr restart a cell's old pane stays as an empty shell. **s** and **n** now offer to start the cell there again. They offer it only for the pane the deck last started that cell in, still in the same tab, with no agent in it. Herdr can't tell an empty shell prompt from vim or ssh running there, so the deck asks first; the first answer, **no, open a new tab**, opens a new tab as before. Everything typed into a shell is quoted, a cell name has to follow a4sx's rule (also for **bring**), and a folder or command with a backslash or line break is refused rather than typed.
- Moving a cell (view 5): **bring here** starts one of your cells that runs elsewhere on this host, signed in; **Start from a saved session** starts a cell here seeded from a saved conversation. There is no hand-off yet: the conversation follows a moved cell once a4sx #2292 lands (an exact copy; a scrubbed one would change its peers' names).

## 0.3.3 - 2026-11-21

From the owner's live walkthrough on Omarchy (herdr 0.9.5, a4sx issue #2289):

- **A cell picked from your home folder starts in `~/projects/NAME`**, made if missing. a4sx refuses to run a cell in your home folder (it holds a4sx's state), so the pane used to end in that refusal. The picker says which folder and why. From any other folder the cell starts where you were, as before.
- **"Stop it there and start it here."** A cell that already runs on this machine (in VS Code or another pane) is marked in the list. Pick it and answer yes: the plugin runs `a4sx mesh cell stop NAME` (with `--mesh MESH_ID`, or `--mesh standalone`, when two cells here share the name), only once everything else the start needs has been checked, shows what a4sx said, and starts the cell in the new pane only once it was stopped. No starts nothing.

## 0.3.2 - 2026-11-21

From the first live run on Omarchy (herdr 0.9.1):

- **A key for the menu from the menu itself.** While no key opens it, the menu offers **4 Open this menu with a key**. After a yes, the plugin appends `[[keys.command]] key = "prefix+a" … command = "a4sx.mesh.menu"` to herdr's config.toml: a backup first, `herdr config check` after (the file goes back if herdr refuses it), then `herdr server reload-config`. The README says why `herdr plugin action invoke` prints herdr's JSON first, and that a key avoids it.
- **A readable peers view.** It used to show a4sx's raw table (an instance id, a 43-character key, `None` for the isolation an admin sees). Now each session is shown by name, where it is (this cell / this machine / your other machine / another account's) and its status (online, offline, waits for approval, messages blocked). `i` shows the ids and keys. It reads `a4sx mesh peers --json`; an older a4sx gets its own table as before.
- **The cell picker marks a cell that already runs here "(running here)"**, from `a4sx mesh cells --json` (`local.state`, this machine's running proxies), so you aren't sent into a refusal.
- The key prompt names your prefix as config.toml sets it ("Ctrl+Space, then a") and says the key is for all your herdr sessions. Peers of other accounts show as "another account's" (one person can have two accounts).
- **The cell picker no longer says "waits for approval" for an active cell.** a4sx's note is what it knew when the cell was made. For a cell with that note, the picker asks the mesh's own list, and shows the note only while the cell really waits.


## 0.3.1 - 2026-11-14

First public version.

- One menu action (`a4sx.mesh.menu`) to bind to a single key, offering: start a cell in a new pane, show mesh peers, join a mesh.
- Start a cell: lists this machine's cells and types `a4sx launch --cell NAME` (with a4sx's full path) into a new pane in the same folder, only into a pane herdr has just created. Extra flags come only from your own `launch-args.json`, and only three pass, spelled in full: `--mesh-reduced-isolation`, `--local-login`, `--model=NAME`. The plugin never adds `--mesh-reduced-isolation` itself.
- Peers: a4sx's own table, with `--no-browser`.
- Join: runs `a4sx mesh join -` in a pane with you at the keyboard; the plugin never sees an invitation code.
