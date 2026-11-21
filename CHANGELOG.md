# Changelog

## 0.4.0 - 2026-11-21

- **The deck** (a4sx issue #2290). One pane shows the mesh, its cells, your a4sx library, the mesh's rules, this host and moving a cell (keys 1 to 5), with the selected row's operations on the right, each one key. Short commands run in place; anything you answer, or that opens the browser, runs in a new herdr tab. Everything it runs is an ordinary `a4sx` or `herdr` command; the deck stores only the id of its own pane.
- The deck is the first thing a herdr session shows. Set `on-start` to `focus` (the default), `open` (a tab, not in front) or `off` (only the cells' names go into the agents list), with `DECK_ON_START` or one word in the file `on-start` in this plugin's config folder. After a herdr restart it starts again in its restored pane.
- It reads locally every 5 seconds and asks the server at most once a minute (some things every 5 minutes), and waits longer each time the server says "slow down". It never reads or shows a key or a sign-in.
- New actions: `deck` (open the deck) and `deck-label` (the cells' names in the agents list).
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
