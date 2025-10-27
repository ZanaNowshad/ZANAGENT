"""Textual application powering the Vortex terminal experience."""
from __future__ import annotations

import asyncio
import os
import socket
from itertools import cycle
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Iterable, Optional

from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView

from vortex.utils.logging import get_logger
from vortex.utils.profiling import profile

from vortex.performance.analytics import SessionAnalyticsStore
from vortex.org.ops_center import OpsSnapshot

from .actions import CommandResult, TUIActionCenter
from .accessibility import (
    AccessibilityAnnouncer,
    AccessibilityPreferences,
    AccessibilityPreferencesChanged,
    AccessibilityToggle,
)
from .analytics_panel import analytics_dashboard, analytics_trend_panel
from .command_parser import SlashCommand, parse_slash_command
from .context import CollaboratorState, TUIOptions, TUIRuntimeBridge, TUISessionState
from .hotkeys import bindings_for_app
from .layout import build_layout
from .lyra_assistant import LyraAssistant
from .palette import search_entries
from .panels import (
    AnalyticsPanel,
    CommandBar,
    MainPanel,
    OrgCenterPanel,
    ProjectDashboardPanel,
    SessionsPanel,
    StatusPanel,
    TeamPanel,
    TelemetryBar,
    ToolPanel,
)
from .settings import InitialSetupWizard, SettingsScreen, TUISettings, TUISettingsManager
from .session_manager import SessionEvent, SessionManager
from .status import StatusAggregator, StatusSnapshot
from .themes import ThemeError, theme_css

logger = get_logger(__name__)


class RefreshCoalescer:
    """Coalesce refresh calls to maintain a stable frame budget."""

    def __init__(self, app: App[Any], interval: float) -> None:
        self._app = app
        self._interval = interval
        self._task: Optional[asyncio.Task[None]] = None

    def request(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._dispatch())

    async def _dispatch(self) -> None:
        await asyncio.sleep(self._interval)
        await self._app.refresh()


class PanelUpdateCoalescer:
    """Batch panel mutations to avoid redundant redraws."""

    def __init__(self, app: App[Any], interval: float) -> None:
        self._app = app
        self._interval = interval
        self._pending: list[Callable[[], None]] = []
        self._task: Optional[asyncio.Task[None]] = None

    def enqueue(self, callback: Callable[[], None]) -> None:
        self._pending.append(callback)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush())

    async def _flush(self) -> None:
        await asyncio.sleep(self._interval)
        callbacks = self._pending
        self._pending = []
        for callback in callbacks:
            callback()
        await self._app.refresh()


class ConfirmQuitScreen(ModalScreen[bool]):
    """Simple confirmation dialog before exiting."""

    CSS = """
    #quit-panel {
        padding: 1 2;
        border: heavy $accent;
        background: $panel;
        width: 60%;
        margin: auto;
    }
    #quit-actions {
        padding-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Container(id="quit-panel"):
            yield Label("Exit Vortex session?")
            with Horizontal(id="quit-actions"):
                yield Button("Cancel", id="quit-cancel")
                yield Button("Exit", id="quit-confirm", variant="error")

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#quit-cancel")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#quit-confirm")
    def _confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class VortexTUI(App[None]):
    """Interactive Textual application embedding the Vortex runtime."""

    BINDINGS = bindings_for_app()

    def __init__(self, runtime: Any, options: TUIOptions) -> None:
        super().__init__()
        self.runtime = runtime
        self.options = options
        self.bridge = TUIRuntimeBridge(runtime)
        self.state = self._load_state(options)
        self.status = StatusAggregator(runtime)
        self.settings_manager = TUISettingsManager()
        self.tui_settings: Optional[TUISettings] = None
        self.analytics_store = SessionAnalyticsStore()
        self.session_manager = SessionManager(analytics=self.analytics_store)
        fps = max(15, min(120, int(os.getenv("VORTEX_TUI_FPS", "60"))))
        self._frame_interval = 1.0 / fps
        self._refresh_coalescer = RefreshCoalescer(self, self._frame_interval)
        self._panel_coalescer: Optional[PanelUpdateCoalescer] = None
        self.actions: Optional[TUIActionCenter] = None
        self.announcer: Optional[AccessibilityAnnouncer] = None
        self.lyra = LyraAssistant(runtime)
        self._theme_css: str = ""
        self._focus_order = [
            "main-panel",
            "context-panel",
            "sessions-panel",
            "team-panel",
            "org-panel",
            "actions-panel",
            "analytics-panel",
            "project-panel",
            "status-panel",
        ]
        self._focus_index = 0
        self._telemetry_bar: Optional[TelemetryBar] = None
        self._last_status: Optional[StatusSnapshot] = None
        self.command_bar: Optional[CommandBar] = None
        self._main_panel: Optional[MainPanel] = None
        self._spinner_task: Optional[asyncio.Task[None]] = None
        self._spinner_label: Optional[str] = None
        self._sessions_panel: Optional[SessionsPanel] = None
        self._analytics_panel: Optional[AnalyticsPanel] = None
        self._team_panel: Optional[TeamPanel] = None
        self._org_panel: Optional[OrgCenterPanel] = None
        self._project_panel: Optional[ProjectDashboardPanel] = None
        self._session_iterator: Optional[AsyncIterator[SessionEvent]] = None
        self._session_listener: Optional[asyncio.Task[None]] = None
        self._auto_sync_interval = max(5.0, float(os.getenv("VORTEX_SYNC_INTERVAL", "15")))
        self._last_analytics: Dict[str, Any] = {}
        self._identity = f"{os.getenv('USER', 'operator')}@{socket.gethostname()}"

    def _load_state(self, options: TUIOptions) -> TUISessionState:
        if options.resume:
            previous = self.bridge.load_state()
            if previous:
                return previous
        return TUISessionState()

    def _syntax_theme_name(self) -> str:
        if self.options.no_color:
            return "ansi"
        theme = self.state.theme or "dark"
        return "ansi_light" if theme == "light" else "ansi_dark"

    def compose(self) -> ComposeResult:
        layout = build_layout(Path.cwd(), settings=self.tui_settings or TUISettings())
        yield layout

    async def on_mount(self) -> None:
        self._main_panel = self.query_one("#main-panel", MainPanel)
        self.command_bar = self.query_one("#command-bar", CommandBar)
        self._sessions_panel = self.query_one("#sessions-panel", SessionsPanel)
        self._analytics_panel = self.query_one("#analytics-panel", AnalyticsPanel)
        self._team_panel = self.query_one("#team-panel", TeamPanel)
        self._org_panel = self.query_one("#org-panel", OrgCenterPanel)
        self._project_panel = self.query_one("#project-panel", ProjectDashboardPanel)
        self._panel_coalescer = PanelUpdateCoalescer(self, max(self._frame_interval / 2, 0.005))
        self.tui_settings = await self.settings_manager.load()
        if await self.settings_manager.needs_initial_setup():
            wizard = InitialSetupWizard(self.tui_settings)
            self.push_screen(wizard)
            setup = await wizard.wait()
            if setup is None:
                await self.action_quit_app()
                return
            self.tui_settings = setup
            await self.settings_manager.persist(setup)
        self._apply_settings_to_state()
        self._apply_theme()
        await self._ensure_session()
        prefs = AccessibilityPreferences(
            enabled=self.state.accessibility_enabled,
            verbosity=self.state.accessibility_verbosity,
            announce_narration=self.state.narration_enabled,
        )
        self.announcer = AccessibilityAnnouncer(self, preferences=prefs)
        self.announcer.set_high_contrast(self.state.high_contrast)
        self.actions = TUIActionCenter(
            self.runtime,
            self.state,
            self.status,
            syntax_theme=self._syntax_theme_name(),
            session_manager=self.session_manager,
            analytics=self.analytics_store,
        )
        await self._announce("TUI initialised")
        self._telemetry_bar = self.query_one("#telemetry-bar", TelemetryBar)
        await self.refresh_status()
        self._restore_logs()
        self.set_interval(5.0, self._poll_status)
        self.set_interval(self._auto_sync_interval, self._auto_sync)
        await self._start_session_listener()
        self.query_one("#command-input", Input).focus()

    def _apply_settings_to_state(self) -> None:
        if not self.tui_settings:
            return
        settings = self.tui_settings
        if self.options.color_scheme in {"dark", "light"}:
            self.state.theme = self.options.color_scheme
            self.state.high_contrast = False
        elif self.options.color_scheme == "high_contrast":
            self.state.theme = "dark"
            self.state.high_contrast = True
        else:
            self.state.theme = settings.theme
            self.state.high_contrast = settings.high_contrast
        self.state.accessibility_enabled = self.options.screen_reader or settings.accessibility_enabled
        self.state.accessibility_verbosity = settings.accessibility_verbosity
        self.state.narration_enabled = settings.narration_enabled
        self.state.feature_flags.update(settings.feature_flags)
        if settings.model:
            self.state.add_log("info", f"Default model: {settings.model}")

    def _apply_theme(self) -> None:
        try:
            css = theme_css(
                self.state.theme,
                no_color=self.options.no_color,
                high_contrast=self.state.high_contrast,
                custom=self.tui_settings.custom_theme_path if self.tui_settings else None,
            )
        except ThemeError as exc:  # pragma: no cover - misconfiguration
            self.state.add_log("error", str(exc))
            css = theme_css("dark", no_color=self.options.no_color)
        self._theme_css = css
        self.stylesheet.read(css)
        if self.announcer:
            self.announcer.set_high_contrast(self.state.high_contrast)

    async def _ensure_session(self) -> None:
        if self.state.session_id:
            details = await self.session_manager.session_details(self.state.session_id)
            self._apply_session_details(details)
        else:
            metadata = await self.session_manager.create_session("Vortex Session", os.getenv("USER", "operator"))
            details = await self.session_manager.session_details(metadata.session_id)
            self._apply_session_details(details)
            self.state.session_role = "owner"
        if self.state.session_id:
            await self.session_manager.record_presence(self.state.session_id, self._identity)
        await self._update_session_panels()

    async def _start_session_listener(self) -> None:
        if not self.state.session_id:
            return
        self._session_iterator = await self.session_manager.subscribe(self.state.session_id)
        self._session_listener = asyncio.create_task(self._consume_session_events())

    async def _consume_session_events(self) -> None:
        if not self._session_iterator:
            return
        async for event in self._session_iterator:
            if event.author == self._identity:
                continue
            message = event.payload.get("summary") or event.kind
            log_entry = self.state.add_log("info", f"{event.author}: {message}", icon="👥")
            panel = self._main_panel or self.query_one("#main-panel", MainPanel)

            def append(entry: Text = Text(log_entry.format(), style="cyan")) -> None:
                panel.append(entry)

            self._panel_update(append)
            if self.announcer:
                await self.announcer.announce_collaboration(f"{event.author} {event.kind}")
            await self._refresh_session_metadata()

    async def _refresh_session_metadata(self) -> None:
        if not self.state.session_id:
            return
        details = await self.session_manager.session_details(self.state.session_id)
        self._apply_session_details(details)
        await self._update_session_panels()

    def _apply_session_details(self, details: Dict[str, Any]) -> None:
        session_id = details.get("session_id")
        if session_id:
            self.state.session_id = session_id
        collaborators: Dict[str, CollaboratorState] = {}
        for key, raw in details.get("collaborators", {}).items():
            if isinstance(raw, CollaboratorState):
                collaborators[key] = raw
                continue
            try:
                collaborators[key] = CollaboratorState(
                    user=raw.get("user", key),
                    host=raw.get("host", ""),
                    role=raw.get("role", "collaborator"),
                    read_only=bool(raw.get("read_only", False)),
                    last_seen=float(raw.get("last_seen", 0.0)),
                )
            except Exception:
                continue
        if collaborators:
            self.state.collaborators = collaborators
            self.state.session_acl = {key: value.role for key, value in collaborators.items()}
            if not self.state.team_nodes:
                self.state.team_nodes = {
                    key: {
                        "name": value.user,
                        "role": value.role,
                        "read_only": value.read_only,
                        "repositories": [],
                    }
                    for key, value in collaborators.items()
                }
        transcript = details.get("transcript")
        if transcript:
            self.state.transcript_path = transcript

    async def _update_session_panels(self) -> None:
        if not self._sessions_panel:
            return
        collaborator_payload = {
            key: {
                "user": value.user,
                "host": value.host,
                "role": value.role,
                "read_only": value.read_only,
                "last_seen": value.last_seen,
            }
            for key, value in self.state.collaborators.items()
        }
        checkpoints = [
            {
                "identifier": checkpoint.identifier,
                "summary": checkpoint.summary,
            }
            for checkpoint in self.state.checkpoints
        ]
        self._sessions_panel.update_sessions(
            collaborator_payload,
            lock_holder=self.state.session_lock_holder,
            checkpoints=checkpoints,
        )
        if self._team_panel:
            ledger = self.state.project_status.get("ledger", {})
            self._team_panel.update_nodes(self.state.team_nodes or collaborator_payload, ledger)
        if self._analytics_panel and self._last_analytics:
            self._analytics_panel.update_summary(self._last_analytics, self.state.insights)

    async def _auto_sync(self) -> None:
        if not self.state.session_id:
            return
        await self.session_manager.sync_now(self.state.session_id)
        await self._refresh_session_metadata()

    async def _show_dashboard(self, summary: Dict[str, Any], insights: Iterable[str]) -> None:
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            panel.show(analytics_dashboard(summary, list(insights)))
            timeline = summary.get("timeline")
            if timeline:
                panel.append(analytics_trend_panel(timeline))

        self._panel_update(display)
        insights_list = list(insights)
        self._last_analytics = summary
        self.state.insights = insights_list
        if self.announcer and insights_list:
            await self.announcer.announce_insight(insights_list[0])

    async def _manual_sync(self) -> None:
        if not self.state.session_id:
            return
        await self.session_manager.sync_now(self.state.session_id)
        await self._refresh_session_metadata()
        await self._announce("Session synchronised")

    def _panel_update(self, callback: Callable[[], None]) -> None:
        if self._panel_coalescer:
            self._panel_coalescer.enqueue(callback)
        else:
            callback()
            self._refresh_coalescer.request()

    def _start_spinner(self, label: str) -> None:
        if self._spinner_task and not self._spinner_task.done():
            self._spinner_task.cancel()
        self._spinner_label = label
        self._spinner_task = asyncio.create_task(self._spinner_loop(label))
        if self.announcer:
            asyncio.create_task(self.announcer.announce_progress(label.title()))

    async def _stop_spinner(self) -> None:
        if self._spinner_task:
            self._spinner_task.cancel()
            try:
                await self._spinner_task
            except asyncio.CancelledError:
                pass
            finally:
                self._spinner_task = None
                self._spinner_label = None
                self._refresh_coalescer.request()

    async def _spinner_loop(self, label: str) -> None:
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)
        frames = cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        try:
            while True:
                frame = next(frames)
                text = Text(f"{frame} {label.capitalize()}…", style="cyan")

                def apply(renderable: Text = text) -> None:
                    panel.show(renderable, plain_text=f"{label} in progress")

                self._panel_update(apply)
                await asyncio.sleep(max(self._frame_interval, 0.08))
        except asyncio.CancelledError:
            raise

    def _restore_logs(self) -> None:
        if not self.state.logs:
            return
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def apply() -> None:
            for entry in self.state.logs[-50:]:
                panel.append(Text(entry.format()), plain_text=entry.format())

        self._panel_update(apply)

    async def on_unmount(self) -> None:
        self.bridge.save_state(self.state)
        if self.tui_settings:
            await self.settings_manager.persist(self.tui_settings)

    async def _poll_status(self) -> None:
        await self.refresh_status()

    async def refresh_status(self) -> None:
        if not self.actions:
            return
        checkpoint = self.state.latest_checkpoint()
        with profile("status_refresh"):
            collaborators = [
                value.label() if isinstance(value, CollaboratorState) else key
                for key, value in self.state.collaborators.items()
            ]
            worker = self.work(
                self.status.gather(
                    mode=self.state.mode,
                    budget_minutes=self.state.budget_minutes,
                    checkpoint=checkpoint.identifier if checkpoint else None,
                    collaborators=collaborators,
                    lock_holder=self.state.session_lock_holder,
                ),
                exclusive=True,
                name="status-gather",
                group="status",
            )
            try:
                snapshot = await worker.wait()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.exception("status gather failed", exc_info=exc)
                return
        self._last_status = snapshot
        renderable = StatusAggregator.render(snapshot)
        self.state.status_renderable = renderable
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_status(renderable)
        self._update_telemetry(snapshot)
        if self._org_panel:
            ops_snapshot = self.runtime.ops_center.aggregate()

            def update_panel(snap: OpsSnapshot = ops_snapshot) -> None:
                self._org_panel.update_snapshot(snap)

            self._panel_update(update_panel)

    def _update_telemetry(self, snapshot: StatusSnapshot) -> None:
        if not self._telemetry_bar:
            return
        self._telemetry_bar.cpu_usage = snapshot.cpu_percent
        self._telemetry_bar.memory_usage = snapshot.memory_percent

    async def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            if self.command_bar:
                self.command_bar.clear_suggestions()
            return
        if text.startswith(":"):
            resolved = self._resolve_colon_command(text)
            if resolved is None:
                await self._open_palette(text[1:])
            else:
                await self._execute_command(resolved)
            return
        command = parse_slash_command(text)
        if not command:
            self.state.add_log("info", text)
            panel = self._main_panel or self.query_one("#main-panel", MainPanel)

            def append() -> None:
                panel.append(Text(text), plain_text=text)

            self._panel_update(append)
            self.state.last_plain_text = text
            await self._announce(f"Appended note: {text}")
            self._refresh_coalescer.request()
            if self.command_bar:
                self.command_bar.clear_suggestions()
            return
        await self._execute_command(command)

    @profile("tui.execute_command")
    async def _execute_command(self, command: SlashCommand) -> None:
        if not self.actions:
            return
        spinner = command.name in {"plan", "apply", "test", "simulate"}
        if spinner:
            self._start_spinner(command.name)
        try:
            result = await self.actions.handle(command)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("command failed", extra={"command": command.raw})
            self.state.add_log("error", str(exc))
            panel = self._main_panel or self.query_one("#main-panel", MainPanel)

            def show_error() -> None:
                panel.append(Text(f"Error: {exc}", style="bold red"))

            self._panel_update(show_error)
            await self._announce(f"Command failed: {exc}", severity="error")
            self._refresh_coalescer.request()
            return
        finally:
            if spinner:
                await self._stop_spinner()
        await self._render_result(command, result)
        if self.command_bar:
            self.command_bar.clear_suggestions()
        await self._handle_metadata(result.metadata)
        if command.name == "help":
            self.toggle_help()
        await self.refresh_status()

    async def _render_result(self, command: SlashCommand, result: CommandResult) -> None:
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)
        self.state.add_log("info", result.message)
        summary = Text(f"{command.raw} → {result.message}", style="green")

        def show_renderable() -> None:
            panel.show(result.renderable, plain_text=result.plain_text)
            panel.append(summary)

        def append_only() -> None:
            panel.append(summary, plain_text=result.plain_text)

        if result.renderable is not None:
            self._panel_update(show_renderable)
        else:
            self._panel_update(append_only)
        if result.plain_text:
            self.state.last_plain_text = result.plain_text
        self.state.active_panel = "main"
        self._refresh_coalescer.request()
        toast_meta = result.metadata.get("toast") if isinstance(result.metadata, dict) else None
        severity = "information"
        if isinstance(toast_meta, dict):
            severity = toast_meta.get("severity", severity)
        self.notify(result.message, severity=severity)
        await self._announce(result.message)
        if result.plain_text and self.announcer:
            await self.announcer.announce_plain_text(result.plain_text)
        elif result.plain_text:
            await self._announce(result.plain_text)

    async def _handle_metadata(self, metadata: dict[str, Any]) -> None:
        if not metadata:
            return
        persist_required = False
        if "theme" in metadata:
            theme_info = metadata["theme"]
            self.state.theme = theme_info.get("name", self.state.theme)
            self.state.high_contrast = theme_info.get("high_contrast", False)
            if self.tui_settings:
                self.tui_settings.theme = self.state.theme
                self.tui_settings.high_contrast = self.state.high_contrast
                if theme_info.get("custom_path"):
                    self.tui_settings.custom_theme_path = Path(
                        str(theme_info["custom_path"])
                    ).expanduser()
                persist_required = True
            self._apply_theme()
            await self._announce(f"Theme set to {self.state.theme}")
        if "accessibility" in metadata:
            prefs = metadata["accessibility"]
            if "enabled" in prefs:
                self.state.accessibility_enabled = prefs["enabled"]
                if self.announcer:
                    self.announcer.set_enabled(prefs["enabled"])
                if self.tui_settings:
                    self.tui_settings.accessibility_enabled = prefs["enabled"]
                    persist_required = True
            if "verbosity" in prefs:
                self.state.accessibility_verbosity = prefs["verbosity"]
                if self.announcer:
                    self.announcer.set_verbosity(prefs["verbosity"])
                if self.tui_settings:
                    self.tui_settings.accessibility_verbosity = prefs["verbosity"]
                    persist_required = True
            if "narration" in prefs:
                self.state.narration_enabled = prefs["narration"]
                if self.tui_settings:
                    self.tui_settings.narration_enabled = prefs["narration"]
                    persist_required = True
            if "contrast" in prefs:
                self.state.high_contrast = prefs["contrast"]
                if self.tui_settings:
                    self.tui_settings.high_contrast = prefs["contrast"]
                    persist_required = True
                self._apply_theme()
        if metadata.get("open_settings"):
            await self._open_settings()
        if metadata.get("quit"):
            await self.action_quit_app()
        if metadata.get("reload_theme"):
            self._apply_theme()
        if "lyra_prompt" in metadata:
            await self._open_lyra(metadata["lyra_prompt"])
        if "session" in metadata:
            self._apply_session_details(metadata["session"])
            await self._update_session_panels()
        if metadata.get("refresh_sessions"):
            await self._refresh_session_metadata()
        if "analytics" in metadata:
            summary = metadata["analytics"]
            self._last_analytics = summary
            self.state.session_metrics = summary.get("kpis", {})
            timeline = summary.get("timeline")
            if timeline:
                self.state.analytics_trends.append(timeline)
            insights = metadata.get("insights") or self.state.insights
            self.state.insights = insights
            if self._analytics_panel:
                self._analytics_panel.update_summary(summary, insights)
            if self.announcer and insights:
                await self.announcer.announce_insight(insights[0])
        elif "insights" in metadata:
            self.state.insights = metadata["insights"]
            if self._analytics_panel and self._last_analytics:
                self._analytics_panel.update_summary(self._last_analytics, self.state.insights)
        if metadata.get("open_dashboard"):
            summary = metadata.get("analytics") or self._last_analytics
            insights = metadata.get("insights") or self.state.insights
            if summary:
                await self._show_dashboard(summary, insights)
        if "team_nodes" in metadata:
            self.state.team_nodes = metadata.get("team_nodes", {})
            ledger = metadata.get("ledger", self.state.project_status.get("ledger", {}))
            if self._team_panel:
                self._team_panel.update_nodes(self.state.team_nodes, ledger)
        if "project_status" in metadata:
            self.state.project_status = metadata["project_status"]
        if "pipeline_history" in metadata:
            self.state.pipeline_history.extend(metadata.get("pipeline_history", []))
        if "governance" in metadata:
            self.state.governance_reports.append(metadata["governance"])
        if any(key in metadata for key in ("project_status", "pipeline_history", "governance")):
            payload = {
                "milestones": self.state.project_status.get("milestones", []),
                "pipelines": self.state.pipeline_history,
                "governance": self.state.governance_reports,
                "summary": metadata.get("summary", self.state.project_status.get("summary", "")),
            }
            if self._project_panel:
                self._project_panel.update_dashboard(payload)
        if "ledger" in metadata and self._team_panel:
            self._team_panel.update_nodes(self.state.team_nodes, metadata["ledger"])
        if persist_required and self.tui_settings:
            await self.settings_manager.persist(self.tui_settings)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self.handle_input(event.value)
        event.input.value = ""

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-input" or not self.command_bar:
            return
        query = event.value.strip()
        cleaned = query.lstrip("/:").strip()
        if not cleaned:
            self.command_bar.clear_suggestions()
            return
        entries = search_entries(self.state, cleaned, runtime=self.runtime)
        self.command_bar.update_suggestions(entries)

    async def _open_palette(self, query: str = "") -> None:
        entries = search_entries(self.state, query, runtime=self.runtime)
        table = Table.grid(expand=True)
        table.add_column("Command")
        table.add_column("Description")
        for entry in entries:
            table.add_row(entry.command, f"{entry.hint} ({entry.category})")
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            panel.show(table)

        self._panel_update(display)
        await self._announce("Palette opened")
        self._refresh_coalescer.request()

    def _resolve_colon_command(self, text: str) -> Optional[SlashCommand]:
        mapping = {
            ":q": "/quit",
            ":quit": "/quit",
            ":help": "/help",
            ":settings": "/settings",
        }
        if text in mapping:
            return parse_slash_command(mapping[text])
        if text.startswith(":palette"):
            return None
        if text.startswith(":theme"):
            _, _, arg = text.partition(" ")
            return parse_slash_command(f"/theme {arg.strip()}" if arg else "/theme")
        return None

    async def _open_settings(self) -> None:
        screen = SettingsScreen(self.tui_settings or TUISettings())
        self.push_screen(screen)
        updated = await screen.wait()
        if updated is None:
            return
        self.tui_settings = updated
        await self.settings_manager.persist(updated)
        self._apply_settings_to_state()
        self._apply_theme()
        await self._announce("Settings updated")

    async def handle_command_bar_suggestion_selected(
        self, message: CommandBar.SuggestionSelected
    ) -> None:
        if not self.command_bar:
            return
        input_widget = self.command_bar.input
        input_widget.value = message.command
        input_widget.cursor_position = len(message.command)
        input_widget.focus()
        self.command_bar.clear_suggestions()

    async def _open_lyra(self, prompt: str) -> None:
        if not self.state.feature_flags.get("lyra_assistant", True):
            self.state.add_log("warning", "Lyra assistant disabled")
            return
        result = await self.lyra.invoke(prompt)
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            panel.show(result.renderable, plain_text=result.plain_text)

        self._panel_update(display)
        self.state.last_plain_text = result.plain_text
        await self._announce(result.message)
        await self._announce(result.plain_text)
        self._refresh_coalescer.request()

    async def action_focus_next(self) -> None:
        self._focus_index = (self._focus_index + 1) % len(self._focus_order)
        await self._focus_panel(self._focus_order[self._focus_index])

    async def action_focus_previous(self) -> None:
        self._focus_index = (self._focus_index - 1) % len(self._focus_order)
        await self._focus_panel(self._focus_order[self._focus_index])

    async def _focus_panel(self, panel_id: str) -> None:
        widget = self.query_one(f"#{panel_id}")
        widget.focus()
        if self.announcer:
            await self.announcer.announce_panel(panel_id.replace("-", " ").title())
        else:
            await self._announce(f"Focus moved to {panel_id}")

    async def action_sessions_focus(self) -> None:
        await self._focus_panel("sessions-panel")

    async def action_analytics_focus(self) -> None:
        await self._focus_panel("analytics-panel")

    async def action_org_focus(self) -> None:
        await self._focus_panel("org-panel")

    async def action_alerts_focus(self) -> None:
        await self._focus_panel("org-panel")
        alerts = self.runtime.ops_center.active_alerts()
        if not alerts:
            await self._announce("No active alerts")
            return
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            table = self.runtime.ops_center.alerts_table()
            panel.show(table, plain_text="alerts")

        self._panel_update(display)
        if self.announcer:
            await self.announcer.announce_alert(alerts[0].message)

    async def action_graph_focus(self) -> None:
        snapshot = self.runtime.knowledge_graph.snapshot()
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            table = Table(title="Knowledge Graph Snapshot", expand=True)
            table.add_column("Entities")
            table.add_column("Relations")
            table.add_row(str(len(snapshot.entities)), str(len(snapshot.relations)))
            panel.show(table, plain_text="knowledge graph snapshot")

        self._panel_update(display)
        await self._focus_panel("main-panel")

    async def action_dashboard_open(self) -> None:
        summary = self._last_analytics
        insights = self.state.insights
        if not summary and self.state.session_id:
            summary = await self.session_manager.analytics_report(self.state.session_id)
            insights = await self.session_manager.analytics_insights(self.state.session_id)
        if summary:
            await self._show_dashboard(summary, insights or [])

    async def action_sync_now(self) -> None:
        await self._manual_sync()

    async def action_palette_open(self) -> None:
        input_widget = self.query_one("#command-input", Input)
        input_widget.value = ":"
        input_widget.focus()
        await self._open_palette()

    async def action_slash_focus(self) -> None:
        input_widget = self.query_one("#command-input", Input)
        input_widget.value = "/"
        input_widget.focus()

    async def action_help_toggle(self) -> None:
        self.toggle_help()

    def toggle_help(self) -> None:
        help_panel = self.query_one("#help-panel")
        if help_panel.has_class("hidden"):
            help_panel.remove_class("hidden")
            help_panel.display = True
        else:
            help_panel.add_class("hidden")
            help_panel.display = False

    async def action_tools_toggle(self) -> None:
        panel = self.query_one("#tool-panel", ToolPanel)
        if panel.has_class("hidden"):
            panel.remove_class("hidden")
            panel.display = True
            tools = self._discover_tools()
            panel.populate(tools)
            await self._announce("Tools panel opened")
        else:
            panel.add_class("hidden")
            panel.display = False
            await self._announce("Tools panel closed")

    def _discover_tools(self) -> Iterable[str]:
        plugins = getattr(self.runtime, "plugins", None)
        if plugins is None:
            return []
        try:
            discovered = plugins.discover()
            return sorted(discovered.keys())
        except Exception:
            return []

    async def action_action_apply(self) -> None:
        await self._execute_command(SlashCommand(raw="/apply", name="apply", args=[], options={}))

    async def action_action_undo(self) -> None:
        await self._execute_command(SlashCommand(raw="/undo", name="undo", args=[], options={}))

    async def action_action_plan(self) -> None:
        await self._execute_command(SlashCommand(raw="/plan", name="plan", args=[], options={}))

    async def action_action_simulate(self) -> None:
        await self._execute_command(SlashCommand(raw="/simulate", name="simulate", args=[], options={}))

    async def action_action_test(self) -> None:
        await self._execute_command(SlashCommand(raw="/test", name="test", args=[], options={}))

    async def action_settings_open(self) -> None:
        await self._open_settings()

    async def action_theme_reload(self) -> None:
        self._apply_theme()
        await self._announce("Theme reloaded")

    async def action_history_search(self) -> None:
        if self.command_bar is None:
            return
        query = await self.prompt("History search")
        matches = self.state.search_history(query or "")
        table = Table(title="History", expand=True)
        table.add_column("Command")
        for item in matches:
            table.add_row(item)
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            panel.show(table)

        self._panel_update(display)
        await self._announce("History displayed")

    async def action_team_new_node(self) -> None:
        await self.handle_input("/session new")

    async def action_ledger_view(self) -> None:
        ledger = self.state.project_status.get("ledger", {})
        table = Table(title="Budget Ledger", expand=True)
        table.add_column("Metric")
        table.add_column("Value")
        for key, value in ledger.items():
            table.add_row(key.title(), f"{value}")
        panel = self._main_panel or self.query_one("#main-panel", MainPanel)

        def display() -> None:
            panel.show(table)

        self._panel_update(display)
        await self._announce("Ledger summary displayed")

    async def action_team_broadcast(self) -> None:
        if self.command_bar:
            self.command_bar.input.value = "/broadcast "
            self.command_bar.input.focus()

    async def action_project_dashboard(self) -> None:
        if self._project_panel:
            await self.set_focus(self._project_panel)
            await self._announce("Project dashboard focused")
        else:
            await self.handle_input("/project status")

    async def action_pipeline_run_hotkey(self) -> None:
        if self.command_bar:
            self.command_bar.input.value = "/pipeline run "
            self.command_bar.input.focus()

    async def action_pipeline_logs_hotkey(self) -> None:
        if self.command_bar:
            self.command_bar.input.value = "/pipeline dashboard"
            self.command_bar.input.focus()

    async def action_quit_app(self) -> None:
        screen = ConfirmQuitScreen()
        self.push_screen(screen)
        confirm = await screen.wait()
        if confirm:
            await self._announce("Exiting session", severity="warning")
            self.exit()

    async def action_list_down(self) -> None:
        self._list_action("down")

    async def action_list_up(self) -> None:
        self._list_action("up")

    async def action_list_top(self) -> None:
        self._list_action("top")

    async def action_list_bottom(self) -> None:
        self._list_action("bottom")

    async def action_list_activate(self) -> None:
        self._list_action("activate")

    def _list_action(self, action: str) -> None:
        widget = self.focused
        if isinstance(widget, ListView):
            if action == "down":
                widget.action_cursor_down()
            elif action == "up":
                widget.action_cursor_up()
            elif action == "top":
                widget.index = 0
            elif action == "bottom":
                widget.index = max(0, len(widget.children) - 1)
            elif action == "activate":
                widget.action_select()

    async def action_diff_prev_hunk(self) -> None:
        await self._announce("Previous diff hunk")

    async def action_diff_next_hunk(self) -> None:
        await self._announce("Next diff hunk")

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.toggle_help()

    async def handle_accessibility_toggle(self, message: AccessibilityToggle) -> None:
        if not self.announcer:
            return
        self.announcer.set_enabled(message.enabled)
        self.state.accessibility_enabled = message.enabled
        await self._announce(
            f"Accessibility {'enabled' if message.enabled else 'disabled'}",
            severity="information",
        )

    async def handle_accessibility_preferences_changed(
        self, message: AccessibilityPreferencesChanged
    ) -> None:
        if not self.announcer:
            return
        self.announcer.set_verbosity(message.preferences.verbosity)
        await self._announce(f"Verbosity {message.preferences.verbosity}")

    async def on_error(self, error: Exception) -> None:  # pragma: no cover - defensive
        self.state.add_log("error", str(error))
        logger.exception("tui unhandled error", exc_info=error)
        await self._announce(f"Unhandled error: {error}", severity="error")

    async def _announce(self, message: str, *, severity: str = "info") -> None:
        if self.announcer:
            await self.announcer.announce(message, severity=severity)


async def launch_tui(runtime: Any, options: TUIOptions) -> None:
    """Launch the TUI using Textual's asynchronous API."""

    app = VortexTUI(runtime, options)
    await app.run_async()


__all__ = ["VortexTUI", "launch_tui"]
