# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [1.0.3] - 2024-03-10
### Added
- feat: enabled multi-session collaboration, presence indicators, and encrypted share tokens across the TUI.
- feat: introduced analytics dashboards, session comparison reports, and collaborative diagnostics commands.

### Changed
- ux: refreshed the layout with dedicated Sessions and Analytics panels plus dashboard hotkeys.

### Security
- security: enforced end-to-end encryption for shared transcripts and configurable LAN sync hosts.

### Testing
- test: added coverage for session manager events, analytics reporting, and dashboard renderables.

### Documentation
- docs: published a collaboration guide and expanded the TUI reference with analytics shortcuts and commands.

## [1.0.2] - 2024-03-09
### Added
- feat: introduced command palette suggestions, colon command shortcuts, and rich progress spinners for long-running actions.
- feat: expanded accessibility controls with narration, contrast toggles, and persistent Textual settings tabs.

### Changed
- ux: refactored TUI rendering with panel update coalescers, screen-reader announcements, and theme reload metadata plumbing.

### Testing
- test: broadened TUI coverage with accessibility progress checks, panel coalescer validation, and settings persistence tests.

### Documentation
- docs: refreshed TUI reference with new slash commands, palette behaviour, and performance guidance.

## [1.0.1] - 2024-03-08
### Added
- feat: introduced Textual-based accessibility improvements including announcers, settings wizard, and Lyra assistant panel.
- feat: added dynamic theming with high-contrast and custom palette support plus runtime palette suggestions.
- test: expanded coverage with performance and accessibility suites validating slash commands and refresh coalescing.

### Performance
- perf: coalesced refresh cycles with FPS tuning and psutil-backed telemetry bar for CPU/memory tracking.

### Documentation
- docs: updated TUI reference with setup wizard guidance, accessibility tips, and enhanced shortcut tables.

## [1.0.0] - 2024-03-01
### Added
- feat: initial public release of the Vortex AI agent framework with multi-modal orchestration.
- feat: advanced subsystem expansion covering integration, performance, workflow, UI, devtools, education, and experimental modules.
- ci: continuous integration pipeline with automated testing and coverage enforcement.

### Security
- security: enforced encryption, audit logging, and access control defaults for packaged deployments.

### Documentation
- docs: comprehensive user, developer, and deployment guides alongside release documentation.
