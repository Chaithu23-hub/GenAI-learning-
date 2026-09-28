"""The single judge both race arms are scored with.

The judge-validation work split grading into deterministic assertions plus one binary criterion:
"Is the answer a supported and useful response to the question based on the supplied documents?"
Judge v2 replays recorded verdicts, so it cannot score fresh answers, and no LLM key is
configured. This judge therefore runs the same three assertions and an offline check of the
binary criterion: answered, every cited excerpt verified against the store, and on topic.
"""
import re

from ..generation.generator import _verify_sources
from .deterministic_assertions import run_assertions

_STOPWORDS = frozenset(
    "what which does that this with from have there their about under between when where into "
    "your they them were been being after before only also than then amendment amendments agreement "
    "contract document documents section clause constitution".split()
)


def _content_words(text):
    return {word.rstrip("s") for word in re.findall(r"[a-z]{4,}", text.lower())} - {w.rstrip("s") for w in _STOPWORDS}


def judge_answer(question: str, answer: dict) -> dict:
    checks = run_assertions(answer, [])
    checks["answered"] = not answer.get("out_of_scope", False) and bool(answer.get("sources"))
    checks["sources_verified"] = checks["answered"] and not _verify_sources(answer)
    checks["on_topic"] = bool(_content_words(question) & _content_words(answer.get("answer", "")))
    return {"passed": all(checks.values()), "checks": checks}
