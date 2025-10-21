# Vortex TUI Reference

The Vortex terminal interface is built with [Textual](https://textual.textualize.io/)
and layers the plan→act→review workflow directly into the console. This
reference documents the interaction model for operators and contributors.

## Launching

```bash
vortex tui                 # start a fresh session
vortex tui --resume        # restore the previous session state
vortex tui --theme light   # override theme
vortex tui --no-color      # 16-colour safe output
vortex tui --screen-reader # announce panel changes
```

State is persisted under `~/.agent/sessions/` using JSON so that transient runs
survive terminal restarts.

## Panels

| Panel        | Purpose                                                        |
| ------------ | -------------------------------------------------------------- |
| Main         | Active transcript/diff/log output depending on the current mode|
| Context      | Repository tree and relevant snippets                          |
| Actions      | High-value buttons with hotkey hints                           |
| Status       | Branch, checkpoints, budgets, model, and latest test status    |
| Tools (T)    | Discoverable plugin/tool registry                              |
| Help (?)     | Key bindings, slash commands, copyable examples                |

Use `Tab`/`Shift+Tab` to cycle focus across panels. Focus changes trigger a
screen-reader announcement when enabled.

## Command Palette and Slash Commands

Press `:` to open the inline palette. It lists frequently used commands and your
recent history. Selecting an entry injects the corresponding slash command into
the command bar.

Slash commands are parsed with shell semantics (quotes honoured). Supported
commands include:

| Command | Description |
| ------- | ----------- |
| `/plan` | Generate the execution order from the planner |
| `/apply` | Capture a checkpoint from the current git diff |
| `/undo [id]` | Restore the previous checkpoint (or by id) |
| `/diff [path]` | Show a unified diff for the workspace or a specific path |
| `/test -k expr` | Run pytest with an optional keyword filter |
| `/ctx add <path>` | Add the contents of a file to conversational context |
| `/tool <name> {json}` | Invoke a plugin/tool with JSON parameters |
| `/mode <chat|fix|gen|review|run|plan|diff>` | Switch the main panel mode |
| `/budget <minutes>` | Update the remaining budget in minutes |
| `/auto <steps>` | Configure autonomous execution depth |
| `/help` | Toggle the help overlay |

Slash commands integrate with the runtime managers (planner, workflow engine,
memory, plugin system, cost tracker, git integration) and log results in the
main panel with timestamps for traceability.

## Keyboard Shortcuts

- `a` – Apply: capture checkpoint
- `u` – Undo: revert checkpoint
- `p` – Plan: refresh execution order
- `s` – Simulate: run the workflow engine with the current context
- `t` – Toggle the tools panel
- `T` – Run the test suite (`/test`)
- `/` – Focus the slash command bar
- `:` – Open the command palette
- `?` – Toggle help
- `j`/`k` – Navigate list items
- `g`/`G` – Jump to top/bottom
- `h`/`l` – Navigate diff hunks
- `Enter` – Activate focused list entry

## Accessibility

Enable announcements with `--screen-reader` or at runtime by emitting an
`AccessibilityToggle` message. Panel switches, palette openings, and diff
navigation all trigger short notifications. Combine with `--no-color` for
maximum compatibility with screen readers and high-contrast requirements.

## Session Artifacts

All commands log to the main panel and persist in the session file. Checkpoints
store git diff snapshots so `/undo` can restore file state. Logs are also
written to the standard `vortex` JSON log stream, enabling tailing via
`vortex.utils.logging.configure_logging()`.

## Troubleshooting

- Ensure `git` is installed; the diff/undo/checkpoint features shell out to it.
- The command palette displays your history. Clear the session file to reset.
- Textual supports mouse interaction—click panel headers to move focus if
  desired.

## Extending the UI

New panels can subscribe to the `AccessibilityToggle` message to honour screen
reader mode. Layout customisations live in `vortex/ui_tui/panels.py`; additional
bindings belong in `vortex/ui_tui/hotkeys.py`. Keep slash command handlers in
`vortex/ui_tui/actions.py` to preserve a single orchestration layer.
