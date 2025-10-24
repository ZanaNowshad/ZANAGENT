# Vortex Advanced Modules

This document summarises the phase-three subsystems and how to operate them from
both code and the CLI.

## Integration Hub

- **APIHub** — register external APIs with `register_api` and call endpoints via
  `vortex integration apis` to inspect available connectors.
- **DatabaseManager** — store sensitive records using transparent encryption;
  the CLI uses the shared connection when workflows persist artefacts.
- **CloudIntegration** — add cloud accounts from plugins or configuration and
  query them with `vortex integration cloud`.
- **GitManager** — enforces permissions before executing Git commands; the CLI
  exposes `vortex integration git-status` for quick diagnostics.

## AI Enhancements

- `vortex ai summary` renders the latest conversation summary.
- `vortex ai sentiment` analyses short text snippets using the `NLPEngine`.
- `vortex ai feedback` records structured feedback so the learning system can
  surface trending categories.

## Performance Toolkit

- `vortex perf metrics` prints averages and percentiles captured by
  `PerformanceMonitor`.
- `vortex perf costs` computes the token spend tracked by `CostTracker`.
- Developers can reuse `CacheManager`, `ConnectionPool`, `LazyLoader`, and
  `ParallelProcessor` for high throughput integrations.

## Workflow Automation

- Use `vortex workflow run plan.json` to execute dependency-aware steps defined
  as JSON.
- `vortex workflow macros` lists macro definitions registered via `MacroSystem`.
- The scheduler powers background tasks such as periodic key rotation.

## Security Layer

- `AccessControl` builds role-based permissions on top of the existing registry.
- `AuditSystem` loads recent audit events for forensics.
- `DataEncryptor` encrypts column values when persisting through
  `DatabaseManager`.

## User Interfaces

- `WebUI` offers a lightweight JSON-over-HTTP endpoint for remote orchestration.
- `DesktopGUI` and `RichUIBridge` render dashboards directly inside the console.
- `MobileAPI` enforces fine-grained permissions for mobile clients.

## Developer Tooling

- `vortex dev tests` runs the project test suite via the `TestFramework`.
- `vortex dev health` reports discovered tests and quick diagnostics.
- `DevOpsHelper` and `Debugger` assist with asynchronous command execution and
  failure analysis.

## Education & Experimentation

- `LearningMode` guides users through interactive lessons while persisting
  context.
- `CodeExplainer` leverages the advanced code intelligence layer to generate
  structured code summaries.
- `MultiAgentCoordinator`, `SelfImprovementLoop`, and `Predictor` demonstrate
  how experimental features can plug into the production runtime, accessible via
  `vortex experimental broadcast` and supporting APIs.
