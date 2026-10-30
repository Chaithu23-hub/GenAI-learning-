"""Conservative spelling normalization for document search vocabulary."""
import re
from difflib import SequenceMatcher, get_close_matches


_TERMS = (
    "available", "amendment", "amendments", "agreement", "agreements",
    "contract", "contracts", "termination", "confidentiality", "liability",
    "payment", "payments", "renewal", "obligation", "obligations",
    "effective", "expiration", "expiry", "notice", "clause", "clauses",
)


def normalize_document_query(query: str) -> str:
    """Correct only unambiguous close matches; preserve names, IDs and dates.

    Short words and tokens within identifiers are deliberately left alone.
    """
    def correct(match: re.Match[str]) -> str:
        word = match.group()
        if len(word) < 6 or word.lower() in _TERMS or word.isupper():
            return word
        matches = get_close_matches(word.lower(), _TERMS, n=2, cutoff=0.84)
        if not matches:
            return word
        if len(matches) > 1:
            scores = [SequenceMatcher(None, word.lower(), term).ratio() for term in matches]
            if scores[0] - scores[1] < 0.03:
                return word
        return matches[0].capitalize() if word.istitle() else matches[0]

    return re.sub(r"(?<![\w-])[A-Za-z]+(?![\w-])", correct, query)
