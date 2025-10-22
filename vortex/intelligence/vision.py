"""Computer vision helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from vortex.core.model import UnifiedModelManager


@dataclass
class ImageDescription:
    path: Path
    dominant_colour: str
    size: int


class UnifiedVisionPro:
    """Simple image analytics with optional model explanations."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self.model_manager = model_manager

    def analyse(self, path: Path) -> ImageDescription:
        data = path.read_bytes()
        size = len(data)
        dominant = self._dominant_colour(data)
        return ImageDescription(path=path, dominant_colour=dominant, size=size)

    async def describe(self, path: Path) -> str:
        description = self.analyse(path)
        prompt = (
            f"Analyse the image with dominant colour {description.dominant_colour} "
            f"and size {description.size} bytes. Provide a creative caption."
        )
        result = await self.model_manager.generate(prompt)
        return result["text"]

    def _dominant_colour(self, data: bytes) -> str:
        if not data:
            return "unknown"
        r = sum(data[0::3]) % 256
        g = sum(data[1::3]) % 256
        b = sum(data[2::3]) % 256
        return f"#{r:02x}{g:02x}{b:02x}"


__all__ = ["UnifiedVisionPro", "ImageDescription"]
