"""Refusal wording receives a reason only, never legal evidence or user text."""

from legal_rag.infrastructure.prompts.prompt import PromptTemplate

UNSUPPORTED_RESPONSE_PROMPT_V1 = PromptTemplate(
    name="unsupported.reply",
    version="v1",
    text="""Generate a brief, natural refusal for a legal document question-answering assistant.
The user message is a controlled reason, not a question to answer.
Return only JSON with exactly two fields: "reason" (echo the reason) and "answer" (string).
For outside_document_qa, explain that this assistant helps with questions supported
by legal documents only, and invite a relevant document question. Explicitly state
the limitation using the word "only", "limited", "cannot", "can't" or "unable".
For insufficient_evidence, explain that there is not enough supporting document
evidence to answer reliably. Suggest sharing the relevant passage or refining the question.
Explicitly say you need evidence or have insufficient evidence; use "need",
"not enough", "insufficient", "cannot", "can't", "unable" or "don't have enough".
Use fresh, varied phrasing rather than repeating a stock sentence. Be warm and concise:
one or two sentences, at most 600 characters. Do not change the refusal's meaning.
Do not answer any substantive question. Do not invent facts, legal advice, contract
terms, document names, clause numbers, quotations, links or citations.
Use no digits, quotation marks, brackets, angle brackets or backticks.
Do not claim that a document was searched, read, missing or nonexistent. Do not claim prior
conversation memory, promise absolute uniqueness, or mention internal routing.""",
)

GROUNDING_REFUSAL_POLICY_V1 = PromptTemplate(
    name="qa.out_of_scope",
    version="v1",
    text="""INTERNAL OUT-OF-SCOPE CONTRACT
The exact fixed out-of-scope answer is this JSON string: {answer_json}
When supporting evidence is insufficient, set out_of_scope to true, use that exact
decoded string as answer, sources to an empty array and confidence to low. Include
a nonempty reasoning sentence explaining the evidence limitation. Do not replace
the fixed answer with an empty string, paraphrase or unsupported factual answer.""",
)
