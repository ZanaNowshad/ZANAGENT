"""Textual application powering the Vortex terminal experience."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView

from vortex.utils.logging import get_logger
from vortex.utils.profiling import profile

from .actions import CommandResult, TUIActionCenter
from .accessibility import (
    AccessibilityAnnouncer,
    AccessibilityPreferences,
    AccessibilityPreferencesChanged,
    AccessibilityToggle,
)
from .command_parser import SlashCommand, parse_slash_command
from .context import TUIOptions, TUIRuntimeBridge, TUISessionState
from .hotkeys import bindings_for_app
from .layout import build_layout
from .lyra_assistant import LyraAssistant
from .palette import search_entries
from .panels import MainPanel, StatusPanel, TelemetryBar, ToolPanel
from .settings import InitialSetupWizard, SettingsScreen, TUISettings, TUISettingsManager
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
        fps = max(15, min(120, int(os.getenv("VORTEX_TUI_FPS", "60"))))
        self._frame_interval = 1.0 / fps
        self._refresh_coalescer = RefreshCoalescer(self, self._frame_interval)
        self.actions: Optional[TUIActionCenter] = None
        self.announcer: Optional[AccessibilityAnnouncer] = None
        self.lyra = LyraAssistant(runtime)
        self._theme_css: str = ""
        self._focus_order = ["main-panel", "context-panel", "actions-panel", "status-panel"]
        self._focus_index = 0
        self._telemetry_bar: Optional[TelemetryBar] = None
        self._last_status: Optional[StatusSnapshot] = None

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
        prefs = AccessibilityPreferences(
            enabled=self.state.accessibility_enabled,
            verbosity=self.state.accessibility_verbosity,
            announce_narration=self.state.narration_enabled,
        )
        self.announcer = AccessibilityAnnouncer(self, preferences=prefs)
        self.actions = TUIActionCenter(
            self.runtime,
            self.state,
            self.status,
            syntax_theme=self._syntax_theme_name(),
        )
        await self._announce("TUI initialised")
        self._telemetry_bar = self.query_one("#telemetry-bar", TelemetryBar)
        await self.refresh_status()
        self._restore_logs()
        self.set_interval(5.0, self._poll_status)
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

    def _restore_logs(self) -> None:
        if not self.state.logs:
            return
        panel = self.query_one("#main-panel", MainPanel)
        for entry in self.state.logs[-50:]:
            panel.append(Text(entry.format()), plain_text=entry.format())

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
            worker = self.run_worker(
                self.status.gather(
                    mode=self.state.mode,
                    budget_minutes=self.state.budget_minutes,
                    checkpoint=checkpoint.identifier if checkpoint else None,
                ),
                exclusive=True,
                name="status-gather",
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

    def _update_telemetry(self, snapshot: StatusSnapshot) -> None:
        if not self._telemetry_bar:
            return
        self._telemetry_bar.cpu_usage = snapshot.cpu_percent
        self._telemetry_bar.memory_usage = snapshot.memory_percent

    async def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text.startswith(":"):
            await self._open_palette(text[1:])
            return
        command = parse_slash_command(text)
        if not command:
            self.state.add_log("info", text)
            panel = self.query_one("#main-panel", MainPanel)
            panel.append(Text(text))
            self.state.last_plain_text = text
            await self._announce(f"Appended note: {text}")
            self._refresh_coalescer.request()
            return
        await self._execute_command(command)

    async def _execute_command(self, command: SlashCommand) -> None:
        if not self.actions:
            return
        try:
            result = await self.actions.handle(command)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("command failed", extra={"command": command.raw})
            self.state.add_log("error", str(exc))
            panel = self.query_one("#main-panel", MainPanel)
            panel.append(Text(f"Error: {exc}", style="bold red"))
            await self._announce(f"Command failed: {exc}", severity="error")
            self._refresh_coalescer.request()
            return
        self._render_result(command, result)
        await self._handle_metadata(result.metadata)
        if command.name == "help":
            self.toggle_help()
        await self.refresh_status()

    def _render_result(self, command: SlashCommand, result: CommandResult) -> None:
        panel = self.query_one("#main-panel", MainPanel)
        self.state.add_log("info", result.message)
        summary = Text(f"{command.raw} → {result.message}", style="green")
        if result.renderable is not None:
            panel.show(result.renderable, plain_text=result.plain_text)
            panel.append(summary)
        else:
            panel.append(summary, plain_text=result.plain_text)
        if result.plain_text:
            self.state.last_plain_text = result.plain_text
        self.state.active_panel = "main"
        self._refresh_coalescer.request()
        asyncio.create_task(self._announce(result.message))
        if result.plain_text:
            asyncio.create_task(self._announce(result.plain_text))

    async def _handle_metadata(self, metadata: dict[str, Any]) -> None:
        if not metadata:
            return
        if "theme" in metadata:
            theme_info = metadata["theme"]
            self.state.theme = theme_info.get("name", self.state.theme)
            self.state.high_contrast = theme_info.get("high_contrast", False)
            if self.tui_settings:
                self.tui_settings.theme = self.state.theme
                self.tui_settings.high_contrast = self.state.high_contrast
            self._apply_theme()
            await self._announce(f"Theme set to {self.state.theme}")
        if "accessibility" in metadata and self.announcer:
            prefs = metadata["accessibility"]
            if "enabled" in prefs:
                self.announcer.set_enabled(prefs["enabled"])
                self.state.accessibility_enabled = prefs["enabled"]
            if "verbosity" in prefs:
                self.announcer.set_verbosity(prefs["verbosity"])
                self.state.accessibility_verbosity = prefs["verbosity"]
        if metadata.get("open_settings"):
            await self._open_settings()
        if metadata.get("quit"):
            await self.action_quit_app()
        if metadata.get("reload_theme"):
            self._apply_theme()
        if "lyra_prompt" in metadata:
            await self._open_lyra(metadata["lyra_prompt"])

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self.handle_input(event.value)
        event.input.value = ""

    async def _open_palette(self, query: str = "") -> None:
        entries = search_entries(self.state, query, runtime=self.runtime)
        table = Table.grid(expand=True)
        table.add_column("Command")
        table.add_column("Description")
        for entry in entries:
            table.add_row(entry.command, f"{entry.hint} ({entry.category})")
        panel = self.query_one("#main-panel", MainPanel)
        panel.show(table)
        await self._announce("Palette opened")
        self._refresh_coalescer.request()

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

    async def _open_lyra(self, prompt: str) -> None:
        if not self.state.feature_flags.get("lyra_assistant", True):
            self.state.add_log("warning", "Lyra assistant disabled")
            return
        result = await self.lyra.invoke(prompt)
        panel = self.query_one("#main-panel", MainPanel)
        panel.show(result.renderable, plain_text=result.plain_text)
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
        await self._announce(f"Focus moved to {panel_id}")

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
        table = Table.grid(expand=True)
        table.add_column("Recent Commands")
        for command in self.state.search_history(""):
            table.add_row(command)
        panel = self.query_one("#main-panel", MainPanel)
        panel.show(table)
        await self._announce("Displayed recent commands")
        self._refresh_coalescer.request()

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
        await self._announce(f"Unhandled error: {error}", severity="error")

    async def _announce(self, message: str, *, severity: str = "info") -> None:
        if self.announcer:
            await self.announcer.announce(message, severity=severity)


async def launch_tui(runtime: Any, options: TUIOptions) -> None:
    """Launch the TUI using Textual's asynchronous API."""

    app = VortexTUI(runtime, options)
    await app.run_async()


__all__ = ["VortexTUI", "launch_tui"]
