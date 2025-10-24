"""Predictive analytics experimentation."""
from __future__ import annotations

from typing import Iterable, List

from vortex.ai.nlp import NLPEngine
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class Predictor:
    """Perform simple trend predictions from textual data."""

    def __init__(self, nlp: NLPEngine) -> None:
        self._nlp = nlp

    def predict_sentiment_trend(self, documents: Iterable[str]) -> float:
        scores = [self._nlp.sentiment(doc) for doc in documents]
        trend = sum(scores) / max(len(scores), 1)
        logger.debug("sentiment trend", extra={"trend": trend})
        return trend

    def top_keywords(self, documents: Iterable[str], *, limit: int = 5) -> List[str]:
        keywords: List[str] = []
        for doc in documents:
            keywords.extend(self._nlp.keyword_summary(doc, top_k=limit))
        unique = list(dict.fromkeys(keywords))
        return unique[:limit]
