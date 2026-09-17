# evaluation — offline hit-rate metrics, LLM-as-judge, before/after validation
from .evaluation import compare_retrieval, hit_rate_at_k, EVALUATION_CASES
from .judges import evaluate_answer_completeness, score_answer_on_problem_type
from .judge_validation import build_report

__all__ = [
    "compare_retrieval", "hit_rate_at_k", "EVALUATION_CASES",
    "evaluate_answer_completeness", "score_answer_on_problem_type",
    "build_report",
]
