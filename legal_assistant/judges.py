import json
from typing import Optional

from . import config
from .generator import get_generator

JUDGE_SYSTEM_PROMPT = """You are an expert legal document evaluator grading answers about constitutional amendments and legal clauses.

Your job: Given a question, retrieved documents, and a system-generated answer, score it 1-10 on:
1. **Completeness** (0-3): Does the answer address all key legal elements?
2. **Accuracy** (0-3): Is the answer faithful to the source documents?
3. **Confidence Calibration** (0-4): Is confidence level appropriate? (high=full answer, medium=partial, low=uncertain/out-of-scope)

Return a JSON object with:
- score (1-10, where 10 = perfect answer)
- completeness (0-3)
- accuracy (0-3)
- calibration (0-4)
- reason (short explanation of scoring)
- major_gaps (list of missing legal elements, if any)
- hallucinations (list of facts not in sources, if any)
"""

JUDGE_USER_TEMPLATE = """
Question: {question}

Retrieved Documents:
{sources}

System Answer:
{answer}

Reasoning given: {reasoning}
Confidence: {confidence}
Out-of-scope: {out_of_scope}

Score this answer on completeness, accuracy, and confidence calibration.
Respond with only valid JSON.
"""


def evaluate_answer_completeness(
    question: str,
    answer_dict: dict,
    retrieved_sources: list,
    backend: Optional[str] = None,
) -> dict:
    if not backend:
        backend = "llm"

    sources_text = "\n".join([
        f"- Doc: {c.document}, Chunk: {c.chunk_id}\n  Text: {c.text[:300]}..."
        for c in retrieved_sources[:5]
    ])

    user_message = JUDGE_USER_TEMPLATE.format(
        question=question,
        sources=sources_text,
        answer=answer_dict.get("answer", ""),
        reasoning=answer_dict.get("reasoning", ""),
        confidence=answer_dict.get("confidence", "medium"),
        out_of_scope=answer_dict.get("out_of_scope", False),
    )

    try:
        gen = get_generator(backend)
        import os
        from openai import OpenAI

        client = OpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY,
        )

        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        response_text = response.choices[0].message.content.strip()
        score_dict = json.loads(response_text)
        return score_dict

    except Exception:
        return _rule_based_score(question, answer_dict, retrieved_sources)


def _rule_based_score(question: str, answer_dict: dict, retrieved_sources: list) -> dict:
    completeness = 0
    accuracy = 0
    calibration = 0

    answer_len = len(answer_dict.get("answer", ""))
    source_count = len(answer_dict.get("sources", []))

    if answer_len > 200:
        completeness = 3
    elif answer_len > 100:
        completeness = 2
    elif answer_len > 0:
        completeness = 1

    if source_count > 0:
        cited_chunk_ids = {s.get("chunk_id") for s in answer_dict.get("sources", [])}
        retrieved_ids = {c.chunk_id for c in retrieved_sources}
        if cited_chunk_ids.issubset(retrieved_ids):
            accuracy = 3
        else:
            accuracy = 1
    else:
        if answer_dict.get("out_of_scope"):
            accuracy = 3
        else:
            accuracy = 0

    confidence = answer_dict.get("confidence", "medium")
    out_of_scope = answer_dict.get("out_of_scope", False)

    if out_of_scope:
        if confidence == "low":
            calibration = 4
        else:
            calibration = 2
    elif confidence == "high" and completeness == 3 and accuracy == 3:
        calibration = 4
    elif confidence == "medium" and completeness >= 2:
        calibration = 3
    elif confidence == "low" and (completeness < 2 or accuracy < 2):
        calibration = 3
    else:
        calibration = 1

    return {
        "score": min(10, (completeness + accuracy + calibration) * 10 // 10),
        "completeness": completeness,
        "accuracy": accuracy,
        "calibration": calibration,
        "reason": (
            f"Based on answer length ({answer_len} chars), "
            f"source count ({source_count}), and confidence '{confidence}'"
        ),
        "major_gaps": [],
        "hallucinations": [],
    }


def score_answer_on_problem_type(answer_dict: dict, problem_category: str) -> dict:
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
        elif answer_dict.get("out_of_scope") and answer_dict.get("answer") == config.OUT_OF_SCOPE_ANSWER:
            score = 9
        else:
            score = 2

    elif problem_category == "incomplete_retrieval":
        source_count = len(answer_dict.get("sources", []))
        if source_count >= 3:
            score = 8
        elif source_count >= 1:
            score = 5
        else:
            score = 2

    elif problem_category == "retrieval_ranking":
        if answer_dict.get("confidence") == "high" and answer_dict.get("sources"):
            score = 7
        elif answer_dict.get("confidence") == "medium":
            score = 5
        else:
            score = 3

    elif problem_category == "poor_synthesis":
        source_count = len(answer_dict.get("sources", []))
        reasoning = answer_dict.get("reasoning", "")

        if source_count > 1 and "and" in reasoning and len(reasoning) > 200:
            score = 6
        elif source_count > 1 and len(reasoning) < 100:
            score = 3
        else:
            score = 5

    return {"score": score, "category": problem_category}
