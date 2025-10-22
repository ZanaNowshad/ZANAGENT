"""Code analysis helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List

from vortex.core.model import UnifiedModelManager


@dataclass
class FunctionSignature:
    name: str
    args: List[str]


class UnifiedCodeIntelligence:
    """Static analysis utilities augmented by LLM hints."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self.model_manager = model_manager

    def inspect_file(self, path: Path) -> List[FunctionSignature]:
        tree = ast.parse(path.read_text())
        signatures: List[FunctionSignature] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = [arg.arg for arg in node.args.args]
                signatures.append(FunctionSignature(name=node.name, args=args))
        return signatures

    async def suggest_tests(self, path: Path) -> str:
        signatures = self.inspect_file(path)
        signature_text = ", ".join(f"{s.name}({', '.join(s.args)})" for s in signatures)
        prompt = (
            "Given the following functions: "
            f"{signature_text}. Suggest targeted unit tests focusing on edge cases."
        )
        result = await self.model_manager.generate(prompt)
        return result["text"]


__all__ = ["UnifiedCodeIntelligence", "FunctionSignature"]
