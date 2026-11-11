"""Conservative checks binding explicit document references to their evidence."""

from __future__ import annotations

import re

from legal_rag.domain.clauses import DOCUMENT_ID_RE, clause_excerpt, parse_clause_request
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.pages import page_references_supported
from legal_rag.domain.policies import QUOTATION_RE


def quotation_association_errors(text: str, excerpts: dict[str, list[str]]) -> list[str]:
    """Bind quotes to the last named document, without changing quoted bytes.

    A following sentence inherits the document scope. Document IDs occurring
    inside a quotation cannot change that scope. An unscoped quotation may be
    supported by any of the cited excerpts, as before.
    """
    scope: str | None = None
    cursor = 0
    errors: list[str] = []
    dashes = str.maketrans(dict.fromkeys("‐‑‒–—―−", "-"))
    for match in QUOTATION_RE.finditer(text):
        prefix = text[cursor : match.start()].translate(dashes)
        references = list(DOCUMENT_ID_RE.finditer(prefix))
        if references:
            scope = references[-1].group().upper()
        quote = next(value for value in match.groups() if value is not None)
        candidates = (
            excerpts.get(scope, [])
            if scope is not None
            else [excerpt for values in excerpts.values() for excerpt in values]
        )
        if not any(quote in excerpt for excerpt in candidates):
            errors.append("answer quotation is not present verbatim in its cited excerpts")
        cursor = match.end()
    return errors


def reference_association_errors(text: str, chunks: list[RetrievedChunk]) -> list[str]:
    """Validate local document/page/clause pairings, without inventing prose semantics.

    Explicit IDs scope their sentence (or passage up to the next ID). A following
    sentence inherits that scope. Unscoped references must hold for every cited
    document; ambiguous multi-document claims should be restated explicitly.
    """
    by_document: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        identity = str(chunk.metadata.get("source_doc") or chunk.document).upper()
        by_document.setdefault(identity, []).append(chunk)
    scope = list(by_document)
    errors: list[str] = []
    for sentence in re.split(r"[.!?;](?=\s|$)|\n+", text):
        references = list(DOCUMENT_ID_RE.finditer(sentence))
        sentence_documents = {match.group().upper() for match in references}
        explicit_amendment = re.search(r"\b(?:amend\w*|replac\w*)\b", sentence, re.IGNORECASE)
        boundaries = [0, *(match.start() for match in references[1:]), len(sentence)]
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
            passage = sentence[start:end]
            if references:
                scope = [references[index].group().upper()]
            clauses = parse_clause_request(passage)
            for document in scope:
                evidence = by_document.get(document, [])
                pages = {str(chunk.metadata.get("page_number")) for chunk in evidence}
                if not page_references_supported(passage, pages):
                    errors.append(f"page reference is not supported by cited document {document}")
                # A quoted replacement can define a base clause, but only when
                # the answer explicitly identifies the linked amendment. Its
                # physical page still belongs solely to the amendment itself.
                clause_evidence = evidence + [
                    chunk
                    for chunk in chunks
                    if explicit_amendment
                    and str(chunk.metadata.get("amends", "")).upper() == document
                    and chunk.document.upper() in sentence_documents
                ]
                if clauses and any(
                    not any(clause_excerpt(chunk, number) for chunk in clause_evidence)
                    for number in clauses.numbers
                ):
                    errors.append(f"clause reference is not supported by cited document {document}")
    return errors
