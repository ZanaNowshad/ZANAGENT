# Vortex TUI Reference

The Vortex terminal interface is built with [Textual](https://textual.textualize.io/)
and layers the plan→act→review workflow directly into the console. This
reference documents the interaction model for operators and contributors.

## Launching

```bash
vortex tui                 # start a fresh session
vortex tui --resume        # restore the previous session state
vortex tui --theme light   # override theme
vortex tui --theme high_contrast
vortex tui --no-color      # 16-colour safe output
vortex tui --screen-reader # announce panel changes
```

State is persisted under `~/.agent/sessions/` using JSON so that transient runs
survive terminal restarts. The TUI honours the global configuration stored in
`~/.vortex/config.toml` and writes theme/accessibility updates back to the file.

## Initial Setup Wizard

The first launch presents a multi-step wizard collecting:

1. **Model** preference and narration verbosity.
2. **Theme** selection (dark, light, or high contrast) plus narration toggle. Custom
   themes can be imported later via `/theme custom <path>`.
3. **Safety & privacy** knobs (telemetry consent, write guard, accessibility, feature
   flags).

Answers persist in the operator config and are replayed on subsequent sessions.
Invoke the wizard again at any time via `/settings` or `Ctrl+,`.

## Panels

| Panel        | Purpose                                                        |
| ------------ | -------------------------------------------------------------- |
| Main         | Active transcript/diff/log output depending on the current mode|
| Context      | Repository tree and relevant snippets                          |
| Sessions     | Presence indicators, locks, and checkpoint summaries           |
| Actions      | High-value buttons with hotkey hints                           |
| Analytics    | Session KPIs, charts, and narrative insights                   |
| Status       | Branch, checkpoints, budgets, model, CPU/memory, tests         |
| Tools (T)    | Discoverable plugin/tool registry                              |
| Help (?)     | Key bindings, slash commands, copyable examples                |
| Telemetry    | Resource bar anchored at the bottom of the layout              |

Use `Tab`/`Shift+Tab` to cycle focus across panels. Focus changes trigger a
screen-reader announcement when enabled.

## Command Palette and Slash Commands

Press `:` to open the inline palette. It lists frequently used commands, your
recent history, fuzzy matches for tools and file paths, and palette history.
Selecting an entry injects the corresponding slash command into the command bar.

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
| `/accessibility <on|off>` | Toggle announcements |
| `/accessibility verbosity <minimal|normal|verbose>` | Adjust narration granularity |
| `/accessibility narration <on|off>` | Enable or disable narration cues |
| `/accessibility contrast <on|off>` | Toggle high-contrast palette |
| `/theme <dark|light|high_contrast>` | Switch theme and high-contrast mode |
| `/theme custom <path>` | Load custom TOML/YAML theme overrides |
| `/settings` | Launch the settings surface |
| `/lyra [prompt]` | Open the Lyra inline assistant for quick tips |
| `/doctor` | Run diagnostics on terminal, fonts, and colours |
| `/reload theme` | Reload the active theme from disk |
| `/session new [title]` | Start a collaborative session and persist transcripts |
| `/session list` | Show locally cached sessions and collaborator counts |
| `/session join <id|token>` | Attach to a shared session using an ID or share token |
| `/session share [role]` | Generate an encrypted share token (use `--read-only` for RO) |
| `/sync` | Push/pull collaborative state immediately |
| `/analytics` | Render session KPIs and action frequency tables |
| `/dashboard` | Load the analytics dashboard into the main panel |
| `/reports` | Export metrics as JSON for downstream automation |
| `/compare <id1> <id2>` | Compare KPIs across two sessions |
| `/insights` | Generate narrative insights from the transcript metrics |
| `/quit` | Confirm exit and persist session |
| `/help` | Toggle the help overlay |

Slash commands integrate with the runtime managers (planner, workflow engine,
memory, plugin system, cost tracker, git integration) and log results in the
main panel with timestamps for traceability. Results include plain-text
summaries so screen readers can announce diffs, diagnostics, and log entries.
Type `:` to access the palette; the inline autocomplete surfaces commands,
tools, files, and tests using RapidFuzz scoring. `:q` serves as a quick alias
for `/quit`.

## Collaboration & Analytics

The TUI keeps collaborative sessions under `~/.vortex/sessions/`. `/session new`
spins up a workspace with encrypted transcripts, while `/session share` issues a
token granting read/write or read-only access. Presence updates stream into the
Sessions panel and you can manually sync via `/sync` or `Ctrl+Y`. The Analytics
panel surfaces KPIs and `/dashboard` renders a Rich chart overview for ongoing
work. All metrics land in an SQLite store so `/reports` and `/compare` remain
fast, even across large transcripts.

## Keyboard Shortcuts

| Shortcut | Action |
| -------- | ------ |
| `a` | Apply: capture checkpoint |
| `u` | Undo: revert checkpoint |
| `p` | Plan: refresh execution order |
| `s` | Simulate: run the workflow engine with the current context |
| `t` | Toggle the tools panel |
| `T` | Run the test suite (`/test`) |
| `/` | Focus the slash command bar |
| `:` | Open the command palette |
| `?` | Toggle help |
| `Ctrl+,` | Open settings |
| `Ctrl+T` | Reload the active theme (`/reload theme`) |
| `Ctrl+R` | Show recent command history |
| `Ctrl+D` | Open analytics dashboard |
| `Ctrl+A` | Focus analytics panel |
| `Ctrl+S` | Focus sessions panel |
| `Ctrl+Y` | Manual session sync |
| `Ctrl+Q` | Prompt to quit |
| `j`/`k` | Navigate list items |
| `g`/`G` | Jump to top/bottom |
| `h`/`l` | Navigate diff hunks |
| `Enter` | Activate focused list entry |

## Performance & Accessibility

- Rendering is governed by refresh and panel coalescers targeting ~60 fps (tune via the
  `VORTEX_TUI_FPS` environment variable). Heavy operations such as git status run via
  Textual's `work` API to avoid blocking the UI.
- The telemetry bar surfaces live CPU and memory usage using `psutil`. Disable
  colour entirely with `--no-color` for legacy terminals.
- Accessibility narration is available through `--screen-reader`, the
  `/accessibility` command, or settings. Verbosity can be set to `minimal`,
  `normal`, or `verbose`. Plain-text summaries and progress announcements are
  emitted for diffs, diagnostics, and background work.
- `/accessibility narration on` toggles screen-reader narration; `/accessibility contrast on`
  switches to a WCAG AA high-contrast palette.
- Collaboration updates are coalesced before rendering; adjust background
  syncing by exporting `VORTEX_SYNC_INTERVAL` (seconds) when working offline.

## Lyra Assistant

Toggle Lyra with `/lyra [prompt]` or pick it from the palette. The assistant
streams inline Markdown guidance derived from the configured model manager.
Enable or disable Lyra at runtime in the settings panel (feature flag
`lyra_assistant`). Responses are added to the session log for later recall.

## Shortcuts Table

Refer to the keyboard table above for a quick mapping of action keys. Use
`Ctrl+R` to surface searchable command history and `Ctrl+T` for live theme reloads.

## Diagnostics & Doctor

Run `/doctor` to collect terminal compatibility information (platform, Python
version, terminal dimensions, git availability). Use `/reload theme` after
modifying custom theme files on disk.

## Session Artifacts

All commands log to the main panel and persist in the session file. Checkpoints
store git diff snapshots so `/undo` can restore file state. Logs are also
written to the standard `vortex` JSON log stream, enabling tailing via
`vortex.utils.logging.configure_logging()`.

## Extending the UI

New panels can subscribe to `AccessibilityToggle` messages to honour screen
reader mode. Layout customisations live in `vortex/ui_tui/panels.py`; additional
bindings belong in `vortex/ui_tui/hotkeys.py`. Keep slash command handlers in
`vortex/ui_tui/actions.py` to preserve a single orchestration layer.
