"""Advanced code intelligence helpers."""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from typing import Iterable, List

from vortex.core.model import UnifiedModelManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FunctionInsight:
    """Metadata about a function extracted via static analysis."""

    name: str
    arguments: List[str]
    cyclomatic_complexity: int


class AdvancedCodeIntelligence:
    """Perform static analysis to complement LLM based reasoning."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self._model_manager = model_manager

    def analyse_module(self, source: str) -> List[FunctionInsight]:
        """Parse Python source code and calculate complexity metrics."""

        tree = ast.parse(textwrap.dedent(source))
        insights: List[FunctionInsight] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.BoolOp)):
                        complexity += 1
                insight = FunctionInsight(
                    name=node.name,
                    arguments=[arg.arg for arg in node.args.args],
                    cyclomatic_complexity=complexity,
                )
                insights.append(insight)
        return insights

    async def refactor_suggestion(self, description: str, source: str) -> str:
        """Request a refactoring suggestion from the underlying models."""

        prompt = (
            "You are a senior engineer producing refactoring advice.\n"
            f"Context: {description}\n\n"
            "Source code:\n"
            f"{source}\n\nRespond with actionable improvement steps."
        )
        logger.debug("requesting refactor suggestion")
        result = await self._model_manager.generate(prompt)
        return result.get("text", "")

    def list_hotspots(self, insights: Iterable[FunctionInsight], *, threshold: int = 8) -> List[FunctionInsight]:
        """Identify functions exceeding the complexity threshold."""

        return [insight for insight in insights if insight.cyclomatic_complexity >= threshold]
