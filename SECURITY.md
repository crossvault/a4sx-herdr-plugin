# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Use the contact details on
https://session-exchange.com/contact and say that it is a security report.

Please include what you found, how to reproduce it, and the plugin version (`version` in
`herdr-plugin.toml`). Don't include real tokens, invitation links or other people's data.

## What this plugin does with credentials

The plugin holds no credentials and stores none. It never sees an invitation code: joining runs
`a4sx mesh join -` in a pane, and you paste the link into a4sx itself. It removes herdr's context
variables (selected text, a clicked link) from the environment of every process it starts. It
reads only `a4sx mesh cells --json` and never shows key fields from it.
