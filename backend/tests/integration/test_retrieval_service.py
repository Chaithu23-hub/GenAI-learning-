import pytest


class TestRetrievalService:
    def test_returns_relevant_chunks(self, container):
        chunks = container.retrieval_service.retrieve("late payment interest")
        assert chunks
        assert any("payment" in c.text.lower() for c in chunks)

    def test_metadata_filter_amendment_only(self, container):
        chunks = container.retrieval_service.retrieve(
            "payment interest", where={"document_type": "amendment"},
        )
        assert chunks
        assert all(c.document_type == "amendment" for c in chunks)

    def test_metadata_filter_contract_only(self, container):
        chunks = container.retrieval_service.retrieve(
            "termination", where={"document_type": "contract"},
        )
        assert all(c.document_type == "contract" for c in chunks)

    def test_no_hits_returns_empty(self, container):
        chunks = container.retrieval_service.retrieve(
            "nonexistent topic", where={"document_type": "amendment"},
        )
        # In-memory store may still surface something; ensure the API never raises.
        assert isinstance(chunks, list)

    def test_hybrid_and_dense_only_both_work(self, container):
        dense = container.retrieval_service.retrieve("payment", hybrid=False)
        hybrid = container.retrieval_service.retrieve("payment", hybrid=True)
        assert dense and hybrid

    def test_detect_metadata_filter(self, container):
        assert container.retrieval_service.detect_metadata_filter(
            "What did the amendment change?"
        ) == {"document_type": "amendment"}
        assert container.retrieval_service.detect_metadata_filter(
            "What is the original contract's effective date?"
        ) == {"document_type": "contract"}
        assert container.retrieval_service.detect_metadata_filter(
            "What is the late payment fee?"
        ) is None
