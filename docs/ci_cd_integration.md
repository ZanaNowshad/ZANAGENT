# CI/CD Integration

The pipeline manager unifies CI/CD execution across hosted and on-premise targets.
Pipelines are defined declaratively inside `project.yml` and executed asynchronously
via connector classes that encapsulate provider-specific behaviour.

## Pipeline Definition

```
pipelines:
  build:
    environment: ci
    stages:
      - name: lint
        connector: docker
        config:
          image: ghcr.io/example/lint
      - name: tests
        connector: github_actions
        config:
          workflow: tests.yml
      - name: deploy
        connector: kubernetes
        config:
          deployment: web
          namespace: staging
```

Each stage specifies a `connector` and optional `config` payload. The available
connectors in `pipeline_manager.py` are:

| Connector          | Description                                       |
| ------------------ | ------------------------------------------------- |
| `github_actions`   | Trigger GitHub Actions workflows                  |
| `gitlab`           | Schedule GitLab CI jobs                           |
| `circleci`         | Enqueue CircleCI workflows                        |
| `docker`           | Execute local or remote Docker image builds       |
| `kubernetes`       | Apply Kubernetes deployments for canary rollouts  |

## Runtime Behaviour

1. `PipelineManager.register_project` caches the pipeline definition.
2. `PipelineManager.run` iterates the configured stages, measuring duration via
   `PerformanceMonitor.track` and writing history to `<project>.history.jsonl`.
3. The pipeline history is accessible via `status`, `logs`, and `dashboard` calls
   and is surfaced in both the CLI and TUI project dashboards.
4. Each stage emits audit events through `AuditSystem` for traceability.

## CLI Usage

```
vortex pipeline run build --stage lint
vortex pipeline status build
vortex pipeline logs build
vortex pipeline dashboard build
```

The CLI forwards arguments to the pipeline manager and prints Rich tables showing
stage status, duration, and environment metadata.

## Extending Pipelines

- Implement new connectors by subclassing the `_BaseConnector` in
  `pipeline_manager.py`.
- Use environment variables or secrets management to enrich stage configuration.
- Combine pipeline results with governance audits to block releases until policies
  succeed.
- Query `PipelineManager.dashboard` to render custom dashboards or alerts.
