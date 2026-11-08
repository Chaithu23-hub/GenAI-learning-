"""Source-backed lookup for MCP legal corpus tools."""

from __future__ import annotations

import re
from typing import Any

from legal_rag.application.ports import Chunker, DocumentSource
from legal_rag.domain.clauses import clause_excerpt
from legal_rag.domain.entities import Chunk, Document, RetrievedChunk


class CorpusLookupService:
    """Search source documents and return exact chunk text and parsed metadata."""

    def __init__(
        self,
        document_source: DocumentSource,
        chunker: Chunker,
        *,
        chunk_size: int = 512,
        overlap: int = 50,
    ):
        self._document_source = document_source
        self._chunker = chunker
        self._chunk_size = chunk_size
        self._overlap = overlap

    def _documents(self) -> list[Document]:
        return list(self._document_source.iter_documents())

    @staticmethod
    def _source_id(document: Document) -> str:
        return str(document.metadata.get("source_doc") or "")

    def _chunks(self, document: Document) -> list[dict[str, Any]]:
        chunks = self._chunker.chunk(
            document.text, chunk_size=self._chunk_size, overlap=self._overlap
        )
        return [self._chunk_record(document, chunk) for chunk in chunks]

    def _chunk_record(self, document: Document, chunk: Chunk) -> dict[str, Any]:
        record: dict[str, Any] = {
            "document": self._source_id(document) or document.name,
            "document_name": document.name,
            "document_type": document.document_type,
            "document_version": document.metadata.get("document_version", "Unknown"),
            "heading": chunk.heading,
            "text": chunk.text,
        }
        matching_pages = [
            index
            for index, page in enumerate(document.pages, 1)
            if " ".join(chunk.text.split()) in " ".join(page.split())
        ]
        if len(matching_pages) == 1:
            record["page"] = matching_pages[0]
        return record

    @staticmethod
    def _related_documents(contract_id: str, documents: list[Document]) -> list[Document]:
        direct = [
            document
            for document in documents
            if CorpusLookupService._source_id(document) == contract_id
        ]
        if not direct:
            return []
        return direct + [
            document
            for document in documents
            if document not in direct and document.metadata.get("amends") == contract_id
        ]

    def search_clauses(self, query: str) -> list[dict[str, Any]]:
        terms = {term.casefold() for term in re.findall(r"\w+", query or "")}
        if not terms:
            return []
        matches = []
        for document in self._documents():
            for chunk in self._chunks(document):
                score = sum(chunk["text"].casefold().count(term) for term in terms)
                if score:
                    matches.append({**chunk, "matches": str(score)})
        return sorted(matches, key=lambda item: int(item["matches"]), reverse=True)[:5]

    def get_contract_clause(self, contract_id: str, clause_number: str) -> dict[str, Any]:
        documents = self._related_documents(contract_id, self._documents())
        if not documents:
            return {"error": "contract_not_found"}
        target = clause_number.strip()
        matches = []
        for document in documents:
            chunks = self._chunker.chunk(
                document.text, chunk_size=self._chunk_size, overlap=self._overlap
            )
            for index, chunk in enumerate(chunks):
                retrieved = RetrievedChunk(
                    chunk_id=f"{self._source_id(document)}:{index}",
                    document=self._source_id(document),
                    document_type=document.document_type,
                    heading=chunk.heading,
                    text=chunk.text,
                    distance=0.0,
                    metadata=document.metadata,
                )
                excerpt = clause_excerpt(retrieved, target)
                if excerpt:
                    record = self._chunk_record(document, chunk)
                    matches.append({**record, "text": excerpt})
        if not matches:
            return {"error": "clause_not_found"}
        if len(matches) > 1:
            return {"error": "ambiguous_clause", "candidates": matches}
        match = matches[0]
        return {"contract_id": contract_id, "clause": target, **match}

    def lookup_contract(self, contract_id: str) -> dict[str, Any]:
        all_documents = self._documents()
        documents = [doc for doc in all_documents if self._source_id(doc) == contract_id]
        if not documents:
            return {"error": "contract_not_found"}
        if len(documents) > 1:
            return {
                "error": "ambiguous_contract",
                "candidates": [self._source_id(doc) for doc in documents],
            }
        document = documents[0]
        metadata = document.metadata
        amendments = [
            self._amendment_metadata(doc)
            for doc in all_documents
            if doc.metadata.get("amends") == contract_id
        ]
        return {
            "contract_id": contract_id,
            "document": document.name,
            "document_type": document.document_type,
            "effective_date": metadata.get("effective_date", "Unknown"),
            "document_version": metadata.get("document_version", "Unknown"),
            "status": metadata.get("status", "Unknown"),
            "amendments": amendments,
        }

    def get_effective_date(self, contract_id: str) -> dict[str, Any]:
        result = self.lookup_contract(contract_id)
        if "error" in result:
            return result
        return {"contract_id": contract_id, "effective_date": result["effective_date"]}

    def get_amendment_chain(self, contract_id: str) -> dict[str, Any]:
        result = self.lookup_contract(contract_id)
        if "error" in result:
            return result
        return {"contract_id": contract_id, "amendments": result["amendments"]}

    def _amendment_metadata(self, document: Document) -> dict[str, Any]:
        metadata = document.metadata
        result = {"document": self._source_id(document)}
        for key in ("effective_date", "status", "document_version"):
            result[key] = metadata.get(key, "Unknown")
        return result
