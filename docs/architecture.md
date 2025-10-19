# Vortex Architecture

Vortex follows a clean architecture approach where the CLI, orchestration
managers, and security layers are decoupled from infrastructure concerns.

## Core Components

- **UnifiedConfigManager** loads YAML/TOML configuration, validates it with
  Pydantic, and supports live reload with change callbacks.
- **UnifiedModelManager** orchestrates multiple model providers with automatic
  failover, token tracking, and cost estimation.
- **UnifiedMemorySystem** persists short and long term memory in SQLite and a
  vector store to enable semantic search and summarisation.
- **UnifiedPluginSystem** discovers plugins on disk, runs them in sandboxes, and
  supports hot reloading on demand.
- **UnifiedAdvancedPlanner** executes dependency-aware plans with retry and
  progress tracking instrumentation.
- **UnifiedSecurityManager** centralises sandboxing, permission checks,
  credential storage, and audit logging.
- **UnifiedRichUI** offers a Rich-powered console experience with spinners,
  tables, and live updates.

## Intelligence Modules

Domain-specific capabilities (data analysis, audio insights, computer vision,
code intelligence) build on the shared runtime managers. They are intentionally
lightweight so teams can swap or extend them without impacting the rest of the
system.

## Data Flow

1. Configuration is loaded at startup and passed to all managers.
2. CLI commands call into managers, which perform work asynchronously.
3. Model responses can be cached or persisted in memory for future retrieval.
4. Plugins run inside sandboxes with restricted builtins to maintain safety.
5. Security events are logged to both structured logs and an audit trail.

## Extensibility

- Add providers by subclassing `BaseProvider` and registering it in
  `PROVIDER_REGISTRY`.
- Extend the CLI by adding commands to `vortex/cli/app.py` or new Typer subapps.
- Intelligence modules can consume managers through dependency injection.
