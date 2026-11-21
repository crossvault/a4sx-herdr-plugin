# Changelog

## 0.3.2 - 2026-11-21

From the first live run on Omarchy (herdr 0.9.1):

- **A key for the menu from the menu itself.** While no key opens it, the menu offers **4 Open this menu with a key**. After a yes, the plugin appends `[[keys.command]] key = "prefix+a" … command = "a4sx.mesh.menu"` to herdr's config.toml: a backup first, `herdr config check` after (the file goes back if herdr refuses it), then `herdr server reload-config`. The README says why `herdr plugin action invoke` prints herdr's JSON first, and that a key avoids it.
- **A readable peers view.** It used to show a4sx's raw table (an instance id, a 43-character key, `None` for the isolation an admin sees). Now each session is shown by name, where it is (this cell / this machine / your other machine / another person's) and its status (online, offline, waits for approval, messages blocked). `i` shows the ids and keys. It reads `a4sx mesh peers --json`; an older a4sx gets its own table as before.
- **The cell picker no longer says "waits for approval" for an active cell.** a4sx's note is what it knew when the cell was made. For a cell with that note, the picker asks the mesh's own list, and shows the note only while the cell really waits.


## 0.3.1 - 2026-11-14

First public version.

- One menu action (`a4sx.mesh.menu`) to bind to a single key, offering: start a cell in a new pane, show mesh peers, join a mesh.
- Start a cell: lists this machine's cells and types `a4sx launch --cell NAME` (with a4sx's full path) into a new pane in the same folder, only into a pane herdr has just created. Extra flags come only from your own `launch-args.json`, and only three pass, spelled in full: `--mesh-reduced-isolation`, `--local-login`, `--model=NAME`. The plugin never adds `--mesh-reduced-isolation` itself.
- Peers: a4sx's own table, with `--no-browser`.
- Join: runs `a4sx mesh join -` in a pane with you at the keyboard; the plugin never sees an invitation code.
