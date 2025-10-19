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
