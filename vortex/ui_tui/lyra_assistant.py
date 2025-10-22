"""Inline Lyra assistant surfaced inside the TUI."""

"""Inline Lyra assistant surfaced inside the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel

from vortex.utils.logging import get_logger
from vortex.utils.profiling import profile

logger = get_logger(__name__)


@dataclass
class LyraResponse:
    """Encapsulates Lyra's output for rendering and accessibility."""

    renderable: RenderableType
    plain_text: str
    message: str


class LyraAssistant:
    """Lightweight assistant leveraged within the TUI.

    The assistant keeps a compact history to power contextual suggestions while
    ensuring prompts remain cheap to run. Profiling decorators help spot
    regressions when operators rely on Lyra for quick syntax hints.
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._history: List[str] = []

    @profile("lyra.invoke")
    async def invoke(self, prompt: str) -> LyraResponse:
        """Invoke the backing model to obtain contextual help."""

        prompt = prompt.strip() or "Provide an actionable code-assistant tip."
        model_manager = getattr(self._runtime, "model_manager", None)
        try:
            if model_manager is None:
                raise RuntimeError("Model manager unavailable")
            payload = await model_manager.generate(
                "You are Lyra, an inline assistant guiding a developer using a terminal UI. "
                "Offer concise steps or syntax tips.",
                f"\nUser query: {prompt}\nRespond with bullet points.",
            )
            text = payload.get("text", "Unable to provide guidance right now.")
        except Exception as exc:  # pragma: no cover - runtime dependent
            logger.exception("lyra invocation failed", extra={"prompt": prompt})
            text = f"Lyra fallback: {exc}"
        self._history.append(text)
        renderable: RenderableType = Panel(
            Markdown(text),
            title="Lyra Assistant",
            border_style="magenta",
        )
        return LyraResponse(renderable=renderable, plain_text=text, message="Lyra response ready")

    def history(self) -> List[str]:
        """Return the most recent responses."""

        return self._history[-5:]


__all__ = ["LyraAssistant", "LyraResponse"]
