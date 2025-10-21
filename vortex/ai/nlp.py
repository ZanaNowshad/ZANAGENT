"""Natural language processing helpers."""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class NLPEngine:
    """Perform lightweight NLP tasks without external dependencies."""

    SENTENCE_SPLIT = re.compile(r"(?<=[.!?]) +")
    WORD_SPLIT = re.compile(r"[^a-zA-Z0-9']+")

    def tokenize(self, text: str) -> List[str]:
        tokens = [token for token in self.WORD_SPLIT.split(text.lower()) if token]
        logger.debug("tokenized", extra={"tokens": len(tokens)})
        return tokens

    def sentences(self, text: str) -> List[str]:
        return [segment.strip() for segment in self.SENTENCE_SPLIT.split(text.strip()) if segment]

    def keyword_summary(self, text: str, *, top_k: int = 5) -> List[str]:
        tokens = self.tokenize(text)
        counts = Counter(tokens)
        return [word for word, _ in counts.most_common(top_k)]

    def sentiment(self, text: str) -> float:
        """Naive sentiment by counting positive/negative tokens."""

        positive = {"good", "great", "excellent", "happy", "love"}
        negative = {"bad", "terrible", "sad", "hate", "poor"}
        tokens = self.tokenize(text)
        score = sum(1 for token in tokens if token in positive) - sum(1 for token in tokens if token in negative)
        normalised = score / max(len(tokens), 1)
        logger.debug("sentiment score", extra={"score": normalised})
        return normalised

    def detect_entities(self, text: str) -> Dict[str, List[str]]:
        """Perform rule-based entity extraction from capitalisation."""

        entities: Dict[str, List[str]] = {"person": [], "org": []}
        for sentence in self.sentences(text):
            words = sentence.split()
            for word in words:
                if word.istitle() and len(word) > 2:
                    if word.endswith("Inc") or word.endswith("Corp"):
                        entities["org"].append(word)
                    else:
                        entities["person"].append(word)
        return entities
