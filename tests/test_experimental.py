import pytest

from vortex.ai import NLPEngine
from vortex.core.model import UnifiedModelManager
from vortex.experimental import MultiAgentCoordinator, Predictor, SelfImprovementLoop


@pytest.fixture()
def model_manager() -> UnifiedModelManager:
    return UnifiedModelManager([
        {"name": "echo", "type": "echo"},
    ])


@pytest.mark.asyncio
async def test_multiagent_broadcast(model_manager) -> None:
    coordinator = MultiAgentCoordinator(model_manager)

    async def agent(message: str) -> str:
        return message.upper()

    coordinator.register("alpha", agent)
    result = await coordinator.broadcast("ping")
    assert result["alpha"] == "PING"

@pytest.mark.asyncio
async def test_self_improvement_and_predictor() -> None:
    loop = SelfImprovementLoop(lambda idea: len(idea))
    score = await loop.iterate("idea", attempts=2)
    assert score == len("idea")
    assert loop.history
    predictor = Predictor(NLPEngine())
    trend = predictor.predict_sentiment_trend(["I love this", "bad experience"])
    keywords = predictor.top_keywords(["alpha beta", "beta gamma"], limit=2)
    assert isinstance(trend, float)
    assert keywords
