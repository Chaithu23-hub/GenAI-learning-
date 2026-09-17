import re
from datetime import datetime


CLAUSE_REFERENCE = re.compile(r"\b(?:section|clause|§)\s*([0-9]+(?:\.[0-9]+)?)\b", re.IGNORECASE)
DATE_PATTERNS = (
    re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+(?:19|20)\d{2}\b", re.IGNORECASE),
)
NOTICE_PERIOD = re.compile(r"\b\d+\s+(?:calendar\s+|business\s+)?(?:day|days|month|months|year|years)\b", re.IGNORECASE)


def _source_text(answer: dict, retrieved_sources: list) -> str:
    chunks = [source.text for source in retrieved_sources]
    chunks.extend(source.get("excerpt", "") for source in answer.get("sources", []))
    return "\n".join(chunks)


def clause_references_exist(answer: dict, retrieved_sources: list) -> bool:
    """Assert that every clause reference in the answer exists in the retrieved source text."""
    source_text = _source_text(answer, retrieved_sources)
    return all(reference in source_text for reference in CLAUSE_REFERENCE.findall(answer.get("answer", "")))


def effective_dates_are_parseable(answer: dict) -> bool:
    """Assert that every date in the answer is a parseable date string."""
    text = answer.get("answer", "")
    for pattern in DATE_PATTERNS:
        for value in pattern.findall(text):
            try:
                datetime.strptime(value.replace(".", ""), "%b %d, %Y")
            except ValueError:
                if not re.fullmatch(r"(?:19|20)\d{2}-\d{2}-\d{2}", value):
                    return False
    return True


def notice_periods_are_numeric(answer: dict) -> bool:
    """Assert that any notice period mentioned in the answer is given as a numeric quantity."""
    text = answer.get("answer", "")
    return not any(word in text.lower() for word in ("notice", "period", "days", "months", "years")) or bool(NOTICE_PERIOD.search(text))


def run_assertions(answer: dict, retrieved_sources: list) -> dict[str, bool]:
    """Run all three deterministic assertions and return their results."""
    return {
        "clause_references_exist": clause_references_exist(answer, retrieved_sources),
        "effective_dates_parseable": effective_dates_are_parseable(answer),
        "notice_periods_numeric": notice_periods_are_numeric(answer),
    }
