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

## Phase 3 Subsystems

- **Integration Layer** — `APIHub`, `CloudIntegration`, `DatabaseManager`, and
  `GitManager` provide unified access to external APIs, cloud control planes,
  encrypted data persistence, and repository automation. All integrations reuse
  the security manager for credential storage and permission checks.
- **AI Enhancements** — `ContextManager`, `ContinuousLearningSystem`,
  `AdvancedCodeIntelligence`, and `NLPEngine` extend reasoning by persisting
  conversational context, analysing source code, learning from feedback, and
  extracting language insights without additional dependencies.
- **Performance Suite** — The `PerformanceMonitor`, `PerformanceAnalytics`,
  `CostTracker`, `CacheManager`, `ConnectionPool`, `LazyLoader`, and
  `ParallelProcessor` cooperate to track latency, estimate spend, cache
  expensive calls, and bound concurrency across integrations.
- **Workflow Automation** — `WorkflowEngine`, `MacroSystem`, and
  `WorkflowScheduler` deliver dependency-aware orchestration, reusable macro
  definitions, and timed task execution.
- **Security Extensions** — New `AccessControl`, `AuditSystem`, and
  `DataEncryptor` components sit alongside the existing security manager to
  implement RBAC, rich audit queries, and encrypted database storage.
- **UI Adapters** — `WebUI`, `DesktopGUI`, `MobileAPI`, and `RichUIBridge`
  expose the runtime through HTTP, desktop-style dashboards, mobile-friendly
  JSON APIs, and higher-level Rich renderers.
- **Developer Tooling** — `TestFramework`, `DevToolsSuite`, `Debugger`, and
  `DevOpsHelper` support automated diagnostics, local workflows, and safe shell
  execution.
- **Education & Experimentation** — `LearningMode`, `CodeExplainer`,
  `MultiAgentCoordinator`, `SelfImprovementLoop`, and `Predictor` demonstrate
  how advanced features plug into the runtime for training, explanation, and
  research use cases.
