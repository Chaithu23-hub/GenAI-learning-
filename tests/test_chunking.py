"""Unit tests for the markdown-aware chunker."""

from legal_assistant.chunking import chunk_document, split_into_sections


def test_split_into_sections():
    text = "Intro text.\n\n## Section A\nBody A.\n\n## Section B\nBody B."
    sections = split_into_sections(text)
    assert sections[0] == ("Preamble", "Intro text.")
    assert ("Section A", "Body A.") in sections
    assert ("Section B", "Body B.") in sections


def test_short_section_becomes_one_chunk():
    chunks = chunk_document("## Fees\nPay within 30 days.")
    assert len(chunks) == 1
    assert chunks[0].heading == "Fees"
    assert chunks[0].text == "Pay within 30 days."


def test_chunk_indexes_are_sequential():
    chunks = chunk_document("# Doc\n## A\ntext a\n\n## B\ntext b")
    assert [c.index for c in chunks] == [0, 1]


def test_long_section_slides_with_overlap():
    body = " ".join(f"w{i}" for i in range(120))
    chunks = chunk_document(f"## Long\n{body}", chunk_size=50, overlap=10)
    assert len(chunks) >= 3
    assert all(len(c.text.split()) <= 50 for c in chunks)
    # Consecutive chunks share exactly `overlap` words at the boundary.
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert first[-10:] == second[:10]


def test_all_content_is_covered():
    body = " ".join(f"w{i}" for i in range(120))
    chunks = chunk_document(f"## Long\n{body}", chunk_size=50, overlap=10)
    covered = set()
    for c in chunks:
        covered.update(c.text.split())
    assert covered == {f"w{i}" for i in range(120)}
