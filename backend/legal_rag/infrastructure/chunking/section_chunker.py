"""Section- and clause-aware chunker for legal documents.

Supports markdown, docx, and pdf documents. Splits by headings (markdown or text)
and numbered subclauses (e.g. 3.4 Late Payment) so that individual legal clauses
are not buried in long mixed chunks, giving high semantic precision for retrieval.
"""
from __future__ import annotations

import re

from legal_rag.domain.entities import Chunk

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+(.+?)|((?:Schedule\s+[A-Z0-9-]+|Part\s+\d+|Section\s+\d+|Calendar\s+Year\s+\d+|AMENDMENT\s+NO\.|MASTER\s+SERVICES\s+AGREEMENT|MUTUAL\s+NON-DISCLOSURE|SCHEDULES\s+TO)\b[^\n]*))\s*$",
    re.IGNORECASE,
)


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split a document into ``[(heading, body), ...]`` with hierarchy tracking."""
    sections: list[tuple[str, str]] = []
    heading = "Preamble"
    parent_title = ""
    parent_intro = ""
    lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        match = HEADING_RE.match(stripped)
        if match:
            body = "\n".join(lines).strip()
            if body:
                sections.append((heading, body))
            raw_title = (match.group(1) or match.group(2)).strip()
            lines = []
            md_level = len(stripped) - len(stripped.lstrip("#"))
            if md_level == 1:
                parent_title = raw_title
                parent_intro = ""
                heading = raw_title
            elif md_level >= 2 and parent_title and not re.match(r"^(?:Section|Clause|Schedule)\b", raw_title, re.IGNORECASE):
                heading = f"{parent_title}: {raw_title}"
                if parent_intro:
                    lines.append(parent_intro)
            else:
                heading = raw_title
        else:
            lines.append(line)
            if (
                not parent_intro
                and parent_title
                and heading == parent_title
                and stripped
                and not stripped.startswith("|")
                and not stripped.startswith("---")
            ):
                parent_intro = stripped

    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))
    return sections


def chunk_document(text: str, chunk_size: int = 512, overlap: int = 50) -> list[Chunk]:
    """Chunk a document into overlapping windows of ~``chunk_size`` tokens, respecting clause boundaries."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[Chunk] = []

    for heading, body in split_into_sections(text):
        matches = list(re.finditer(r"(?m)^(?:\*\*)?(\d+\.\d+(?:\.\d+)?)\s*(?:\*\*)?\s*", body))
        if len(matches) >= 2:
            prefix = body[:matches[0].start()].strip()
            if prefix:
                _emit_tokens(chunks, prefix, heading, chunk_size, overlap)
            for i, match in enumerate(matches):
                clause_num = match.group(1)
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
                c_text = body[start:end].strip()
                title_m = re.match(
                    r"^(?:\*\*)?" + re.escape(clause_num) + r"\s*(?:\*\*)?\s*([^.\n]+?)(?:\.|\*\*|\n)",
                    c_text,
                )
                title = title_m.group(1).strip() if title_m and len(title_m.group(1).strip()) < 50 else ""
                c_heading = f"Section {clause_num} {title}".strip() if title else f"Section {clause_num}"
                _emit_tokens(chunks, c_text, c_heading, chunk_size, overlap)
        else:
            _emit_tokens(chunks, body, heading, chunk_size, overlap)

    return chunks


def _emit_tokens(
    chunks: list[Chunk], text: str, heading: str, chunk_size: int, overlap: int
) -> None:
    words = text.split()
    if not words:
        return
    if len(words) <= chunk_size:
        chunks.append(Chunk(text=text, heading=heading, index=len(chunks)))
        return
    step = chunk_size - overlap
    for start in range(0, len(words), step):
        window = words[start : start + chunk_size]
        chunks.append(Chunk(text=" ".join(window), heading=heading, index=len(chunks)))
        if start + chunk_size >= len(words):
            break


class SectionChunker:
    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[Chunk]:
        return chunk_document(text, chunk_size=chunk_size, overlap=overlap)

