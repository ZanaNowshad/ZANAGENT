"""Natural language helper for knowledge graph queries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from vortex.ai import NLPEngine

from .knowledge_graph import OrgKnowledgeGraph, GraphQueryResult
from .relations import EntityType


@dataclass
class QueryInterpretation:
    """Structured representation produced from a natural-language prompt."""

    entity_type: Optional[EntityType]
    text: Optional[str]


class GraphQueryService:
    """Translate text prompts into graph lookups using heuristics and NLP."""

    def __init__(self, graph: OrgKnowledgeGraph, nlp: NLPEngine) -> None:
        self._graph = graph
        self._nlp = nlp

    def interpret(self, prompt: str) -> QueryInterpretation:
        prompt_lower = prompt.lower()
        keywords: List[str] = self._nlp.keyword_summary(prompt)
        for entity_type in EntityType:
            if re.search(rf"\b{entity_type.value}\b", prompt_lower):
                text = keywords[0] if keywords else prompt
                return QueryInterpretation(entity_type, text)
        # Fall back to keyword-only search
        text = keywords[0] if keywords else prompt
        return QueryInterpretation(None, text)

    def query(self, prompt: str) -> GraphQueryResult:
        interpretation = self.interpret(prompt)
        entities = self._graph.find_entities(interpretation.entity_type, interpretation.text)
        relations = []
        for entity in entities[:5]:  # limit fan-out for responsiveness
            result = self._graph.neighbours(entity.id)
            relations.extend(result.relations)
        return GraphQueryResult(entities, relations)

