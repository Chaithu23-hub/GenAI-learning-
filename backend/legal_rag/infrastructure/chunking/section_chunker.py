"""Section-aware markdown chunker.

Splits on markdown headings first, then windows each section into overlapping
token spans (whitespace-tokenised for CPU-friendly, dependency-free
operation).
"""
from __future__ import annotations

import re

from legal_rag.domain.entities import Chunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown document into ``[(heading, body), ...]``."""
    sections: list[tuple[str, str]] = []
    heading, lines = "Preamble", []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            body = "\n".join(lines).strip()
            if body:
                sections.append((heading, body))
            heading, lines = match.group(2).strip(), []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))
    return sections


def chunk_document(text: str, chunk_size: int = 512, overlap: int = 50) -> list[Chunk]:
    """Chunk a document into overlapping windows of ~``chunk_size`` tokens."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[Chunk] = []
    for heading, body in split_into_sections(text):
        words = body.split()
        if len(words) <= chunk_size:
            chunks.append(Chunk(text=body, heading=heading, index=len(chunks)))
            continue
        step = chunk_size - overlap
        for start in range(0, len(words), step):
            window = words[start:start + chunk_size]
            chunks.append(Chunk(text=" ".join(window), heading=heading, index=len(chunks)))
            if start + chunk_size >= len(words):
                break
    return chunks
