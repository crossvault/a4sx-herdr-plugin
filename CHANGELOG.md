# Changelog

## 0.4.7 - 2026-11-22

From cell01's Omarchy check of 0.4.6 (a4sx #2309 q, r):
- **r on a cell whose tab isn't in ~/projects/<cell>** starts it in the folder its last session ran in, from a4sx's own record on this host, and reuses the bare shell prompt open in that folder. Before, it opened a new tab in a new folder ~/projects/<cell>, and Claude Code asked whether to trust that folder. If the record is missing, or its folder is gone, it uses ~/projects/<cell> as before.
- **r on a stopped cell** runs no stop first. Before, the first result line was the CLI's "nothing was stopped", which read like an error.
- **r on a cell that is online on another host** says so before the list of saved conversations, not after you pick one. The fresh check after the pick stays.
- **The where column** reads "● runs elsewhere" for a cell stored here that runs on another host. Before, view 1 cut "● elsewhere now · stored here" short. The details still say "stored on <this host> too".

## 0.4.6 - 2026-11-22

From cell01's move round trip (a4sx #2309 q, r):
- **r (restore from a saved state)** lists the saved conversations newest first and marks this cell's own saves (exactly `<cell>-backup`, `handoff-<cell>` and `<cell>`) with ◆. When the cell's tab from before a herdr restart shows a bare shell prompt, it starts there instead of opening one more tab. It checks first that the cell isn't online on another host, as **s** and **n** do; if it is, it says the cell can't be started here from a saved conversation yet and starts nothing. A second Enter while that check runs starts nothing more.
- **A cell stored here that runs on another host** reads "● elsewhere now · stored here" instead of "◇ stored here" next to "● online". Its details say "on another host now; stored on <this host> too" instead of "on <this host>", and view 5 lists it with the cells on other hosts.
- **The messages panel** says "reading this host's delivery records …" until its first read is done (it can take a minute), not "no messages recorded on this host yet". A deck without a mesh says "no messages recorded on this host yet" right away.
- **m on a cell that runs here** shows that cell's recent deliveries with the mesh's cells that don't run on this host, not "«cell» ↔ «cell»" and an old record of another cell stored here.

## 0.4.5 - 2026-11-22

From cell01's Omarchy recheck of 0.4.4 (a4sx #2309 F6, bb):
- **F6 in the common case.** After one round trip, every cell is also stored on the other host, with its old tab there. Before, **s** on such a cell, while it was online on another host, reused its old tab and said "started"; view 5's **n** opened a new tab. In both cases the CLI then refused the start. Now **s** and **n** check first whether the cell is online and doesn't run on this host. The deck's presence can be a minute old, so they read `mesh peers` again before refusing. If the cell is still online there, they show the same note as for a cell stored only elsewhere, and open, reuse and type nothing. A cell just stopped here starts as before, and when the read can't be made (slowed down, an error), nothing is refused and the CLI decides in the tab.
- **No claimed start.** The result line says "ran the start in its tab «cell» again (… the tab shows the outcome)" or "opened the tab «cell» (it shows the outcome)", because the CLI in the tab may still refuse.
- **The first cell's tab** is named after the folder you type, not «first cell».
- **Messages of this host's cells** are read for every peer that doesn't run here. Remote peers come first. Before, a peer also stored here was left out, so the panel said "no messages recorded on this host yet" while `a4sx mesh deliveries` listed hundreds.
- **A running cell whose folder isn't named after it** is found in the herdr pane its launch runs in: the agent pane whose shell is the nearest of the launch's parent processes. It never takes a pane that another cell has by its folder name, and the launch must be that pane's foreground job, so an agent host started in a Claude Code pane doesn't give its cells that pane. herdr `pane process-info` is asked once per pane, and a cell's answer, including "none", is kept until the panes change. Before, it read "here, no pane".

## 0.4.4 - 2026-11-22

From cell01's from-scratch runs (a4sx #2309 F6, bb):
- **Bring here on a cell that is online on another host** says so first: "«cell» is online on another host now, so it can't be brought here yet: stop it there first (on that host's deck: x stops it), then bring it here". It creates no folder and opens no tab; **.** reads the mesh again once it is stopped there. Before, it made ~/projects/<cell>, opened a tab, and the start then failed. A cell that is offline there is brought here as before.
- **A fresh host is no empty frame.** Once the mesh data is read and no cell is stored or listed, the cells list shows the one next step in the CLI's own words: `a4sx launch --cell` in a project folder, which claims a new cell in your browser (`a4sx launch --cell -` starts one with a code from the console). **f** asks for a project folder name (a-z, 0-9 and -; name it like the cell you will claim) and starts it there, in a new tab in ~/projects/<name>. A cell of yours on another host is brought here with view 5, **n**. The traffic-rules view (3) doesn't show this step.

## 0.4.3 - 2026-11-22

- S's note for an a4sx without `agent-host stop` names the version that has it: a4sx 0.59.10 (the number #2326 got at its merge; it said 0.59.15). Only the text changed: the check stays a probe of `agent-host stop --help`, not a version compare.

## 0.4.2 - 2026-11-21

Follow-ups from cell01's Omarchy recheck (herdr 0.9.5, a4sx #2309):
- **Leftover tabs.** After a herdr restart, the tabs the deck once started cells in can pile up as empty shells. In the host view (4), **L** lists the ones in which every pane shows a bare shell prompt (herdr's `pane process-info`) and its shell runs no job: no child process, so a vim suspended with Ctrl-Z or a `… &` keeps the tab open. It names their cells and asks. It closes them only after a yes, and only those still all bare prompts by then (`herdr tab close`). It says which stayed open, and which herdr didn't close. The deck's own tab is never closed.
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
