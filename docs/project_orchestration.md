# Project Orchestration

The project orchestration subsystem coordinates milestones, pipelines, and releases
for every repository managed by Vortex. Each project is described by a `project.yml`
file that captures the vision, milestones, policies, and pipeline definitions used
during automation.

## Project Files

```
project.yml
roadmap.json
roadmap.yml
releases.json
```

The `project.yml` file is the source of truth for project metadata. It can include:

- `vision`: a human readable description of the project's objective.
- `milestones`: a list of milestone descriptors with identifiers, due dates, and
  optional budgets.
- `pipelines`: the pipeline definitions consumed by the pipeline manager.
- `settings.policies`: compliance policies that the governance audit validates.

The roadmap planner produces machine- and human-readable summaries in `roadmap.json`
and `roadmap.yml`. Release history is appended to `releases.json` to support auditing
and rollback.

## Lifecycle Commands

```
vortex project init ./repo --team-id TeamA
vortex project status alpha
vortex project plan alpha backlog/issues.md
vortex release tag alpha 1.2.0 --summary "Staging promotion"
vortex govern audit alpha
```

Each command maps to the orchestration modules:

- `project init` registers a repository and syncs the initial milestone configuration.
- `project status` collates milestones, release history, and ledger totals.
- `project plan` invokes the roadmap planner to convert backlogs into milestones.
- `release` commands create or roll back release entries.
- `govern audit` runs compliance checks using the configured policies.

## Integrations

Project orchestration integrates with:

- the team ledger for spend tracking (`~/.vortex/teams/<team>/ledger.json`)
- the pipeline manager for CI/CD execution
- the governance audit for compliance verification
- the TUI project dashboard for real-time visibility

## Data Flow

1. `ProjectManager.init_project` reads `project.yml`, registers pipelines, and
   persists metadata under `~/.vortex/projects/<id>/`.
2. `RoadmapPlanner.generate` extracts backlog tasks and groups them into milestones,
   storing the results next to the project metadata.
3. `PipelineManager.run` executes each stage using the configured connector and
   writes execution history to `<project>.history.jsonl`.
4. Governance audits query the persisted metadata, coverage metrics, and policies to
   emit pass/warn/fail verdicts.
5. The TUI receives updates via metadata events and refreshes the project dashboard
   and team panels accordingly.

## Extending Projects

To extend the orchestration layer:

- add new connectors inside `pipeline_manager.py` for additional CI providers
- update `project.yml` schema with extra milestone metadata (the manager preserves
  unknown keys)
- publish custom governance policies by extending `ProjectManager.governance_audit`
- hook additional automation into the CLI by calling the orchestration managers via
  Typer commands
