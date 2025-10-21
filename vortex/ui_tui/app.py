"""Textual application powering the Vortex terminal experience."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Input, ListView

from vortex.utils.logging import get_logger

from .actions import CommandResult, TUIActionCenter
from .accessibility import AccessibilityAnnouncer, AccessibilityToggle
from .command_parser import SlashCommand, parse_slash_command
from .context import TUIOptions, TUIRuntimeBridge, TUISessionState
from .hotkeys import bindings_for_app
from .layout import build_layout
from .palette import iter_palette_entries
from .panels import MainPanel, StatusPanel, ToolPanel
from .status import StatusAggregator
from .themes import theme_css

logger = get_logger(__name__)


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
        self._theme_mode = self._determine_theme_mode()
        self._theme_css = theme_css(self._theme_mode, no_color=self.options.no_color)
        self.actions = TUIActionCenter(
            runtime,
            self.state,
            self.status,
            syntax_theme=self._syntax_theme_name(),
        )
        self.announcer = AccessibilityAnnouncer(self, enabled=options.screen_reader)
        self._focus_order = ["main-panel", "context-panel", "actions-panel", "status-panel"]
        self._focus_index = 0

    def _load_state(self, options: TUIOptions) -> TUISessionState:
        if options.resume:
            previous = self.bridge.load_state()
            if previous:
                return previous
        return TUISessionState()

    def _determine_theme_mode(self) -> str:
        mode = self.options.color_scheme
        if mode == "auto":
            settings = getattr(self.runtime, "settings", None)
            mode = getattr(settings.ui, "theme", "dark") if settings else "dark"
        return mode if mode in {"dark", "light"} else "dark"

    def _syntax_theme_name(self) -> str:
        if self.options.no_color:
            return "ansi"
        return "ansi_light" if self._theme_mode == "light" else "ansi_dark"

    def compose(self) -> ComposeResult:
        layout = build_layout(Path.cwd())
        yield layout

    async def on_mount(self) -> None:
        self.stylesheet.read(self._theme_css)
        await self.announcer.announce("TUI initialised", severity="information")
        await self.refresh_status()
        self._restore_logs()
        self.set_interval(5.0, self._poll_status)
        self.query_one("#command-input", Input).focus()

    def _restore_logs(self) -> None:
        if not self.state.logs:
            return
        panel = self.query_one("#main-panel", MainPanel)
        for entry in self.state.logs[-50:]:
            panel.append(Text(entry.format()))

    async def on_unmount(self) -> None:
        self.bridge.save_state(self.state)

    async def _poll_status(self) -> None:
        await self.refresh_status()

    async def refresh_status(self) -> None:
        checkpoint = self.state.latest_checkpoint()
        snapshot = await self.status.gather(
            mode=self.state.mode,
            budget_minutes=self.state.budget_minutes,
            checkpoint=checkpoint.identifier if checkpoint else None,
        )
        renderable = StatusAggregator.render(snapshot)
        self.state.status_renderable = renderable
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_status(renderable)

    async def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text.startswith(":"):
            await self._open_palette()
            return
        command = parse_slash_command(text)
        if not command:
            self.state.add_log("info", text)
            self.query_one("#main-panel", MainPanel).append(Text(text))
            await self.announcer.announce(f"Appended freeform note: {text}")
            return
        await self._execute_command(command)

    async def _execute_command(self, command: SlashCommand) -> None:
        try:
            result = await self.actions.handle(command)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("command failed", extra={"command": command.raw})
            self.state.add_log("error", str(exc))
            self.query_one("#main-panel", MainPanel).append(Text(f"Error: {exc}", style="bold red"))
            await self.announcer.announce(f"Command failed: {exc}", severity="error")
            return
        self._render_result(command, result)
        if command.name == "help":
            self.toggle_help()
        await self.refresh_status()

    def _render_result(self, command: SlashCommand, result: CommandResult) -> None:
        panel = self.query_one("#main-panel", MainPanel)
        self.state.add_log("info", result.message)
        summary = Text(f"{command.raw} → {result.message}", style="green")
        if result.renderable is not None:
            panel.show(result.renderable)
            panel.append(summary)
        else:
            panel.append(summary)
        self.state.active_panel = "main"

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self.handle_input(event.value)
        event.input.value = ""

    async def _open_palette(self) -> None:
        entries = list(iter_palette_entries(self.state))
        renderable = Text("\n".join(f"{item.command} — {item.hint}" for item in entries))
        panel = self.query_one("#main-panel", MainPanel)
        panel.show(renderable)
        await self.announcer.announce("Palette opened")

    async def action_focus_next(self) -> None:
        self._focus_index = (self._focus_index + 1) % len(self._focus_order)
        await self._focus_panel(self._focus_order[self._focus_index])

    async def action_focus_previous(self) -> None:
        self._focus_index = (self._focus_index - 1) % len(self._focus_order)
        await self._focus_panel(self._focus_order[self._focus_index])

    async def _focus_panel(self, panel_id: str) -> None:
        widget = self.query_one(f"#{panel_id}")
        widget.focus()
        await self.announcer.announce(f"Focus moved to {panel_id}")

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
            await self.announcer.announce("Tools panel opened")
        else:
            panel.add_class("hidden")
            panel.display = False
            await self.announcer.announce("Tools panel closed")

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
        await self.announcer.announce("Previous diff hunk")

    async def action_diff_next_hunk(self) -> None:
        await self.announcer.announce("Next diff hunk")

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.toggle_help()

    async def handle_accessibility_toggle(self, message: AccessibilityToggle) -> None:
        self.announcer.set_enabled(message.enabled)
        await self.announcer.announce(
            f"Accessibility {'enabled' if message.enabled else 'disabled'}",
            severity="information",
        )


async def launch_tui(runtime: Any, options: TUIOptions) -> None:
    """Launch the TUI using Textual's asynchronous API."""

    app = VortexTUI(runtime, options)
    await app.run_async()


__all__ = ["VortexTUI", "launch_tui"]
