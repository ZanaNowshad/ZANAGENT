# Development Guide

## Repository Layout

- `vortex/` contains the runtime packages.
- `vortex/cli/` defines the Typer application and commands.
- `vortex/core/` hosts foundational managers such as configuration, models,
  memory, plugins, planner, and UI.
- `vortex/security/` implements sandboxing, permissions, encryption, and audit
  logging.
- `vortex/intelligence/` provides higher-level capability modules consuming the
  core managers.
- `tests/` contains unit and integration tests.

## Coding Standards

- Follow the SOLID principles and keep modules cohesive.
- Use docstrings on every public class and method.
- Prefer asynchronous APIs when IO is involved.
- Log using `vortex.utils.logging.get_logger` to keep structured JSON logging.

## Adding Providers

1. Subclass `BaseProvider` in `vortex/core/model.py`.
2. Implement `generate` and optionally `stream`.
3. Register the provider in `PROVIDER_REGISTRY`.
4. Update configuration with provider settings and credentials.

## Plugin Development

Plugins are standard Python files located in `plugins/`. Each plugin must define
one class inheriting from `BasePlugin` with `setup`, `teardown`, and `execute`
methods. The runtime automatically runs plugins inside a sandboxed thread.

## Testing

Run the test suite with coverage using:

```bash
pytest
```

Mock provider responses by configuring the `echo` provider or by injecting test
providers into `UnifiedModelManager`.

## Continuous Integration

The `.github/workflows/ci.yml` workflow runs pytest and coverage. Extend it with
linting tools as needed.

## TUI Interaction Model

Vortex ships with a Textual-powered terminal interface optimised for the
plan→act→review feedback loop. Launch it via `vortex tui` and navigate the four
primary panels using `Tab`/`Shift+Tab`:

- **Main Panel** – renders chat transcripts, plans, diffs, and log summaries.
- **Context Panel** – shows the working tree and context snippets.
- **Actions Panel** – exposes high-value operations with keyboard hints.
- **Status Panel** – tracks branch, checkpoints, budgets, and test results.

Key bindings favour home-row ergonomics: `a` applies checkpoints, `u` undoes,
`p` plans, `s` simulates workflows, `t` toggles the tool list, `T` runs tests,
`:` opens the command palette, `/` focuses the slash command bar, and `?`
toggles the help overlay. Diff navigation uses `h`/`l` while list navigation is
handled with `j`/`k`/`g`/`G`.

Slash commands power automation and integrate with the runtime managers. Use
`/plan`, `/apply`, `/undo`, `/diff`, `/test -k pattern`, `/ctx add path`, `/tool
name {json}`, `/mode review`, `/budget 15`, `/auto 6`, and `/help` to orchestrate
the agent without leaving the terminal. The UI persists session state under
`~/.agent/sessions/` so `vortex tui --resume` restores the previous context.
