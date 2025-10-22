"""Data analysis capabilities."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Dict, Iterable, List

from vortex.core.model import UnifiedModelManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DataSummary:
    column: str
    count: int
    mean: float
    median: float


class UnifiedDataAnalyst:
    """Lightweight numeric dataset analyst."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self.model_manager = model_manager

    def summarise(self, data: Dict[str, Iterable[float]]) -> List[DataSummary]:
        summaries: List[DataSummary] = []
        for column, values in data.items():
            values_list = list(values)
            if not values_list:
                continue
            summaries.append(
                DataSummary(
                    column=column,
                    count=len(values_list),
                    mean=statistics.fmean(values_list),
                    median=statistics.median(values_list),
                )
            )
        return summaries

    async def explain(self, context: str, question: str) -> str:
        prompt = f"Context: {context}\nQuestion: {question}\nAnswer succinctly."
        result = await self.model_manager.generate(prompt)
        return result["text"]


__all__ = ["UnifiedDataAnalyst", "DataSummary"]
