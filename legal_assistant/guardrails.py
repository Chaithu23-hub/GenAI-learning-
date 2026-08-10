"""Input guardrails: block prompt-injection attempts and drafting requests.

Screening happens *before* the query reaches retrieval or generation, so the
model is never asked to comply with a hostile instruction.
"""

import re

# [TOPIC: Prompt injection] — the injection detector checks for override
# phrases like "ignore instructions", "you are now", "disregard the above" in
# user input and blocks the request before any retrieval or model call is
# made. An optional filler word (e.g. "forget your *earlier* instructions")
# is tolerated between the determiner and the protected noun.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier|preceding|your|the)\s+(?:\w+\s+)?(instructions|rules|prompts)",
    r"disregard\s+(all\s+)?(previous|prior|your|the|earlier)\s+(?:\w+\s+)?(instructions|rules|prompts)",
    r"forget\s+(all\s+)?(previous|prior|your|the|earlier)\s+(?:\w+\s+)?(instructions|rules|training|prompts)",
    r"override\s+(your|the|all)\s+(instructions|rules|guardrails|safety)",
    r"pretend\s+(you\s+are|you're|to\s+be)",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if|a|an)\b",
    r"new\s+instructions?\s*:",
    r"\breveal\b.*\bsystem\s+prompt\b",
    r"\bDAN\s+mode\b",
    r"\bjailbreak",
]

# [TOPIC: Guardrails] — the assistant retrieves and explains; it never drafts
# or rewrites contract language, so such requests are rejected up front.
DRAFTING_PATTERNS = [
    r"\b(draft|write|compose|create)\b.*\b(contract|clause|amendment|agreement|nda)\b",
    r"\b(draft|write|compose|create)\b\s+(me\s+)?(a|an|the)\b.*\b(terms?|language|provision)\b",
    r"\b(rewrite|modify|revise|redline)\b.*\b(clause|contract|section|agreement|terms?)\b",
    r"\badd\s+a\s+(new\s+)?(clause|section|provision)\b",
]

_INJECTION_RES = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
_DRAFTING_RES = [re.compile(p, re.IGNORECASE) for p in DRAFTING_PATTERNS]


def screen_query(query):
    """Screen a user question before it enters the pipeline.

    Returns (allowed, reason): allowed=False means respond with the canned
    rejection message for `reason` ("injection" or "drafting").
    """
    # [TOPIC: Guardrails] — user input is screened before it hits the retrieval
    # pipeline; flagged inputs are rejected with a fixed safe response and never
    # passed to the model.
    for pattern in _INJECTION_RES:
        if pattern.search(query):
            return False, "injection"
    for pattern in _DRAFTING_RES:
        if pattern.search(query):
            return False, "drafting"
    return True, None
