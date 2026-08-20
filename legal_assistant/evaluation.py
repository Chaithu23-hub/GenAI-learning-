from dataclasses import dataclass

from . import config
from .retrieval import retrieve


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    relevant_chunk_ids: frozenset[str]


# Labels are deliberately tied to the headings in the bundled corpus.
EVALUATION_CASES = (
    EvaluationCase("What freedoms are protected by the First Amendment?",
                   frozenset({"test_america_amedments::001"})),
    EvaluationCase("What does the Fourth Amendment protect?",
                   frozenset({"test_america_amedments::002"})),
    EvaluationCase("What rights does the Sixth Amendment grant criminal defendants?",
                   frozenset({"test_america_amedments::002"})),
    EvaluationCase("What is sovereign immunity under the amendments?",
                   frozenset({"test_america_amedments::003"})),
    EvaluationCase("What does the 12th Amendment change about presidential elections?",
                   frozenset({"test_america_amedments::004"})),
)


def hit_rate_at_k(cases=EVALUATION_CASES, k=3, hybrid=config.HYBRID_ENABLED, client=None):
    hits = 0
    for case in cases:
        results = retrieve(case.question, n=k, hybrid=hybrid, client=client)
        if any(result.chunk_id in case.relevant_chunk_ids for result in results):
            hits += 1
    return hits / len(cases) if cases else 0.0


def compare_retrieval(cases=EVALUATION_CASES, k=3, client=None):
    return {
        "k": k,
        "questions": len(cases),
        "before_dense": hit_rate_at_k(cases, k=k, hybrid=False, client=client),
        "after_hybrid": hit_rate_at_k(cases, k=k, hybrid=True, client=client),
    }