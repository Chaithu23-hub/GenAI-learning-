"""Legal reference parsing and citation validation; no retrieval or generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from legal_rag.domain.entities import RetrievedChunk

DOCUMENT_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d{4}-\d{3}(?:-\d{2})?\b", re.IGNORECASE)
_NUMBER = r"\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))*"
_QUERY_RE = re.compile(
    rf"\b(?:clauses?|sections?|articles?)\s+({_NUMBER}(?:(?:\s*,\s*|\s+and\s+|\s*&\s*){_NUMBER})*)",
    re.IGNORECASE,
)
# Only a definition at a line boundary counts. A cross-reference in prose does not.
_DEFINITION_RE = re.compile(
    rf"(?m)^[ \t]*(?:>\s*)?[\"'“‘*# ]*(?:(?P<label>Section|Clause|Article)\s+)?"
    rf"(?P<number>{_NUMBER})(?![\d.\w])(?:\.(?!\d))?[\"'”’* ]*(?=\s|[A-Z])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClauseRequest:
    numbers: tuple[str, ...]
    documents: tuple[str, ...]


def parse_clause_request(query: str) -> ClauseRequest | None:
    numbers = tuple(
        dict.fromkeys(
            number.lower()
            for match in _QUERY_RE.finditer(query)
            for number in re.findall(_NUMBER, match.group(1))
        )
    )
    if not numbers:
        return None
    return ClauseRequest(
        numbers,
        tuple(dict.fromkeys(match.group().upper() for match in DOCUMENT_ID_RE.finditer(query))),
    )


def clause_excerpt(chunk: RetrievedChunk, number: str) -> str | None:
    """Return an exact indexed substring defining this number, never a mention."""
    definitions = list(_DEFINITION_RE.finditer(chunk.text))
    for index, match in enumerate(definitions):
        if match.group("number").lower() == number.lower():
            remainder = chunk.text[match.end() :].lstrip()
            if re.match(
                r"(?:of|under)\b|in\s+(?:(?:the|this|that)\s+)?"
                r"(?:agreement|contract|section|clause|article|schedule)\b",
                remainder,
                re.IGNORECASE,
            ) or (
                match.group("label")
                and re.match(
                    r"(?:is|shall|was|has)\b",
                    remainder,
                    re.IGNORECASE,
                )
            ):
                continue
            end = (
                definitions[index + 1].start() if index + 1 < len(definitions) else len(chunk.text)
            )
            return chunk.text[match.start() : end].split("\n\n---", 1)[0].strip()
    heading = re.match(
        rf"^(?:Section|Clause|Article)\s+({_NUMBER})(?![\d.\w])", chunk.heading, re.IGNORECASE
    )
    if heading and heading.group(1).lower() == number.lower():
        return chunk.text.strip() or None
    return None
