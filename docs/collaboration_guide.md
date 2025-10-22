# Vortex Collaboration Guide

Vortex ships with a multi-user workflow that keeps transcripts, metrics, and
session state under `~/.vortex/sessions/`. This guide explains how to invite
teammates, manage permissions, and troubleshoot common scenarios when running
the Textual TUI in shared environments.

## Session Basics

1. Start a new session with `vortex tui` then run `/session new <title>`.
2. The session directory is created on disk with:
   - `transcript.md` – append-only log of commands and diffs.
   - `plan.json` – latest planner output.
   - `metrics.jsonl` – JSON lines used by the analytics engine.
3. Resume the previous session using `vortex tui --resume`.

## Inviting Collaborators

| Command | Description |
| ------- | ----------- |
| `/session share reviewer --read-only` | Generate a share token for a reviewer.
| `/session share maintainer` | Invite with read/write privileges. |
| `/session join <token>` | Join a remote session using the issued token. |

- Tokens encapsulate the session ID, role, and access level. They are encrypted
  using the local credential store and can be pasted directly into another
  terminal.
- The Sessions panel shows active collaborators along with their last activity.

## Sync & Presence

- Presence is refreshed automatically every time a collaborator executes a
  command. Manual updates can be triggered with `/sync` or the `Ctrl+Y`
  shortcut.
- Set `VORTEX_SYNC_INTERVAL=5` (seconds) to tighten background syncing when
  pair-programming over LAN.
- Offline edits are merged during the next sync; conflicting checkpoints are
  surfaced in the Sessions panel with their IDs.

## Roles & Permissions

| Role | Capabilities |
| ---- | ------------ |
| `owner` | Full control, can share tokens and configure settings. |
| `maintainer` | Read/write access to commands and analytics. |
| `reviewer` | Read-only view of transcripts, checkpoints, and analytics. |
| `observer` | Minimal access intended for audit-only scenarios. |

The current role is displayed in the Status panel. Adjust permissions by
issuing a new share token with the desired role.

## Analytics & Reporting

- Use `/analytics` to display KPIs and `/dashboard` for the live chart view.
- `/reports` exports the current metrics as JSON, ideal for attaching to pull
  requests.
- `/compare <id1> <id2>` compares the success rate, cost, and throughput of two
  previous sessions.
- The analytics backend stores data in `~/.vortex/sessions/analytics.sqlite` and
  is safe to back up or query for historical reports.

## Network Configuration

- By default sessions sync over the local filesystem. Set
  `VORTEX_TUI_SYNC_HOST` and `VORTEX_TUI_SYNC_PORT` to enable socket-based
  propagation for LAN collaboration. All payloads are encrypted before leaving
  disk.
- Ensure the port is reachable between collaborators and that the underlying
  filesystem is writable by all participants.

## Security Considerations

- Transcripts and share tokens are encrypted with keys stored in
  `~/.vortex/sessions/secrets/`.
- Avoid sharing tokens over insecure channels; revoke access by rotating the
  session key (delete the `session-<id>.key` file) and regenerating tokens.
- The `/doctor` command includes diagnostics for terminal compatibility and
  permissions, helping diagnose remote issues quickly.

## Troubleshooting

- **Stale presence:** run `/sync` to refresh metadata or ensure the collaborator
  has write permissions on the session directory.
- **Missing analytics:** if `/analytics` shows no data, confirm the event log is
  being written (check `metrics.jsonl`) and that the analytics database is
  writable.
- **Incompatible terminals:** remind collaborators to set `--no-color` for 16-
  color terminals and `/accessibility narration on` when using screen readers.

For more TUI commands and shortcuts, refer to `docs/tui_reference.md`.
