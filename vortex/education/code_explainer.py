"""Explain source code for educational purposes."""

from __future__ import annotations

from typing import Dict, List

from vortex.ai.code_intelligence import AdvancedCodeIntelligence
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class CodeExplainer:
    """Generate annotated explanations for code snippets."""

    def __init__(self, intelligence: AdvancedCodeIntelligence) -> None:
        self._intelligence = intelligence

    async def explain(self, description: str, source: str) -> Dict[str, List[str]]:
        insights = self._intelligence.analyse_module(source)
        narrative = await self._intelligence.refactor_suggestion(description, source)
        return {
            "functions": [f"{item.name} ({item.cyclomatic_complexity})" for item in insights],
            "narrative": [line.strip() for line in narrative.splitlines() if line.strip()],
        }
