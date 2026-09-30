"""Judge system + user templates (v1)."""
from legal_rag.infrastructure.prompts.prompt import PromptTemplate

_SYS_TEXT = """You are an expert legal document evaluator grading answers about constitutional amendments and legal clauses.

Your only judged criterion is binary: is the answer a supported and useful response to the question based on the supplied documents?
Do not judge clause-reference existence, date parsing, defined-term presence, or numeric notice periods; those are deterministic assertions run before this prompt.
Use the provided question, sources, answer, and confidence to decide whether the answer is substantively supported and useful.

Return a JSON object with:
- score (1-10, where 10 = perfect answer)
- completeness (0-3)
- accuracy (0-3)
- calibration (0-4)
- reason (short explanation of scoring)
- major_gaps (list of missing legal elements, if any)
- hallucinations (list of facts not in sources, if any)
"""

_USER_TEXT = """
Question: {question}

Retrieved Documents:
{sources}

System Answer:
{answer}

Reasoning given: {reasoning}
Confidence: {confidence}
Out-of-scope: {out_of_scope}

Decide whether this answer is substantively supported and useful. Mechanical source and format checks are handled outside the judge.
Respond with only valid JSON.
"""

JUDGE_SYSTEM_PROMPT = _SYS_TEXT
JUDGE_USER_TEMPLATE = _USER_TEXT

JUDGE_SYSTEM_PROMPT_V1 = PromptTemplate(name="judge.system", version="v1", text=_SYS_TEXT)
JUDGE_USER_TEMPLATE_V1 = PromptTemplate(name="judge.user", version="v1", text=_USER_TEXT)
