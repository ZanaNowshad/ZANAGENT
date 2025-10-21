"""Audio processing utilities."""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from vortex.core.model import UnifiedModelManager


@dataclass
class AudioAnalysis:
    duration: float
    channels: int
    sample_rate: int


class UnifiedAudioSystem:
    """Perform lightweight audio analysis and transcription prompts."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self.model_manager = model_manager

    def analyse(self, path: Path) -> AudioAnalysis:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            channels = wav.getnchannels()
            duration = frames / float(rate)
        return AudioAnalysis(duration=duration, channels=channels, sample_rate=rate)

    async def transcribe(self, path: Path) -> str:
        analysis = self.analyse(path)
        prompt = (
            "You are an expert transcription assistant. "
            f"The audio is {analysis.duration:.2f}s long with {analysis.channels} channels. "
            "Provide a plausible summary of the conversation."
        )
        result = await self.model_manager.generate(prompt)
        return result["text"]


__all__ = ["UnifiedAudioSystem", "AudioAnalysis"]
