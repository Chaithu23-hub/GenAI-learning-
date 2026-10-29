from legal_rag.application.workflows.generation import ExtractiveGenerator, GenerationSettings
from legal_rag.domain.entities import RetrievedChunk


def chunk(document, text):
    return RetrievedChunk(
        chunk_id=document + "::001", document=document, document_type="contract",
        heading="Section 5: Termination", text=text, distance=0.1, score=5.0,
    )


def generate(chunks):
    generator = ExtractiveGenerator(
        retrieval=None,
        settings=GenerationSettings(0.0, 3.0, "No answer", 0.0),
    )
    return generator.generate("What is the notice requirement?", chunks=chunks)


def test_single_document_reply_starts_with_the_fact():
    text = "Either party may terminate this agreement with 30 days written notice."
    answer = generate([chunk("master_services_agreement.md", text)])
    assert answer["answer"] == text
    assert answer["sources"][0]["excerpt"] == text
    assert answer["sources"][0]["document"] == "master_services_agreement.md"


def test_different_agreements_remain_distinguishable_without_file_narration():
    answer = generate([
        chunk("master_services_agreement.md", "30 days written notice."),
        chunk("enterprise_saas_subscription_agreement.md", "60 days written notice."),
    ])
    assert "**Master Services Agreement**\n\n30 days" in answer["answer"]
    assert "**Enterprise Saas Subscription Agreement**\n\n60 days" in answer["answer"]
    assert ".md" not in answer["answer"]
    assert "Based on" not in answer["answer"]
    assert "According to" not in answer["answer"]
    assert len(answer["sources"]) == 2
