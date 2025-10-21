"""Settings management and setup flows for the Vortex TUI."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select

try:  # pragma: no cover - psutil optional for packaging
    import tomllib
except ModuleNotFoundError:  # Python <3.11 fallback should never trigger in CI
    tomllib = None  # type: ignore[assignment]


DEFAULT_FLAGS: Dict[str, bool] = {"experimental_tui": False, "lyra_assistant": True}


@dataclass
class TUISettings:
    """Persisted configuration backing the user experience."""

    model: Optional[str] = None
    theme: str = "dark"
    high_contrast: bool = False
    accessibility_enabled: bool = False
    accessibility_verbosity: str = "normal"
    narration_enabled: bool = False
    telemetry_opt_in: Optional[bool] = None
    write_guard: Optional[bool] = None
    feature_flags: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_FLAGS))
    custom_theme_path: Optional[Path] = None

    def missing_keys(self) -> set[str]:
        missing: set[str] = set()
        if not self.model:
            missing.add("model")
        if self.telemetry_opt_in is None:
            missing.add("telemetry")
        if self.write_guard is None:
            missing.add("write_guard")
        if not self.theme:
            missing.add("colors")
        return missing

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "model": self.model,
            "theme": self.theme,
            "high_contrast": self.high_contrast,
            "accessibility_enabled": self.accessibility_enabled,
            "accessibility_verbosity": self.accessibility_verbosity,
            "narration_enabled": self.narration_enabled,
            "telemetry_opt_in": self.telemetry_opt_in,
            "write_guard": self.write_guard,
            "feature_flags": self.feature_flags,
        }
        if self.custom_theme_path is not None:
            data["custom_theme_path"] = str(self.custom_theme_path)
        return data

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "TUISettings":
        settings = cls()
        settings.model = payload.get("model")
        settings.theme = payload.get("theme", settings.theme)
        settings.high_contrast = payload.get("high_contrast", settings.high_contrast)
        settings.accessibility_enabled = payload.get(
            "accessibility_enabled", settings.accessibility_enabled
        )
        settings.accessibility_verbosity = payload.get(
            "accessibility_verbosity", settings.accessibility_verbosity
        )
        settings.narration_enabled = payload.get("narration_enabled", settings.narration_enabled)
        settings.telemetry_opt_in = payload.get("telemetry_opt_in", settings.telemetry_opt_in)
        settings.write_guard = payload.get("write_guard", settings.write_guard)
        settings.feature_flags.update(payload.get("feature_flags", {}))
        custom = payload.get("custom_theme_path")
        if custom:
            settings.custom_theme_path = Path(str(custom)).expanduser()
        return settings


class SettingsChanged(Message):
    """Message emitted when settings were updated via the UI."""

    def __init__(self, settings: TUISettings) -> None:
        self.settings = settings
        super().__init__()


class TUISettingsManager:
    """Load and persist Textual-specific settings."""

    def __init__(self, *, global_path: Optional[Path] = None, local_path: Optional[Path] = None) -> None:
        self.global_path = global_path or Path.home() / ".vortex" / "config.toml"
        self.local_path = local_path or Path.cwd() / ".agentrc"
        self._settings: Optional[TUISettings] = None
        self._raw_global: Dict[str, Any] = {}
        self._raw_local: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def load(self) -> TUISettings:
        async with self._lock:
            if self._settings is not None:
                return self._settings
            merged: Dict[str, Any] = {}
            self._raw_global = self._read_config(self.global_path)
            self._raw_local = self._read_config(self.local_path)
            for payload in (self._raw_global, self._raw_local):
                if not payload:
                    continue
                merged.update(payload.get("tui", {}))
            self._settings = TUISettings.from_mapping(merged)
            return self._settings

    async def reload(self) -> TUISettings:
        async with self._lock:
            self._settings = None
        return await self.load()

    async def persist(self, settings: TUISettings) -> None:
        async with self._lock:
            self._settings = settings
            data = dict(self._raw_global)
            tui_payload = settings.to_dict()
            data.setdefault("tui", {})
            data["tui"].update(tui_payload)
            self._write_config(self.global_path, data)
            self._raw_global = data

    async def update(self, **updates: Any) -> TUISettings:
        settings = await self.load()
        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        await self.persist(settings)
        return settings

    async def needs_initial_setup(self) -> bool:
        settings = await self.load()
        return bool(settings.missing_keys())

    @staticmethod
    def _read_config(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            if path.suffix in {".yaml", ".yml"}:
                return yaml.safe_load(path.read_text()) or {}
            if path.suffix == ".toml" and tomllib is not None:
                with path.open("rb") as handle:
                    return tomllib.load(handle)
        except Exception:
            return {}
        return {}

    @staticmethod
    def _write_config(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in {".yaml", ".yml"}:
            path.write_text(yaml.safe_dump(payload, sort_keys=True))
            return
        content = _dump_toml(payload)
        path.write_text(content)


class _BaseSettingsScreen(ModalScreen[Optional[TUISettings]]):
    """Shared helpers for settings modals."""

    CSS = """
    #settings-panel {
        padding: 1 2;
        border: heavy $accent;
        background: $panel;
        width: 70%;
        max-width: 90;
        margin: auto;
    }
    #settings-actions {
        padding-top: 1;
    }
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, defaults: TUISettings) -> None:
        super().__init__()
        self.defaults = defaults
        self._future: asyncio.Future[Optional[TUISettings]] = asyncio.get_running_loop().create_future()

    async def wait(self) -> Optional[TUISettings]:
        return await self._future

    def _set_result(self, settings: Optional[TUISettings]) -> None:
        if not self._future.done():
            self._future.set_result(settings)

    def action_cancel(self) -> None:
        self._set_result(None)
        self.dismiss(None)


class InitialSetupWizard(_BaseSettingsScreen):
    """Modal wizard requesting the minimum viable configuration."""

    def __init__(self, defaults: TUISettings) -> None:
        super().__init__(defaults)
        self._step = 0

    def compose(self) -> ComposeResult:
        yield Container(
            Vertical(
                Label("Welcome to Vortex", id="wizard-title"),
                Label(
                    "We need a few details to tailor the experience. Use Tab/Shift+Tab to navigate.",
                    id="wizard-subtitle",
                ),
                Container(
                    self._model_step(),
                    self._appearance_step(),
                    self._safety_step(),
                    id="settings-steps",
                ),
                Horizontal(
                    Button("Back", id="wizard-back", disabled=True),
                    Button("Next", id="wizard-next"),
                    id="settings-actions",
                ),
                id="settings-panel",
            ),
        )

    def on_mount(self) -> None:  # pragma: no cover - visual only
        self._show_step(0)
        self.query_one("#wizard-model", Input).focus()

    def _model_step(self) -> Container:
        return Container(
            Label("Default model"),
            Input(
                value=self.defaults.model or os.environ.get("VORTEX_DEFAULT_MODEL", ""),
                placeholder="e.g. gpt-4",
                id="wizard-model",
            ),
            Label("Choose how verbose on-screen narration should be."),
            Select(
                (
                    ("Minimal", "minimal"),
                    ("Normal", "normal"),
                    ("Verbose", "verbose"),
                ),
                value=self.defaults.accessibility_verbosity,
                id="wizard-verbosity",
            ),
            id="step-0",
            classes="wizard-step",
        )

    def _appearance_step(self) -> Container:
        return Container(
            Label("Pick a theme"),
            Select(
                (
                    ("Dark", "dark"),
                    ("Light", "light"),
                    ("High Contrast", "high_contrast"),
                ),
                value=self.defaults.theme,
                id="wizard-theme",
            ),
            Checkbox(
                "Enable high contrast mode", value=self.defaults.high_contrast, id="wizard-contrast"
            ),
            Checkbox(
                "Enable narration for screen readers",
                value=self.defaults.narration_enabled,
                id="wizard-narration",
            ),
            id="step-1",
            classes="wizard-step hidden",
        )

    def _safety_step(self) -> Container:
        return Container(
            Label("Privacy & safety"),
            Checkbox(
                "Share anonymised telemetry",
                value=bool(self.defaults.telemetry_opt_in),
                id="wizard-telemetry",
            ),
            Checkbox(
                "Enable write guard (confirm before overwriting files)",
                value=self.defaults.write_guard if self.defaults.write_guard is not None else True,
                id="wizard-write-guard",
            ),
            Checkbox(
                "Enable accessibility announcements",
                value=self.defaults.accessibility_enabled,
                id="wizard-accessibility",
            ),
            id="step-2",
            classes="wizard-step hidden",
        )

    def _show_step(self, step: int) -> None:
        steps = self.query(".wizard-step")
        for index, widget in enumerate(steps):
            if index == step:
                widget.remove_class("hidden")
            else:
                widget.add_class("hidden")
        back = self.query_one("#wizard-back", Button)
        next_button = self.query_one("#wizard-next", Button)
        back.disabled = step == 0
        next_button.label = "Finish" if step == len(steps) - 1 else "Next"
        self._step = step

    @on(Button.Pressed, "#wizard-next")
    def _handle_next(self, _: Button.Pressed) -> None:
        steps = list(self.query(".wizard-step"))
        if self._step >= len(steps) - 1:
            self._finish()
            return
        self._show_step(self._step + 1)
        self._focus_visible()

    @on(Button.Pressed, "#wizard-back")
    def _handle_back(self, _: Button.Pressed) -> None:
        if self._step == 0:
            return
        self._show_step(self._step - 1)
        self._focus_visible()

    def _finish(self) -> None:
        model = self.query_one("#wizard-model", Input).value.strip() or None
        verbosity = self.query_one("#wizard-verbosity", Select).value or "normal"
        theme_value = self.query_one("#wizard-theme", Select).value or "dark"
        high_contrast = bool(self.query_one("#wizard-contrast", Checkbox).value)
        narration = bool(self.query_one("#wizard-narration", Checkbox).value)
        telemetry = bool(self.query_one("#wizard-telemetry", Checkbox).value)
        write_guard = bool(self.query_one("#wizard-write-guard", Checkbox).value)
        accessibility = bool(self.query_one("#wizard-accessibility", Checkbox).value)
        if theme_value == "high_contrast":
            theme = "dark"
            high_contrast = True
        else:
            theme = theme_value
        settings = TUISettings(
            model=model,
            theme=theme,
            high_contrast=high_contrast,
            accessibility_enabled=accessibility,
            accessibility_verbosity=verbosity,
            narration_enabled=narration,
            telemetry_opt_in=telemetry,
            write_guard=write_guard,
            feature_flags=dict(DEFAULT_FLAGS),
        )
        self._set_result(settings)
        self.dismiss(settings)

    def _focus_visible(self) -> None:
        visible = list(
            self.query(".wizard-step:not(.hidden) Input, .wizard-step:not(.hidden) Select")
        )
        if visible:
            visible[0].focus()


class SettingsScreen(_BaseSettingsScreen):
    """Editable settings surface accessible during a session."""

    def compose(self) -> ComposeResult:
        yield Container(
            Vertical(
                Label("Session Settings", id="settings-title"),
                Select(
                    (
                        ("Dark", "dark"),
                        ("Light", "light"),
                        ("High Contrast", "high_contrast"),
                    ),
                    value="high_contrast" if self.defaults.high_contrast else self.defaults.theme,
                    id="settings-theme",
                ),
                Checkbox(
                    "Enable accessibility narration",
                    value=self.defaults.accessibility_enabled,
                    id="settings-accessibility",
                ),
                Checkbox(
                    "Enable high contrast palette",
                    value=self.defaults.high_contrast,
                    id="settings-contrast",
                ),
                Checkbox(
                    "Announce verbose updates",
                    value=self.defaults.accessibility_verbosity == "verbose",
                    id="settings-verbosity",
                ),
                Checkbox(
                    "Activate Lyra assistant",
                    value=self.defaults.feature_flags.get("lyra_assistant", True),
                    id="settings-lyra",
                ),
                Checkbox(
                    "Opt into telemetry",
                    value=bool(self.defaults.telemetry_opt_in),
                    id="settings-telemetry",
                ),
                Checkbox(
                    "Enable write guard",
                    value=self.defaults.write_guard if self.defaults.write_guard is not None else True,
                    id="settings-write-guard",
                ),
                Input(
                    value=self.defaults.model or "",
                    placeholder="Preferred model identifier",
                    id="settings-model",
                ),
                Input(
                    value=str(self.defaults.custom_theme_path or ""),
                    placeholder="Custom theme file (toml/yaml)",
                    id="settings-custom-theme",
                ),
                Horizontal(
                    Button("Cancel", id="settings-cancel"),
                    Button("Save", id="settings-save", variant="primary"),
                    id="settings-actions",
                ),
                id="settings-panel",
            )
        )

    @on(Button.Pressed, "#settings-cancel")
    def _cancel(self, _: Button.Pressed) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#settings-save")
    def _save(self, _: Button.Pressed) -> None:
        theme_value = self.query_one("#settings-theme", Select).value or "dark"
        high_contrast = bool(self.query_one("#settings-contrast", Checkbox).value)
        accessibility = bool(self.query_one("#settings-accessibility", Checkbox).value)
        verbose = bool(self.query_one("#settings-verbosity", Checkbox).value)
        lyra_enabled = bool(self.query_one("#settings-lyra", Checkbox).value)
        telemetry = bool(self.query_one("#settings-telemetry", Checkbox).value)
        write_guard = bool(self.query_one("#settings-write-guard", Checkbox).value)
        model = self.query_one("#settings-model", Input).value.strip() or self.defaults.model
        custom_theme_value = self.query_one("#settings-custom-theme", Input).value.strip()
        custom_theme = Path(custom_theme_value).expanduser() if custom_theme_value else None
        if theme_value == "high_contrast":
            theme = "dark"
            high_contrast = True
        else:
            theme = theme_value
        settings = TUISettings(
            model=model,
            theme=theme,
            high_contrast=high_contrast,
            accessibility_enabled=accessibility,
            accessibility_verbosity="verbose" if verbose else self.defaults.accessibility_verbosity,
            narration_enabled=self.defaults.narration_enabled,
            telemetry_opt_in=telemetry,
            write_guard=write_guard,
            feature_flags={
                **self.defaults.feature_flags,
                "lyra_assistant": lyra_enabled,
            },
            custom_theme_path=custom_theme,
        )
        self._set_result(settings)
        self.dismiss(settings)


def _dump_toml(payload: Dict[str, Any]) -> str:
    """Serialize a limited TOML subset suitable for the config file."""

    def render(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if value is None:
            return '""'
        if isinstance(value, dict):
            raise TypeError("Nested dicts must be handled by caller")
        return f'"{str(value).replace("\"", "\\\"")}"'

    lines: list[str] = []
    tables: Dict[str, Dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            tables[key] = value
        else:
            lines.append(f"{key} = {render(value)}")
    for table, values in tables.items():
        lines.append("")
        lines.append(f"[{table}]")
        for key, value in values.items():
            if isinstance(value, dict):
                lines.append(f"[{table}.{key}]")
                for nested_key, nested_value in value.items():
                    lines.append(f"{nested_key} = {render(nested_value)}")
            else:
                lines.append(f"{key} = {render(value)}")
    return "\n".join(lines) + "\n"


__all__ = [
    "InitialSetupWizard",
    "SettingsChanged",
    "SettingsScreen",
    "TUISettings",
    "TUISettingsManager",
]
