import pytest

from vortex.ai import AdvancedCodeIntelligence, ContextManager, ContinuousLearningSystem, NLPEngine
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager


@pytest.fixture()
def model_manager() -> UnifiedModelManager:
    return UnifiedModelManager(
        [
            {"name": "echo", "type": "echo", "cost_per_1k_tokens": 0.01},
        ]
    )


@pytest.fixture()
def memory(tmp_path) -> UnifiedMemorySystem:
    return UnifiedMemorySystem(f"sqlite:///{tmp_path/'memory.sqlite'}")


@pytest.mark.asyncio
async def test_context_manager_summary(model_manager, memory) -> None:
    ctx = ContextManager(model_manager, memory)
    await ctx.add_exchange("user", "Hello there")
    summary = await ctx.summarise()
    assert "Hello" in summary
    trimmed = await ctx.trim_until(0)
    assert trimmed


@pytest.mark.asyncio
async def test_continuous_learning(memory) -> None:
    learning = ContinuousLearningSystem(memory)
    await learning.record_feedback("ui", 4)
    await learning.record_feedback("ui", 2)
    avg = await learning.average_score("ui")
    assert avg == pytest.approx(3.0)
    trending = await learning.trending_categories()
    assert trending == ["ui"]


def test_nlp_engine_keyword() -> None:
    engine = NLPEngine()
    tokens = engine.keyword_summary("Hello hello world")
    assert tokens[0] == "hello"
    sentiment = engine.sentiment("I love this great library")
    assert sentiment > 0


@pytest.mark.asyncio
async def test_advanced_code_intelligence(model_manager) -> None:
    intelligence = AdvancedCodeIntelligence(model_manager)
    source = """
    def add(a, b):
        if a > b:
            return a - b
        return a + b
    """
    insights = intelligence.analyse_module(source)
    assert insights and insights[0].cyclomatic_complexity >= 2
    suggestion = await intelligence.refactor_suggestion("test", source)
    assert isinstance(suggestion, str)
    hotspots = intelligence.list_hotspots(insights, threshold=1)
    assert hotspots
