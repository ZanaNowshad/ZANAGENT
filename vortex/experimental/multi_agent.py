"""Multi-agent experimentation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from vortex.core.model import UnifiedModelManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)

AgentCallback = Callable[[str], Awaitable[str]]


@dataclass
class Agent:
    name: str
    callback: AgentCallback


class MultiAgentCoordinator:
    """Coordinate concurrent agent interactions."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self._model_manager = model_manager
        self._agents: Dict[str, Agent] = {}

    def register(self, name: str, callback: AgentCallback) -> None:
        if name in self._agents:
            raise ValueError(f"Agent {name} already exists")
        self._agents[name] = Agent(name=name, callback=callback)

    async def broadcast(self, message: str) -> Dict[str, str]:
        async def _send(agent: Agent) -> str:
            prompt = f"Agent {agent.name}, respond to: {message}"
            await self._model_manager.generate(prompt)  # prime usage metrics
            return await agent.callback(message)

        tasks = [_send(agent) for agent in self._agents.values()]
        results = await asyncio.gather(*tasks)
        return {agent.name: result for agent, result in zip(self._agents.values(), results)}
