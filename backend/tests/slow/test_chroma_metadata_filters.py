"""Real Chroma regression: combined port filters must remain a conjunction."""
import pytest

from legal_rag.domain.entities import IndexedChunk
from legal_rag.infrastructure.vector_store.chroma import ChromaVectorStore

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("operation", ["dense", "keyword", "get_all"])
def test_counterparty_and_document_type_filter_together(tmp_path, operation):
    store = ChromaVectorStore(tmp_path / "chroma")
    rows = [
        ("northwind-contract", "Northwind Logistics", "contract"),
        ("northwind-amendment", "Northwind Logistics", "amendment"),
        ("vertex-contract", "Vertex Retail", "contract"),
    ]
    chunks = [
        IndexedChunk(
            id=identifier, text="late payment interest", heading="Payment", chunk_index=0,
            document=identifier, document_type=document_type,
            metadata={"counterparty": counterparty},
        )
        for identifier, counterparty, document_type in rows
    ]
    store.upsert(chunks, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    where = {"counterparty": "Northwind Logistics", "document_type": "contract"}
    if operation == "dense":
        ids = store.dense_search([1.0, 0.0, 0.0], k=3, where=where)["ids"][0]
    elif operation == "keyword":
        ids = [row["id"] for row in store.keyword_search("late payment", k=3, where=where)]
    else:
        ids = store.get_all(where=where)["ids"]
    assert ids == ["northwind-contract"]
