import pytest

from legal_rag.infrastructure.chunking import chunk_document, split_into_sections


class TestSplitIntoSections:
    def test_preamble_when_no_heading(self):
        sections = split_into_sections("plain text with no heading")
        assert sections == [("Preamble", "plain text with no heading")]

    def test_captures_headings(self):
        text = "## Alpha\nbody\n## Beta\nsecond"
        assert split_into_sections(text) == [("Alpha", "body"), ("Beta", "second")]

    def test_empty_text_returns_empty(self):
        assert split_into_sections("") == []

    def test_heading_without_body_is_dropped(self):
        assert split_into_sections("## OnlyHeading\n") == []


class TestChunkDocument:
    def test_short_section_becomes_single_chunk(self):
        chunks = chunk_document("## Title\nshort body", chunk_size=10, overlap=2)
        assert len(chunks) == 1
        assert chunks[0].heading == "Title"

    def test_long_section_splits_with_overlap(self):
        long_body = "## Long\n" + " ".join(f"w{i}" for i in range(100))
        chunks = chunk_document(long_body, chunk_size=30, overlap=5)
        assert len(chunks) > 1
        # adjacent chunks share overlap tokens
        first_tokens = chunks[0].text.split()
        second_tokens = chunks[1].text.split()
        overlap_actual = set(first_tokens[-5:]) & set(second_tokens[:5])
        assert overlap_actual  # non-empty

    def test_overlap_must_be_smaller_than_chunk(self):
        with pytest.raises(ValueError):
            chunk_document("body", chunk_size=10, overlap=20)

    def test_chunk_indexes_are_monotonic(self):
        text = "## S\n" + " ".join(f"w{i}" for i in range(200))
        chunks = chunk_document(text, chunk_size=20, overlap=4)
        indexes = [c.index for c in chunks]
        assert indexes == sorted(indexes)
        assert indexes == list(range(len(chunks)))
