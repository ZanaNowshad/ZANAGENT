# AI Ops Center

The AI Ops Centre aggregates operational telemetry across every Vortex node. It
collects pipeline executions, runtime alerts, cost data, and collaborator
activity to produce an at-a-glance operational dashboard.

## Components

- **OrgOpsCenter** – Aggregates metrics, persists event logs, and surfaces
  alerts. Data is stored locally in `~/.vortex/org/ops_metrics.jsonl`.
- **OrgAnalyticsEngine** – Computes organisation-wide KPIs (teams, sessions,
  tokens, minutes) based on the analytics SQLite stores.
- **OrgOpsAPIServer** – Optional HTTP endpoint exposing `/metrics`, `/graph`, and
  `/policies` for integration with external dashboards.

## Usage

### CLI

```
vortex org analytics
vortex org report --period 14
vortex ops status
vortex ops alerts
```

### TUI

- `Ctrl+O` focuses the Org Centre panel with live metrics and presence data.
- `Ctrl+A` focuses alerts, rendering the latest incidents in the main panel.
- `Ctrl+G` renders a knowledge-graph snapshot.

Slash commands mirror the CLI surface:

- `/org analytics`
- `/org report`
- `/ops alerts`
- `/graph view`
- `/policy evaluate --coverage 0.85`

## API Server

The API server can be started locally with `vortex org serve`. Clients must
include the generated bearer token in the `Authorization` header:

```
GET /metrics HTTP/1.1
Authorization: Bearer <token>
```

Responses are lightweight JSON documents suitable for dashboards and monitoring
systems.
