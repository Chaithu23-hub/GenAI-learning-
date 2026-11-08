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
    def test_plain_schedule_parts_keep_their_schedule_identity(self):
        text = (
            "Schedule A - Services\nPart 2 - Credits\nService credits apply.\n"
            "Schedule B - Fees\nPart 2 - Credits\nFee credits apply."
        )
        chunks = chunk_document(text)
        assert [(chunk.heading, chunk.text) for chunk in chunks] == [
            ("Schedule A - Services: Part 2 - Credits", "Service credits apply."),
            ("Schedule B - Fees: Part 2 - Credits", "Fee credits apply."),
        ]

    def test_single_numbered_clause_keeps_its_exact_identity(self):
        chunks = chunk_document("## Payment\n3.4(a) Late payment. Interest applies.")
        assert len(chunks) == 1
        assert chunks[0].heading.startswith("Section 3.4(a)")
        assert chunks[0].text == "3.4(a) Late payment. Interest applies."

    def test_deep_clause_number_is_not_shortened(self):
        chunks = chunk_document(
            "## Terms\n3.4.1.2 Liability. A cap applies.\n3.5 Fees. Fees apply."
        )
        assert [chunk.heading.split()[1] for chunk in chunks] == ["3.4.1.2", "3.5"]

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
