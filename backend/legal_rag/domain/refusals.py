"""Conservative refusal wording checks, not a general factual verifier."""

import re

_CONTEXT = re.compile(r"\b(?:documents?|evidence|passages?)\b", re.IGNORECASE)
_SCOPE_LIMIT = re.compile(r"\b(?:only|limited|cannot|can['’]t|unable|outside)\b", re.IGNORECASE)
_EVIDENCE_LIMIT = re.compile(
    r"\b(?:not enough|insufficient|need|cannot|can['’]t|unable|"
    r"don['’]t have enough|do not have enough|lack)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_DETAILS = re.compile(
    r'[\d"“”`\[\]<>]|https?://|www\.|'
    r"\b(?:contract|clause|agreement|law)\s+(?:permits|requires|allows|says|states|provides)\b",
    re.IGNORECASE,
)


def is_refusal_wording(answer: str, reason: str) -> bool:
    """Require an explicit limitation and reject obvious invented detail/markup.

    These bounded checks supplement the reason-only prompt. They cannot prove
    arbitrary natural-language text is fact-free or replace evidence validation.
    """
    limitation = {
        "outside_document_qa": _SCOPE_LIMIT,
        "insufficient_evidence": _EVIDENCE_LIMIT,
    }.get(reason)
    return bool(
        limitation
        and limitation.search(answer)
        and _CONTEXT.search(answer)
        and not _UNSUPPORTED_DETAILS.search(answer)
    )
