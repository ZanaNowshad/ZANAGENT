"""Entity and relation primitives for the organisational graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class EntityType(str, Enum):
    PROJECT = "project"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    POLICY = "policy"
    RELEASE = "release"
    SESSION = "session"
    PIPELINE = "pipeline"
    TEAM = "team"


class RelationType(str, Enum):
    OWNS = "owns"
    PRODUCES = "produces"
    RUNS = "runs"
    USES = "uses"
    DEPENDS_ON = "depends_on"
    RELATES_TO = "related_to"
    MEMBER_OF = "member_of"
    VIOLATES = "violates"


@dataclass
class GraphEntity:
    """Entity stored in the knowledge graph."""

    id: str
    type: EntityType
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "attributes": self.attributes,
        }


@dataclass
class GraphRelation:
    """Relationship between two :class:`GraphEntity` instances."""

    source: str
    target: str
    type: RelationType
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
            "attributes": self.attributes,
        }
