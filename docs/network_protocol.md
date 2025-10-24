# Network Protocol Overview

The Vortex team manager communicates using a compact JSON-RPC 2.0 dialect over
WebSockets. Each payload is encrypted with AES-GCM using the shared team key.
This document describes the framing so operators can audit or extend the
transport.

## Transport

- **URL scheme** – `ws://` (or `wss://` when reverse proxied).
- **Handshake** – clients connect to the broker URI published via `vortex agent
  join`. No additional HTTP headers are required.
- **Encryption** – payloads are encrypted server-side using
  `vortex.security.encryption.NetworkEncryptor`. Messages contain:

```json
{
  "jsonrpc": "2.0",
  "id": "b3d3...",            # optional for notifications
  "payload": {
    "nonce": "...",
    "ciphertext": "..."       # base64 encoded AES-GCM ciphertext
  }
}
```

Decrypting the payload reveals the JSON-RPC request or response with `method`
and `params` fields.

## Methods

| Method             | Direction | Params                                   | Description |
| ------------------ | --------- | ---------------------------------------- | ----------- |
| `register`         | client→broker | `node_id`, `name`, `role`, `capabilities` | Register a node and receive the team snapshot |
| `broadcast`        | client→broker | `message`, `payload`                     | Publish a message to all peers |
| `ledger`           | either    | `entry`                                  | Append a budget entry and persist to disk |
| `attach`           | client→broker | `repo`, `path`, `node_id`                | Share repository context |
| `handoff`          | client→broker | `repo`, `task`, `target`                 | Delegate work to another node |
| `mode`             | either    | `mode`                                   | Update collaboration mode |
| `heartbeat`        | client→broker | `node_id`                                | Keep-alive ping to update presence |
| `leave`            | client→broker | `node_id`                                | Disconnect a node |
| `team.event`       | broker→client | event payload                            | Notification wrapper used for broadcasts |

Responses either contain an encrypted result (`{"result": { ... }}`) or an
`error` string.

## Capability Exchange

Upon registration, the broker responds with the current team state:

```json
{
  "team_id": "alpha123",
  "mode": "sync",
  "nodes": [
    {"node_id": "node-1", "name": "build", "role": "admin", "host": "vortex"}
  ],
  "ledger": [ ... ],
  "attachments": {"repo-alpha": "node-1"}
}
```

Clients persist `agent.capabilities.json` under `~/.vortex/teams/<team_id>/` so
other tooling can introspect available skills.

## Error Handling

- Unknown methods return a JSON-RPC error string which is surfaced in the TUI log.
- If a client cannot decrypt a payload it drops the frame and logs a warning.
- Brokers remove a node after consecutive heartbeat failures (default 5 seconds
  via `VORTEX_SYNC_INTERVAL`).

## Extensibility

New methods can be added by extending `vortex.agents.team_manager.TeamManager`
and `vortex.agents.protocol.AgentProtocol`. Keep the payloads small and
self-describing; structured metadata should be included in the encrypted body.
