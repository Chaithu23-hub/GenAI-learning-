"""Legal reference parsing and citation validation; no retrieval or generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from legal_rag.domain.entities import RetrievedChunk

DOCUMENT_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d{4}-\d{3}(?:-\d{2})?\b", re.IGNORECASE)
_NUMBER = r"\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))*"
_RANGE = re.compile(
    rf"(?P<start>{_NUMBER})\s*(?P<separator>-|\u2013|\u2014|\bto\b)\s*(?P<end>{_NUMBER})",
    re.IGNORECASE,
)
_INVALID_RANGE_REFERENCE = "__invalid_clause_range__"
_CHAINED_RANGE = re.compile(
    rf"{_NUMBER}\s*(?:-|\u2013|\u2014|\bto\b)\s*{_NUMBER}"
    rf"\s*(?:-|\u2013|\u2014|\bto\b)\s*{_NUMBER}",
    re.IGNORECASE,
)
_QUERY_RE = re.compile(
    rf"\b(?:clauses?|sections?|articles?)\s+({_NUMBER}(?:(?:\s*(?:-|\u2013|\u2014|\bto\b)\s*|\s*,\s*|\s+and\s+|\s*&\s*){_NUMBER})*)",
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
    valid: bool = True


def parse_clause_request(query: str) -> ClauseRequest | None:
    matches = list(_QUERY_RE.finditer(query))
    if not matches:
        return None
    numbers: list[str] = []
    valid = True
    for match in matches:
        expression = match.group(1)
        if _CHAINED_RANGE.search(expression):
            valid = False
        cursor = 0
        for range_match in _RANGE.finditer(expression):
            # Add standalone references before this range.
            numbers.extend(
                value.lower()
                for value in re.findall(_NUMBER, expression[cursor : range_match.start()])
            )
            start, end = range_match.group("start"), range_match.group("end")
            start_parts, end_parts = start.split("."), end.split(".")
            if (
                "(" in start
                or "(" in end
                or len(start_parts) != len(end_parts)
                or start_parts[:-1] != end_parts[:-1]
                or int(end_parts[-1]) < int(start_parts[-1])
                or int(end_parts[-1]) - int(start_parts[-1]) > 99
            ):
                valid = False
            else:
                numbers.extend(
                    ".".join([*start_parts[:-1], str(value)])
                    for value in range(int(start_parts[-1]), int(end_parts[-1]) + 1)
                )
            cursor = range_match.end()
        numbers.extend(value.lower() for value in re.findall(_NUMBER, expression[cursor:]))
    numbers = list(dict.fromkeys(numbers))
    if len(numbers) > 100:
        valid = False
    if not valid:
        # Existing answer validators require every parsed reference to resolve
        # against evidence. This sentinel makes unsupported input fail closed.
        numbers.append(_INVALID_RANGE_REFERENCE)
    return ClauseRequest(
        tuple(numbers),
        tuple(dict.fromkeys(match.group().upper() for match in DOCUMENT_ID_RE.finditer(query))),
        valid,
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
