"""LLM judge + deterministic assertions + label management."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from legal_rag.application.ports import EvaluationFiles, LLMClient, VectorStore
from legal_rag.domain.clauses import parse_clause_request
from legal_rag.infrastructure.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE

# ─── Deterministic assertions ─────────────────────────────────────────────

_CLAUSE_REFERENCE = re.compile(r"\b(?:section|clause|§)\s*([0-9]+(?:\.[0-9]+)?)\b", re.IGNORECASE)
_DATE_PATTERNS = (
    re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+(?:19|20)\d{2}\b",
        re.IGNORECASE,
    ),
)
_NOTICE_PERIOD = re.compile(
    r"\b\d+\s+(?:calendar\s+|business\s+)?(?:day|days|month|months|year|years)\b", re.IGNORECASE
)


def _source_text(answer: dict[str, Any], retrieved_sources: list[Any]) -> str:
    chunks = [getattr(s, "text", "") for s in retrieved_sources]
    chunks.extend(source.get("excerpt", "") for source in answer.get("sources", []))
    return "\n".join(chunks)


def clause_references_exist(answer: dict[str, Any], retrieved_sources: list[Any]) -> bool:
    text = _source_text(answer, retrieved_sources)
    answer_text = answer.get("answer", "")
    request = parse_clause_request(answer_text)
    if request and not request.valid:
        return False
    references = set(_CLAUSE_REFERENCE.findall(answer_text))
    if request:
        references.update(request.numbers)
    return all(re.search(rf"(?<![\w.]){re.escape(ref)}(?!\w|\.\d)", text) for ref in references)


def effective_dates_are_parseable(answer: dict[str, Any]) -> bool:
    """Every date-looking token in the answer must be a real, parseable date.

    Handles both ISO (YYYY-MM-DD — validated with strptime, so 2024-13-45 fails)
    and English long form (Jan 14, 2021).
    """
    text = answer.get("answer", "")
    for pattern in _DATE_PATTERNS:
        for value in pattern.findall(text):
            parsed = False
            for fmt in ("%Y-%m-%d", "%b %d, %Y"):
                try:
                    datetime.strptime(value.replace(".", ""), fmt)
                    parsed = True
                    break
                except ValueError:
                    continue
            if not parsed:
                return False
    return True


def notice_periods_are_numeric(answer: dict[str, Any]) -> bool:
    text = answer.get("answer", "")
    if not any(w in text.lower() for w in ("notice", "period", "days", "months", "years")):
        return True
    return bool(_NOTICE_PERIOD.search(text))


def run_assertions(answer: dict[str, Any], retrieved_sources: list[Any]) -> dict[str, bool]:
    return {
        "clause_references_exist": clause_references_exist(answer, retrieved_sources),
        "effective_dates_parseable": effective_dates_are_parseable(answer),
        "notice_periods_numeric": notice_periods_are_numeric(answer),
    }


DETERMINISTIC_ASSERTION_COUNT = 3
JUDGED_CRITERION_COUNT = 1


# ─── Race judge (offline) ─────────────────────────────────────────────────

_STOPWORDS = frozenset(
    [
        "what",
        "which",
        "does",
        "that",
        "this",
        "with",
        "from",
        "have",
        "there",
        "their",
        "about",
        "under",
        "between",
        "when",
        "where",
        "into",
        "your",
        "they",
        "them",
        "were",
        "been",
        "being",
        "after",
        "before",
        "only",
        "also",
        "than",
        "then",
        "amendment",
        "amendments",
        "agreement",
        "contract",
        "document",
        "documents",
        "section",
        "clause",
    ]
)


def _content_words(text: str) -> set[str]:
    words = {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", text.lower())}
    stops = {w.rstrip("s") for w in _STOPWORDS}
    return words - stops


# ─── Judge service ────────────────────────────────────────────────────────


@dataclass
class JudgeSettings:
    labels_path: Path


class JudgeService:
    """Grades answers using deterministic assertions plus an offline race judge; also runs
    Week 6 label-based agreement reporting."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        llm: LLMClient | None,
        settings: JudgeSettings,
        evaluation_files: EvaluationFiles | None = None,
    ):
        self._vector_store = vector_store
        self._llm = llm
        self._settings = settings
        self._evaluation_files = evaluation_files

    # ── Race judge (offline, deterministic) ───────────────────────────
    def judge_answer(self, question: str, answer: dict[str, Any]) -> dict[str, Any]:
        checks = run_assertions(answer, [])
        checks["answered"] = not answer.get("out_of_scope", False) and bool(answer.get("sources"))
        checks["sources_verified"] = checks["answered"] and self._verify_all_sources(answer)
        checks["on_topic"] = bool(
            _content_words(question) & _content_words(answer.get("answer", ""))
        )
        return {"passed": all(checks.values()), "checks": checks}

    def _verify_all_sources(self, answer: dict[str, Any]) -> bool:
        stored = self._vector_store.get_all()
        records = {
            chunk_id: (text, metadata or {})
            for chunk_id, text, metadata in zip(
                stored.get("ids", []),
                stored.get("documents", []),
                stored.get("metadatas", []),
                strict=False,
            )
        }
        for source in answer.get("sources", []):
            record = records.get(source.get("chunk_id"))
            if record is None:
                return False
            stored_text, metadata = record
            excerpt = source.get("excerpt", "").strip()
            if not excerpt or excerpt not in stored_text:
                return False
            stored_document = metadata.get("document")
            if not stored_document or source.get("document") != stored_document:
                return False
        return True

    # ── LLM completeness judge ────────────────────────────────────────
    def evaluate_answer_completeness(
        self,
        question: str,
        answer_dict: dict[str, Any],
        retrieved_sources: list[Any],
    ) -> dict[str, Any]:
        if self._llm is None:
            raise RuntimeError("LLM client not configured for judge")
        sources_text = "\n".join(
            [
                f"- Doc: {getattr(c, 'document', '?')}, Chunk: {getattr(c, 'chunk_id', '?')}"
                f"\n  Text: {getattr(c, 'text', '')[:300]}..."
                for c in retrieved_sources[:5]
            ]
        )
        user_message = JUDGE_USER_TEMPLATE.format(
            question=question,
            sources=sources_text,
            answer=answer_dict.get("answer", ""),
            reasoning=answer_dict.get("reasoning", ""),
            confidence=answer_dict.get("confidence", "medium"),
            out_of_scope=answer_dict.get("out_of_scope", False),
        )
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        return json.loads((response["content"] or "").strip())

    # ── Score by problem category (Week 5 target) ─────────────────────
    @staticmethod
    def score_answer_on_problem_type(
        answer_dict: dict[str, Any],
        problem_category: str,
        *,
        out_of_scope_sentinel: str = "",
    ) -> dict[str, Any]:
        score = 0
        if problem_category == "shallow_answer":
            answer = answer_dict.get("answer", "").lower()
            reasoning = answer_dict.get("reasoning", "").lower()
            if len(answer) < 150 and len(reasoning) < 200:
                score = 3
            elif len(answer) > 300 and "because" in reasoning and "however" in reasoning:
                score = 9
            else:
                score = 6
        elif problem_category == "hallucination":
            if answer_dict.get("sources") and not answer_dict.get("out_of_scope"):
                score = 8
            elif (
                answer_dict.get("out_of_scope")
                and answer_dict.get("answer") == out_of_scope_sentinel
            ):
                score = 9
            else:
                score = 2
        elif problem_category == "incomplete_retrieval":
            n = len(answer_dict.get("sources", []))
            score = 8 if n >= 3 else (5 if n >= 1 else 2)
        elif problem_category == "retrieval_ranking":
            if answer_dict.get("confidence") == "high" and answer_dict.get("sources"):
                score = 7
            elif answer_dict.get("confidence") == "medium":
                score = 5
            else:
                score = 3
        elif problem_category == "poor_synthesis":
            n = len(answer_dict.get("sources", []))
            reasoning = answer_dict.get("reasoning", "")
            if n > 1 and "and" in reasoning and len(reasoning) > 200:
                score = 6
            elif n > 1 and len(reasoning) < 100:
                score = 3
            else:
                score = 5
        return {"score": score, "category": problem_category}

    # ── Week 6 judge-validation report ────────────────────────────────
    def load_labels(self) -> list[dict[str, Any]]:
        if self._evaluation_files is None:
            raise RuntimeError("evaluation files port is required to load judge labels")
        payload = json.loads(self._evaluation_files.read_labels())
        labels = payload["labels"]
        if len(labels) < 25:
            raise ValueError("judge validation requires at least 25 hand-labeled cases")
        return labels

    @staticmethod
    def _human_label_distribution(labels: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        for label in labels:
            value = label.get("human_label")
            label_value = str(value).lower() if isinstance(value, bool) else "unknown"
            grouped[str(label.get("mode", "unknown"))][label_value] += 1
        return {mode: dict(sorted(counts.items())) for mode, counts in sorted(grouped.items())}

    def build_report(self) -> dict[str, Any]:
        labels = self.load_labels()
        return {
            "cases": len(labels),
            "status": "not_evaluated",
            "human_label_distribution_by_mode": self._human_label_distribution(labels),
            "agreement_before": None,
            "agreement_after": None,
        }
