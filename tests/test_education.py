import pytest

from vortex.ai import AdvancedCodeIntelligence, ContextManager
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.education import CodeExplainer, LearningMode


@pytest.fixture()
def model_manager() -> UnifiedModelManager:
    return UnifiedModelManager([
        {"name": "echo", "type": "echo"},
    ])


@pytest.fixture()
def memory(tmp_path):
    return UnifiedMemorySystem(f"sqlite:///{tmp_path/'edu.sqlite'}")


@pytest.mark.asyncio
async def test_learning_mode(memory, model_manager) -> None:
    context = ContextManager(model_manager, memory)
    mode = LearningMode(context)
    await mode.add_lesson("Explain recursion")
    outputs = await mode.run(lambda lesson: f"Answering {lesson}")
    assert outputs == ["Answering Explain recursion"]


@pytest.mark.asyncio
async def test_code_explainer(model_manager) -> None:
    intelligence = AdvancedCodeIntelligence(model_manager)
    explainer = CodeExplainer(intelligence)
    source = "def demo(x):\n    return x\n"
    report = await explainer.explain("demo", source)
    assert "functions" in report
