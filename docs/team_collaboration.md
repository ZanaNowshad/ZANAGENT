# Team Collaboration Guide

Vortex nodes can now cooperate as an encrypted AI team. This guide walks
operators and platform engineers through setup, security, and day-to-day
collaboration flows.

## Prerequisites

- Ensure the Python environment has the `websockets` and `cryptography` packages
  installed (bundled with the core distribution).
- Open the necessary port on the coordinating host when collaborating across a
  LAN/WAN. By default the broker binds to `127.0.0.1` and picks a random port;
  override via `VORTEX_TUI_SYNC_HOST`/`VORTEX_TUI_SYNC_PORT`.
- Share the AES-GCM network key (`VORTEX_AGENT_KEY`) out-of-band when forming a
  secure mesh across machines. Each node stores the key in
  `~/.vortex/teams/secrets/agent-network.key`.

## Creating a Team

```bash
# Start the CLI or TUI on the coordinating host
vortex tui                       # launches local broker and joins automatically
# …or from the CLI
vortex agent join auto           # start local broker and join it
```

The first node generates a team identifier and persists ledger files under
`~/.vortex/teams/<team_id>/`. Subsequent nodes can join over LAN by pointing at
that broker URI:

```bash
vortex agent join ws://host:8765 --role editor
```

Inside the TUI, `/session share` produces encrypted share tokens for
collaborators. Use `/team list` to confirm that remote nodes are connected.

## Collaboration Modes

- **Sync** – real-time pair programming. Plans, diffs, and context broadcasts are
  live. Enable via `/mode sync` or `/team mode sync`.
- **Async** – tasks are queued and nodes pick work based on load. Trigger with
  `/mode async`.
- **Review** – one node acts as gatekeeper; others submit checkpoints for review
  using `/mode review`.

The active mode is reflected in the Team panel caption and the status bar.

## Sharing Context and Tasks

- `/attach <path|git_url>` registers a repository with the team. The Team panel
  shows which node currently owns each repo.
- `/handoff <repo> <task>` delegates a plan fragment to another node. Add
  `--to <node_id>` to target a specific collaborator.
- `/broadcast <message>` delivers encrypted notifications to every node.

Use `/insights team` to summarise collaboration health, including mean time to
fix, error spikes, and token consumption across the mesh.

## Ledger & Budgets

Budgets are tracked centrally via `/team ledger` and updated programmatically
with `TeamManager.record_budget`. Ledger files live under
`~/.vortex/teams/<team_id>/ledger.json` and are consumed by the team analytics
store. The Team panel caption displays aggregate token/minute spend.

## Security & Governance

- Transport is secured with AES-GCM using the network encryptor. Rotate the key
  by regenerating `VORTEX_AGENT_KEY` and restarting nodes.
- Every collaboration action records an audit event via
  `vortex.security.audit_system`. Review logs under
  `~/.vortex/sessions/<session_id>/events.jsonl`.
- Reuse the existing permission system: assign roles (admin/editor/observer)
  when generating share tokens to gate write operations.

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| Remote node cannot decrypt frames | Verify both nodes use the same `VORTEX_AGENT_KEY`. |
| Broadcasts do not appear | Ensure the receiving node joined after the broker was online and check `vortex agent list`. |
| Ledger totals incorrect | Run `/team ledger` to refresh; the TUI also syncs every `VORTEX_SYNC_INTERVAL` seconds. |
| Ports unavailable | Override `VORTEX_TUI_SYNC_PORT` to an open port or use SSH port forwarding. |

For deeper protocol information see `docs/network_protocol.md`.
