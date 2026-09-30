import pytest

from legal_rag.infrastructure.prompts import (
    ACTIVE_PROMPTS,
    JUDGE_SYSTEM_PROMPT_V1,
    ORCHESTRATOR_PROMPT_V1,
    PromptTemplate,
    QA_SYSTEM_PROMPT,
    get,
    snapshot,
)


class TestPromptTemplate:
    def test_render_substitutes_variables(self):
        p = PromptTemplate(name="t", version="v1", text="Hello, {name}!")
        assert p.render(name="World") == "Hello, World!"

    def test_missing_variable_raises_named_error(self):
        p = PromptTemplate(name="t", version="v1", text="Hello, {name}!")
        with pytest.raises(KeyError, match="t@v1"):
            p.render()

    def test_id_property(self):
        assert PromptTemplate("qa.system", "v1", "x").id == "qa.system@v1"


class TestRegistry:
    def test_all_expected_prompts_present(self):
        expected = {
            "qa.system",
            "orchestrator.planner",
            "orchestrator.defined_terms",
            "orchestrator.synthesizer",
            "judge.system",
            "judge.user",
        }
        assert set(ACTIVE_PROMPTS) == expected

    def test_snapshot_returns_pinned_versions(self):
        snap = snapshot()
        assert snap["qa.system"] == "v1"
        assert snap["judge.system"] == "v1"

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get("nonexistent.prompt")

    def test_qa_prompt_equals_string_constant(self):
        from legal_rag.infrastructure.prompts import SYSTEM_PROMPT
        assert QA_SYSTEM_PROMPT.text == SYSTEM_PROMPT
